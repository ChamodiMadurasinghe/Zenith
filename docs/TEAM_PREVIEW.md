# Team preview (Render)

Render is only for the four people building Zenith. It is the competition demo host. Customers do not use this URL, and you should not put a real shop’s invoices here.

## How everyone sees the same app

1. The GitHub repo stays connected to the Render web service (`render.yaml`).
2. Turn **Auto-Deploy** on for `main` (or the branch you agreed on).
3. Anyone pushes to that branch. Render rebuilds in a few minutes.
4. Open the same preview URL. You do not need Python on your laptop to look at that copy.

`USE_FAKE_AI=true` in `render.yaml` is fine for the shared preview. Use a real Gemini key only when you are testing photo reading on purpose.

## What not to do

- Do not treat the preview database as a customer’s books. The Render disk can be wiped, and the preview may still seed demo data when `ZENITH_DESKTOP` and `ZENITH_PRODUCTION_INIT` are off.
- Do not turn on the first-run wizard for judges (`ZENITH_SHOW_ONBOARDING` stays unset or `false`) unless you are testing the wizard itself.
- Customer data belongs on their PC. See [DESKTOP_INSTALL.md](DESKTOP_INSTALL.md).

## Who can change the preview

Whoever has the Render dashboard can see logs, env vars, and the deploy history. API keys for the preview live in the Render dashboard, not in git.
