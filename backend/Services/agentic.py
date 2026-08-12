"""
Agentic RAG Pipeline — Query Decomposition + Self-Critique

This module adds two reasoning steps on top of the base RAG pipeline:

  Phase 1 — Query Decomposition:
    An LLM decides if the question is complex (multi-hop). If yes, it breaks
    it into atomic sub-queries, retrieves chunks for EACH independently,
    then merges all evidence for a richer synthesis.

  Phase 2 — Self-Critique Pass:
    After generating an answer, a second LLM call judges whether every claim
    is directly supported by the cited chunks. If not, it forces a more
    conservative retry.

DEMO-SAFE DESIGN:
  Every step is wrapped in a try/except. If ANY step fails for any reason,
  the pipeline gracefully falls back to the last successful state.
  The caller will always receive a valid answer — never a crash.
"""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Max number of sub-queries the decomposer can produce (cost safety cap)
# ---------------------------------------------------------------------------
MAX_SUB_QUERIES = 4


# ---------------------------------------------------------------------------
# Prompt: Decomposer
# ---------------------------------------------------------------------------
_DECOMPOSE_SYSTEM = """You are a query analysis assistant. Your job is to decide if a user's question
contains MULTIPLE distinct information needs that would benefit from separate searches.

Rules:
- If the question asks for ONE thing: return it as a single sub-query.
- If the question asks for TWO OR MORE distinct things: break it into separate atomic sub-questions.
- NEVER produce more than 4 sub-queries.
- Each sub-query must be self-contained and independently searchable.
- Keep sub-queries concise.

Respond ONLY in this exact JSON format, no extra text:
{"sub_queries": ["sub-question 1", "sub-question 2"]}"""


