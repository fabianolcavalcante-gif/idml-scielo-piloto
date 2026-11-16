import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from idml_foundation.ingest.safe_zip import UnsafeArchiveError
from idml_foundation.ingest.scanner import ScannerUnavailableError
from idml_foundation.logging_config import configure_logging
from idml_foundation.routers import (
    article_sources,
    artifacts,
    assistants,
    audit,
    auth,
    edit_evaluation_ui,
    edit_evaluations,
    health,
    jobs,
    organizations,
    releases,
    resources,
    reviews,
    source_access_ui,
    ui,
)
from idml_foundation.services.storage_budget import ArtifactStorageError
from idml_foundation.settings import get_settings

REQUESTS = Counter("idml_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "idml_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,100}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = supplied if CORRELATION_PATTERN.fullmatch(supplied) else str(uuid4())
        request.state.correlation_id = correlation_id
        started = time.monotonic()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        LATENCY.labels(request.method, route_path).observe(time.monotonic() - started)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
            if request.url.path.startswith("/app")
            else "default-src 'none'; frame-ancestors 'none'"
        )
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title="IDML Foundation API",
        version="0.1.0",
        docs_url="/docs" if settings.environment in {"development", "test"} else None,
        redoc_url=None,
    )
    application.add_middleware(RequestContextMiddleware)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(resources.router)
    application.include_router(article_sources.router)
    application.include_router(edit_evaluations.router)
    application.include_router(edit_evaluation_ui.router)
    application.include_router(source_access_ui.router)
    application.include_router(jobs.router)
    application.include_router(artifacts.router)
    application.include_router(organizations.router)
    application.include_router(reviews.router)
    application.include_router(releases.router)
    application.include_router(audit.router)
    application.include_router(assistants.router)
    application.include_router(ui.router)

    @application.exception_handler(UnsafeArchiveError)
    async def unsafe_archive_handler(request: Request, exc: UnsafeArchiveError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content={"detail": "unsafe IDML package", "code": exc.code},
        )

    @application.exception_handler(ScannerUnavailableError)
    async def scanner_unavailable_handler(
        request: Request, exc: ScannerUnavailableError
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=503,
            content={"detail": "content scanner unavailable", "code": "scanner_unavailable"},
        )

    @application.exception_handler(ArtifactStorageError)
    async def artifact_storage_handler(request: Request, exc: ArtifactStorageError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "artifact storage rejected operation", "code": exc.code},
            headers={"Retry-After": "5"} if exc.status_code == 503 else None,
        )

    return application


app = create_app()
