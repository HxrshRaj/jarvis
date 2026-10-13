import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import router
from app.config import get_settings
from app.db import session_factory
from app.llm.providers import get_provider
from app.services.engine import engine

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')


class RateLimiter:
    """Sliding-window limiter, in-process. Replace with Redis when running multiple workers."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_factory()  # lazy: creates the engine+tables once unless already initialised
    engine.recover_interrupted()
    yield
    engine.wait_idle(5)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="JARVIS API", version="0.1.0", lifespan=lifespan)
    app.state.limiter = RateLimiter()
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def limit_and_headers(request: Request, call_next):
        key = request.client.host if request.client else "unknown"
        if request.url.path.startswith("/api/") and not app.state.limiter.allow(key, get_settings().rate_limit_per_minute):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logging.getLogger("jarvis").exception("unhandled error")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)  # no internals leaked

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            with session_factory()() as db:
                db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        p = get_provider()
        return JSONResponse(
            {"database": db_ok, "llm_provider": p.name, "llm_is_real": p.is_real,
             "workspace": str(s.workspace_root)},
            status_code=200 if db_ok else 503,
        )

    app.include_router(router)
    return app


app = create_app()
