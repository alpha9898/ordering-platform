"""FastAPI application. All API routes live under /api."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import admin, auth, chat, dashboard, public, setup

settings = get_settings()

app = FastAPI(
    title="Ordering platform",
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

# Cookie-authenticated, state-changing requests must carry this header.
# Browsers cannot add custom headers cross-site without a CORS preflight
# (which we never allow), so this blocks CSRF from other origins.
CSRF_HEADER = "x-requested-with"
CSRF_PROTECTED = ("/api/dash", "/api/admin", "/api/auth", "/api/setup")


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith(CSRF_PROTECTED):
        if request.headers.get(CSRF_HEADER) != "fetch":
            return JSONResponse({"detail": "csrf_check_failed"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


for r in (auth.router, setup.router, public.router, chat.router, dashboard.router, admin.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# Optional: serve the built SPA when running as a single process (not on
# Vercel, where static files are served by the platform).
_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file = _DIST / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(_DIST / "index.html")
