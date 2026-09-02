"""ChromaDB vector store for dealer payment pattern memory."""

from __future__ import annotations

import logging
from pathlib import Path

from config import Config, BASE_DIR
from core.dealer_patterns import (
    build_dealer_pattern_document,
    build_dealer_pattern_metadata,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "dealer_payment_patterns"
_NO_PATTERNS_MSG = "No historical payment patterns recorded for this dealer yet."


def _chroma_path() -> Path:
    raw = Config.chroma_persist_dir()
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _embed_texts(texts: list[str]) -> list[list[float]]:
    from agents.providers.openai import get_openai_client

    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI client unavailable for embeddings")
    model = Config.openai_embedding_model()
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def _get_collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(_chroma_path()))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_dealer_pattern(dealer_id: int) -> None:
    """Rebuild and upsert the dealer pattern document into ChromaDB."""
    if not Config.enable_vector_patterns():
        return
    if Config.use_fake_ai():
        return

    document = build_dealer_pattern_document(dealer_id)
    metadata = build_dealer_pattern_metadata(dealer_id)
    doc_id = f"dealer-{dealer_id}"

    try:
        collection = _get_collection()
        embedding = _embed_texts([document])[0]
        collection.upsert(
            ids=[doc_id],
            documents=[document],
            embeddings=[embedding],
            metadatas=[
                {
                    "dealer_id": dealer_id,
                    "updated_at": metadata["updated_at"],
                    "bundling_behavior": metadata["bundling_behavior"],
                }
            ],
        )
    except Exception:
        logger.exception("Failed to upsert dealer pattern for dealer_id=%s", dealer_id)
        raise


def query_dealer_patterns(dealer_id: int, invoice_total: float) -> str:
    """Retrieve historical payment pattern text for a dealer."""
    if Config.use_fake_ai():
        from agents.mock import mock_dealer_payment_patterns

        return mock_dealer_payment_patterns(dealer_id, invoice_total)

    if not Config.enable_vector_patterns():
        return _NO_PATTERNS_MSG

    document = build_dealer_pattern_document(dealer_id)
    if "No committed cheque payment history" in document:
        return _NO_PATTERNS_MSG

    try:
        collection = _get_collection()
        query_text = (
            f"Dealer {dealer_id} payment history for invoice total "
            f"{invoice_total:,.0f} LKR"
        )
        query_embedding = _embed_texts([query_text])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=1,
            where={"dealer_id": dealer_id},
        )
        docs = (results.get("documents") or [[]])[0]
        if docs:
            return docs[0]
    except Exception:
        logger.exception(
            "Vector query failed for dealer_id=%s; falling back to live document",
            dealer_id,
        )

    return document


def backfill_all_dealer_patterns() -> int:
    """Index all dealers that have committed payment history."""
    from db import repositories as repo

    if not Config.enable_vector_patterns() or Config.use_fake_ai():
        return 0

    count = 0
    for dealer in repo.get_dealers():
        dealer_id = int(dealer["dealer_id"])
        history = repo.get_dealer_committed_payment_history(dealer_id)
        if not history:
            continue
        try:
            upsert_dealer_pattern(dealer_id)
            count += 1
        except Exception:
            logger.exception("Backfill failed for dealer_id=%s", dealer_id)
    return count
