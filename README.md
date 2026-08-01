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

## WhatsApp invoice agent (Meta Cloud API)

Cashiers can snap invoice/cheque photos on WhatsApp instead of using the web upload form. Default provider is **Meta WhatsApp Cloud API** (`WHATSAPP_PROVIDER=meta`).

1. Create a Meta app with WhatsApp → copy **Temporary/permanent access token** and **Phone number ID** into `.env`:
   - `META_WHATSAPP_TOKEN`
   - `META_PHONE_NUMBER_ID`
   - `META_VERIFY_TOKEN` (any secret string you choose)
2. Keep `USE_WHATSAPP_MOCK=true` for local testing; set a sample invoice at `MOCK_IMAGE_PATH=storage/invoices/your-sample.jpg`
3. Run the mock pipeline: `python whatsapp_agent.py` (prints the reply text)
4. Live webhook:
   - Run `python app.py` and expose with [ngrok](https://ngrok.com/) (`ngrok http 5000`)
   - In Meta → WhatsApp → Configuration, set callback URL to `https://YOUR-NGROK-HOST/webhook/whatsapp`
   - Use the same `META_VERIFY_TOKEN` for Verify Token
   - Subscribe to `messages`
5. Set `USE_WHATSAPP_MOCK=false` and optionally restrict senders with `WHATSAPP_ALLOWED_NUMBERS=+9477...`

Optional legacy Twilio: set `WHATSAPP_PROVIDER=twilio` and fill `TWILIO_*` vars.

The webhook downloads the image, runs Gemini extraction, computes CBSL holiday liquidity, replies on WhatsApp, and saves intakes as pending verification in the web app.

## Database

See [database/DATABASE.md](database/DATABASE.md) for full schema reference.

Rebuild anytime: `python scripts/init_db.py`

## Features

- **Login** — single-user password gate
- **Invoice upload** — Gemini vision extraction + human verification
- **Cheque bundling** — LKR ceiling grouping with guardrails + chat assistant
- **Cash flow** — when to deposit money into the bank
- **Analytics** — Agent 3 markdown reports after cheque commits
