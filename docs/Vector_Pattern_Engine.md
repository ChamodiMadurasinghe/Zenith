# Zenith Vector Pattern Engine — Complete Guide

SQLite file: `database/invoice_cheque.db`  
Chroma index: `database/chroma/` (local, gitignored)  
Related: [DATABASE.md](../database/DATABASE.md)

---

## 1. Introduction

The **Vector Pattern Engine** gives the AI Bundling Assistant **semantic memory** of how each supplier (dealer) was paid in the past — bundling habits, invoice aging, preferred bank accounts, and split-payment patterns.

### What it is

- A **recommendation engine** that stores one searchable text summary per dealer in **ChromaDB**
- Refreshed automatically every time you **commit cheques** to SQLite
- Queried by the read-only tool `get_dealer_historical_payment_patterns`

### What it is not

| Not this | Why |
|----------|-----|
| Source of truth | SQLite holds all committed invoices and cheques |
| Auto-commit | No cheque is saved without explicit user approval in the UI |
| Date/ceiling calculator | Python `core/guardrails.py` and `core/bundling.py` own all math |
| Required for bundling | App works without it; patterns only improve AI suggestions |

**One-line summary:** SQLite stores facts; ChromaDB stores **searchable pattern summaries** for the AI.

---

## 2. Why a vector database?

Plain SQL can list past cheques, but the Bundling Assistant needs **natural-language context** the model can reason about:

- “This dealer is usually paid individually” vs “frequently bundled”
- Exact aging per invoice (unbundled) vs average aging (bundled groups)
- “Commercial Bank was used 80% of the time”
- “Large bills over 500k are usually split into 2 cheques 7 days apart”

**ChromaDB + OpenAI embeddings** store a pre-written pattern document per dealer. When the assistant asks for history, it retrieves that document semantically (filtered by `dealer_id`).

All proposed dates, LKR ceilings, CBSL holiday shifts, and usable funds still pass through **Python guardrails** — patterns are suggestions only.

---

## 3. Architecture diagrams

