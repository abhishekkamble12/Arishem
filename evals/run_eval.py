import asyncio
import json
import os
import sys
import time

import nest_asyncio

# Apply nest_asyncio to allow nested event loops in case ragas or langchain needs it
nest_asyncio.apply()

# Add parent directory to path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import dotenv

# The backend reads backend/backend/.env (python-decouple searches upward from
# settings.py), so load the same file here rather than a path that never existed.
dotenv.load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "backend", ".env")))

# Services.storage reads settings.BASE_DIR at import time, so Django has to be
# configured before anything under Services is imported. Without this the harness
# cannot even start.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ.setdefault("SECRET_KEY", "eval-harness-only")

import django

django.setup()

import Services.agent as agent_mod
import Services.Ai_service.embedding as embedding_mod
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

# ── Eval configuration (recorded in the scorecard so results are reproducible)
# Default to whatever the application uses, so the two cannot drift apart.
CONFIDENCE_THRESHOLD = float(os.getenv("EVAL_CONFIDENCE_THRESHOLD", agent_mod.CONFIDENCE_THRESHOLD))
TOP_K = agent_mod.TOP_K
# Mirrors Services/Extractor.py — kept local because importing it requires Django
CHUNK_SIZE, CHUNK_OVERLAP = 800, 150
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "openai/gpt-oss-120b")
# Generation is expensive and scoring is rate-limited, so the two are
# decoupled: answers are cached, and EVAL_REUSE_ANSWERS=1 scores the cache
# without spending generation tokens again.
ANSWERS_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers_cache.json")
REUSE_ANSWERS = os.getenv("EVAL_REUSE_ANSWERS", "").lower() in ("1", "true", "yes")
# Four metrics over 30 questions is ~120 judge calls, which exhausts a free
# Groq daily token budget. On a corpus small enough that every query retrieves
# everything, the context metrics cannot discriminate anyway, so EVAL_METRICS
# lets the budget go to the two that can.
EVAL_METRICS = [m.strip() for m in os.getenv(
    "EVAL_METRICS", "faithfulness,answer_relevancy,context_precision,context_recall"
).split(",") if m.strip()]

agent_mod.CONFIDENCE_THRESHOLD = CONFIDENCE_THRESHOLD
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize local in-memory Qdrant
local_client = QdrantClient(location=":memory:")

def mock_get_vector_store():
    return QdrantVectorStore(
        client=local_client,
        collection_name="documents",
        embedding=embedding_mod.get_embeddings(),
        vector_name="content-dense",
    )

# Patch both modules
embedding_mod.get_vector_store = mock_get_vector_store
agent_mod.get_vector_store = mock_get_vector_store

def load_documents():
    docs = []
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pcaps"))

    # 1. PDF
    pdf_path = os.path.join(base_dir, "SOP-104_Data_Retention_Policy.pdf")
    if os.path.exists(pdf_path):
        loader = PyMuPDFLoader(pdf_path)
        pdf_docs = loader.load()
        for d in pdf_docs:
            d.metadata["workspace_id"] = 1
            d.metadata["source"] = os.path.basename(pdf_path)
        docs.extend(pdf_docs)

    # 2. TXT
    txt_path = os.path.join(base_dir, "HR-201_Leave_Policy.txt")
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8") as f:
            docs.append(Document(page_content=f.read(), metadata={"source": "HR-201_Leave_Policy.txt", "workspace_id": 1}))

    # 3. MD
    md_path = os.path.join(base_dir, "Engineering_Onboarding.md")
    if os.path.exists(md_path):
        with open(md_path, encoding="utf-8") as f:
            docs.append(Document(page_content=f.read(), metadata={"source": "Engineering_Onboarding.md", "workspace_id": 1}))

    # Chunk exactly like the production ingestion pipeline does
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(docs)

def setup_qdrant(docs):
    if local_client.collection_exists(collection_name="documents"):
        local_client.delete_collection(collection_name="documents")

    local_client.create_collection(
        collection_name="documents",
        vectors_config={
            "content-dense": VectorParams(
                size=384, # all-MiniLM-L6-v2 dimension
                distance=Distance.COSINE,
            )
        },
    )

    vector_store = mock_get_vector_store()
    vector_store.add_documents(docs)
    print(f"Added {len(docs)} chunks to Qdrant.")

REFUSAL_GROUND_TRUTH = "I don't have enough information to answer that."


