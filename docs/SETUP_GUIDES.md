# How to get optional keys

Zenith works without any of this. You can add suppliers, type invoices, bundle cheques, watch the bank balance, and print with nothing below filled in.

API keys, WhatsApp, and Google Drive only turn on extra features. Skip them until you are ready. You can reopen **Settings → Setup guide** later.

## Gemini (read invoice photos)

Not required. Without it, type the invoice by hand, or leave photo reading in demo mode.

You need a Google account. This takes a few minutes. Any billing is between you and Google.

1. Open [Google AI Studio API keys](https://aistudio.google.com/apikey).
2. Sign in with Google.
3. Click **Create API key** and copy the key.
4. Paste it into the setup guide (Gemini step) or add `GEMINI_API_KEY` to the desktop `.env`.

When a real key is saved, Zenith turns demo reading off (`USE_FAKE_AI=false`).

## OpenAI (cheque chat only)

Not required. Cheque bundling still runs without a chat assistant.

1. Open [OpenAI platform](https://platform.openai.com) and sign in or create an account.
2. Open **API keys**, click **Create new secret key**, and paste it into the setup guide.

The key is a secret. Do not send it in chat or email.

## WhatsApp

Not required. Uploading a photo in the app is enough. This is the hardest extra.

- Cloud API: a Meta business app, a phone number, and a public HTTPS address so Meta can reach this PC (often a tunnel). Tokens go in `.env` (`META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`). Then add supplier numbers under **WhatsApp settings** in the app.
- Local bridge: see `whatsapp-bridge/README.md`. The bridge is for development and a shop PC that keeps WhatsApp linked. It is still optional.

You can leave this until someone who has done the Meta or bridge setup is with you.

## Google Drive backup

Not required for daily work. Your database and photos stay on this PC either way. A backup is an extra copy off the computer.

1. Choose a **backup passphrase** you will remember. Zenith cannot recover it if you forget it.
2. In [Google Cloud Console](https://console.cloud.google.com/), create or pick a project, enable the **Google Drive API**, and create an OAuth client of type **Desktop**.
3. Sign in once with PyDrive2 so it writes a `mycreds.txt` file (the saved token, not your Google password).
4. Put that file in `%LOCALAPPDATA%\Zenith\mycreds.txt`, or choose it in the setup guide.
5. Later: **Settings → Backup to Google Drive**. Open Drive and search for `Zenith_Backup` to see the file.

The uploaded file is encrypted. You need the same passphrase to restore it.
