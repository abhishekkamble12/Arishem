"""
RAG Query Agent — the retrieval half of the pipeline.

(Reloaded to pick up updated .env configs)

Takes a user question, retrieves the most relevant chunks from Qdrant,
and uses Amazon Bedrock (Claude) to generate a grounded answer.

Flow:
  question → embed question → Qdrant similarity search → top-k chunks
           → Claude prompt (chunks + question) → answer + sources

Environment variables required:
    QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION  — from embedding.py
    AWS_REGION                                      — Bedrock region
    BEDROCK_MODEL_ID                                — Claude model (default below)
    RAG_TOP_K                                       — chunks to retrieve (default 5)
"""

import logging
from typing import Any

from decouple import config
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document

from .Ai_service.embedding import get_vector_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_REGION      = config("AWS_REGION", default="us-east-1")
TOP_K           = int(config("RAG_TOP_K", default=5))
CONFIDENCE_THRESHOLD = float(config("RAG_CONFIDENCE_THRESHOLD", default=0.35))
GROQ_MODEL      = config("GROQ_MODEL_ID", default="llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# Singleton LLM
# ---------------------------------------------------------------------------
_llm: ChatGroq | None = None


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0.2,      # low temp → factual, grounded answers
            max_tokens=2048,
        )
        logger.info("ChatGroq initialised (model: %s)", GROQ_MODEL)
    return _llm



# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly
based on the provided context documents. 

Rules:
- Only use information from the context below.
- If the answer is not in the context, say "I don't have enough information to answer that."
- Always cite the source document (filename) when you use information from it.
- Be concise and direct."""


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query(question: str, workspace_id: int, top_k: int = TOP_K, user_email: str = None, user_role: str = None) -> dict[str, Any]:
    """
    Answer a question using RAG over the Qdrant vector store.

    Args:
        question: The user's natural language question.
        workspace_id: The active workspace ID to filter contexts from.
        top_k:    Number of chunks to retrieve (default from RAG_TOP_K env var).
        user_email: The email address of the current user.
        user_role:  The role of the current user ('viewer', 'editor', or 'admin').

    Returns:
        {
            "answer":  str,           — Claude's grounded answer
            "sources": list[str],     — deduplicated list of source filenames
            "chunks":  int,           — number of chunks used as context
        }

    Raises:
        ValueError:  Empty question.
        Exception:   Propagates Qdrant / Bedrock errors.
    """
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")

    logger.info("RAG query: '%s' (workspace=%d, top_k=%d, user=%s, role=%s)", question[:80], workspace_id, top_k, user_email, user_role)

    # 1. Retrieve relevant chunks from Qdrant with workspace filter
    vector_store = get_vector_store()

    from qdrant_client.http import models as qdrant_models
    
    must_conditions = [
        qdrant_models.FieldCondition(
            key="metadata.workspace_id",
            match=qdrant_models.MatchValue(value=workspace_id)
        )
    ]

    # Rule-Based Access Control: viewers can only search/ground their own uploaded files
    if user_role == 'viewer' and user_email:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="metadata.uploaded_by",
                match=qdrant_models.MatchValue(value=user_email)
            )
        )

    qdrant_filter = qdrant_models.Filter(must=must_conditions)

    chunks_with_scores = vector_store.similarity_search_with_score(
        question, 
        k=top_k, 
        filter=qdrant_filter
    )

    if not chunks_with_scores:
        logger.warning("No relevant chunks found for question: '%s' in workspace: %d", question[:80], workspace_id)
        return {
            "answer": "I don't have any relevant documents to answer that question.",
            "sources": [],
            "chunks": 0,
            "confidence": 0.0,
        }

    chunks = [doc for doc, score in chunks_with_scores]
    avg_score = sum(score for doc, score in chunks_with_scores) / len(chunks_with_scores)

    logger.info("Retrieved %d chunks (avg score: %.4f)", len(chunks), avg_score)

    if avg_score < CONFIDENCE_THRESHOLD:
        logger.warning("Query average confidence (%.4f) below threshold (%.4f). Rejecting and bypassing LLM.", avg_score, CONFIDENCE_THRESHOLD)
        return {
            "answer": "I don't have enough relevant context in the uploaded documents to answer your question confidently.",
            "sources": [],
            "chunks": len(chunks),
            "confidence": avg_score,
        }

    logger.info("Calling LLM…")

    # 2. Build prompt and call Claude
    messages = _build_prompt(question, chunks)
    response = _get_llm().invoke(messages)
    answer = response.content

    # 3. Collect unique sources
    sources = list({doc.metadata.get("source", "unknown") for doc in chunks})

    logger.info("Query answered. Sources: %s", sources)

    return {
        "answer": answer,
        "sources": sources,
        "chunks": len(chunks),
        "confidence": avg_score,
    }
