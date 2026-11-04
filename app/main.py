"""Virasat Atlas application entry point."""
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import BASE_DIR, settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.routes import auth, entries, meta, ocr, search, sites, tag, trails, user
from app.services.search_index import rebuild_from_db
from app.utils.logger import get_logger

logger = get_logger("main")

VERSION = "1.0.0"
PREFIX = "/api/v1"
FRONTEND_DIR = BASE_DIR / "frontend"
# The exact 8 MB image check happens on the file itself; this allows for multipart overhead.
BODY_LIMIT_BYTES = settings.max_upload_bytes + 1024 * 1024

Path(settings.MEDIA_DIR).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create tables and build the search index before serving."""
    await init_db()
    async with AsyncSessionLocal() as db:
        await rebuild_from_db(db)
    logger.info("startup_complete")
    yield
    from app.db.session import engine

    await engine.dispose()


app = FastAPI(
    title="Virasat Atlas API",
    description="Turns unstructured heritage field documentation into a searchable map of Gujarat.",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


def _error(status: int, code: str, message: str, detail: object = None) -> JSONResponse:
    """Build the one error envelope used by every endpoint."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Reject oversized bodies early, log each request and set safety headers."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > BODY_LIMIT_BYTES:
        return _error(413, "PAYLOAD_TOO_LARGE", f"Upload limit is {settings.MAX_UPLOAD_MB} MB")

    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        f"method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={duration_ms}"
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only these keys: raw pydantic errors can contain objects JSON cannot serialise.
    detail = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return _error(422, "VALIDATION_ERROR", "Request validation failed", detail)


@app.exception_handler(StarletteHTTPException)
async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {
        400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
        409: "CONFLICT", 413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR", 501: "NOT_IMPLEMENTED",
    }
    return _error(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error(f"unhandled_exception: {exc}", exc_info=exc)
    return _error(500, "INTERNAL_ERROR", "An internal error occurred")


@app.get("/health", tags=["health"])
@app.get(f"{PREFIX}/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": VERSION}


for module in (auth, user, sites, entries, tag, search, trails, ocr, meta):
    app.include_router(module.router, prefix=PREFIX)

app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")
# Must stay last: a mount at "/" would otherwise swallow the API routes.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
