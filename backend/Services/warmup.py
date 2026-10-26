"""
Load the slow, one-off dependencies before a process serves its first request.

The embedding model and the LLM client are lazy singletons, so whichever request
came first used to pay for them: importing torch and sentence-transformers,
loading the model, and building the HTTP client. Measured on a warm machine,
that was 14-22 s on top of a ~3 s query, which is where the "16 s per answer"
seen on a freshly deployed box came from. Calling warm_up() when a worker boots
moves that cost to start-up, where nobody is waiting for it.
"""

import logging
import time

logger = logging.getLogger(__name__)


def warm_up(include_llm: bool = True) -> float:
    """
    Load the embedding model, and optionally build the LLM client. Returns seconds taken.

    Never raises: a worker that cannot warm up (no GROQ_API_KEY yet, say) must still
    start and answer /app/health. It just pays the cost on its first request, as
    before.
    """
    started = time.perf_counter()
    try:
        from Services.Ai_service.embedding import get_embeddings

        get_embeddings().embed_query("warm up")
    except Exception:
        logger.exception("Warm-up: embedding model failed to load; it will load on first use")

    if include_llm:
        try:
            from Services import agent

            agent._get_llm()  # builds the client only; makes no API call and spends no tokens
        except Exception:
            logger.exception("Warm-up: LLM client could not be built; it will be built on first use")

    elapsed = time.perf_counter() - started
    logger.info("Warm-up finished in %.1fs", elapsed)
    return elapsed
