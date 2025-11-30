"""统一的错误处理中间件"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging
logger = logging.getLogger(__name__)
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from schemas.api_response import ApiError, ApiResponse


class UnifiedErrorHandlerMiddleware(BaseHTTPMiddleware):
    """统一的错误处理中间件"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return await self._handle_exception(request, exc)
    
    async def _handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """处理各种异常"""
        
        # 记录错误日志
        logger.error(f"请求处理异常: {request.method} {request.url.path}")
        logger.error(f"异常类型: {type(exc).__name__}")
        logger.error(f"异常信息: {str(exc)}")
        logger.error(f"堆栈跟踪: {traceback.format_exc()}")
        
        # 处理不同类型的异常
        if isinstance(exc, ValidationError):
            return await self._handle_validation_error(request, exc)
        elif isinstance(exc, ValueError):
            return await self._handle_value_error(request, exc)
        elif hasattr(exc, 'status_code') and hasattr(exc, 'detail'):
            return await self._handle_http_exception(request, exc)
        else:
            return await self._handle_internal_error(request, exc)
    
    async def _handle_validation_error(self, request: Request, exc: ValidationError) -> JSONResponse:
        """处理Pydantic验证错误"""
        error_detail = {
            "errors": exc.errors(),
            "model": exc.model.__name__ if hasattr(exc, 'model') else None
        }
        
        api_error = ApiError(
            code="VALIDATION_ERROR",
            message="请求数据验证失败",
            details=error_detail,
            field=None
        )
        
        response = ApiResponse(
            success=False,
            message="请求数据格式错误",
            error=api_error.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response.model_dump()
        )
    
    async def _handle_value_error(self, request: Request, exc: ValueError) -> JSONResponse:
        """处理值错误"""
        api_error = ApiError(
            code="INVALID_VALUE",
            message=str(exc),
            details=None,
            field=None
        )
        
        response = ApiResponse(
            success=False,
            message="参数值无效",
            error=api_error.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response.model_dump()
        )
    
    async def _handle_http_exception(self, request: Request, exc) -> JSONResponse:
        """处理HTTP异常"""
        api_error = ApiError(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            details=None,
            field=None
        )
        
        response = ApiResponse(
            success=False,
            message="HTTP错误",
            error=api_error.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump()
        )
    
    async def _handle_internal_error(self, request: Request, exc: Exception) -> JSONResponse:
        """处理内部服务器错误"""
        api_error = ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误",
            details={"error_type": type(exc).__name__} if __debug__ else None,
            field=None
        )
        
        response = ApiResponse(
            success=False,
            message="服务器处理请求时发生错误",
            error=api_error.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump()
        )


def create_success_response(data: Any = None, message: str = "操作成功") -> ApiResponse:
    """创建成功响应"""
    return ApiResponse(
        success=True,
        message=message,
        data=data,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


def create_error_response(
    message: str,
    code: str = "ERROR",
    details: Dict[str, Any] | None = None,
    field: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST
) -> JSONResponse:
    """创建错误响应"""
    api_error = ApiError(
        code=code,
        message=message,
        details=details,
        field=field
    )
    
    response = ApiResponse(
        success=False,
        message=message,
        error=api_error.model_dump(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump()
    )