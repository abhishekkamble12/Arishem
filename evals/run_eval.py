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

dotenv.load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", ".env")))

import Services.agent as agent_mod
import Services.Ai_service.embedding as embedding_mod
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

# ── Eval configuration (recorded in the scorecard so results are reproducible)
CONFIDENCE_THRESHOLD = 0.35
TOP_K = agent_mod.TOP_K
# Mirrors Services/Extractor.py — kept local because importing it requires Django
CHUNK_SIZE, CHUNK_OVERLAP = 800, 150

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
        "judge_llm": "llama-3.3-70b-versatile (Groq)",
        "agentic_mode": agent_mod.AGENTIC_MODE,
        "top_k": TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }

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

    lines += ["", "## Configuration", ""]
    lines += [f"- **{key}**: {value}" for key, value in config.items()]
    lines += [
        "", "## Caveats", "",
        "- Small golden set; treat differences under ~0.05 as noise.",
        "- The judge is the same model family as the generator, which can inflate scores.",
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

    # Wait, ragas requires specific wrappers depending on the version
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

    eval_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

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
        results = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            raise_exceptions=False,
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
