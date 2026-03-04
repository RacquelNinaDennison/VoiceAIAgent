import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from loguru import logger as log
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        method = request.method

        path_qs = request.url.path
        if request.url.query:
            path_qs = f"{path_qs}?{request.url.query}"

        client = request.client
        client_addr = f"{client.host}:{client.port}" if client else "-"
        http_version = request.scope.get("http_version", "1.1")

        try:
            response = await call_next(request)
            status_code = response.status_code
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.info(
                f'{client_addr} - "{method} {path_qs} HTTP/{http_version}" '
                f"{status_code} in {duration_ms}ms"
            )
            return response
        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.error(
                f'{client_addr} - "{method} {path_qs} HTTP/{http_version}" '
                f"500 in {duration_ms}ms - Exception: {type(e).__name__}: {e}"
            )
            raise


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        level: int | str
        try:
            level = log.level(record.levelname).name
        except ValueError:
            level = record.levelno

        log.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_uvicorn_loggers() -> None:
    handler = InterceptHandler()
    logging.root.handlers = [handler]
    logging.root.setLevel(0)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(0)
        logger.propagate = False
