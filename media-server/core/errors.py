"""统一异常处理。

定义通用异常并注册到 FastAPI 应用，以统一响应结构。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette import status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi import HTTPException


class AppError(Exception):
    """业务异常基类。"""

    def __init__(self, message: str, code: str = "app_error", http_status: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


def error_response(code: str, message: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理。"""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:  # type: ignore[override]
        return JSONResponse(status_code=exc.http_status, content=error_response(exc.code, exc.message))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:  # type: ignore[override]
        # 统一 FastAPI 内置 HTTPException 的响应结构
        detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(status_code=exc.status_code, content=error_response("http_error", detail))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:  # type: ignore[override]
        # 非生产环境可以暴露 message，生产环境仅返回通用信息
        message = str(exc) if __debug__ else "Internal Server Error"
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_response("internal_error", message))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:  # type: ignore[override]
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error_response("validation_error", "Validation failed", {"errors": exc.errors()}))

    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:  # type: ignore[override]
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error_response("validation_error", "Validation failed", {"errors": exc.errors()}))