def is_answerable(item) -> bool:
    """
    Whether the corpus should be able to answer this question. Explicit
    "answerable" wins; otherwise a ground truth that is itself a refusal marks
    the question as a negative example.
    """
    if "answerable" in item:
        return bool(item["answerable"])
    return item["ground_truth"].strip().lower() != REFUSAL_GROUND_TRUTH.lower()


def threshold_sweep(per_question):
    """
    What the refusal threshold would have done, at every value, from one run.

    Retrieval confidence does not depend on the threshold, so the whole curve
    comes out of a single pass. This is the calibration the default was missing.
    """
    answerable = [q for q in per_question if q["answerable"]]
    unanswerable = [q for q in per_question if not q["answerable"]]
    rows = []
    for threshold in [round(0.02 * i, 2) for i in range(1, 11)] + [0.25, 0.30, 0.35, 0.40]:
        # A question is refused when its confidence falls below the threshold.
        wrongly_refused = sum(1 for q in answerable if (q["confidence"] or 0) < threshold)
        wrongly_answered = sum(1 for q in unanswerable if (q["confidence"] or 0) >= threshold)
        rows.append({
            "threshold": threshold,
            "answerable_refused": wrongly_refused,
            "answerable_total": len(answerable),
            "unanswerable_answered": wrongly_answered,
            "unanswerable_total": len(unanswerable),
            "mistakes": wrongly_refused + wrongly_answered,
        })
    return rows


def write_outputs(results, per_question, n_golden):
    """Attach the judge's scores to each question, then write both reports."""
    import datetime

    frame = results.to_pandas()
    metric_names = [c for c in frame.columns if c in
                    ("faithfulness", "answer_relevancy", "context_precision", "context_recall")]
    for row, item in zip(frame.to_dict("records"), per_question, strict=False):
        item.update({m: row.get(m) for m in metric_names})

    config = {
        "date": datetime.date.today().isoformat(),
        "golden_questions": n_golden,
        "answered_without_error": len(per_question),
        "embedding_model": "all-MiniLM-L6-v2 (384-dim, local)",
        "llm": agent_mod.GROQ_MODEL,
        "judge_llm": JUDGE_MODEL,
        "metrics": metric_names,
        "agentic_mode": agent_mod.AGENTIC_MODE,
        "top_k": TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "threshold_sweep": threshold_sweep(per_question),
    }
    with open(os.path.join(EVAL_DIR, "eval_results.json"), "w", encoding="utf-8") as f:
        json.dump({"config": config, "questions": per_question}, f, indent=2, default=str)
    render_report(per_question, config)


def _mean(values):
    values = [v for v in values if v is not None and v == v]  # drop NaN: judge failures
    return (sum(values) / len(values) if values else float("nan")), len(values)


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy) if sx and sy else float("nan")


