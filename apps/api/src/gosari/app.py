"""Litestar 앱 팩토리 — SRS 모듈 경로 gosari.app:create_app."""

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from litestar import Litestar, Request, Response, Router
from litestar.config.compression import CompressionConfig
from litestar.exceptions import HTTPException, ValidationException
from litestar.openapi.config import OpenAPIConfig
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from gosari.api.analysis import AnalysisController, JobsController
from gosari.api.consent import ActionsController, ConsentsController
from gosari.api.evidence import EvidenceController
from gosari.api.health import CapabilitiesController, HealthController
from gosari.api.personal import NotebookController, RegionsController, ShareController
from gosari.api.sessions import SessionsController
from gosari.api.stations import MapsController, StationsController
from gosari.config import get_settings
from gosari.db import close_pool, open_pool
from gosari.domain.errors import GosariError
from gosari.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        open_pool(settings)
        logger.info("public DB pool opened")
    except Exception as exc:
        logger.warning("DB unavailable — limited mode", error_type=type(exc).__name__)
    yield
    close_pool()


def gosari_error_handler(
    request: Request[Any, Any, Any], exc: GosariError
) -> Response[dict[str, Any]]:
    return Response(
        exc.to_body(),
        status_code=exc.http_status,
        headers={"Cache-Control": "no-store"},
    )


def http_exception_handler(
    request: Request[Any, Any, Any], exc: HTTPException
) -> Response[dict[str, Any]]:
    if isinstance(exc, ValidationException):
        return Response(
            {
                "error": "INVALID_INPUT",
                "message": "입력 형식을 확인해 주세요.",
                "detail": exc.extra,
            },
            status_code=400,
        )
    return Response({"error": "HTTP_ERROR", "message": exc.detail}, status_code=exc.status_code)


def global_exception_handler(
    request: Request[Any, Any, Any], exc: Exception
) -> Response[dict[str, Any]]:
    logger.error(
        "unhandled exception",
        exc_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    return Response(
        {"error": "INTERNAL_ERROR", "message": "요청을 처리할 수 없습니다."},
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
    )


class SPAStaticMiddleware:
    """/api 경로는 Litestar로, 나머지는 정적 파일 + index.html 폴백으로 서빙한다.

    Litestar StaticFilesConfig의 catch-all이 파라미터 API 라우트를 가로채는 것을 피한다.
    경로 순회는 resolve 후 ui_dir 하위인지 검사하여 차단한다.
    """

    def __init__(self, app: ASGIApp, ui_dir: Path) -> None:
        self.app = app
        self.ui_dir = ui_dir

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or path.startswith("/api")
            or scope["method"] not in ("GET", "HEAD")
        ):
            await self.app(scope, receive, send)
            return
        relative = path.lstrip("/") or "index.html"
        candidate = (self.ui_dir / relative).resolve()
        if not candidate.is_relative_to(self.ui_dir.resolve()) or not candidate.is_file():
            candidate = self.ui_dir / "index.html"
        if not candidate.is_file():
            await self.app(scope, receive, send)
            return
        content = candidate.read_bytes()
        media_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        start: Message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", media_type.encode()),
                (b"content-length", str(len(content)).encode()),
                (
                    b"cache-control",
                    (
                        "no-cache"
                        if candidate.name == "index.html"
                        else "public, max-age=31536000, immutable"
                    ).encode(),
                ),
            ],
        }
        await send(start)
        body = cast(Message, {"type": "http.response.body", "body": content})
        await send(body)


def create_app() -> Litestar:
    route_handlers = [
        HealthController,
        CapabilitiesController,
        SessionsController,
        AnalysisController,
        JobsController,
        StationsController,
        MapsController,
        NotebookController,
        RegionsController,
        ShareController,
        ConsentsController,
        ActionsController,
        EvidenceController,
    ]
    ui_candidates = [
        Path("/app/web-dist"),
        Path(__file__).resolve().parents[4] / "apps" / "web" / "dist",
    ]
    ui_dir = next((p for p in ui_candidates if p.is_dir()), None)
    app = Litestar(
        route_handlers=[Router(path="/api/v1", route_handlers=route_handlers)],
        exception_handlers={
            GosariError: gosari_error_handler,
            HTTPException: http_exception_handler,
            Exception: global_exception_handler,
        },
        compression_config=CompressionConfig(backend="gzip"),
        openapi_config=OpenAPIConfig(title="고사리잇 API", version="0.1.0", path="/schema"),
        lifespan=[lifespan],
        request_max_body_size=1_000_000,
    )
    if ui_dir is not None:
        # Litestar 앱 미들웨어는 매칭된 라우트에만 적용되므로 ASGI 핸들러를 직접 래핑한다.
        app.asgi_handler = SPAStaticMiddleware(app.asgi_handler, ui_dir=ui_dir)
    return app
