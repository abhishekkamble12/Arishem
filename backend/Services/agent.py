"""
RAG Query Agent — the retrieval half of the pipeline.

Two modes:
  RAG_AGENTIC_MODE=false  →  Original single-pass RAG (fast, cheap)
  RAG_AGENTIC_MODE=true   →  Agentic RAG with Query Decomposition + Self-Critique

DEMO-SAFE: If agentic mode fails at ANY step, the pipeline automatically
falls back to the original simple RAG path. The user always gets an answer.

Flow (simple):
  question → embed → Qdrant search → LLM → answer

Flow (agentic):
  question → [LLM: decompose] → N×Qdrant searches → merge chunks
           → [LLM: synthesise] → [LLM: self-critique] → answer + reasoning_steps
"""

import json
import logging
from typing import Any

from decouple import config
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document
from langchain_core.tools import tool

from .Ai_service.embedding import get_vector_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_REGION           = config("AWS_REGION", default="us-east-1")
TOP_K                = int(config("RAG_TOP_K", default=5))
CONFIDENCE_THRESHOLD = float(config("RAG_CONFIDENCE_THRESHOLD", default=0.35))
GROQ_MODEL           = config("GROQ_MODEL_ID", default="llama-3.3-70b-versatile")
AGENTIC_MODE         = config("RAG_AGENTIC_MODE", default="true").lower() == "true"
SELF_CRITIQUE        = config("SELF_CRITIQUE_ENABLED", default="true").lower() == "true"

# ---------------------------------------------------------------------------
# Singleton LLM
# ---------------------------------------------------------------------------
_llm: ChatGroq | None = None


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@tool
def fetch_s3_metadata(workspace_id: int, file_key: str) -> str:
    """Fetch structured metadata from S3 for a given document."""
    # Dummy MCP integration example allowing the LLM to access live system state
    return f"Metadata for {file_key}: Uploaded by admin, size 2MB, retention 90 days."

def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0.2,
            max_tokens=2048,
        )
        _llm = _llm.bind_tools([fetch_s3_metadata])
        logger.info("ChatGroq initialised with MCP tools (model: %s)", GROQ_MODEL)
    return _llm


# ---------------------------------------------------------------------------
# Prompt builder (used by both simple and agentic paths)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly
based on the provided context documents.

Rules:
- Only use information from the context below.
- If the answer is not in the context, say "I don't have enough information to answer that."
- Always cite the source document (filename) when you use information from it.
- Be concise and direct.

