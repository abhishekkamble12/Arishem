"""
Arishem RAG evaluation harness.

    python evals/run_eval.py                      # generate, judge, report (all resumable)
    EVAL_SKIP_JUDGE=1  python evals/run_eval.py   # deterministic metrics only, no judge tokens
    EVAL_REPORT_ONLY=1 python evals/run_eval.py   # rebuild SCORECARD.md, no model calls at all
    python evals/judge_control.py                 # prove the judge can fail

Indexes every document in pcaps/ into an in-memory Qdrant with the production
chunking settings, runs the labelled golden set (evals/golden_set.json) through
the real query pipeline, and scores it two ways:

  deterministic   key-fact correctness, retrieval hit@k / MRR / recall, abstention
                  precision and recall, prompt-injection resistance (evals/metrics.py)
  LLM-judged      RAGAS faithfulness, by a judge from a different model family

Generation and judging are both resumable. Every answer and every score is written
to evals/.eval_cache.json the moment it exists, so running into the Groq free
tier's daily token cap pauses the run instead of losing it: rerun the same command
later and it continues where it stopped.
"""

import asyncio
import datetime
import hashlib
import json
import os
import statistics
import sys
import time

import nest_asyncio

nest_asyncio.apply()  # ragas runs its own event loop inside ours

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, HERE)

import dotenv  # noqa: E402

# The backend reads backend/backend/.env (python-decouple searches upward from
# settings.py and caches the first file it finds), so load the same one here.
dotenv.load_dotenv(os.path.join(ROOT, "backend", "backend", ".env"))
# Services.storage reads settings.BASE_DIR at import time, so Django must be
# configured before anything under Services is imported.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ.setdefault("SECRET_KEY", "eval-harness-only")

import django  # noqa: E402

django.setup()

import Services.agent as agent_mod  # noqa: E402
import Services.Ai_service.embedding as embedding_mod  # noqa: E402
from langchain_community.document_loaders import PyMuPDFLoader  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_qdrant import QdrantVectorStore  # noqa: E402
from metrics import (  # noqa: E402
    abstention_report,
    contains_any,
    is_abstention,
    key_fact_score,
    mean_or_none,
    retrieval_ranks,
)
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qdrant_models  # noqa: E402
from qdrant_client.http.models import Distance, VectorParams  # noqa: E402
from Services.Extractor import CHUNK_OVERLAP, CHUNK_SIZE, normalise_newlines, split_pages  # noqa: E402


def _flag(name: str) -> bool:
    return os.getenv(name, "").lower() in ("1", "true", "yes")


# ── Configuration (all of it is recorded in the scorecard) ───────────────────
CORPUS_DIR = os.path.join(ROOT, "pcaps")
GOLDEN_FILE = os.path.join(HERE, "golden_set.json")
CACHE_FILE = os.path.join(HERE, ".eval_cache.json")
RESULTS_FILE = os.path.join(HERE, "eval_results.json")
SCORECARD_FILE = os.path.join(HERE, "SCORECARD.md")

# The threshold and top_k default to the application's own values, so the eval
# measures what actually ships and the two cannot drift apart.
CONFIDENCE_THRESHOLD = float(os.getenv("EVAL_CONFIDENCE_THRESHOLD", agent_mod.CONFIDENCE_THRESHOLD))
TOP_K = agent_mod.TOP_K
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GENERATOR_MODEL = agent_mod.GROQ_MODEL
# A different model family from the generator, so it is not grading its own
# output. evals/judge_control.py checks that this judge scores fabrication low.
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "qwen/qwen3.8-27b")
JUDGE_METRICS = [m.strip() for m in os.getenv("EVAL_METRICS", "faithfulness").split(",") if m.strip()]
JUDGE_BATCH = int(os.getenv("EVAL_JUDGE_BATCH", "6"))
SLEEP_BETWEEN_QUESTIONS = float(os.getenv("EVAL_SLEEP", "2"))

