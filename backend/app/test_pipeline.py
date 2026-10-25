"""
Tests — RAG query routing (out-of-domain refusal) and the ingestion task.

The vector store and LLM are replaced with in-memory fakes so these run
offline and deterministically.
"""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from langchain_core.documents import Document
from Services import agent

from .models import IngestedFile
from .tasks import reconcile_stuck_ingestions, run_ingestion_task
from .tests import _make_user


class FakeVectorStore:
    """Returns the same scored chunks for every search."""

    def __init__(self, scored_chunks):
        self.scored_chunks = scored_chunks
        self.calls = []

    def similarity_search_with_score(self, query, k, filter):
        self.calls.append((query, k, filter))
        return self.scored_chunks[:k]


def _llm_returning(*payloads):
    llm = MagicMock()
    llm.invoke.side_effect = [SimpleNamespace(content=json.dumps(p)) for p in payloads]
    return llm


def _chunks(*scores):
    return [(Document(page_content=f"chunk {i}", metadata={"source": "doc.pdf"}), s)
            for i, s in enumerate(scores)]


THRESHOLD = patch.object(agent, "CONFIDENCE_THRESHOLD", 0.35)  # independent of local .env

ANSWER = {"answer": "90 days", "citations": [{"source": "doc.pdf", "snippet": "90 days"}],
          "unverified": "", "confidence_score": 0.9}


@THRESHOLD
class SimpleQueryTests(TestCase):

    def _run(self, store, llm):
        with patch.object(agent, "AGENTIC_MODE", False), \
             patch.object(agent, "get_vector_store", return_value=store), \
             patch.object(agent, "_get_llm", return_value=llm):
            return agent.query("How long are logs kept?", workspace_id=7)

    def test_low_confidence_skips_llm(self):
        llm = _llm_returning(ANSWER)
        result = self._run(FakeVectorStore(_chunks(0.1, 0.05)), llm)
        llm.invoke.assert_not_called()
        self.assertEqual(result["sources"], [])
        self.assertAlmostEqual(result["confidence"], 0.075)

    def test_high_confidence_calls_llm(self):
        llm = _llm_returning(ANSWER)
        result = self._run(FakeVectorStore(_chunks(0.8, 0.6)), llm)
        llm.invoke.assert_called_once()
        self.assertEqual(result["answer"], "90 days")
        self.assertEqual(result["sources"], ["doc.pdf"])

    def test_search_is_filtered_by_workspace_only(self):
        store = FakeVectorStore(_chunks(0.8))
        with patch.object(agent, "AGENTIC_MODE", False), \
             patch.object(agent, "get_vector_store", return_value=store), \
             patch.object(agent, "_get_llm", return_value=_llm_returning(ANSWER)):
            agent.query("q", workspace_id=7, user_role="viewer", user_email="v@test.com")

        conditions = store.calls[0][2].must
        self.assertEqual([(c.key, c.match.value) for c in conditions], [("metadata.workspace_id", 7)])


@THRESHOLD
class AgenticQueryTests(TestCase):

    def _run(self, store, llm):
        with patch.object(agent, "AGENTIC_MODE", True), \
             patch.object(agent, "SELF_CRITIQUE", True), \
             patch.object(agent, "get_vector_store", return_value=store), \
             patch.object(agent, "_get_llm", return_value=llm):
            return agent.query("How long are logs kept?", workspace_id=7)

    def test_low_confidence_refuses_after_decomposition(self):
        # Only the decomposition call may happen — no synthesis, no critique
        llm = _llm_returning({"sub_queries": ["How long are logs kept?"]})
        result = self._run(FakeVectorStore(_chunks(0.1, 0.2)), llm)
        self.assertEqual(llm.invoke.call_count, 1)
        self.assertTrue(result["agentic_mode"])
        self.assertEqual(result["sources"], [])
        self.assertAlmostEqual(result["confidence"], 0.15)

    def test_confident_path_synthesises_and_critiques(self):
        llm = _llm_returning(
            {"sub_queries": ["How long are logs kept?"]},
            ANSWER,
            {"verdict": "PASS", "unsupported_claims": []},
        )
        result = self._run(FakeVectorStore(_chunks(0.8, 0.7)), llm)
        self.assertEqual(llm.invoke.call_count, 3)
        self.assertEqual(result["answer"], "90 days")
        self.assertEqual(result["critique_verdict"], "PASS")
        self.assertAlmostEqual(result["confidence"], 0.75)


