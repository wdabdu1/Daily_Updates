import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import accounts, analysis, auth, dues, fx, home, receivables, settings
from .seed import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Treasury Dashboard API")

# In local dev the React app runs on its own Vite port and needs CORS; in
# production it's served by this same FastAPI process (see static mount
# below) so CORS is a non-issue there, but harmless to leave on.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(settings.router)
app.include_router(accounts.router)
app.include_router(dues.router)
app.include_router(receivables.router)
app.include_router(fx.router)
app.include_router(analysis.router)


@app.on_event("startup")
def on_startup():
    logger.info("Running database initialization / legacy migration...")
    init_db()
    logger.info("Database ready.")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the built React frontend, so this single service handles both the
# API and the UI on Railway. The build step (see frontend/README or the
# top-level Dockerfile) produces frontend/dist, copied here as ./static.
#
# React Router does client-side routing, so a hard load/refresh of e.g.
# /fx or /settings has no matching file on disk -- every non-API,
# non-asset path must fall back to index.html and let the client router
# take over from there.
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "static")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        candidate = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
else:
    logger.warning(
        "No built frontend found at %s -- API-only mode (fine for local backend dev).",
        FRONTEND_DIST,
    )
