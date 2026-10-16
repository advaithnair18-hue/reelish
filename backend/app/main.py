import logging
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from . import models  # noqa: F401 - registers tables on Base.metadata
from .config import settings
from .db import Base, engine
from .routers import auth, lists, recipes, shortcut, videos

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fine for a portfolio project; swap for Alembic migrations once the schema settles.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Reelish API", version="1.0.0", lifespan=lifespan,
              description="Turn recipe videos into a merged grocery list.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, videos.router, recipes.router, lists.router, shortcut.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def public_config():
    """Settings the app reads at runtime, so they can change without rebuilding it."""
    return {"shortcut_url": settings.shortcut_url}


# ---------------------------------------------------------------- the web app
# In production one service serves both the API and the built app (frontend/dist),
# so there's one address to deploy, install and point the iPhone shortcut at.

@app.post("/share-target", include_in_schema=False)
async def share_target_fallback(request: Request):
    """Normally the app's service worker catches shares. If it isn't running yet (the very
    first share after installing), pass the shared link along to the share screen."""
    form = await request.form()
    params = {k: str(form.get(k) or "") for k in ("title", "text", "url")}
    return RedirectResponse("/share?" + urlencode({k: v for k, v in params.items() if v}), status_code=303)


if settings.static_dir and (settings.static_dir / "index.html").is_file():
    STATIC = settings.static_dir.resolve()
    NO_CACHE = {"Cache-Control": "no-cache"}

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file = (STATIC / path).resolve()
        if path and file.is_file() and STATIC in file.parents:
            if path.startswith("assets/"):  # content-hashed by Vite, safe to cache forever
                return FileResponse(file, headers={"Cache-Control": "public, max-age=31536000, immutable"})
            media = "application/manifest+json" if file.suffix == ".webmanifest" else None
            return FileResponse(file, media_type=media, headers=NO_CACHE)
        # Any other path is a screen in the app (/list, /recipes/3...): serve the app shell.
        return FileResponse(STATIC / "index.html", headers=NO_CACHE)
