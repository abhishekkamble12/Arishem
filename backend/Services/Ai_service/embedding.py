"""
Embedding + Qdrant storage layer.

Uses Amazon Bedrock Titan Embeddings (v2) for vectors and Qdrant Cloud as
the vector store.  All credentials come from environment variables — nothing
is hardcoded here.

Environment variables required (set in .env):
    QDRANT_URL          — Qdrant Cloud cluster URL
    QDRANT_API_KEY      — Qdrant Cloud API key
    QDRANT_COLLECTION   — collection name (default: "documents")
    AWS_REGION          — AWS region for Bedrock (default: "us-east-1")
"""

import logging
from typing import List

from decouple import config
from langchain_aws import BedrockEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
QDRANT_URL = config("QDRANT_URL")
QDRANT_API_KEY = config("QDRANT_API_KEY")
QDRANT_COLLECTION = config("QDRANT_COLLECTION", default="documents")
AWS_REGION = config("AWS_REGION", default="us-east-1")

# Titan Embed Text v2 produces 1024-dimensional vectors.
# If you switch models, update this constant.
EMBEDDING_DIMENSION = 1024

# ---------------------------------------------------------------------------
# Singletons — created once per process
# ---------------------------------------------------------------------------
_embeddings: BedrockEmbeddings | None = None
_qdrant_client: QdrantClient | None = None


def get_embeddings() -> BedrockEmbeddings:
    """Lazy singleton for the Bedrock embedding model."""
    global _embeddings
    if _embeddings is None:
        _embeddings = BedrockEmbeddings(
            model_id="amazon.titan-embed-text-v2:0",
            region_name=AWS_REGION,
            # boto3 picks up AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from env,
            # or uses the attached IAM role in production — no hardcoding needed.
        )
        logger.info("BedrockEmbeddings initialised (model: titan-embed-text-v2:0)")
    return _embeddings


def get_qdrant_client() -> QdrantClient:
    """Lazy singleton for the Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=30,
        )
        logger.info("QdrantClient connected to %s", QDRANT_URL)
    return _qdrant_client


def ensure_collection_exists() -> None:
    """
    Create the Qdrant collection if it doesn't already exist.
    Safe to call multiple times (idempotent).
    """
    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}

    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection '%s'", QDRANT_COLLECTION)
    else:
        logger.debug("Collection '%s' already exists", QDRANT_COLLECTION)


def embed_and_store(chunks: List[Document]) -> int:
    """
    Embed a list of Document chunks and upsert them into Qdrant.

    Args:
        chunks: List of LangChain Documents (typically from Extractor.extract_and_chunk).

    Returns:
        Number of chunks stored.

    Raises:
        ValueError: if chunks is empty.
        Exception:  propagates Qdrant / Bedrock errors.
    """
    if not chunks:
        raise ValueError("embed_and_store received an empty chunk list — nothing to store.")

    ensure_collection_exists()

    logger.info("Embedding and storing %d chunks into '%s'…", len(chunks), QDRANT_COLLECTION)

    QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION,
        # force_recreate=False keeps existing vectors — safe for incremental ingestion
    )

    logger.info("Successfully stored %d chunks", len(chunks))
    return len(chunks)


def get_vector_store() -> QdrantVectorStore:
    """
    Return a QdrantVectorStore instance connected to the existing collection.
    Use this for similarity search / retrieval (e.g. in the agent).
    """
    ensure_collection_exists()
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=QDRANT_COLLECTION,
        embedding=get_embeddings(),
    )
