# Zenith on a shop PC

Zenith for a customer runs on **their Windows computer**. The database and invoice photos stay on that machine. The Render URL is only for the development team.

Until the single installer exists, a shop can run the app from this folder with desktop mode turned on.

## First launch

1. Install Python 3.11+.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and set:

   ```env
   ZENITH_DESKTOP=true
   ZENITH_PRODUCTION_INIT=true
   APP_PASSWORD=choose-a-password
   ```

4. `python app.py`
5. Open http://127.0.0.1:5000 and sign in.

The first database is a **shop** database: one login and the Pending Supplier row. It does not load the Yohan Hardware demo dealers or sample invoices.

Data files:

| Item | Location |
|------|----------|
| Database | `%LOCALAPPDATA%\Zenith\invoice_cheque.db` |
| Invoice photos | `%LOCALAPPDATA%\Zenith\invoices\` |
| Secrets from the setup guide | `%LOCALAPPDATA%\Zenith\.env` |
| Google Drive token | `%LOCALAPPDATA%\Zenith\mycreds.txt` |

`python scripts/init_db.py` **without** `--migrate` deletes the database. On a live shop, only use:

```text
python scripts/init_db.py --migrate
```

The app also runs migrations every time it starts, so a normal restart is enough after you copy in a new version of the code.

## Setup guide

The first time you sign in with desktop mode, Zenith opens a setup guide.

- Nothing in that guide is required for basic use (suppliers, typed invoices, cheques, bank balance, print).
- Gemini, OpenAI, WhatsApp, and Google Drive are optional. Each step has **Skip for now** and **Show me how to get this**.
- The same instructions are in [SETUP_GUIDES.md](SETUP_GUIDES.md) and inside the app at `/help/setup`.
- Settings → **Setup guide** opens the wizard again without deleting keys.

If Gemini is skipped, photo reading stays in demo mode until a key is added. A banner says so.

## Backup

Settings → **Backup to Google Drive** needs a passphrase and `mycreds.txt`. The passphrase cannot be recovered if it is forgotten. Skipping backup does not stop the app. Local files remain the real books.

## Cheque printing

Use the printer calibration screen in the app and a test print on the shop’s cheque paper before the first real cheque.

## Updates

The installed version is in `VERSION` and under Settings (“Version …”). `/health` returns the same version.

When `ZENITH_DESKTOP=true`, the app checks GitHub once a day (default 02:15 Asia/Colombo) for a newer **release tag**. If one exists, Settings shows “Update available”. It does **not** download or replace the app yet. Set `AUTO_UPDATE_CHECK=false` to turn the check off.

Publishing a version (for the team, before the installer):

1. Run the unit tests.
2. Bump `VERSION` and add a user-visible note to `CHANGELOG.md`.
3. Commit, tag `vX.Y.Z`, and push the tag.
4. Tell the shop what changed. They keep using the same data folder.

## Later: single installer (not built yet)

Do not bundle Zenith until the product work is finished. When that starts:

| Piece | Plan |
|-------|------|
| Bundle | PyInstaller: `app.py` and dependencies → `Zenith.exe` |
| Installer | Inno Setup: Program Files, shortcut, starts the local server and opens the browser |
| Apply update | Download the GitHub Release installer, check a SHA256, restart. Never overwrite `%LOCALAPPDATA%\Zenith\` |
| CI | The `v*` GitHub Action is a stub until this exists. It should then build the installer and attach it to the Release. |

## Support

The shop’s questions come to the four people who built Zenith. The preview site is not their support channel.
