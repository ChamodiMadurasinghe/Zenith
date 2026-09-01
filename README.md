# Zenith

Local cheque & invoice management for Sri Lankan businesses. Python (Flask) backend with multi-provider AI:

- **Gemini** — invoice document check + OCR (Agent 1)
- **Bundling Assistant** — OpenAI + LangChain tool-calling over `core/bundling.py`
- **Analyst** — OpenAI reports
- **agentic/** pipeline — Agents 1–4 (Vision → Anomaly → Liquidity → Dealer liaison)

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env    # or cp on Linux/Mac
```

Edit `.env`:
- `APP_PASSWORD` — your login password
- `GEMINI_API_KEY` — invoice document verification + OCR
- `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN` — Meta WhatsApp Cloud API
- `OPENAI_API_KEY` — Bundling Assistant + analyst (optional)
- `USE_FAKE_AI=true` — demo mode (zero API quota while designing UI)

Initialize the database:

```bash
python scripts/init_db.py
```

## Run

**Terminal 1 — Python backend:**

```bash
python app.py
```

**Terminal 2 — public HTTPS tunnel (for Meta webhooks):**

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

Copy the `https://….trycloudflare.com` URL into Meta Developer Console → WhatsApp → Configuration → Webhook callback URL: `https://YOUR-TUNNEL/webhook/whatsapp`. Use the same `META_VERIFY_TOKEN` as in `.env`. Subscribe to `messages`.

Open http://127.0.0.1:5000 and sign in with `APP_PASSWORD`.

## WhatsApp invoice intake (Meta Cloud API)

1. Go to **Invoices → WhatsApp settings** and add supplier phone numbers to the whitelist.
2. Suppliers send invoice photos on WhatsApp to your Meta-linked business number.
3. Meta POSTs to `/webhook/whatsapp`; photos are saved to the **WhatsApp photos** inbox tab.
4. In the web app, open **Invoices → WhatsApp photos** and tap **Send to AI** when ready.
5. Gemini OCR runs; the invoice appears under **Waiting for User Approval** for human verify.

**Local mock (no Meta):** set `USE_WHATSAPP_MOCK=true` and `MOCK_IMAGE_PATH=path/to/test.jpg`, then run `python whatsapp_agent.py`.

**Optional dev bridge:** `whatsapp-bridge/` (Node.js) can POST to `/api/invoices/ingest` — not required for Meta production.

Probe webhook: `WEBHOOK_PUBLIC_URL=https://your-tunnel python scripts/probe_whatsapp_webhook.py`

## Database

See [database/DATABASE.md](database/DATABASE.md) for full schema reference.

Rebuild anytime: `python scripts/init_db.py`

## Features

- **Login** — single-user password gate
- **Invoice upload** — Gemini vision extraction + human verification
- **WhatsApp inbox** — Meta webhook intake, manual Send to AI, whitelist
- **Cheque bundling** — LKR ceiling grouping with guardrails + chat assistant
- **Cash flow** — when to deposit money into the bank
- **Analytics** — Agent 3 markdown reports after cheque commits
