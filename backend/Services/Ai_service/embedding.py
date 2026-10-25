import logging

from decouple import config
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
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


class CollectionConfigError(RuntimeError):
    """The existing Qdrant collection is incompatible with the embedding model."""


_collection_ready = False

# (field, schema) payload indexes every query/delete relies on.
_PAYLOAD_INDEXES = (
    ("metadata.workspace_id", "integer"),
    ("metadata.file_id", "integer"),
    ("metadata.uploaded_by", "keyword"),
)


def _dense_vector_size(info) -> int | None:
    """Size of the 'content-dense' vector, or None if it can't be determined."""
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        params = vectors.get("content-dense")
        return params.size if params is not None else None
    return getattr(vectors, "size", None)


def ensure_collection_exists() -> None:
    """
    Create the Qdrant collection and payload indexes if they are missing.

    Never deletes data. A transient Qdrant error propagates to the caller (the
    request fails and can be retried) instead of being treated as "needs
    recreating". A collection whose vector size differs from the embedding
    model raises CollectionConfigError: switching models means re-embedding,
    which is an explicit migration, not something to do silently at request time.
    Runs its checks once per process; safe to call repeatedly.
    """
    global _collection_ready
    if _collection_ready:
        return

    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}

    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "content-dense": VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
            },
        )
        logger.info("Created Qdrant collection '%s' (dim %d)", QDRANT_COLLECTION, EMBEDDING_DIMENSION)
    else:
        size = _dense_vector_size(client.get_collection(collection_name=QDRANT_COLLECTION))
        if size is not None and size != EMBEDDING_DIMENSION:
            raise CollectionConfigError(
                f"Collection '{QDRANT_COLLECTION}' has vector size {size} but the embedding model "
                f"produces {EMBEDDING_DIMENSION}. Re-embed into a new collection "
                f"(set QDRANT_COLLECTION) instead of reusing this one."
            )

    for field, schema in _PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=QDRANT_COLLECTION, field_name=field, field_schema=schema
            )
        except Exception:
            # Index already exists (Qdrant has no "if not exists"); a real outage
            # would have failed the calls above.
            logger.debug("Payload index %s not created (probably exists)", field)

    _collection_ready = True


def embed_and_store(
    chunks: list[Document],
    workspace_id: int,
    uploaded_by: str = None,
    file_id: int | None = None,
) -> int:
    """
    Embed a list of Document chunks and upsert them into Qdrant.

    Args:
        chunks: List of LangChain Documents (typically from Extractor.extract_and_chunk).
        workspace_id: The ID of the workspace these chunks belong to.
        uploaded_by: The email address of the user who uploaded these documents.
        file_id: IngestedFile id, stored on every chunk so the file's vectors
                 can be deleted later.

    Returns:
        Number of chunks stored.

    Raises:
        ValueError: if chunks is empty.
        Exception:  propagates Qdrant / embedding errors.
    """
    if not chunks:
        raise ValueError("embed_and_store received an empty chunk list — nothing to store.")

    for chunk in chunks:
        chunk.metadata["workspace_id"] = workspace_id
        if uploaded_by:
            chunk.metadata["uploaded_by"] = uploaded_by
        if file_id is not None:
            chunk.metadata["file_id"] = file_id

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


def delete_file_vectors(file_id: int, workspace_id: int) -> None:
    """
    Delete every vector belonging to one ingested file.

    Filters on workspace_id as well as file_id so a bad id can never touch
    another tenant's data. Idempotent: deleting twice is a no-op.
    """
    ensure_collection_exists()
    get_qdrant_client().delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=qdrant_models.FilterSelector(
            filter=qdrant_models.Filter(must=[
                qdrant_models.FieldCondition(
                    key="metadata.file_id",
                    match=qdrant_models.MatchValue(value=file_id),
                ),
                qdrant_models.FieldCondition(
                    key="metadata.workspace_id",
                    match=qdrant_models.MatchValue(value=workspace_id),
                ),
            ])
        ),
        wait=True,
    )
    logger.info("Deleted vectors for file #%d (workspace %d)", file_id, workspace_id)


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