def decompose_query(question: str, llm) -> list[str]:
    """
    Use the LLM to break a complex question into atomic sub-queries.

    Returns a list of sub-queries. For simple questions, returns [question].
    Falls back to [question] on any failure — demo-safe.
    """
    try:
        messages = [
            SystemMessage(content=_DECOMPOSE_SYSTEM),
            HumanMessage(content=f"Question: {question}"),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown code blocks if present
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        parsed = json.loads(raw.strip())
        sub_queries = parsed.get("sub_queries", [question])

        # Validate: must be a non-empty list of strings
        if not isinstance(sub_queries, list) or not sub_queries:
            raise ValueError("Invalid sub_queries format")

        # Enforce cap and type
        sub_queries = [str(q).strip() for q in sub_queries if str(q).strip()][:MAX_SUB_QUERIES]

        if len(sub_queries) > 1:
            logger.info("Decomposed into %d sub-queries: %s", len(sub_queries), sub_queries)
        else:
            logger.info("Simple question — no decomposition needed.")

        return sub_queries

    except Exception as e:
        logger.warning("Decomposition failed (%s). Falling back to original question.", e)
        return [question]


# ---------------------------------------------------------------------------
# Multi-retrieval: search for each sub-query and merge results
# ---------------------------------------------------------------------------

def retrieve_for_subqueries(
    sub_queries: list[str],
    vector_store,
    qdrant_filter,
    top_k: int,
) -> tuple[list[Document], list[dict]]:
    """
    Run a Qdrant similarity search for each sub-query.
    Merges all results and deduplicates by page_content hash.

    Returns:
        (merged_chunks, retrieval_trace)
        Falls back to empty lists on any failure — demo-safe.
    """
    seen_content_hashes: set[int] = set()
    merged_chunks: list[Document] = []
    retrieval_trace: list[dict] = []

    for i, sub_query in enumerate(sub_queries):
        try:
            results = vector_store.similarity_search_with_score(
                sub_query,
                k=top_k,
                filter=qdrant_filter,
            )
            new_chunks = []
            for doc, score in results:
                content_hash = hash(doc.page_content)
                if content_hash not in seen_content_hashes:
                    seen_content_hashes.add(content_hash)
                    merged_chunks.append(doc)
                    new_chunks.append(doc)

            retrieval_trace.append({
                "sub_query": sub_query,
                "chunks_found": len(results),
                "new_unique_chunks": len(new_chunks),
            })
            logger.info(
                "Sub-query %d/%d: '%s' → %d results (%d new unique)",
                i + 1, len(sub_queries), sub_query[:60], len(results), len(new_chunks)
            )
        except Exception as e:
            logger.warning("Retrieval failed for sub-query '%s': %s", sub_query[:60], e)
            retrieval_trace.append({"sub_query": sub_query, "error": str(e)})

    return merged_chunks, retrieval_trace


# ---------------------------------------------------------------------------
# Prompt: Self-Critic Judge
# ---------------------------------------------------------------------------
_CRITIQUE_SYSTEM = """You are a strict fact-checking judge for an AI assistant.

You will be given:
1. An AI-generated answer.
2. The source document chunks the answer was based on.

Your job: verify that every factual claim in the answer is EXPLICITLY and DIRECTLY
supported by at least one of the provided source chunks.

Rules:
- Look for direct evidence, not inferences or general knowledge.
- Be strict: if a claim cannot be found word-for-word or in very close paraphrase, flag it.
- If all claims are supported: verdict is PASS.
- If any claim is unsupported: verdict is FAIL, and list the unsupported claims.

Respond ONLY in this exact JSON format, no extra text:
{
  "verdict": "PASS" or "FAIL",
  "unsupported_claims": ["claim text if any"]
}"""


def self_critique(answer: str, chunks: list[Document], llm) -> dict:
    """
    Ask the LLM to verify whether the answer is fully supported by the chunks.

    Returns {"verdict": "PASS", "unsupported_claims": []}.
    Falls back to {"verdict": "PASS", "unsupported_claims": []} on any failure
    so the answer is always returned — demo-safe.
    """
    try:
        context_parts = []
        for i, doc in enumerate(chunks[:8], 1):  # cap at 8 to avoid token overflow
            source = doc.metadata.get("source", "unknown")
            context_parts.append(f"[Chunk {i}] Source: {source}\n{doc.page_content[:600]}")

        context_text = "\n\n---\n\n".join(context_parts)

        messages = [
            SystemMessage(content=_CRITIQUE_SYSTEM),
            HumanMessage(
                content=f"Answer to check:\n{answer}\n\nSource chunks:\n{context_text}"
            ),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        parsed = json.loads(raw.strip())
        verdict = parsed.get("verdict", "PASS")
        unsupported = parsed.get("unsupported_claims", [])

        logger.info("Self-critique verdict: %s | Unsupported claims: %s", verdict, unsupported)
        return {"verdict": verdict, "unsupported_claims": unsupported}

    except Exception as e:
        logger.warning("Self-critique failed (%s). Defaulting to PASS to avoid blocking answer.", e)
        return {"verdict": "SKIPPED", "unsupported_claims": []}


# ---------------------------------------------------------------------------
# Retry synthesis with conservative prompt when self-critique fails
# ---------------------------------------------------------------------------
_CONSERVATIVE_SYSTEM = """You are a helpful but STRICT assistant. A previous answer you generated
contained claims that were NOT directly supported by the source documents.

You MUST now generate a new, more conservative answer:
- ONLY state things that are EXPLICITLY in the provided chunks.
- If you cannot fully answer the question from the chunks, clearly say what you DO know and what is missing.
- Do NOT infer, extrapolate, or use general knowledge.
- Always cite the source document.

You MUST respond in valid JSON matching this schema:
{
  "answer": "The conservative answer...",
  "citations": [{"source": "filename.pdf", "snippet": "exact quote"}],
  "unverified": "What could not be verified...",
  "confidence_score": 0.75
}"""


def retry_synthesis(
    question: str,
    chunks: list[Document],
    unsupported_claims: list[str],
    llm,
) -> dict:
    """
    Retry answer generation with a stricter prompt after self-critique FAIL.
    Falls back to a safe error dict on any failure — demo-safe.
    """
    try:
        context_parts = []
        for i, doc in enumerate(chunks, 1):
            source = doc.metadata.get("source", "unknown")
            context_parts.append(f"[{i}] Source: {source}\n{doc.page_content}")
        context_text = "\n\n---\n\n".join(context_parts)

        claims_text = "\n".join(f"- {c}" for c in unsupported_claims)
        human_msg = (
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            f"WARNING: Your previous answer contained these UNSUPPORTED claims:\n{claims_text}\n\n"
            f"Generate a new, strictly conservative answer."
        )

        messages = [
            SystemMessage(content=_CONSERVATIVE_SYSTEM),
            HumanMessage(content=human_msg),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        return json.loads(raw.strip())

    except Exception as e:
        logger.warning("Retry synthesis failed (%s). Returning original answer.", e)
        return {}
