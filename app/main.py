import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.routes import auth, user, routing, report, sos
from app.utils.logger import get_logger

# Import all models so SQLAlchemy registers them
import app.models.user  # noqa
import app.models.location  # noqa
import app.models.safety_report  # noqa
import app.models.route  # noqa

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    yield
    await engine.dispose()


app = FastAPI(
    title="SafeRoute API",
    description="Intelligent Safe Route Navigation System for Women and Vulnerable Groups",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        f"method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={duration_ms}"
    )
    return response


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred", "detail": None}},
    )


# --- Routers ---
PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(user.router, prefix=PREFIX)
app.include_router(routing.router, prefix=PREFIX)
app.include_router(report.router, prefix=PREFIX)
app.include_router(sos.router, prefix=PREFIX)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
