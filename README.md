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

One migration caveat: existing user passwords were unsalted SHA256 and can't be converted to the new bcrypt scheme. Every migrated user (other than a freshly-seeded default admin) will need a password reset from Settings > User Management before they can log in again.

## Fixed from the old app
- The old app reset the `admin` password to `admin123` on *every* restart/deploy, silently reverting any password change in production. The new app only seeds a default admin the very first time the `users` table is empty.
- Passwords are now bcrypt-hashed instead of unsalted SHA256.

## Project status: Phase 1 of 5

Built so far: project skeleton, auth (JWT, 3 roles: Manager / ReadWrite / ReadOnly), the Bosch-inspired top nav (Home | Analysis | Bank Dues | FX | Settings), the legacy-data migration path, and the Home dashboard (today's Receivables vs. active Bank Dues, gap in SDG and USD-equivalent, and a Business Unit / Division / Bank drill-down to spot cross-subsidy between units). Analysis, Bank Dues, FX, and Settings pages are routed and role-gated but still placeholders — see the in-app "Coming in Phase N" notes.

Next: Phase 2 (FX rate entry, carry-forward table, current/prior-month view), Phase 3 (Bank Dues registration + the Update Today's Receivables workflow), Phase 4 (Analysis: FX trend + Cover drill-down with filters), Phase 5 (Settings: BU/Division/Bank/Currency/User management).
