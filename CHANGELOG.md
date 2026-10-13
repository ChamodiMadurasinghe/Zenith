# Changelog

User-visible changes. The copy on a shop PC shows the version in Settings and at `/health`.

## 1.0.0

- First version number for shop installs.
- Desktop mode stores the database, photos, and secrets under `%LOCALAPPDATA%\Zenith` so a later update does not wipe the shop’s data.
- A new shop database no longer starts with demo dealers or sample invoices.
- The app applies database migrations every time it starts.
- First-run setup guide: password, Gemini, OpenAI, WhatsApp, and Google Drive. Every integration can be skipped. Zenith still works without them.
- Once a day, a desktop install can check GitHub for a newer release and show “Update available”. It does not install the update yet.
- Render stays a team preview only.

## Note to send after a shop update

```text
Zenith updated to vX.Y.Z.
What changed: <one or two sentences from this file>
Your invoices and cheques are still on this computer. Sign in as usual.
If Settings says a newer version is available, that only means we published it. Installing it comes later with the Windows installer.
```
