"""
Cache of answers to questions a workspace has already asked.

Exact match on a lightly normalised question, not semantic similarity. Measured
on the golden set with this system's embedding model (all-MiniLM-L6-v2): "How many
days of paid time off do full-time employees get?" and the same question about
part-time employees score 0.918 but have different answers, while genuine
rewordings of one question score 0.66-0.91. No threshold catches the rewordings
without serving one group the other group's answer, so a semantic cache would buy
lower cost with wrong answers. Folding case and spacing still catches the common
repeat: the same question asked again, by the same person or by a teammate.

Entries are keyed on the workspace's corpus_version, which ingestion and deletion
increment. Old entries are never deleted one by one; nothing looks them up any
more and they expire. The version lives in Postgres rather than in the cache
because the Celery worker that finishes an ingestion and the gunicorn process
that answers the next question do not necessarily share a cache (they don't in
development, where each process has its own in-memory one). A version kept there
could keep serving an answer from before a document was deleted.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db.models import F

from .models import Workspace

_TRAILING = " \t\r\n?!.;:\"'"


def normalise_question(question: str) -> str:
    """
    Lower-case, collapse whitespace, drop trailing punctuation. Deliberately no
    more: stripping punctuation inside the question would make "-5" and "5", or
    "5.5%" and "55%", the same question.
    """
    return " ".join(question.lower().split()).strip(_TRAILING)


def _key(workspace_id: int, question: str, top_k) -> str:
    version = Workspace.objects.filter(id=workspace_id).values_list("corpus_version", flat=True).first()
    digest = hashlib.sha256(f"{top_k}|{normalise_question(question)}".encode()).hexdigest()
    return f"answer:v1:{workspace_id}:{version}:{digest}"


def enabled() -> bool:
    return settings.ANSWER_CACHE_TTL_SECONDS > 0


def get(workspace_id: int, question: str, top_k=None):
    """Returns (cached result or None, key to store under)."""
    key = _key(workspace_id, question, top_k)
    return cache.get(key), key


def put(key: str, result: dict) -> None:
    # Usage describes the call that produced the answer, not a later cache hit.
    cache.set(key, {k: v for k, v in result.items() if k != "usage"}, settings.ANSWER_CACHE_TTL_SECONDS)


def bump_corpus_version(workspace_id: int) -> None:
    """Call whenever a workspace's documents change, so its cached answers stop matching."""
    Workspace.objects.filter(id=workspace_id).update(corpus_version=F("corpus_version") + 1)