You MUST respond in valid JSON format matching this schema:
{
  "answer": "The concise answer...",
  "citations": [
    {"source": "filename.pdf", "snippet": "exact quote from text"}
  ],
  "unverified": "What I could not verify or what is missing...",
  "confidence_score": 0.95
}
"""


def _build_prompt(question: str, chunks: list[Document]) -> list:
    context_parts = []
    for i, doc in enumerate(chunks, 1):
        source = doc.metadata.get("source", "unknown")
        context_parts.append(f"[{i}] Source: {source}\n{doc.page_content}")

    context_text = "\n\n---\n\n".join(context_parts)

    return [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Context:\n{context_text}\n\nQuestion: {question}"),
    ]


def _parse_llm_json(raw_content: str, avg_score: float) -> dict:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    raw = raw_content.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON from LLM: %s", raw_content[:200])
        return {
            "answer": raw_content,
            "citations": [],
            "unverified": "",
            "confidence_score": avg_score,
        }


# ---------------------------------------------------------------------------
# Simple (original) single-pass RAG — primary path and nuclear fallback
# ---------------------------------------------------------------------------
def _simple_query(
    question: str,
    workspace_id: int,
    top_k: int,
    user_email: str | None,
    user_role: str | None,
    qdrant_filter,
    vector_store,
) -> dict[str, Any]:
    """Original single-pass RAG. Used as primary path (non-agentic) and as fallback."""
    chunks_with_scores = vector_store.similarity_search_with_score(
        question, k=top_k, filter=qdrant_filter
    )

    if not chunks_with_scores:
        logger.warning("No relevant chunks found for question: '%s' (workspace=%d)", question[:80], workspace_id)
        return {
            "answer": "I don't have any relevant documents to answer that question.",
            "sources": [], "chunks": 0, "confidence": 0.0,
            "agentic_mode": False,
        }

    chunks = [doc for doc, score in chunks_with_scores]
    avg_score = sum(score for _, score in chunks_with_scores) / len(chunks_with_scores)

    logger.info("Retrieved %d chunks (avg score: %.4f)", len(chunks), avg_score)

    if avg_score < CONFIDENCE_THRESHOLD:
        logger.warning("Confidence %.4f below threshold %.4f. Rejecting.", avg_score, CONFIDENCE_THRESHOLD)
        return {
            "answer": "I don't have enough relevant context in the uploaded documents to answer your question confidently.",
            "sources": [], "chunks": len(chunks), "confidence": avg_score,
            "agentic_mode": False,
        }

    messages = _build_prompt(question, chunks)
    response = _get_llm().invoke(messages)
    parsed = _parse_llm_json(response.content, avg_score)

    sources = list({doc.metadata.get("source", "unknown") for doc in chunks})
    return {
        "answer": parsed.get("answer", ""),
        "sources": sources,
        "citations": parsed.get("citations", []),
        "unverified": parsed.get("unverified", ""),
        "chunks": len(chunks),
        "confidence": avg_score,
        "llm_confidence": parsed.get("confidence_score", avg_score),
        "agentic_mode": False,
    }


# ---------------------------------------------------------------------------
# Agentic multi-step RAG
# ---------------------------------------------------------------------------
def _agentic_query(
    question: str,
    workspace_id: int,
    top_k: int,
    user_email: str | None,
    user_role: str | None,
    qdrant_filter,
    vector_store,
) -> dict[str, Any]:
    """
    Agentic pipeline: Decompose → Multi-retrieve → Synthesise → Self-Critique.
    Falls back to _simple_query if ANYTHING goes wrong at any step.
    """
    from .agentic import (
        decompose_query,
        retrieve_for_subqueries,
        self_critique,
        retry_synthesis,
    )

    llm = _get_llm()
    reasoning_steps = []

    # ── Step 1: Decompose ────────────────────────────────────────────────────
    try:
        sub_queries = decompose_query(question, llm)
        reasoning_steps.append({
            "phase": "decomposition",
            "sub_queries": sub_queries,
            "is_complex": len(sub_queries) > 1,
        })
        logger.info("Agentic: decomposed into %d sub-queries", len(sub_queries))
    except Exception as e:
        logger.warning("Decomposition crashed (%s). Falling back to simple RAG.", e)
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store)

    # ── Step 2: Multi-retrieval ──────────────────────────────────────────────
    try:
        merged_chunks, retrieval_trace = retrieve_for_subqueries(
            sub_queries, vector_store, qdrant_filter, top_k
        )
        reasoning_steps.append({
            "phase": "retrieval",
            "retrieval_trace": retrieval_trace,
            "total_unique_chunks": len(merged_chunks),
        })
    except Exception as e:
        logger.warning("Multi-retrieval crashed (%s). Falling back to simple RAG.", e)
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store)

    if not merged_chunks:
        return {
            "answer": "I don't have any relevant documents to answer that question.",
            "sources": [], "chunks": 0, "confidence": 0.0,
            "reasoning_steps": reasoning_steps, "agentic_mode": True,
        }

    avg_score = 0.5  # neutral placeholder for merged pool

    # ── Step 3: Synthesise ───────────────────────────────────────────────────
    try:
        messages = _build_prompt(question, merged_chunks)
        response = llm.invoke(messages)
        parsed_answer = _parse_llm_json(response.content, avg_score)
        reasoning_steps.append({"phase": "synthesis", "llm_call": 2})
    except Exception as e:
        logger.warning("Synthesis crashed (%s). Falling back to simple RAG.", e)
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store)

    answer_text = parsed_answer.get("answer", "")

    # ── Step 4: Self-Critique ────────────────────────────────────────────────
    critique_verdict = "SKIPPED"
    if SELF_CRITIQUE and answer_text:
        try:
            critique_result = self_critique(answer_text, merged_chunks, llm)
            critique_verdict = critique_result.get("verdict", "SKIPPED")
            unsupported = critique_result.get("unsupported_claims", [])

            reasoning_steps.append({
                "phase": "self_critique",
                "llm_call": 3,
                "verdict": critique_verdict,
                "unsupported_claims": unsupported,
            })

            # If FAIL → retry once with conservative prompt
            if critique_verdict == "FAIL" and unsupported:
                logger.info("Self-critique FAIL. Retrying synthesis with conservative prompt.")
                retry = retry_synthesis(question, merged_chunks, unsupported, llm)
                if retry and retry.get("answer"):
                    parsed_answer = retry
                    answer_text = parsed_answer.get("answer", answer_text)
                    critique_verdict = "PARTIAL"
                    reasoning_steps.append({"phase": "retry_synthesis", "llm_call": 4})

        except Exception as e:
            logger.warning("Self-critique crashed (%s). Returning answer without critique.", e)
            critique_verdict = "SKIPPED"

    # ── Build final response ─────────────────────────────────────────────────
    sources = list({doc.metadata.get("source", "unknown") for doc in merged_chunks})
    return {
        "answer": answer_text,
        "sources": sources,
        "citations": parsed_answer.get("citations", []),
        "unverified": parsed_answer.get("unverified", ""),
        "chunks": len(merged_chunks),
        "confidence": avg_score,
        "llm_confidence": parsed_answer.get("confidence_score", avg_score),
        "reasoning_steps": reasoning_steps,
        "critique_verdict": critique_verdict,
        "agentic_mode": True,
    }


# ---------------------------------------------------------------------------
# Public API — single entry point (unchanged signature, backward compatible)
# ---------------------------------------------------------------------------
def query(
    question: str,
    workspace_id: int,
    top_k: int = TOP_K,
    user_email: str = None,
    user_role: str = None,
) -> dict[str, Any]:
    """
    Answer a question using RAG over the Qdrant vector store.

    If RAG_AGENTIC_MODE=true (default), runs the full agentic pipeline.
    Any failure in the agentic path silently falls back to simple RAG.
    The caller always receives a valid response dict.
    """
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")

    logger.info(
        "RAG query [agentic=%s]: '%s' (workspace=%d, top_k=%d, user=%s, role=%s)",
        AGENTIC_MODE, question[:80], workspace_id, top_k, user_email, user_role
    )

    # Build shared Qdrant filter
    from qdrant_client.http import models as qdrant_models

    must_conditions = [
        qdrant_models.FieldCondition(
            key="metadata.workspace_id",
            match=qdrant_models.MatchValue(value=workspace_id)
        )
    ]
    if user_role == "viewer" and user_email:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="metadata.uploaded_by",
                match=qdrant_models.MatchValue(value=user_email)
            )
        )

    qdrant_filter = qdrant_models.Filter(must=must_conditions)
    vector_store  = get_vector_store()

    # Route to correct pipeline
    if AGENTIC_MODE:
        try:
            return _agentic_query(
                question, workspace_id, top_k,
                user_email, user_role,
                qdrant_filter, vector_store,
            )
        except Exception as e:
            # Nuclear fallback — entire agentic function crashed
            logger.exception("Agentic pipeline completely crashed (%s). Falling back to simple RAG.", e)
            return _simple_query(
                question, workspace_id, top_k,
                user_email, user_role,
                qdrant_filter, vector_store,
            )
    else:
        return _simple_query(
            question, workspace_id, top_k,
            user_email, user_role,
            qdrant_filter, vector_store,
        )
