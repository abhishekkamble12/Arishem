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
    """Write SCORECARD.md (summary) and eval_results.json (raw, per question)."""
    import datetime
    import statistics

    frame = results.to_pandas()
    metric_names = [c for c in frame.columns if c in
                    ("faithfulness", "answer_relevancy", "context_precision", "context_recall")]
    for row, item in zip(frame.to_dict("records"), per_question, strict=False):
        item.update({m: row.get(m) for m in metric_names})

    def mean(metric):
        values = [v for v in frame[metric].tolist() if v == v]  # drop NaN (judge failures)
        return (sum(values) / len(values) if values else float("nan")), len(values)

    latencies = [q["latency_ms"] for q in per_question]
    config = {
        "date": datetime.date.today().isoformat(),
        "golden_questions": n_golden,
        "answered_without_error": len(per_question),
        "embedding_model": "all-MiniLM-L6-v2 (384-dim, local)",
        "llm": agent_mod.GROQ_MODEL,
        "judge_llm": f"{JUDGE_MODEL} (Groq)",
        "agentic_mode": agent_mod.AGENTIC_MODE,
        "top_k": TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }

    sweep = threshold_sweep(per_question)
    config["threshold_sweep"] = sweep

    with open(os.path.join(EVAL_DIR, "eval_results.json"), "w", encoding="utf-8") as f:
        json.dump({"config": config, "questions": per_question}, f, indent=2, default=str)

    refused = sum(q["refused"] for q in per_question)
    lines = [
        "# RAG Evaluation Scorecard",
        "",
        "_Generated by `evals/run_eval.py` — do not edit by hand. "
        "Per-question results: `eval_results.json`._",
        "",
        "| Metric | Mean | Scored questions |",
        "| --- | --- | --- |",
    ]
    for m in metric_names:
        value, n = mean(m)
        lines.append(f"| {m.replace('_', ' ').title()} | `{value:.4f}` | {n}/{len(per_question)} |")

    lines += ["", "## Behaviour", "", f"- Refusals (low confidence): {refused}/{len(per_question)}"]
    if latencies:
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
        lines.append(f"- Query latency: median {statistics.median(latencies):.0f} ms, p95 {p95} ms "
                     "(includes LLM calls; local in-memory Qdrant)")

    best = min(sweep, key=lambda r: (r["mistakes"], -r["threshold"]))
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
    lines += [
        "", "## Caveats", "",
        "- Small golden set; treat differences under ~0.05 as noise.",
        "- The judge is the same model family as the generator, which can inflate scores.",
        "- The sweep's best threshold is fitted on this set. With few negative examples "
        "it is a starting point, not a calibration; add unanswerable questions before "
        "trusting a precise value.",
    ]

    with open(os.path.join(EVAL_DIR, "SCORECARD.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote SCORECARD.md and eval_results.json to {EVAL_DIR}")


async def main():
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

    print("Running queries through the agent pipeline...")
    per_question = []
    for item in golden_set:
        question = item["question"]
        gt = item["ground_truth"]

        try:
            # Query the agent
            started = time.perf_counter()
            res = agent_mod.query(question=question, workspace_id=1, top_k=TOP_K)
            latency_ms = int((time.perf_counter() - started) * 1000)
            answer = res.get("answer", "")

            # Retrieve exact chunks for context
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
            data_samples["reference"].append(gt)  # add both for compatibility
            per_question.append({
                "question": question,
                "ground_truth": gt,
                "answerable": is_answerable(item),
                "answer": answer,
                "confidence": res.get("confidence"),
                "refused": not res.get("sources"),
                "latency_ms": latency_ms,
            })

        except Exception as e:
            print(f"Error querying '{question}': {e}")
            continue

        # Sleep to avoid hitting Groq rate limits
        time.sleep(2)

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
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
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
