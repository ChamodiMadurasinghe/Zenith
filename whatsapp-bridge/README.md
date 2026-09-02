# Zenith WhatsApp Bridge

Local [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) bridge for invoice photo intake.

## Setup

Requires **Node 18–22**. Node 24 breaks media download — `npm start` will refuse to run on Node 24+.

Install Node 20 LTS from https://nodejs.org (you can keep Node 24 installed; switch versions in a new terminal after installing 20).

```bash
npm install
npm start
```

Scan the QR code on first run (WhatsApp → Linked devices). Configuration is loaded from the project root `.env` via `src/loadEnv.js`.

## Photo received test reply

For testing that photos reach the bridge and Flask ingest API, the bridge can auto-reply with a short text message after a successful ingest HTTP response.

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_PHOTO_ACK` | `true` | Set `false` to disable auto-replies |
| `WHATSAPP_PHOTO_ACK_MESSAGE` | `Photo received (Zenith test).` | Text sent via `msg.reply()` |

Example log when working:

```
[bridge] ingested true_...@c.us -> processed
[bridge] photo ack sent to +9477... -> processed
```

## Endpoints

- `GET http://127.0.0.1:3001/health` — bridge health (after `ready`)
- `POST http://127.0.0.1:3001/api/send` — outbound text (used by cash alerts)
- Ingest is pushed to Flask `POST /api/invoices/ingest` (see root `.env`)
