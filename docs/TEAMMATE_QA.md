# Teammate QA playbook

Unit-test-style cases for the shop: suppliers, three invoice intake paths, Agent 1, WhatsApp, verify, Agent 2, bank accounts, **per-account cheque ceiling**, and 3-way cheque splits.

Source of truth for this checklist. The Agent Testing Guide PDF (`docs/Agent_Testing_Guide.pdf`) repeats the same chapters.

## Setup (all live cases)

| Item | Value |
|------|--------|
| App | `http://127.0.0.1:5000` |
| Start | `python app.py` |
| Login | seed merchant `yohan@hardware.lk` / `APP_PASSWORD` from `.env` |
| Samples | [docs/agent_test_samples/](agent_test_samples/) (`01`–`15`) |
| Database | Keep the live DB. **Do not** reset. |

Use unique invoice numbers `QA-YYYYMMDD-xx` so duplicate checks do not collide with earlier runs.

After commit, you can sanity-check SQLite with:

```text
python scripts/check_cheques_saved.py
```

### What Agent 1 actually is

One function: `extract_invoice(image_path)` in `agents/ingestion.py`. Gemini vision (or `USE_FAKE_AI` mock) returns JSON: invoice_no, supplier_name, date, total, credit_period_days, supplier contact/bank footer, line items.

Related (not extra Agent 1 functions):

- WhatsApp-web only: `classify_document` in `agents/document_classifier.py`
- Normalize: `core/ingestion_helpers.py`, `core/whatsapp_intake.py`
- Unmatched web upload: OpenAI `suggest_dealer_setup` (defaults for the new-dealer form)

**OCR never inserts a `dealers` row.** Unknown names match by substring, or park on **Pending Supplier** until a human adds the dealer.

### What Agent 2 actually is

Python rules in `agents/anomaly.py` (`audit_invoice` / `check_invoice_anomalies`). Not the bundling chat (that is the Cheque Assistant).

| Code | What it checks | Blocking save? |
|------|----------------|-----------------|
| `math_mismatch` | Line math vs header total | No (confirm) |
| `possible_missing_discount` | Discount on lines but header looks undiscounted | No |
| `bad_date` / `future_date` / `stale_date` | Invalid, >30 days ahead, >365 days old | No |
| `missing_amount` | Total 0 / empty | No |
| `unknown_dealer` | Pending Supplier / unmatched | No |
| `duplicate_invoice_no` | Same number for that dealer | **Yes** |
| `amount_outlier` | >3× dealer average after 3 invoices | No |
| `item_price_spike` | >2× item history | No |
| `qty_unusual` | Qty ≥2× typical | No |
| `item_reordered_soon` | Same item within 30 days | No |

Panel: `templates/_agent2_audit_card.html`. Status `GOOD_TO_GO` / `ISSUE_DETECTED` / `INSUFFICIENT_DATA`. Soft findings never disable Save; duplicate number does.

### Invoice intake — three shop ways

| Way | Route | Agent 1? | Lands as |
|------|--------|----------|----------|
| Web upload | `POST /upload` → `/review/<draft>` | Yes, immediately | Session draft, then verified insert |
| WhatsApp Meta inbox-v2 | Photo → inbox → **Send to AI** `POST /whatsapp-inbox/<id>/extract` | Only after Send to AI | Pending invoice → `/invoice/<id>/verify` |
| Manual | `/invoice/manual` | No | Verified immediately |

Optional fourth (local Node bridge): `POST /api/invoices/ingest` auto-classifies + OCR. This playbook covers health + settings; live Meta send only if the tunnel is up.

---

## A. Supplier

### TC-S1 Add supplier (full form)

- **Given** you are logged in.
- **When** you open `/dealers/new` and save name `QA City Mart`, supplier bank `City Mart Current` / Commercial Bank, paying account = Main Hardware Checking.
- **Then** the dealer appears in the supplier list; a `dealers_bank_account` row is saved for that dealer.
- **SQL / UI:** Cheques tab for that dealer lists the paying account as Main.