| Diagram | Open in browser (any browser) | GitHub copy (after push) | Local file |
|---------|------------------------------|---------------------------|------------|
| High-level domain map | [View image](https://mermaid.ink/img/pako:eNp1kstuwyAQRX8FsWqlpN1nUSmPRSMldVJH3tDKmuBJjITBgSFVFOXfaxurdVuVBTCHC5cZuHJpC-QTftD2Q5bgiO1mb4Y1zYf90UFdMn_SipCJdLtqR2-Dk8jsgZELVL5HdduWL5lQ5myVRD_A8-etkCWeAg7gdLVK5j3O-005aG0lkLKmV6Ipfl2mvlBpDRObONZAhM6wfVC6QDcwWGxEgaDR5b3GP9SXwXqWijNKsi73TYffi389OwETWSeP0Y_0XpP1VNzNS2crWMxYAQR78PgoO3L_77mgmJgFU2hljmzqvfIEhgZH75JkJY5IeZ9JqVpzJUE3SV0qNPSV3B-T-Gjj8VNTiYgWmy7M0hhmaRfG60cU5x1urXuYrNfLnZh3T8WkrSpF750megxVXwZ8xCt0FaiCT66cSqzaT1bgAYImfhtxCGTTi5F80vwiHPFQN2XDhYKmNFWEt09SUdg7) | [GitHub](https://raw.githubusercontent.com/ChamodiMadurasinghe/Zenith/main/docs/diagrams/vector/01-system-overview.jpg) | `docs/diagrams/vector/01-system-overview.jpg` |
| Business lifecycle | [View image](https://mermaid.ink/img/pako:eNpNkE1Lw0AQhv_KMOdEsF9CDoVCLwWRYNTL2sOYnZhgNlsns9bQ9r-bsg04t3keXt5hTlh6y5hh1fpjWZMoPD6_dzBOcW92ndIX7yFN11DMzBtLUw37m55FPDdboUrhI3S25UnOo1yYXPin4ePEF5EvzWvPAqV3rtF-kssoV2NRqV5AuBLu60mvon4wT_yrMB6r8B1Yhn-dd-n6vNmNQbI9HEiVpevPkG9eTB43UO_bMYEJOhZHjcXshFqzu37BckWhVbwkSEF9MXQlZiqBEwwHS8rbhj6FXISXP4oCZQ4) | [GitHub](https://raw.githubusercontent.com/ChamodiMadurasinghe/Zenith/main/docs/diagrams/vector/02-data-lifecycle.jpg) | `docs/diagrams/vector/02-data-lifecycle.jpg` |
| Guardrails boundary | [View image](https://mermaid.ink/img/pako:eNo1kN9rwkAMx_-VcM91e_dBcJuTgg-uRUE6Kbc21oPrXUlySrH-7ztrDQRC8sk3P26q8jWquTpZf63OmgQ22a-DaPvVZ7HHSjxBp0WQHB9hNlsMHJoGWYx3DN7ZfoBlWnwEV1vjGlgyGxbt5PiUWaZjU019ScGBeG95gO2hqDzh-9_U9tb1E789PHhYZxGwNs4vRwZLwxyQJ2qdjdQuLbaEF4PXGE6l3XNgYCTI9QUHyH82RXQjCJVvW_NaLeZGlWz1_bqU8ETI5wioRLVIrTa1mt-UnLF9vKnGkw5W1D1ROojPe1epuVDARIWu1oJfRjek22fy_g_eoXbZ) | [GitHub](https://raw.githubusercontent.com/ChamodiMadurasinghe/Zenith/main/docs/diagrams/vector/03-guardrails-boundary.jpg) | `docs/diagrams/vector/03-guardrails-boundary.jpg` |

## 4. How pattern documents are built

Implemented in [`core/dealer_patterns.py`](../core/dealer_patterns.py). Data comes from [`get_dealer_committed_payment_history()`](../db/repositories.py) (verified cheques only).

### Payment classification

| Type | Rule |
|------|------|
| **Bundled** | Cheque has **2+ distinct invoices** |
| **Unbundled** | Cheque has **exactly 1 invoice**, single part (`part_count == 1`) |
| **Split payment** | Same invoice appears on **2+ cheques** (via `cheque_invoice_allocation`) |

### Aging rules (important)

- **Formula:** `aging_days = clearance_date - invoiced_date`
- **Clearance date** (first match wins):
  1. `cheque.predicted_clearance_date`
  2. `deposit_timetable.target_funding_date`
  3. `cheque.cheque_date`

| History type | What appears in the document |
|--------------|------------------------------|
| Bundled | **Average aging** across all invoice rows in multi-invoice cheques |
| Unbundled | **Exact per-invoice lines** — never an average |
| Mixed | Both sections |
| Split parts | `Inv #101 (part 1/2): 35 days aging` |

### Example pattern document

```text
Dealer: ABD Traders (ID: 1)
Bundling History: mixed

Aging Analysis:
- Bundled Invoices Average Aging: 38 days (calculated across 4 multi-invoice cheques, 9 invoice rows).
- Unbundled Invoice Records: Inv #101 (21 days aging), Inv #104 (14 days aging).

Preferred Paying Account: Commercial Bank (Acc ID: 1) used for 12 out of 15 past cheques (80%).
Payment Pattern: Bills over 500k LKR are usually split into 2 parts with a 7-day clearance gap.
```

### Bundling behavior labels

| Label | Meaning |
|-------|---------|
| `frequently_bundled` | Only multi-invoice cheques in history |
| `paid_individually` | Only 1:1 invoice cheques |
| `mixed` | Both types present |
| `no_history` | No committed cheques yet |

### Split-pattern heuristic

When **≥2** historical examples match: invoice total ≥ `PATTERN_LARGE_BILL_LKR` (default 500,000), split across cheques with `part_count > 1`, the document adds a line like:

> Bills over 500k LKR are usually split into 2 parts with a 7-day clearance gap.

---

## 5. ChromaDB storage model

Implemented in [`core/vector_store.py`](../core/vector_store.py).

| Setting | Value |
|---------|-------|
| **Path** | `database/chroma/` (gitignored, persistent on disk) |
| **Collection** | `dealer_payment_patterns` |
| **Document ID** | `dealer-{dealer_id}` (one doc per dealer) |
| **Metadata** | `dealer_id`, `updated_at`, `bundling_behavior` |
| **Embeddings** | OpenAI `text-embedding-3-small` (configurable) |
| **Similarity** | Cosine (`hnsw:space: cosine`) |

### Upsert (write)

1. `build_dealer_pattern_document(dealer_id)` from SQLite history
2. Embed full text via OpenAI
3. `collection.upsert(...)` — replaces existing doc for that dealer

### Query (read)

1. Build query text: `"Dealer {id} payment history for invoice total {amount} LKR"`
2. Embed query
3. `collection.query(..., where={"dealer_id": dealer_id}, n_results=1)`
4. Return document text (fallback: rebuild live from SQLite if Chroma fails)

---

## 6. Configuration (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_VECTOR_PATTERNS` | `true` | Master switch |
| `CHROMA_PERSIST_DIR` | `database/chroma` | Chroma storage path |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `PATTERN_LARGE_BILL_LKR` | `500000` | Large-bill split heuristic |
| `OPENAI_API_KEY` | — | Required for embeddings |
| `USE_FAKE_AI` | `false` | Mock patterns; skips Chroma writes |

---

## 7. Setup and operations

### First-time setup

```bash
pip install -r requirements.txt
python scripts/backfill_dealer_patterns.py
```

### Automatic updates

After every successful cheque commit in [`routes/bundling.py`](../routes/bundling.py) `commit()`:

```python
threading.Thread(target=upsert_dealer_pattern, args=(dealer_id,), daemon=True).start()
```

### Manual rebuild

Re-run after bulk imports or if patterns look stale:

```bash
python scripts/backfill_dealer_patterns.py
```

---

## 8. How the AI uses patterns

| Component | Role |
|-----------|------|
| [`agents/bundling_tools.py`](../agents/bundling_tools.py) | Tool `get_dealer_historical_payment_patterns(invoice_total)` |
| [`agents/bundling_assistant.py`](../agents/bundling_assistant.py) | System prompt: call before recommendations; cite aging exactly |
| [`agents/mock.py`](../agents/mock.py) | Fake AI stub when `USE_FAKE_AI=true` |

The tool is **read-only** — it does not mutate bundles, session state, or SQLite.

### Example chat flow

1. User: “How did we usually pay ABD Traders?”
2. Assistant calls `get_dealer_historical_payment_patterns(invoice_total=...)`
3. Tool returns pattern text from ChromaDB
4. Assistant suggests a strategy in plain language
5. Assistant calls `compute_cheque_bundles(dry_run=True)`
6. `collect_bundle_issues` validates dates, ceiling, duplicates
7. User previews and clicks Save → SQLite commit → vector refresh

---

## 9. Guardrails boundary

See diagram: [03-guardrails-boundary.jpg](diagrams/vector/03-guardrails-boundary.jpg)

```
Vector patterns ──(suggestions only)──► Bundling Assistant
                                              │
                                              ▼
                                    dry_run mutating tools
                                              │
                                              ▼
                              core/bundling.py + guardrails.py
                                              │
                                              ▼
                                         Preview UI
                                              │
                              user Save ──────┘
                                              │
                                              ▼
                              SQLite commit → vector refresh
```

### Vector DB cannot

- Set cheque dates
- Override LKR ceiling
- Skip CBSL holiday logic
- Commit cheques without user approval
- Write to SQLite

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| “No historical payment patterns recorded…” | No committed cheques for dealer | Commit at least one cheque bundle |
| OpenAI / embedding error | Missing or invalid API key | Set `OPENAI_API_KEY` in `.env` |
| Patterns outdated | Commit happened before backfill | Run `python scripts/backfill_dealer_patterns.py` |
| Feature seems off | Disabled via env | Set `ENABLE_VECTOR_PATTERNS=true` |
| Mock text only | Demo mode | `USE_FAKE_AI=true` skips Chroma |
| Diagram image missing | File not pushed yet | Regenerate JPGs with `python scripts/generate_vector_docs_docx.py` or use mermaid.ink links in section 2 |

---

## 11. File reference

| File | Purpose |
|------|---------|
| `core/dealer_patterns.py` | Build pattern text + metadata from SQLite |
| `core/vector_store.py` | Chroma upsert, query, backfill |
| `db/repositories.py` | `get_dealer_committed_payment_history()` |
| `agents/bundling_tools.py` | LangChain tool wrapper |
| `agents/bundling_assistant.py` | System prompt guidance |
| `routes/bundling.py` | Post-commit background refresh |
| `scripts/backfill_dealer_patterns.py` | Initial / manual re-index |
| `core/tests/test_dealer_patterns.py` | Pattern builder tests |
| `core/tests/test_vector_store.py` | Vector store tests |
| `docs/diagrams/vector/*.jpg` | Architecture diagrams |

---

## 12. Related documentation

- [DATABASE.md](../database/DATABASE.md) — SQLite schema and derived vector index note
- Run `python scripts/generate_vector_docs_docx.py` for a shareable Word copy of this guide (local output, not committed)

Regenerate Word doc:

```bash
python scripts/generate_vector_docs_docx.py
```
