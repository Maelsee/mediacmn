"""统一的API响应模型"""
from __future__ import annotations

from typing import Any, Dict, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一的API响应模型"""
    success: bool = Field(description="请求是否成功")
    message: str = Field(description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")
    error: Optional[Dict[str, Any]] = Field(default=None, description="错误信息")
    timestamp: str = Field(description="响应时间戳")


class ApiError(BaseModel):
    """统一的错误响应模型"""
    code: str = Field(description="错误代码")
    message: str = Field(description="错误消息")
    details: Optional[Dict[str, Any]] = Field(default=None, description="错误详情")
    field: Optional[str] = Field(default=None, description="错误字段")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模型"""
    items: list[T] = Field(description="数据列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    size: int = Field(description="每页大小")
    pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")


class StorageConfigResponse(BaseModel):
    """存储配置响应模型 - 脱敏版本"""
    id: int
    user_id: int
    name: str
    storage_type: str
    created_at: str
    updated_at: str
    status: Optional[str] = None
    # 敏感字段已被移除或设置为None
    
    
class StorageConfigDetailResponse(BaseModel):
    """存储配置详情响应模型 - 脱敏版本"""
    id: int
    user_id: int
    name: str
    storage_type: str
    created_at: str
    updated_at: str
    status: Optional[str] = None
    detail: Dict[str, Any]  # 脱敏后的详细配置


class UserResponse(BaseModel):
    """用户响应模型 - 脱敏版本"""
    id: int
    email: str
    is_active: bool
    created_at: str
    # 不包含密码等敏感字段