def render_report(per_question, config):
    """
    Build SCORECARD.md from per-question results alone, so the report can be
    regenerated (EVAL_REPORT_ONLY=1) without spending a single judge token.
    """
    import statistics

    metric_names = config["metrics"]
    answered = [q for q in per_question if not q["refused"]]
    refused = len(per_question) - len(answered)

    lines = [
        "# RAG Evaluation Scorecard",
        "",
        "_Generated by `evals/run_eval.py` — do not edit by hand. "
        "Per-question results: `eval_results.json`._",
        "",
        "Means are reported twice. A refusal makes no factual claim, so it scores 1.0 on",
        "faithfulness vacuously and 0 on relevancy by construction; the answered-only",
        "column is the one that describes answer quality.",
        "",
        "| Metric | Mean, all | Mean, answered only | Scored |",
        "| --- | --- | --- | --- |",
    ]
    for m in metric_names:
        all_mean, n = _mean([q.get(m) for q in per_question])
        ans_mean, _ = _mean([q.get(m) for q in answered])
        lines.append(f"| {m.replace('_', ' ').title()} | `{all_mean:.4f}` | `{ans_mean:.4f}` "
                     f"| {n}/{len(per_question)} |")

    lines += ["", "## Behaviour", "", f"- Refusals: {refused}/{len(per_question)}"]
    latencies = [q["latency_ms"] for q in answered]
    if latencies:
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
        lines.append(f"- Latency of answered queries: median {statistics.median(latencies) / 1000:.1f} s, "
                     f"p95 {p95 / 1000:.1f} s (includes every LLM call; Qdrant is in-memory)")

    # Interpretation that the bare numbers invite people to get wrong.
    notes = []
    faith = [q.get("faithfulness") for q in answered if q.get("faithfulness") == q.get("faithfulness")]
    if faith and min(faith) >= 0.99:
        notes.append(
            "**Faithfulness is saturated.** Every answered question scored 1.0. That is "
            "credible only because the same judge was shown to score fabricated answers "
            "0.0 (`evals/judge_control.py`), but a ceiling score means this set is too easy "
            "to discriminate: these are single-fact lookups over a corpus small enough "
            "that every query retrieves all of it. It shows the system does not "
            "hallucinate on easy questions, and nothing about hard ones."
        )
    if "answer_relevancy" in metric_names and answered:
        words = [len(str(q["answer"]).split()) for q in answered]
        rel = [q.get("answer_relevancy") or 0.0 for q in answered]
        r = _pearson(words, rel)
        short = [q for q in answered if len(str(q["answer"]).split()) <= 4]
        longer = [q for q in answered if len(str(q["answer"]).split()) > 4]
        if short and longer and r == r and r > 0.4:
            s_mean, _ = _mean([q.get("answer_relevancy") for q in short])
            l_mean, _ = _mean([q.get("answer_relevancy") for q in longer])
            notes.append(
                f"**Answer relevancy is mostly measuring length here.** Its correlation with "
                f"answer word count is {r:+.2f}: answers of four words or fewer average "
                f"{s_mean:.3f}, longer ones {l_mean:.3f}. RAGAS scores relevancy by "
                f"regenerating the question from the answer, which a correct one-word "
                f"answer cannot do. Read it as a verbosity signal, not a quality one."
            )
    if notes:
        lines += ["", "## Reading these numbers", ""] + [f"- {n}" for n in notes]

    sweep = config["threshold_sweep"]
    best = min(sweep, key=lambda row: (row["mistakes"], -row["threshold"]))
    lines += [
        "", "## Refusal threshold sweep", "",
        "Retrieval confidence does not depend on the threshold, so this whole table "
        "comes from the single run above. 'Wrongly refused' is an answerable question "
        "the threshold would reject; 'wrongly answered' is an unanswerable one it "
        "would let through.",
        "",
        "| Threshold | Wrongly refused | Wrongly answered | Total mistakes |",
        "| --- | --- | --- | --- |",
    ]
    for row in sweep:
        marker = "  <- fewest mistakes" if row is best else ""
        lines.append(
            f"| `{row['threshold']:.2f}` | {row['answerable_refused']}/{row['answerable_total']} "
            f"| {row['unanswerable_answered']}/{row['unanswerable_total']} | {row['mistakes']}{marker} |"
        )

    lines += ["", "## Configuration", ""]
    lines += [f"- **{key}**: {value}" for key, value in config.items() if key != "threshold_sweep"]

    caveats = ["Small golden set; treat differences under ~0.05 as noise."]
    gen_family = str(config["llm"]).split("/")[0]
    judge_family = str(config["judge_llm"]).split("/")[0]
    if gen_family == judge_family:
        caveats.append(f"The judge ({config['judge_llm']}) is the same model family as the "
                       f"generator ({config['llm']}), which can inflate scores.")
    else:
        caveats.append(f"The judge ({config['judge_llm']}) is a different model family from the "
                       f"generator ({config['llm']}), so it is not grading its own output.")
    caveats.append("The sweep's best threshold is fitted on this set. With few negative examples "
                   "it is a starting point, not a calibration; add unanswerable questions before "
                   "trusting a precise value.")
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in caveats]

    with open(os.path.join(EVAL_DIR, "SCORECARD.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote SCORECARD.md and eval_results.json to {EVAL_DIR}")


def report_only():
    """Rebuild SCORECARD.md from the last eval_results.json; no model calls."""
    with open(os.path.join(EVAL_DIR, "eval_results.json"), encoding="utf-8") as f:
        saved = json.load(f)
    config, per_question = saved["config"], saved["questions"]
    config.setdefault("metrics", [m for m in ("faithfulness", "answer_relevancy",
                                              "context_precision", "context_recall")
                                  if m in per_question[0]])
    config["judge_llm"] = str(config.get("judge_llm", "")).replace(" (Groq)", "")
    render_report(per_question, config)


async def main():
    if os.getenv("EVAL_REPORT_ONLY", "").lower() in ("1", "true", "yes"):
        report_only()
        return
    print("==================================================")
    print("        ARISHEM RAG PIPELINE EVALUATION           ")
    print("==================================================")
    print("Loading documents and setting up local Qdrant...")
    docs = load_documents()
    setup_qdrant(docs)

    golden_file = os.path.join(os.path.dirname(__file__), "golden_set.json")
    with open(golden_file) as f:
        golden_set = json.load(f)

    print(f"Loaded {len(golden_set)} questions from golden set.")

    data_samples = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
        "reference": []  # for compatibility with ragas 0.2.x
    }

    from langchain_groq import ChatGroq

    print("Importing ragas...")
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    _metrics = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    unknown = [m for m in EVAL_METRICS if m not in _metrics]
    if unknown:
        raise SystemExit(f"Unknown EVAL_METRICS {unknown}; choose from {sorted(_metrics)}")
    chosen_metrics = [_metrics[m] for m in EVAL_METRICS]
    print(f"Metrics: {', '.join(EVAL_METRICS)}")
    try:
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        wrapper_available = True
    except ImportError:
        wrapper_available = False

    # The judge should be at least as strong as the generator, and must be a model
    # Groq still serves: the previous id here was retired, which is one of the two
    # reasons this harness could not run.
    eval_llm = ChatGroq(model=JUDGE_MODEL, temperature=0, timeout=60, max_retries=5)

    if wrapper_available:
        ragas_llm = LangchainLLMWrapper(eval_llm)
        ragas_embeddings = LangchainEmbeddingsWrapper(embedding_mod.get_embeddings())
    else:
        ragas_llm = eval_llm
        ragas_embeddings = embedding_mod.get_embeddings()

    if REUSE_ANSWERS:
        if not os.path.exists(ANSWERS_CACHE):
            raise SystemExit(f"EVAL_REUSE_ANSWERS is set but {ANSWERS_CACHE} is missing.")
        with open(ANSWERS_CACHE, encoding="utf-8") as fh:
            cached = json.load(fh)
        per_question = cached["questions"]
        data_samples = cached["data_samples"]
        print(f"Reusing {len(per_question)} cached answers; no generation calls.")
    else:
        print("Running queries through the agent pipeline...")
        per_question = []
        for item in golden_set:
            question = item["question"]
            gt = item["ground_truth"]

            try:
                started = time.perf_counter()
                res = agent_mod.query(question=question, workspace_id=1, top_k=TOP_K)
                latency_ms = int((time.perf_counter() - started) * 1000)
                answer = res.get("answer", "")

                # The exact chunks the judge will score the answer against.
                vs = mock_get_vector_store()
                from qdrant_client.http import models as qdrant_models
                filter_ = qdrant_models.Filter(must=[
                    qdrant_models.FieldCondition(key="metadata.workspace_id", match=qdrant_models.MatchValue(value=1))
                ])
                docs_res = vs.similarity_search(question, k=TOP_K, filter=filter_)
                contexts = [d.page_content for d in docs_res]

                data_samples["question"].append(question)
                data_samples["answer"].append(answer)
                data_samples["contexts"].append(contexts)
                data_samples["ground_truth"].append(gt)
                data_samples["reference"].append(gt)  # ragas 0.1.x vs 0.2.x
                per_question.append({
                    "question": question,
                    "ground_truth": gt,
                    "answerable": is_answerable(item),
                    "answer": answer,
                    "confidence": res.get("confidence"),
                    "refused": bool(res.get("refused", not res.get("sources"))),
                    "latency_ms": latency_ms,
                    "usage": res.get("usage"),
                })

            except Exception as e:
                print(f"Error querying '{question}': {e}")
                continue

            time.sleep(2)  # stay under Groq's per-minute limits

        with open(ANSWERS_CACHE, "w", encoding="utf-8") as fh:
            json.dump({"data_samples": data_samples, "questions": per_question},
                      fh, indent=2, default=str)
        print(f"Cached answers to {ANSWERS_CACHE} — rescore with EVAL_REUSE_ANSWERS=1.")

    from datasets import Dataset
    dataset = Dataset.from_dict(data_samples)

    print("Running ragas evaluation... (this will take a few minutes)")
    try:
        # ragas fans out one request per metric per row by default, which a free
        # Groq tier answers with a wall of 429s. Four metrics over 30 questions is
        # only ~120 judge calls, so serialising them costs minutes and actually
        # finishes, where the default concurrency thrashes on retries.
        from ragas.run_config import RunConfig

        results = evaluate(
            dataset,
            metrics=chosen_metrics,
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            raise_exceptions=False,
            run_config=RunConfig(max_workers=int(os.getenv("EVAL_MAX_WORKERS", "2")), timeout=180),
        )

        print("Evaluation complete!")
        print(results)

        write_outputs(results, per_question, n_golden=len(golden_set))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Ragas evaluation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
