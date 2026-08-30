"""Backfill ChromaDB dealer payment pattern index from committed SQLite history."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from core.vector_store import backfill_all_dealer_patterns


def main():
    count = backfill_all_dealer_patterns()
    print(f"Indexed {count} dealer(s) into vector store.")


if __name__ == "__main__":
    main()
