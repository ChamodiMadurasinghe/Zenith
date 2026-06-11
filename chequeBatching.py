import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "database" / "invoice_cheque.db"


def query_sqlite(sql: str, params=None):
    """Run a query against invoice_cheque.db and return rows as dictionaries."""
    params = params or ()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def list_tables():
    """Return all non-system tables in the SQLite database."""
    return query_sqlite(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )


def main():
    print(f"Using DB: {DB_PATH}")

    tables = list_tables()
    print("Tables:", [row["name"] for row in tables])

    if tables:
        first_table = tables[0]["name"]
        print(f"\nQuerying first table: {first_table}")
        rows = query_sqlite(f"SELECT * FROM {first_table} LIMIT 10")
        for row in rows:
            print(row)
    else:
        print("No tables found in invoice_cheque.db.")


if __name__ == "__main__":
    main()
