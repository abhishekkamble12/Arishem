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
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from .Ai_service.embedding import get_vector_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TOP_K                = int(config("RAG_TOP_K", default=5))
CONFIDENCE_THRESHOLD = float(config("RAG_CONFIDENCE_THRESHOLD", default=0.35))
# Groq retires models on a few months' notice; GET /openai/v1/models lists what is
# live. Both defaults below were checked against that list.
GROQ_MODEL           = config("GROQ_MODEL_ID", default="openai/gpt-oss-20b")
GROQ_FALLBACK_MODEL  = config("GROQ_FALLBACK_MODEL_ID", default="openai/gpt-oss-120b")
LLM_TIMEOUT_SECONDS  = float(config("LLM_TIMEOUT_SECONDS", default=30))
LLM_MAX_RETRIES      = int(config("LLM_MAX_RETRIES", default=2))
AGENTIC_MODE         = config("RAG_AGENTIC_MODE", default="true").lower() == "true"
SELF_CRITIQUE        = config("SELF_CRITIQUE_ENABLED", default="true").lower() == "true"

# ---------------------------------------------------------------------------
# Singleton LLM
# ---------------------------------------------------------------------------
_llm: Runnable | None = None


def _build_llm(model: str) -> ChatGroq:
    return ChatGroq(
        model=model,
        temperature=0.2,
        max_tokens=2048,
        # Without a timeout a hung Groq connection holds a gunicorn worker open
        # until the client gives up; max_retries covers 429s and 5xx.
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


class UsageCollector(BaseCallbackHandler):
    """
    Counts LLM calls and tokens for one query.

    Agentic mode makes three or four calls per question, so a per-request total is
    the only number that reflects what a query actually costs. One collector per
    query, never shared, because a module-level counter would mix tenants together.
    """

    def __init__(self) -> None:
        self.llm_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def on_llm_end(self, response, **kwargs) -> None:
        self.llm_calls += 1
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage:
            # Fallback for providers that only populate the message's metadata.
            try:
                meta = response.generations[0][0].message.usage_metadata or {}
                usage = {
                    "prompt_tokens": meta.get("input_tokens", 0),
                    "completion_tokens": meta.get("output_tokens", 0),
                }
            except (AttributeError, IndexError, TypeError):
                usage = {}
        self.prompt_tokens += usage.get("prompt_tokens") or 0
        self.completion_tokens += usage.get("completion_tokens") or 0

    def as_dict(self) -> dict[str, int]:
        return {
            "llm_calls": self.llm_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _get_llm(collector: UsageCollector | None = None) -> Runnable:
    """
    The primary model, backed by a second one. Retries inside the client cover
    transient errors; the fallback covers a model being retired, overloaded or
    rejecting the request outright, which a retry would never fix.

    With a collector, the returned runnable is a cheap binding around the same
    cached client that reports usage to it.
    """
    global _llm
    if _llm is None:
        primary = _build_llm(GROQ_MODEL)
        if GROQ_FALLBACK_MODEL and GROQ_FALLBACK_MODEL != GROQ_MODEL:
            _llm = primary.with_fallbacks([_build_llm(GROQ_FALLBACK_MODEL)])
            logger.info("ChatGroq ready (model: %s, fallback: %s)", GROQ_MODEL, GROQ_FALLBACK_MODEL)
        else:
            _llm = primary
            logger.info("ChatGroq ready (model: %s, no fallback)", GROQ_MODEL)
    return _llm.with_config(callbacks=[collector]) if collector else _llm


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


def _confidence(scores: list[float]) -> float:
    """Mean similarity of the retrieved chunks — the out-of-domain signal."""
    return sum(scores) / len(scores) if scores else 0.0


def _low_confidence_response(n_chunks: int, confidence: float, agentic: bool) -> dict[str, Any]:
    return {
        "answer": "I don't have enough relevant context in the uploaded documents to answer your question confidently.",
        "sources": [], "chunks": n_chunks, "confidence": confidence,
        "agentic_mode": agentic,
        # Reported explicitly rather than inferred from a zero token count: in
        # agentic mode the decomposition call has already happened by now, so a
        # refusal is not free, only much cheaper.
        "refused": True,
    }


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
    collector=None,
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
            "agentic_mode": False, "refused": True,
        }

    chunks = [doc for doc, score in chunks_with_scores]
    avg_score = _confidence([score for _, score in chunks_with_scores])

    logger.info("Retrieved %d chunks (avg score: %.4f)", len(chunks), avg_score)

    if avg_score < CONFIDENCE_THRESHOLD:
        logger.warning("Confidence %.4f below threshold %.4f. Rejecting.", avg_score, CONFIDENCE_THRESHOLD)
        return _low_confidence_response(len(chunks), avg_score, agentic=False)

    messages = _build_prompt(question, chunks)
    response = _get_llm(collector).invoke(messages)
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
    collector=None,
) -> dict[str, Any]:
    """
    Agentic pipeline: Decompose → Multi-retrieve → Synthesise → Self-Critique.
    Falls back to _simple_query if ANYTHING goes wrong at any step.
    """
    from .agentic import (
        decompose_query,
        retrieve_for_subqueries,
        retry_synthesis,
        self_critique,
    )

    llm = _get_llm(collector)
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
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store, collector)

    # ── Step 2: Multi-retrieval ──────────────────────────────────────────────
    try:
        merged_chunks, scores, retrieval_trace = retrieve_for_subqueries(
            sub_queries, vector_store, qdrant_filter, top_k
        )
        reasoning_steps.append({
            "phase": "retrieval",
            "retrieval_trace": retrieval_trace,
            "total_unique_chunks": len(merged_chunks),
        })
    except Exception as e:
        logger.warning("Multi-retrieval crashed (%s). Falling back to simple RAG.", e)
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store, collector)

    if not merged_chunks:
        return {
            "answer": "I don't have any relevant documents to answer that question.",
            "sources": [], "chunks": 0, "confidence": 0.0,
            "reasoning_steps": reasoning_steps, "agentic_mode": True, "refused": True,
        }

    # Same out-of-domain check as the simple path: skip the LLM entirely
    # when the merged evidence is too weak to ground an answer.
    avg_score = _confidence(scores)
    reasoning_steps[-1]["confidence"] = round(avg_score, 4)
    if avg_score < CONFIDENCE_THRESHOLD:
        logger.warning("Agentic confidence %.4f below threshold %.4f. Rejecting.", avg_score, CONFIDENCE_THRESHOLD)
        response = _low_confidence_response(len(merged_chunks), avg_score, agentic=True)
        response["reasoning_steps"] = reasoning_steps
        return response

    # ── Step 3: Synthesise ───────────────────────────────────────────────────
    try:
        messages = _build_prompt(question, merged_chunks)
        response = llm.invoke(messages)
        parsed_answer = _parse_llm_json(response.content, avg_score)
        reasoning_steps.append({"phase": "synthesis", "llm_call": 2})
    except Exception as e:
        logger.warning("Synthesis crashed (%s). Falling back to simple RAG.", e)
        return _simple_query(question, workspace_id, top_k, user_email, user_role, qdrant_filter, vector_store, collector)

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

    # The workspace is the tenant boundary: every member, whatever their
    # role, can retrieve every document in it. (Roles control who may
    # upload/delete, not who may read.)
    from qdrant_client.http import models as qdrant_models

    qdrant_filter = qdrant_models.Filter(must=[
        qdrant_models.FieldCondition(
            key="metadata.workspace_id",
            match=qdrant_models.MatchValue(value=workspace_id)
        )
    ])
    vector_store  = get_vector_store()
    collector = UsageCollector()

    # Route to correct pipeline
    if AGENTIC_MODE:
        try:
            result = _agentic_query(
                question, workspace_id, top_k,
                user_email, user_role,
                qdrant_filter, vector_store, collector,
            )
        except Exception as e:
            # Nuclear fallback — entire agentic function crashed
            logger.exception("Agentic pipeline completely crashed (%s). Falling back to simple RAG.", e)
            result = _simple_query(
                question, workspace_id, top_k,
                user_email, user_role,
                qdrant_filter, vector_store, collector,
            )
    else:
        result = _simple_query(
            question, workspace_id, top_k,
            user_email, user_role,
            qdrant_filter, vector_store, collector,
        )

    # Zeros here are meaningful: a refused question costs no tokens, which is the
    # point of refusing before generation.
    result["usage"] = collector.as_dict()
    result.setdefault("refused", False)
    return result