### TC-S2 Quick-add

- **Given** you are on verify or manual invoice.
- **When** you quick-add name `QA Quick Dealer`.
- **Then** the dealer is created and selected.
- **When** you quick-add the exact same name again.
- **Then** the existing dealer is reused (`reused: true`); no second row.

### TC-S3 Auto-match (not auto-create)

- **Given** no dealer named City Mart (skip if TC-S1 already created it — use a unique OCR name, or do this before TC-S1).
- **When** you upload `01_clean_invoice.png` (supplier City Mart).
- **Then** you get the new-dealer form with OCR fields filled. No `dealers` insert yet.
- **Given** TC-S1 is done (City Mart exists).
- **When** you re-upload a *new* invoice number with the same supplier photo.
- **Then** the dealer dropdown is already selected (substring match).
- **When** WhatsApp OCR returns an unknown supplier.
- **Then** the invoice parks on **Pending Supplier** until the verify form creates the dealer.

---

## B. Invoice — three ways

Use unique numbers such as `QA-20260909-01`.

### TC-I1 Web upload

- **Given** sample `01_clean_invoice.png`.
- **When** you upload from Invoices → review → confirm matches → Save.
- **Then** Agent 1 filled fields; invoice is verified (`is_invoice_verified = 1`), `cheque_id` is NULL.

### TC-I2 Manual

- **Given** `/invoice/manual`.
- **When** you pick ABD Traders, invoice no `QA-MAN-001`, total `15000`, one line item, save.
- **Then** saved verified without OCR.

### TC-I3 WhatsApp

- **Given** `GET /webhook/whatsapp/health`.
- **Then** `inbox-v2`, `gemini_on_whatsapp_receive: false`.
- **When** Settings → add an allowed sender if missing.
- **If Meta/tunnel is up:** send a photo → Invoices → WhatsApp photos → **Send to AI** (OCR now) → verify.
- **If not:** run existing webhook/inbox unit tests and mark live send **N/A**.

---

## C. Agent 1 (every extraction capability)

Use samples. **Then** = field present on review/verify (or fake-AI mock if `USE_FAKE_AI`).

| ID | Sample / setup | Expect |
|----|----------------|--------|
| A1-clean | `01_clean_invoice.png` | Invoice no, supplier, date, total, lines |
| A1-messy | `05_messy_handwritten_style.png` | Best-effort fields; not blank crash |
| A1-glare | `15_phone_photo_glare.png` | Best-effort; still opens review |
| A1-bank | `12_supplier_bank_footer.png` | Supplier bank fields filled |
| A1-credit | `13_credit_period.png` | `credit_period_days` = 45 |
| A1-missing | `09_missing_amount.png` | Total 0 + Agent 2 `missing_amount` |
| A1-pdf | Non-image PDF | Rejected (not treated as invoice photo) |
| A1-fake | `USE_FAKE_AI=true` | Mock `WA-MOCK-001` / 125000 |

---

## D. Verify

- Confirm-matches is required before Save.
- Edit a wrong OCR total, save → DB has the **edited** total.
- Pending dealer: Save disabled until a dealer is created.
- Duplicate `invoice_no` for the same dealer is blocked.
- After save: `is_invoice_verified=1`, `pending_dealer_json` NULL, line items replaced.

Quick path (seed, if still pending): Future Tech `INV-FT-2025-003` (1,471,000) and X Suppliers `INV-XS-2025-005`. If those were already verified/committed on this DB, use a new `QA-…` invoice instead.

---

## E. Agent 2 (every check)