agent_mod.CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD
# The application falls back to a second model when the first fails. In an eval
# that would silently mix two generators into one score, so the fallback is off
# unless asked for, and the model behind every answer is recorded regardless.
if not _flag("EVAL_ALLOW_FALLBACK"):
    agent_mod.GROQ_FALLBACK_MODEL = agent_mod.GROQ_MODEL
    agent_mod._llm = None


# ── Corpus ───────────────────────────────────────────────────────────────────
qdrant = QdrantClient(location=":memory:")


def vector_store() -> QdrantVectorStore:
    return QdrantVectorStore(client=qdrant, collection_name="documents",
                             embedding=embedding_mod.get_embeddings(), vector_name="content-dense")


class RecordingStore:
    """
    Passes searches through to the real store and remembers every chunk returned.

    Agentic mode retrieves once per sub-question, so the chunks the model actually
    saw are not the top-k for the original question. Faithfulness has to be judged
    against what the model saw, or a correct multi-hop answer is marked unsupported.
    """

    def __init__(self, store):
        self._store = store
        self.seen: list[Document] = []

    def similarity_search_with_score(self, *args, **kwargs):
        results = self._store.similarity_search_with_score(*args, **kwargs)
        self.seen.extend(doc for doc, _ in results)
        return results

    def __getattr__(self, name):
        return getattr(self._store, name)

    def contexts(self) -> list[str]:
        unique, seen_text = [], set()
        for doc in self.seen:
            if doc.page_content not in seen_text:
                seen_text.add(doc.page_content)
                unique.append(doc.page_content)
        return unique


def load_corpus() -> tuple[list[Document], str]:
    """Every document in pcaps/, chunked like production. Returns (chunks, fingerprint)."""
    docs, digest = [], hashlib.sha256()
    for name in sorted(os.listdir(CORPUS_DIR)):
        path = os.path.join(CORPUS_DIR, name)
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in (".pdf", ".txt", ".md"):
            continue
        if suffix == ".pdf":
            with open(path, "rb") as fh:
                digest.update(name.encode() + fh.read())
            pages = PyMuPDFLoader(path).load()
        else:
            # Fingerprint the normalised text, not the file's bytes: git checks these
            # out with CRLF on Windows and LF elsewhere, and hashing bytes gave the
            # same corpus a different fingerprint on each platform.
            with open(path, encoding="utf-8", newline="") as fh:
                text = normalise_newlines(fh.read())
            digest.update(name.encode() + text.encode("utf-8"))
            pages = [Document(page_content=text)]
        for page in pages:
            page.metadata = {"source": name, "workspace_id": 1}
        docs.extend(pages)

    # Production's own splitter rather than a copy of its settings, so the eval
    # chunks exactly as ingestion does.
    digest.update(f"{CHUNK_SIZE}/{CHUNK_OVERLAP}/{EMBEDDING_MODEL}".encode())
    return split_pages(docs), digest.hexdigest()[:16]


def index_corpus(chunks: list[Document]) -> None:
    if qdrant.collection_exists("documents"):
        qdrant.delete_collection("documents")
    qdrant.create_collection(
        collection_name="documents",
        vectors_config={"content-dense": VectorParams(size=384, distance=Distance.COSINE)},
    )
    vector_store().add_documents(chunks)


WORKSPACE_FILTER = qdrant_models.Filter(must=[qdrant_models.FieldCondition(
    key="metadata.workspace_id", match=qdrant_models.MatchValue(value=1))])


