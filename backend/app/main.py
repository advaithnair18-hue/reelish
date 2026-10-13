import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - registers tables on Base.metadata
from .config import settings
from .db import Base, engine
from .routers import auth, lists, recipes, videos

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fine for a portfolio project; swap for Alembic migrations once the schema settles.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Reel Groceries API", version="1.0.0", lifespan=lifespan,
              description="Turn recipe videos into a merged grocery list.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, videos.router, recipes.router, lists.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}
