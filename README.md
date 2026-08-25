# Treasury Dashboard

Rebuild of the Corporate Treasury Portal: FastAPI (Python) + SQLAlchemy + Postgres backend, React + TypeScript frontend, deployed as a single Railway service (FastAPI serves the built React app).

## Uploading this to GitHub

If you're adding these files through GitHub's web UI rather than `git push`:

1. Go to your repo on github.com, click **Add file → Upload files**.
2. Drag the *contents* of this folder in (drag the `backend`, `frontend`, `Dockerfile`, `.gitignore`, and `README.md` items together — not this folder itself — so they land at the repo root, not nested one level deep).
3. **Do not upload** `backend/.venv/`, `backend/static/`, `backend/local_dev.db`, or `frontend/node_modules/` / `frontend/dist/` if you happened to generate them locally — these are build artifacts/dependencies, not source, and are already listed in `.gitignore` for when you do use real git.
4. Commit directly to `main` (or open a PR if you prefer to review the diff against the old single-file app first).

## Local development

Backend:
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8501
```
Without a `DATABASE_URL` set, it falls back to a local SQLite file (`backend/local_dev.db`) so you can run it without Postgres. Optionally seed a few demo rows: `python -m app.seed_demo` (from `backend/`, venv active).

Frontend (separate dev server, hot reload):
```
cd frontend
cp .env.example .env.local   # points VITE_API_BASE at the backend above
npm install
npm run dev
```

Production-style single-process run (what Railway actually runs):
```
docker build -t treasury-dashboard .
docker run -p 8501:8501 -e DATABASE_URL=... -e JWT_SECRET=... treasury-dashboard
```

## Railway deployment

This repo has one top-level `Dockerfile` (multi-stage: builds the React app, then copies it into the FastAPI image). Point your Railway service at the repo root — no change needed to how Railway already builds this project, it'll pick up the new Dockerfile automatically.

Environment variables to set in Railway:
- `DATABASE_URL` — already set from your existing Postgres plugin, no change needed.
- `JWT_SECRET` — **set this explicitly** to a long random string. If left unset it falls back to an insecure default, which is fine for local dev but must not be used in production.
- `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD` — optional, only used the very first time the `users` table is created (default `admin` / `admin123`). Change the password immediately after first login via Settings > User Management.

## What happens to your existing data on first deploy

On startup, the app inspects the database. If it finds the *old* app's tables, it automatically migrates what it can into the new schema (see `backend/app/migrate_legacy.py` for the exact mapping) and renames anything it can't safely reshape to `<table>_legacy` rather than deleting it. If the database is empty, it just creates the new schema fresh. Either way this is safe to deploy directly onto your existing Railway Postgres.

One migration caveat: existing user passwords were unsalted SHA256 and can't be converted to the new bcrypt scheme, so any migrated user's password is reset to the bootstrap default (`admin`/`admin123` unless you changed `DEFAULT_ADMIN_PASSWORD`) instead of being left unusable. **Change this immediately after logging in** — everyone migrated currently shares the same known password, and there's no self-service password change yet (planned for the full Settings page).

Another migration fix worth knowing about: your old accounts were carried over with their original IDs so existing dues/receivables kept pointing at the right account. On Postgres, that meant the database's internal "next ID" counter for new accounts wasn't updated to account for that — so the very first *new* account created afterwards (e.g. from typing a Business Unit/Division that isn't in the system yet during a Bank Dues import) could collide with an already-migrated one and fail. This deploy fixes that counter automatically on startup; nothing you need to do.

## Fixed from the old app
- The old app reset the `admin` password to `admin123` on *every* restart/deploy, silently reverting any password change in production. The new app only resets a password when the migrated hash genuinely can't be verified (not bcrypt-shaped) — a real password, once set, survives restarts.
- Passwords are now bcrypt-hashed instead of unsalted SHA256.

## Data entry: Excel import (Bank Dues & FX Rates)

Both the **FX** and **Bank Dues** pages have a "Download Template" button (an .xlsx with example rows and a Notes sheet explaining the columns) and an upload control next to it.

- **FX import**: rows are Date / Base Currency / Quote Currency / Rate Type (Market, CBOS, or Pricing) / Rate. Unknown currency pairs are created automatically; CBOS/Pricing are only accepted for a pair where SDG is one side. Re-uploading a row for a Date + Pair + Rate Type that already exists **updates** that rate rather than duplicating it — this is how you replace test data with final figures.
- **Bank Dues import**: rows carry the full account chain (Business Unit / Division / Bank Short Name / Bank Full Name / Account Name / Account Number / Currency) plus the due itself (Due Date / Facility Type / Amount / Status). Any Business Unit, Division, Bank, or Account referenced that doesn't exist yet is created automatically from the row — you don't need to set these up first. Re-uploading the same account + due date + facility type updates the amount/status instead of duplicating.
- **Today's Receivables**: not an Excel import — it's an interactive workflow on the Bank Dues page ("Start Update"), since it's meant to be a quick daily habit: every account shows up prefilled with its last recorded amount, you adjust what changed, and save. This is what feeds the Home page's coverage comparison, so you'll want to use it (or at least save it once) alongside uploading dues to see meaningful Home/Analysis results.
- Number columns (**Rate**, **Amount**) accept plain numbers or thousands-separator-formatted ones — `3610`, `3,610`, and `3,610.00` all work. Just don't include a currency symbol.
- Date columns (**Date**, **Due Date**): if you extend a template by selecting a date cell and dragging Excel's fill handle down, make sure that column is formatted as an actual **Date** (not stored as text) first — Excel only rolls a real date correctly from month to month (Aug 31 → Sep 1). If the column is text, the fill handle just increments the trailing number and produces invalid dates like `2026-08-32`, which the import will reject with a clear per-row error rather than guessing what you meant.

## Settings: Business Units, Divisions, Banks, Currencies, Currency Pairs, Users

Settings (Manager only) now has a real management UI instead of relying only on Excel imports to create these implicitly:

- **Business Units** and **Divisions** (a division belongs to one business unit) — add and view.
- **Banks** — short name + full name.
- **Currencies** — a simple code list (AED, USD, SDG, etc.) plus **Currency Pairs**, which control which rate types a pair tracks (any pair with SDG on one side automatically gets Market + CBOS + Pricing; everything else just gets Market).
- **Users** — add a user with a role (Manager/ReadWrite/ReadOnly), and reset any user's password (this is also how you get a migrated legacy user, or anyone who forgot their password, back into the system).

The Excel imports on the FX Rates and Bank Dues pages still auto-create anything you leave out, so you don't have to predefine everything here before importing — but doing so up front avoids near-duplicate BU/Division names from typos across different uploads.

## Wiping test data

Settings has a "Danger Zone" (Manager only): pick a scope (**Transactions only** — Bank Dues, Receivables, FX Rates; or **Everything** — also Business Units, Divisions, Banks, Master Accounts), type `WIPE` to confirm, and clear it. Users and the base currency list are never touched by either scope. Use this once you're done testing and ready to load final figures.

## Project status: Phases 1–5 in place; FX multi-currency view design in progress

Built: project skeleton, auth (JWT, 3 roles), the Bosch-inspired top nav, the legacy-data migration path (with the lockout and sequence-desync fixes above), the Home dashboard (coverage gap in SDG + USD-equivalent, BU/Division/Bank cross-subsidy breakdown), the FX Rates page (import + current/prior-month carry-forward table), the Bank Dues page (import + settle + the Today's Receivables workflow), the Analysis page (Cover Analysis trend with BU/Division/Bank/Period filters, FX Analysis comparing Market/CBOS/Pricing over a period), and the Settings management UI described above.

Still to come: table filter/sort UI (@tanstack/react-table is installed but not wired in yet), and a bigger FX redesign currently being scoped with the user — a combined Market/CBOS/Pricing table across a full year of dates, viewable in either AED or USD (with USD computed on the fly from AED + the latest USD/AED rate when no direct USD rate was uploaded), and a selectable display currency on the Home page.