class IngestionTaskTests(TestCase):

    def setUp(self):
        self.user = _make_user("e@test.com", "Pass1234!", "editor")
        self.ws = self.user.workspaces.first()
        self.file = IngestedFile.objects.create(
            object_bucket="b", object_key=f"ws_{self.ws.id}/abc_policy.pdf",
            original_filename="policy.pdf", file_type="pdf",
            workspace=self.ws, uploaded_by=self.user, status="PENDING",
        )

    def _run(self):
        return run_ingestion_task.apply(kwargs=dict(
            s3_key=self.file.object_key, user_id=self.user.id,
            workspace_id=self.ws.id, file_id=self.file.id,
        ))

    @patch("app.tasks.delete_file_vectors")
    @patch("app.tasks.embed_and_store", return_value=2)
    @patch("app.tasks.extract_and_chunk")
    def test_success_marks_file_and_tags_chunks(self, mock_extract, mock_embed, mock_clear):
        chunks = [Document(page_content="a", metadata={"source": self.file.object_key}),
                  Document(page_content="b", metadata={"source": self.file.object_key})]
        mock_extract.return_value = chunks

        self._run()

        self.file.refresh_from_db()
        self.assertEqual(self.file.status, "SUCCESS")
        self.assertEqual(self.file.chunks_stored, 2)
        self.assertIsNotNone(self.file.last_indexed_timestamp)
        mock_clear.assert_called_once_with(self.file.id, self.ws.id)
        mock_embed.assert_called_once_with(chunks, self.ws.id, uploaded_by=self.user.email, file_id=self.file.id)
        # Citations show the uploaded name, not the internal storage key
        self.assertEqual({c.metadata["source"] for c in chunks}, {"policy.pdf"})

    @patch("app.tasks.embed_and_store")
    @patch("app.tasks.extract_and_chunk", side_effect=ValueError("corrupt PDF"))
    def test_failure_marks_file_failed(self, _mock_extract, mock_embed):
        result = self._run()

        self.assertTrue(result.failed())
        self.file.refresh_from_db()
        self.assertEqual(self.file.status, "FAILED")
        self.assertIn("corrupt PDF", self.file.error_message)
        mock_embed.assert_not_called()

    @patch("app.tasks.extract_and_chunk")
    def test_redelivered_task_is_a_no_op(self, mock_extract):
        self.file.status = "SUCCESS"
        self.file.save()

        self._run()

        mock_extract.assert_not_called()


class ReconciliationTests(TestCase):

    def test_only_stale_in_flight_files_are_failed(self):
        ws = _make_user("r@test.com", "Pass1234!", "editor").workspaces.first()

        def make(key, status, age_minutes):
            f = IngestedFile.objects.create(object_bucket="b", object_key=key, file_type="pdf",
                                            workspace=ws, status=status)
            IngestedFile.objects.filter(id=f.id).update(
                ingested_at=timezone.now() - timedelta(minutes=age_minutes))
            return f

        stale = make("ws/stale.pdf", "PROCESSING", 45)
        fresh = make("ws/fresh.pdf", "PENDING", 5)
        done = make("ws/done.pdf", "SUCCESS", 45)

        reconcile_stuck_ingestions()

        statuses = {f.id: IngestedFile.objects.get(id=f.id).status for f in (stale, fresh, done)}
        self.assertEqual(statuses, {stale.id: "FAILED", fresh.id: "PENDING", done.id: "SUCCESS"})