| Case | Dummy | Expect finding |
|------|--------|----------------|
| Math | `02_math_mismatch.png` | `math_mismatch` |
| Discount | `03_missing_discount.png` | `possible_missing_discount` |
| Qty | `04_qty_unusual_toffees.png` after a prior TOFFEE-01 qty 10 | `qty_unusual` |
| Future date | `06_future_date.png` | `future_date` |
| Price spike | `07_price_spike.png` after cheaper TOFFEE history | `item_price_spike` |
| Outlier | `08_amount_outlier.png` | `amount_outlier` if dealer has 3+ smaller invoices |
| Missing amount | `09` | `missing_amount` |
| Duplicate | verify same no twice | blocked |
| Unknown dealer | `09` / Pending Supplier | `unknown_dealer` |
| Reorder | same item twice within 30 days | `item_reordered_soon` |
| Clean | `01` on new dealer | `INSUFFICIENT_DATA` or `GOOD_TO_GO` |

Save still works on non-blocking warnings if confirm matches is ticked.

---

## F. Bank updates + ceiling + listing

Ceiling lives on **each paying bank account** (`user_bank_account.ceiling_lkr`). The dealer Cheques tab working cap prefills from that dealer’s paying account and **cannot exceed** it. At commit, the form’s paying account is the source of truth: any cheque over that account’s ceiling is rejected.

Fresh seed (new DB only): Main **500000**, Reserve **250000**. Live DBs that already existed keep 500000 until you edit them.

### TC-B1 Edit Main

- **Given** Cash Flow → Main Hardware Checking → Details.
- **When** you change nickname / balance / overdraft and save.
- **Then** reload shows the new values.

### TC-B2 Deposits

- **When** you record a deposit, then a planned deposit, then mark planned complete.
- **Then** available balance increases by those amounts.

### TC-B3 Default account

- **When** you set Reserve as default, then back to Main.
- **Then** the default badge follows the last save.

### TC-B4 Set ceilings

- **When** you set Main ceiling **500000**, Reserve **200000**; save; reload Details.
- **Then** each account shows its own max. Cash Flow hub cards also show the ceiling.

### TC-B5 Ceiling blocks Reserve, allows Main

- **Given** a verified unpaid invoice of about **300000** (manual `QA-CEIL-300` is enough). Reserve ceiling is **200000**.
- **When** you bundle one cheque of 300000 and preview/commit paying from **Reserve**.
- **Then** commit is **blocked** (over 200k). Preview shows a ceiling warning on Reserve.
- **When** you commit the same cheque from **Main** (ceiling 500000).
- **Then** it is **allowed**.

### TC-B6 Written cheques list by account

- **Given** TC-B5 committed on Main.
- **When** you open Cash Flow → that account → timetable / written cheques.
- **Then** the new cheque(s) appear **only** on that account, not on Reserve. The dealer Cheques tab still shows them for the dealer.

---

## G. 3-way split + data save

- **Given** a large unpaid verified invoice (Future Tech 1.47M if still unpaid, or a 600000 dummy).
- **When** you right-click split into **3** separate cheques; amounts sum to the original.
- **When** you preview with paying account + cheque nos `QA-CH-1/2/3` and commit.
- **Then** SQL:
  - 3 `cheque` rows
  - 3 allocations `part_index` 1..3, `part_count=3`, summing to invoice total
  - `invoices.cheque_id` = first cheque
  - 3 `deposit_timetable` pending rows
  - bundle draft gone
- Print PDF for one cheque (no extra DB write).

---

## Automated tests (no live Gemini / Meta)

```text
python -m unittest discover -s agents/tests -q
python -m unittest discover -s core/tests -q
python -m unittest discover -s routes/tests -q
```

(`pytest` is not required. Agentic tests that import pytest may fail if it is not installed.)

Covers: Agent 1 fake-AI mock, classifier reject, Agent 2 codes, `make_split_parts` 3-way, strategist 3-way allocate, `save_cheques` 3-way, bank `ceiling_lkr` validation, commit reject over account ceiling. WhatsApp unit tests remain the no-Meta proof.
