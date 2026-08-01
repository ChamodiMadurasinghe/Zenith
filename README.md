# Zenith

Local cheque & invoice management for Sri Lankan businesses. Python (Flask) backend with multi-provider AI: Gemini Flash for invoice vision (Agent 1), OpenAI gpt-3.5-turbo for bundling chat (Agent 2) and analytics (Agent 3).

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env    # or cp on Linux/Mac
```

Edit `.env`:
- `APP_PASSWORD` — your login password
- `GEMINI_API_KEY` + `GEMINI_VISION_MODEL` — Agent 1 invoice upload (vision)
- `OPENAI_API_KEY` + `OPENAI_CHAT_MODEL` / `OPENAI_ANALYST_MODEL` — Agent 2 chat + Agent 3 reports
- `USE_FAKE_AI=true` — demo chat mode (zero API quota while designing UI)

Initialize the database:

```bash
python scripts/init_db.py
```

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000 and sign in with `APP_PASSWORD`.

## WhatsApp invoice agent (Twilio)

Cashiers can snap invoice/cheque photos on WhatsApp instead of using the web upload form.

1. Add Twilio credentials to `.env` (see `.env.example`): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
2. Keep `USE_TWILIO_MOCK=true` for local testing; set a real invoice image at `MOCK_IMAGE_PATH=storage/invoices/your-sample.jpg`
3. Run the mock pipeline: `python whatsapp_agent.py` (prints TwiML reply to the terminal)
4. For live Twilio sandbox: run `python app.py`, expose port 5000 with [ngrok](https://ngrok.com/) (`ngrok http 5000`), and set the webhook URL in Twilio Console → WhatsApp Sandbox → **When a message comes in** to `https://YOUR-NGROK-HOST/webhook/whatsapp`
5. Set `USE_TWILIO_MOCK=false` and optionally restrict senders with `WHATSAPP_ALLOWED_NUMBERS=whatsapp:+94...`

The webhook downloads the image, runs Gemini extraction, computes CBSL holiday liquidity, replies on WhatsApp, and saves matched suppliers as pending verification in the web app.

## Database

See [database/DATABASE.md](database/DATABASE.md) for full schema reference.

Rebuild anytime: `python scripts/init_db.py`

## Features

- **Login** — single-user password gate
- **Invoice upload** — Gemini vision extraction + human verification
- **Cheque bundling** — LKR ceiling grouping with guardrails + chat assistant
- **Cash flow** — when to deposit money into the bank
- **Analytics** — Agent 3 markdown reports after cheque commits
