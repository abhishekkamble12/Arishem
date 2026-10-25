"""Qdrant collection setup must never delete data. Offline: the client is faked."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from Services.Ai_service import embedding


class EnsureCollectionTests(SimpleTestCase):
    """ensure_collection_exists must never delete data."""

    def setUp(self):
        embedding._collection_ready = False
        self.addCleanup(setattr, embedding, "_collection_ready", False)
        self.client = MagicMock()
        patcher = patch.object(embedding, "get_qdrant_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _existing(self, size):
        coll = MagicMock()
        coll.name = embedding.QDRANT_COLLECTION
        self.client.get_collections.return_value.collections = [coll]
        info = MagicMock()
        info.config.params.vectors = {"content-dense": MagicMock(size=size)}
        self.client.get_collection.return_value = info

    def test_creates_missing_collection_and_indexes(self):
        self.client.get_collections.return_value.collections = []
        embedding.ensure_collection_exists()
        self.client.create_collection.assert_called_once()
        self.assertEqual(self.client.create_payload_index.call_count, 3)

    def test_dimension_mismatch_raises_and_deletes_nothing(self):
        self._existing(size=1024)
        with self.assertRaises(embedding.CollectionConfigError):
            embedding.ensure_collection_exists()
        self.client.delete_collection.assert_not_called()
        self.client.create_collection.assert_not_called()

    def test_transient_error_propagates_and_deletes_nothing(self):
        self._existing(size=384)
        self.client.get_collection.side_effect = ConnectionError("qdrant down")
        with self.assertRaises(ConnectionError):
            embedding.ensure_collection_exists()
        self.client.delete_collection.assert_not_called()

    def test_checks_run_once_per_process(self):
        self._existing(size=384)
        embedding.ensure_collection_exists()
        embedding.ensure_collection_exists()
        self.assertEqual(self.client.get_collections.call_count, 1)