# ── Cache ────────────────────────────────────────────────────────────────────
def load_cache(fingerprint: dict) -> dict:
    """Reuse cached answers only if nothing that shapes an answer has changed."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as fh:
            cache = json.load(fh)
        if cache.get("fingerprint") == fingerprint:
            return cache
        changed = [k for k in fingerprint if cache.get("fingerprint", {}).get(k) != fingerprint[k]]
        print(f"Cache ignored: {', '.join(changed)} changed since it was written.")
    return {"fingerprint": fingerprint, "answers": {}, "scores": {}}


def save_cache(cache: dict) -> None:
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=1, default=str)
    os.replace(tmp, CACHE_FILE)  # atomic: an interrupted write never corrupts the cache


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "rate_limit" in text or "ratelimit" in text or "429" in text or "tokens per day" in text


def _cached_answer(cache: dict, item: dict) -> dict | None:
    """
    The cached answer for a golden item, but only if it was given to that question.

    Answers are keyed by id. Two categories once produced the same ids, and the
    report paired "Who won the 2022 World Cup?" with the answer to a question about
    Slack retention. Checking the question text means a collision, or an edited
    question, can never be reported against the wrong answer.
    """
    answer = cache["answers"].get(item["id"])
    return answer if answer and answer.get("question") == item["question"] else None


def validate_golden(golden: list[dict]) -> None:
    """Fail before spending a token if the golden set is malformed."""
    counts = {}
    for item in golden:
        counts[item["id"]] = counts.get(item["id"], 0) + 1
    duplicates = sorted(k for k, v in counts.items() if v > 1)
    if duplicates:
        raise SystemExit(f"Golden set has duplicate ids, which would mix up answers: {duplicates}")


# ── Generation ───────────────────────────────────────────────────────────────
def generate(golden: list[dict], cache: dict) -> bool:
    """Answer every question not already cached. Returns False if stopped early."""
    answers = cache["answers"]
    todo = [g for g in golden if answers.get(g["id"], {}).get("question") != g["question"]]
    print(f"Generation: {len(golden) - len(todo)} cached, {len(todo)} to run.")
    for n, item in enumerate(todo, 1):
        recorder = RecordingStore(vector_store())
        agent_mod.get_vector_store = lambda r=recorder: r
        started = time.perf_counter()
        try:
            res = agent_mod.query(question=item["question"], workspace_id=1, top_k=TOP_K)
        except Exception as exc:
            if _is_rate_limit(exc):
                print(f"\nStopped at {n}/{len(todo)}: generator hit a rate limit ({exc}). "
                      "Rerun later to continue — nothing is lost.")
                save_cache(cache)
                return False
            print(f"  error on {item['id']}: {exc}")
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)

        # Ranked sources for the question as asked: the retrieval metrics' basis.
        ranked = vector_store().similarity_search(item["question"], k=TOP_K, filter=WORKSPACE_FILTER)
        # A new answer invalidates every score given to the old one.
        for judge_scores in cache["scores"].values():
            judge_scores.pop(item["id"], None)
        answers[item["id"]] = {
            "question": item["question"],
            "answer": res.get("answer", ""),
            "confidence": res.get("confidence"),
            "refused": bool(res.get("refused")),
            "latency_ms": latency_ms,
            "usage": res.get("usage") or {},
            "retrieved_sources": [d.metadata.get("source") for d in ranked],
            "contexts": recorder.contexts(),
        }
        save_cache(cache)
        print(f"  [{n}/{len(todo)}] {item['id']:8} {latency_ms / 1000:5.1f}s  {str(res.get('answer'))[:70]}")
        time.sleep(SLEEP_BETWEEN_QUESTIONS)
    return True


# ── LLM-judged metrics ───────────────────────────────────────────────────────
def judge(golden: list[dict], cache: dict) -> bool:
    """Score every substantive answer not yet scored by this judge. Resumable."""
    from datasets import Dataset
    from langchain_groq import ChatGroq
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    from ragas.run_config import RunConfig

    available = {"faithfulness": faithfulness, "answer_relevancy": answer_relevancy,
                 "context_precision": context_precision, "context_recall": context_recall}
    unknown = [m for m in JUDGE_METRICS if m not in available]
    if unknown:
        raise SystemExit(f"Unknown EVAL_METRICS {unknown}; choose from {sorted(available)}")

    scores = cache["scores"].setdefault(JUDGE_MODEL, {})
    # An abstention makes no factual claim: judging it would only add a vacuous
    # 1.0. Unanswerable questions the system answered anyway ARE judged — that is
    # exactly where an invented answer would show up.
    pending = [g for g in golden
               if _cached_answer(cache, g)
               and not is_abstention(cache["answers"][g["id"]]["answer"], cache["answers"][g["id"]]["refused"])
               and any(m not in scores.get(g["id"], {}) for m in JUDGE_METRICS)]
    print(f"\nJudging with {JUDGE_MODEL}: {len(pending)} answers pending.")
    if not pending:
        return True

    llm = LangchainLLMWrapper(ChatGroq(model=JUDGE_MODEL, temperature=0, timeout=90, max_retries=3))
    embeddings = LangchainEmbeddingsWrapper(embedding_mod.get_embeddings())
    metrics = [available[m] for m in JUDGE_METRICS]

    for start in range(0, len(pending), JUDGE_BATCH):
        batch = pending[start:start + JUDGE_BATCH]
        data = {"question": [], "answer": [], "contexts": [], "ground_truth": [], "reference": []}
        for g in batch:
            a = cache["answers"][g["id"]]
            data["question"].append(g["question"])
            data["answer"].append(a["answer"])
            data["contexts"].append(a["contexts"] or [""])
            data["ground_truth"].append(g["ground_truth"])
            data["reference"].append(g["ground_truth"])
        result = evaluate(Dataset.from_dict(data), metrics=metrics, llm=llm, embeddings=embeddings,
                          raise_exceptions=False, run_config=RunConfig(max_workers=1, timeout=180))
        frame = result.to_pandas()
        got = 0
        for g, row in zip(batch, frame.to_dict("records"), strict=True):
            for m in JUDGE_METRICS:
                value = row.get(m)
                if value is not None and value == value:  # NaN means the judge call failed
                    scores.setdefault(g["id"], {})[m] = float(value)
                    got += 1
        save_cache(cache)
        print(f"  judged {min(start + JUDGE_BATCH, len(pending))}/{len(pending)} ({got} scores this batch)")
        if got == 0:
            print("Stopped: a whole batch failed, which on the free tier means the judge's daily "
                  "token cap. Rerun later to continue — scores so far are kept.")
            return False
    return True


# ── Assemble results ─────────────────────────────────────────────────────────
def build_rows(golden: list[dict], cache: dict) -> list[dict]:
    scores = cache["scores"].get(JUDGE_MODEL, {})
    rows = []
    for g in golden:
        a = _cached_answer(cache, g)
        if not a:
            continue
        hit, rr, recall = retrieval_ranks(a["retrieved_sources"], g.get("relevant_sources"))
        rows.append({
            "id": g["id"], "category": g["category"], "question": g["question"],
            "ground_truth": g["ground_truth"], "answerable": g["answerable"],
            "answer": a["answer"], "confidence": a["confidence"], "refused": a["refused"],
            "abstained": is_abstention(a["answer"], a["refused"]),
            "correctness": key_fact_score(a["answer"], g.get("key_facts"), g.get("forbidden")),
            "hijacked": contains_any(a["answer"], g.get("forbidden")),
            "retrieval_hit": hit, "reciprocal_rank": rr, "retrieval_recall": recall,
            "retrieved_sources": a["retrieved_sources"],
            "relevant_sources": g.get("relevant_sources"),
            "latency_ms": a["latency_ms"], "usage": a.get("usage", {}),
            **{m: scores.get(g["id"], {}).get(m) for m in JUDGE_METRICS},
        })
    return rows


def threshold_sweep(rows: list[dict]) -> list[dict]:
    """
    What the retrieval-confidence threshold alone would do at each value.

    Confidence does not depend on the threshold, so one run gives the whole curve.
    Note this measures only the first line of defence: a question that clears the
    threshold can still be declined by the model itself, which the abstention
    metrics count.
    """
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    sweep = []
    for t in [0.02, 0.04, 0.06, 0.065, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.35]:
        wr = sum(1 for r in answerable if (r["confidence"] or 0) < t)
        wa = sum(1 for r in unanswerable if (r["confidence"] or 0) >= t)
        sweep.append({"threshold": t, "answerable_refused": wr, "answerable_total": len(answerable),
                      "unanswerable_passed": wa, "unanswerable_total": len(unanswerable),
                      "mistakes": wr + wa})
    return sweep


# ── Report ───────────────────────────────────────────────────────────────────
def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _num(value, digits=3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


CATEGORY_ORDER = ["single_fact", "distractor", "multi_hop", "paraphrase", "injection",
                  "unanswerable_in_domain", "unanswerable_out_of_domain"]


def render_report(rows: list[dict], config: dict) -> None:
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    judged_metrics = config["judge_metrics"]
    faith_rows = [r for r in rows if r.get("faithfulness") is not None]
    abst = abstention_report(rows)
    injection = [r for r in rows if r["category"] == "injection"]
    lat = [r["latency_ms"] for r in rows if not r["abstained"]]
    tokens = [(r["usage"].get("prompt_tokens") or 0) + (r["usage"].get("completion_tokens") or 0)
              for r in rows if r["usage"]]
    models = sorted({m for r in rows for m in (r["usage"].get("models") or [])})

    L = [
        "# RAG Evaluation Scorecard",
        "",
        "_Generated by `evals/run_eval.py` — do not edit by hand. Per-question results: "
        "`eval_results.json`._",
        "",
        f"{len(rows)} questions ({len(answerable)} answerable, {len(unanswerable)} unanswerable) "
        f"over {config['corpus_documents']} documents in {config['corpus_chunks']} chunks, so "
        f"retrieval chooses {config['top_k']} of {config['corpus_chunks']}.",
        "",
        "## Headline",
        "",
        "| Metric | Value | Over |",
        "| --- | --- | --- |",
        f"| Answer correctness (key facts present) | **{_pct(mean_or_none([r['correctness'] for r in answerable]))}** | {len(answerable)} answerable |",
        f"| Fully correct answers | {sum(1 for r in answerable if r['correctness'] == 1.0)}/{len(answerable)} | answerable |",
    ]
    if "faithfulness" in judged_metrics:
        L.append(f"| Faithfulness (RAGAS, judged) | **{_num(mean_or_none([r['faithfulness'] for r in faith_rows]))}** "
                 f"| {len(faith_rows)} substantive answers |")
    for m in judged_metrics:
        if m != "faithfulness":
            vals = [r.get(m) for r in rows if r.get(m) is not None]
            L.append(f"| {m.replace('_', ' ').title()} (RAGAS) | {_num(mean_or_none(vals))} | {len(vals)} answers |")
    L += [
        f"| Retrieval hit@{config['top_k']} | {_pct(mean_or_none([r['retrieval_hit'] for r in answerable]))} | answerable |",
        f"| Retrieval MRR | {_num(mean_or_none([r['reciprocal_rank'] for r in answerable]))} | answerable |",
        f"| Abstention precision | {_pct(abst['precision'])} | questions it declined |",
        f"| Abstention recall | {_pct(abst['recall'])} | {len(unanswerable)} unanswerable |",
        f"| Answered an unanswerable question | {_pct(abst['hallucinated'])} | unanswerable |",
        f"| Wrongly declined an answerable question | {_pct(abst['false_abstain'])} | answerable |",
        f"| Prompt injection resisted | {sum(1 for r in injection if not r['hijacked'])}/{len(injection)} | injection |",
        # Not production latency: the eval sends questions back to back with the model
        # fallback disabled, so most of this is waiting out Groq's per-minute token
        # limit. Production latency is measured separately (see the README).
        f"| Latency in this run (rate-limit bound, not production) | median {statistics.median(lat) / 1000:.1f} s, "
        f"p95 {sorted(lat)[max(0, int(len(lat) * 0.95) - 1)] / 1000:.1f} s | |" if lat else "| Latency | n/a | |",
        f"| Tokens per question | mean {statistics.mean(tokens):,.0f} | |" if tokens else "| Tokens | n/a | |",
    ]

    # Per category
    L += ["", "## By category", "",
          "| Category | n | Correctness | Faithfulness | Hit@k | Declined |",
          "| --- | --- | --- | --- | --- | --- |"]
    for cat in CATEGORY_ORDER:
        cr = [r for r in rows if r["category"] == cat]
        if not cr:
            continue
        L.append(
            f"| {cat.replace('_', ' ')} | {len(cr)} "
            f"| {_pct(mean_or_none([r['correctness'] for r in cr]))} "
            f"| {_num(mean_or_none([r.get('faithfulness') for r in cr]))} "
            f"| {_pct(mean_or_none([r['retrieval_hit'] for r in cr]))} "
            f"| {sum(1 for r in cr if r['abstained'])}/{len(cr)} |")

    # Abstention mechanics
    L += ["", "## How it declined", "",
          f"Of {abst['abstained_by_threshold'] + abst['abstained_by_model']} declined questions, "
          f"{abst['abstained_by_threshold']} were stopped by the retrieval-confidence threshold "
          f"(no synthesis, no self-critique) and {abst['abstained_by_model']} cleared the threshold "
          f"but the model itself said the documents do not cover it. The threshold is only the "
          f"first line of defence; the in-domain unanswerable questions are mostly caught by the "
          f"second."]

    # Failures, concretely
    wrong = [r for r in answerable if r["correctness"] is not None and r["correctness"] < 1.0]
    halluc = [r for r in unanswerable if not r["abstained"]]
    unfaithful = [r for r in faith_rows if r["faithfulness"] < 1.0]
    if wrong or halluc or unfaithful:
        L += ["", "## Failures", "", "Every question that lost points, so the numbers above can be checked.", ""]
    if wrong:
        L += [f"**Incomplete or wrong answers ({len(wrong)})**", ""]
        for r in sorted(wrong, key=lambda r: r["correctness"]):
            why = "declined" if r["abstained"] else ("hijacked by injection" if r["hijacked"] else
                                                     f"{r['correctness']:.0%} of key facts")
            L.append(f"- `{r['id']}` ({why}) — {r['question']}  \n  → {_clip(r['answer'])}")
        L.append("")
    if halluc:
        L += [f"**Answered although the corpus cannot ({len(halluc)})**", ""]
        for r in halluc:
            L.append(f"- `{r['id']}` (confidence {_num(r['confidence'])}) — {r['question']}  \n  → {_clip(r['answer'])}")
        L.append("")
    if unfaithful:
        L += [f"**Judged not fully faithful ({len(unfaithful)})**", ""]
        for r in sorted(unfaithful, key=lambda r: r["faithfulness"]):
            L.append(f"- `{r['id']}` (faithfulness {r['faithfulness']:.2f}) — {r['question']}  \n  → {_clip(r['answer'])}")
        L.append("")

    # Threshold sweep
    sweep = config["threshold_sweep"]
    best = min(sweep, key=lambda s: (s["mistakes"], -s["threshold"]))
    L += ["", "## Retrieval-confidence threshold sweep", "",
          "What the threshold alone would do at each value. It is computed from one run, because "
          "confidence does not depend on the threshold. 'Passed' unanswerable questions are not "
          "necessarily answered — the model can still decline them.",
          "", "| Threshold | Answerable refused | Unanswerable passed | Mistakes |", "| --- | --- | --- | --- |"]
    for s in sweep:
        mark = "  <- fewest" if s is best else ("  <- current" if abs(s["threshold"] - config["confidence_threshold"]) < 1e-9 else "")
        L.append(f"| `{s['threshold']:.3f}` | {s['answerable_refused']}/{s['answerable_total']} "
                 f"| {s['unanswerable_passed']}/{s['unanswerable_total']} | {s['mistakes']}{mark} |")

    # Config + caveats
    L += ["", "## Configuration", ""]
    for key in ["date", "generator", "judge", "judge_metrics", "agentic_mode", "top_k", "chunk_size",
                "chunk_overlap", "embedding_model", "confidence_threshold", "corpus_fingerprint"]:
        L.append(f"- **{key}**: {config.get(key)}")
    if models:
        L.append(f"- **models that actually produced answers**: {', '.join(models)}")

    caveats = [
        "The corpus and questions are synthetic fixtures written for this eval. They test "
        "behaviour — distractors, multi-hop, abstention, injection — not performance on any "
        "real company's documents.",
        "Answer correctness checks that required facts appear, by whole-token match. It "
        "cannot tell a fact stated correctly from one mentioned and then contradicted.",
        "Judged faithfulness is only as good as the judge; `evals/judge_control.py` checks it "
        "scores fabricated answers near 0 before its scores are trusted.",
        f"{len(rows)} questions is still small; differences of a few points between runs are noise.",
        "Latency here is dominated by Groq's per-minute rate limit, because the questions run "
        "back to back with the fallback model disabled. It is not production latency.",
    ]
    if config.get("incomplete"):
        caveats.insert(0, f"**This run is incomplete:** {config['incomplete']}")
    L += ["", "## Caveats", ""] + [f"- {c}" for c in caveats]

    with open(SCORECARD_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"\nWrote {os.path.relpath(SCORECARD_FILE, ROOT)} and {os.path.relpath(RESULTS_FILE, ROOT)}")


def _clip(text, n=160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def write_results(rows: list[dict], config: dict) -> None:
    with open(RESULTS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"config": config, "questions": rows}, fh, indent=2, default=str, ensure_ascii=False)
        fh.write("\n")


# ── Entry point ──────────────────────────────────────────────────────────────
def report_only() -> None:
    with open(RESULTS_FILE, encoding="utf-8") as fh:
        saved = json.load(fh)
    render_report(saved["questions"], saved["config"])


async def main() -> None:
    if _flag("EVAL_REPORT_ONLY"):
        report_only()
        return

    with open(GOLDEN_FILE, encoding="utf-8") as fh:
        golden = json.load(fh)
    validate_golden(golden)
    chunks, corpus_fp = load_corpus()
    print(f"Corpus: {len({c.metadata['source'] for c in chunks})} documents, {len(chunks)} chunks "
          f"(fingerprint {corpus_fp}). Golden set: {len(golden)} questions.")
    index_corpus(chunks)

    fingerprint = {"corpus": corpus_fp, "generator": GENERATOR_MODEL, "threshold": CONFIDENCE_THRESHOLD,
                   "top_k": TOP_K, "agentic": agent_mod.AGENTIC_MODE}
    cache = load_cache(fingerprint)

    incomplete = None
    generated = generate(golden, cache)
    if not generated:
        incomplete = "generation stopped at the generator's daily token cap; rerun to finish."
    # The judge is a different model with its own daily budget, so the generator
    # running out is no reason to stop judging the answers that already exist.
    if not _flag("EVAL_SKIP_JUDGE") and not judge(golden, cache):
        incomplete = (incomplete + " " if incomplete else "") +             "Judging stopped at the judge's daily token cap; rerun to finish."

    rows = build_rows(golden, cache)
    unscored = sum(1 for r in rows if not r["abstained"] and r.get("faithfulness") is None)
    if not incomplete and unscored and "faithfulness" in JUDGE_METRICS and not _flag("EVAL_SKIP_JUDGE"):
        incomplete = f"{unscored} substantive answers have no faithfulness score yet."
    config = {
        "date": datetime.date.today().isoformat(),
        "generator": GENERATOR_MODEL,
        "judge": None if _flag("EVAL_SKIP_JUDGE") else JUDGE_MODEL,
        "judge_metrics": [] if _flag("EVAL_SKIP_JUDGE") else JUDGE_METRICS,
        "agentic_mode": agent_mod.AGENTIC_MODE,
        "top_k": TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "embedding_model": f"{EMBEDDING_MODEL} (384-dim, local)",
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "corpus_fingerprint": corpus_fp,
        "corpus_documents": len({c.metadata["source"] for c in chunks}),
        "corpus_chunks": len(chunks),
        "threshold_sweep": threshold_sweep(rows),
        "incomplete": incomplete,
    }
    write_results(rows, config)
    render_report(rows, config)
    if incomplete:
        print(f"\nINCOMPLETE: {incomplete}")


if __name__ == "__main__":
    asyncio.run(main())
