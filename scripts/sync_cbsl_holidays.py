"""Fetch CBSL bank holidays and weekend dates into cbsl_bank_holidays."""

import argparse
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from bs4 import BeautifulSoup

from db import repositories as repo

CBSL_URL = "https://www.cbsl.gov.lk/en/about/about-the-bank/bank-holidays-{year}"
DEFAULT_YEARS = (2025, 2026, 2027)
USER_AGENT = "Mozilla/5.0 (compatible; Zenith/1.0; +https://github.com/zenith)"

DATE_PATTERNS = (
    "%B %d, %A",  # January 03, Saturday
    "%B %d %A",  # January 3 Saturday (fallback)
)


def parse_cbsl_date(text: str, year: int) -> date | None:
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text.strip(), flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(f"{cleaned} {year}", f"{fmt} %Y").date()
        except ValueError:
            continue
    return None


def fetch_year_page(year: int) -> str:
    url = CBSL_URL.format(year=year)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_cbsl_holidays(html: str, year: int) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return {}

    holidays: dict[str, str] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        date_text = cells[0].get_text(" ", strip=True)
        desc_text = cells[1].get_text(" ", strip=True)
        if not date_text or not desc_text:
            continue
        if "Mercantile Holiday" in desc_text and "All Saturdays" in desc_text:
            continue
        if desc_text.startswith("B – Bank Holiday") or desc_text.startswith("B - Bank Holiday"):
            continue

        parsed = parse_cbsl_date(date_text, year)
        if not parsed:
            continue

        iso = parsed.isoformat()
        if iso in holidays:
            holidays[iso] = f"{holidays[iso]}; {desc_text}"
        else:
            holidays[iso] = desc_text
    return holidays


def weekend_holidays(year: int) -> dict[str, str]:
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    out: dict[str, str] = {}
    while d <= end:
        if d.weekday() >= 5:
            out[d.isoformat()] = "Saturday" if d.weekday() == 5 else "Sunday"
        d += timedelta(days=1)
    return out


def merge_holidays(cbsl: dict[str, str], weekends: dict[str, str]) -> dict[str, str]:
    merged = dict(weekends)
    merged.update(cbsl)
    return merged


def sync_years(years: list[int], dry_run: bool = False) -> int:
    all_rows: dict[str, str] = {}
    failed_years: list[int] = []
    cbsl_total = 0
    weekend_only_total = 0

    for year in years:
        weekends = weekend_holidays(year)
        try:
            html = fetch_year_page(year)
            cbsl = parse_cbsl_holidays(html, year)
            merged = merge_holidays(cbsl, weekends)
            weekend_only = sum(1 for k in weekends if k not in cbsl)
            cbsl_total += len(cbsl)
            weekend_only_total += weekend_only
            all_rows.update(merged)
            print(f"  {year}: {len(cbsl)} CBSL + {weekend_only} weekend-only = {len(merged)} rows")
        except Exception as e:
            failed_years.append(year)
            merged = merge_holidays({}, weekends)
            weekend_only_total += len(weekends)
            all_rows.update(merged)
            print(f"  {year}: CBSL fetch failed ({e}); weekends only = {len(weekends)} rows")

    if not all_rows:
        print("No holidays collected.")
        return 0

    start = f"{min(years)}-01-01"
    end = f"{max(years)}-12-31"
    rows = sorted(all_rows.items())

    print(f"Summary: CBSL rows={cbsl_total}, weekend-only={weekend_only_total}, total={len(rows)}")
    if failed_years:
        print(f"Failed years: {failed_years}")

    if dry_run:
        print(f"Dry run — would replace holidays in {start}..{end}")
        return len(rows)

    inserted = repo.replace_holidays_in_range(start, end, rows)
    print(f"Database updated: {inserted} rows in range {start}..{end} (table total: {repo.get_holiday_count()})")
    return inserted


def load_from_sql(sql_path: Path | None = None) -> int:
    """Load Zenith-1 populate_cbsl_holidays.sql into cbsl_bank_holidays (INSERT OR IGNORE)."""
    from db.connection import get_connection

    path = sql_path or (ROOT / "database" / "populate_cbsl_holidays.sql")
    if not path.exists():
        raise FileNotFoundError(f"Holiday SQL not found: {path}")
    sql = path.read_text(encoding="utf-8")
    # Prefer idempotent inserts when re-running the seed file
    sql = sql.replace("INSERT INTO cbsl_bank_holidays", "INSERT OR IGNORE INTO cbsl_bank_holidays")
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM cbsl_bank_holidays").fetchone()[0]
        conn.executescript(sql)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM cbsl_bank_holidays").fetchone()[0]
    finally:
        conn.close()
    added = after - before
    print(f"Loaded {path.name}: table now has {after} rows (+{added})")
    return added


def main():
    parser = argparse.ArgumentParser(description="Sync CBSL bank holidays and weekends into SQLite")
    parser.add_argument(
        "--years",
        default=",".join(str(y) for y in DEFAULT_YEARS),
        help="Comma-separated years (default: 2025,2026,2027)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse only; do not write DB")
    parser.add_argument(
        "--from-sql",
        action="store_true",
        help="Load database/populate_cbsl_holidays.sql (Zenith-1 seed) instead of fetching CBSL",
    )
    args = parser.parse_args()

    if args.from_sql:
        load_from_sql()
        return

    years = sorted({int(y.strip()) for y in args.years.split(",") if y.strip()})
    print(f"Syncing CBSL holidays for {years}...")
    sync_years(years, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
