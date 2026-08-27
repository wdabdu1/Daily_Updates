import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError

from .routers import accounts, admin, analysis, auth, cash, dues, fx, home, receivables, settings
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
app.include_router(admin.router)
app.include_router(accounts.router)
app.include_router(dues.router)
app.include_router(receivables.router)
app.include_router(cash.router)
app.include_router(fx.router)
app.include_router(analysis.router)


# Every deliberate error in this app already goes out as an HTTPException
# with a clear `detail` string (handled by FastAPI's own default handler,
# untouched by this one -- it only matches exactly the base `Exception`
# type, and Starlette resolves HTTPException's own registered handler
# first). Without this, anything unanticipated -- a DB constraint the code
# didn't check for, a bad cast, whatever -- fell through to Starlette's
# bare-bones default: a 21-byte "Internal Server Error" plain-text body with
# no detail at all, which cost real time to diagnose (a numeric-overflow
# bug this app hit in production looked identical to a network timeout from
# the client's side until the raw response headers were captured directly).
# The full traceback still goes to the server log either way; this just
# also puts the exception's own message in front of whoever hit it, so the
# next time something like this happens the real cause is visible on the
# first report instead of requiring a live repro session to track down.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    # A bare str(exc) on a SQLAlchemy DBAPIError includes the full SQL
    # statement and every bound parameter value -- useful in the server log
    # (still captured above via logger.exception) but far more than
    # belongs in a message echoed back to the browser. exc.orig is just the
    # underlying database driver's own error text (e.g. "numeric field
    # overflow"), which is exactly the useful part.
    message = str(exc.orig) if isinstance(exc, DBAPIError) and exc.orig is not None else str(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Unexpected server error ({type(exc).__name__}): {message}"},
    )


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
