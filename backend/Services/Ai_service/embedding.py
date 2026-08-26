import logging
from typing import List

from decouple import config
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
QDRANT_URL = config("QDRANT_URL", default="http://localhost:6333")
QDRANT_API_KEY = config("QDRANT_API_KEY", default="")
QDRANT_COLLECTION = config("QDRANT_COLLECTION", default="documents")

# all-MiniLM-L6-v2 produces 384-dimensional vectors.
EMBEDDING_DIMENSION = 384

# ---------------------------------------------------------------------------
# Singletons — created once per process
# ---------------------------------------------------------------------------
_embeddings: HuggingFaceEmbeddings | None = None
_qdrant_client: QdrantClient | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Lazy singleton for the local embedding model."""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )
        logger.info("HuggingFaceEmbeddings initialised (model: all-MiniLM-L6-v2)")
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
    Recreates it if there is a vector name or dimension mismatch.
    Safe to call multiple times (idempotent).
    """
    client = get_qdrant_client()
    try:
        existing = {c.name for c in client.get_collections().collections}
    except Exception as e:
        logger.error("Failed to list Qdrant collections: %s", e)
        return

    should_create = QDRANT_COLLECTION not in existing

    if QDRANT_COLLECTION in existing:
        try:
            info = client.get_collection(collection_name=QDRANT_COLLECTION)
            vectors = info.config.params.vectors
            
            # Extract current size of the 'content-dense' vector
            current_size = None
            if isinstance(vectors, dict):
                if "content-dense" in vectors:
                    current_size = vectors["content-dense"].size
            elif hasattr(vectors, "size"):
                current_size = vectors.size
            else:
                # vectors might be a VectorsConfig object (e.g. in some qdrant_client versions)
                if hasattr(vectors, "params") and isinstance(vectors.params, dict):
                    if "content-dense" in vectors.params:
                        current_size = vectors.params["content-dense"].size
                elif hasattr(vectors, "params") and hasattr(vectors.params, "size"):
                    current_size = vectors.params.size

            if current_size is not None and current_size != EMBEDDING_DIMENSION:
                logger.warning(
                    "Qdrant collection '%s' vector dimension mismatch: collection has %d, but embedding model has %d. Recreating...",
                    QDRANT_COLLECTION, current_size, EMBEDDING_DIMENSION
                )
                client.delete_collection(collection_name=QDRANT_COLLECTION)
                should_create = True
        except Exception as e:
            logger.warning("Failed to verify Qdrant collection config: %s. Recreating to be safe.", e)
            try:
                client.delete_collection(collection_name=QDRANT_COLLECTION)
            except Exception:
                pass
            should_create = True

    if should_create:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "content-dense": VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                )
            },
        )
        logger.info("Created Qdrant collection '%s' with dimension %d", QDRANT_COLLECTION, EMBEDDING_DIMENSION)
    else:
        logger.debug("Collection '%s' already exists and matches configuration", QDRANT_COLLECTION)

    # Ensure payload index on metadata.workspace_id exists
    try:
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name="metadata.workspace_id",
            field_schema="integer",
        )
        logger.info("Ensured payload index on 'metadata.workspace_id' exists")
    except Exception as e:
        logger.warning("Failed to create payload index on 'metadata.workspace_id': %s", e)

    # Ensure payload index on metadata.uploaded_by exists
    try:
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name="metadata.uploaded_by",
            field_schema="keyword",
        )
        logger.info("Ensured payload index on 'metadata.uploaded_by' exists")
    except Exception as e:
        logger.warning("Failed to create payload index on 'metadata.uploaded_by': %s", e)


def embed_and_store(chunks: List[Document], workspace_id: int, uploaded_by: str = None) -> int:
    """
    Embed a list of Document chunks and upsert them into Qdrant.

    Args:
        chunks: List of LangChain Documents (typically from Extractor.extract_and_chunk).
        workspace_id: The ID of the workspace these chunks belong to.
        uploaded_by: The email address of the user who uploaded these documents.

    Returns:
        Number of chunks stored.

    Raises:
        ValueError: if chunks is empty.
        Exception:  propagates Qdrant / Bedrock errors.
    """
    if not chunks:
        raise ValueError("embed_and_store received an empty chunk list — nothing to store.")

    for chunk in chunks:
        chunk.metadata["workspace_id"] = workspace_id
        if uploaded_by:
            chunk.metadata["uploaded_by"] = uploaded_by

    ensure_collection_exists()

    logger.info("Embedding and storing %d chunks into '%s' (workspace: %d, uploader: %s)…", len(chunks), QDRANT_COLLECTION, workspace_id, uploaded_by)

    QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION,
        vector_name="content-dense",
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
        vector_name="content-dense",
    )

