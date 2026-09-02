"""Tests for Chroma vector store wrapper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core import vector_store


class VectorStoreTests(unittest.TestCase):
    @patch("core.vector_store.Config.enable_vector_patterns", return_value=False)
    def test_disabled_returns_no_patterns_message(self, _flag):
        text = vector_store.query_dealer_patterns(1, 100_000)
        self.assertIn("No historical payment patterns", text)

    @patch("core.vector_store._get_collection")
    @patch("core.vector_store._embed_texts")
    @patch("core.vector_store.Config.use_fake_ai", return_value=False)
    @patch("core.vector_store.Config.enable_vector_patterns", return_value=True)
    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_bank_account")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_upsert_and_query_round_trip(
        self,
        mock_history,
        mock_acc,
        mock_dealer,
        _enable,
        _fake,
        mock_embed,
        mock_get_collection,
    ):
        mock_dealer.return_value = {"dealer_name": "Test Dealer"}
        mock_acc.return_value = {"bank_name": "Commercial Bank"}
        mock_history.return_value = [
            {
                "cheque_id": 1,
                "user_bank_acc_id": 1,
                "verification_status": 1,
                "clearance_date": "2026-04-01",
                "invoices": [
                    {
                        "invoices_id": 1,
                        "invoice_no": "T-1",
                        "invoiced_date": "2026-03-01",
                        "part_index": 1,
                        "part_count": 1,
                        "total_amount": 50_000,
                    }
                ],
            }
        ]
        stored_doc = {}

        def _upsert(*, ids, documents, embeddings, metadatas):
            stored_doc["text"] = documents[0]

        def _query(**kwargs):
            return {"documents": [[stored_doc.get("text", "")]]}

        collection = MagicMock()
        collection.upsert.side_effect = _upsert
        collection.query.side_effect = _query
        mock_get_collection.return_value = collection
        mock_embed.return_value = [[0.1] * 8]

        vector_store.upsert_dealer_pattern(99)
        collection.upsert.assert_called_once()
        text = vector_store.query_dealer_patterns(99, 50_000)
        self.assertIn("Test Dealer", text)
        self.assertIn("paid_individually", text)
        collection.query.assert_called_once()


if __name__ == "__main__":
    unittest.main()
