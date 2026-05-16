"""
RAG Query Agent — the retrieval half of the pipeline.

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
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document

from .Ai_service.embedding import get_vector_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_REGION      = config("AWS_REGION", default="us-east-1")
BEDROCK_MODEL   = config("BEDROCK_MODEL_ID", default="anthropic.claude-3-5-sonnet-20241022-v2:0")
TOP_K           = int(config("RAG_TOP_K", default=5))

# ---------------------------------------------------------------------------
# Singleton LLM
# ---------------------------------------------------------------------------
_llm: ChatBedrockConverse | None = None


def _get_llm() -> ChatBedrockConverse:
    global _llm
    if _llm is None:
        _llm = ChatBedrockConverse(
            model=BEDROCK_MODEL,
            region_name=AWS_REGION,
            temperature=0.2,      # low temp → factual, grounded answers
            max_tokens=2048,
        )
        logger.info("ChatBedrockConverse initialised (model: %s)", BEDROCK_MODEL)
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

def query(question: str, top_k: int = TOP_K) -> dict[str, Any]:
    """
    Answer a question using RAG over the Qdrant vector store.

    Args:
        question: The user's natural language question.
        top_k:    Number of chunks to retrieve (default from RAG_TOP_K env var).

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

    logger.info("RAG query: '%s' (top_k=%d)", question[:80], top_k)

    # 1. Retrieve relevant chunks from Qdrant
    vector_store = get_vector_store()
    chunks: list[Document] = vector_store.similarity_search(question, k=top_k)

    if not chunks:
        logger.warning("No relevant chunks found for question: '%s'", question[:80])
        return {
            "answer": "I don't have any relevant documents to answer that question.",
            "sources": [],
            "chunks": 0,
        }

    logger.info("Retrieved %d chunks, calling LLM…", len(chunks))

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
    }
