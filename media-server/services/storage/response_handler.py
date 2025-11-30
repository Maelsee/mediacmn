"""存储配置响应处理器 - 用于API响应脱敏"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, List, Union
from models.storage_models import (
    StorageConfig,
    WebdavStorageConfig,
    SmbStorageConfig,
    LocalStorageConfig,
    CloudStorageConfig,
    StorageStatus
)
from schemas.api_response import StorageConfigResponse, StorageConfigDetailResponse


class StorageConfigResponseHandler:
    """存储配置响应处理器 - 处理敏感数据脱敏"""
    
    # 需要脱敏的敏感字段
    SENSITIVE_FIELDS = {
        'webdav': ['password'],
        'smb': ['password'],
        'cloud': ['access_token', 'refresh_token', 'client_secret']
    }
    
    @staticmethod
    def to_list_response(
        storage_config: StorageConfig,
        status: Optional[StorageStatus] = None
    ) -> StorageConfigResponse:
        """转换为列表响应（脱敏）"""
        return StorageConfigResponse(
            id=storage_config.id,
            user_id=storage_config.user_id,
            name=storage_config.name,
            storage_type=storage_config.storage_type,
            created_at=storage_config.created_at.isoformat(),
            updated_at=storage_config.updated_at.isoformat(),
            status=status.status if status else None
        )
    
    @staticmethod
    def to_detail_response(
        storage_config: StorageConfig,
        detail_config: Any,
        status: Optional[StorageStatus] = None,
        include_sensitive: bool = False
    ) -> Dict[str, Any]:
        """转换为详情响应"""
        base_response = {
            "id": storage_config.id,
            "user_id": storage_config.user_id,
            "name": storage_config.name,
            "storage_type": storage_config.storage_type,
            "created_at": storage_config.created_at.isoformat(),
            "updated_at": storage_config.updated_at.isoformat(),
            "status": status.status if status else None,
            "detail": {}
        }
        
        # 处理详细配置
        if detail_config:
            detail_dict = StorageConfigResponseHandler._model_to_dict(detail_config)
            
            if include_sensitive:
                # 包含敏感字段（需要解密）
                base_response["detail"] = detail_dict
            else:
                # 脱敏处理
                base_response["detail"] = StorageConfigResponseHandler._remove_sensitive_fields(
                    storage_config.storage_type,
                    detail_dict
                )
        
        return base_response
    
    @staticmethod
    def _model_to_dict(model) -> Dict[str, Any]:
        """将SQLModel实例转换为字典"""
        result = {}
        for field_name in model.__fields__:
            if field_name != 'storage_config_id':  # 排除外键字段
                value = getattr(model, field_name)
                if hasattr(value, 'isoformat'):
                    result[field_name] = value.isoformat()
                else:
                    result[field_name] = value
        return result
    
    @staticmethod
    def _remove_sensitive_fields(storage_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """移除敏感字段"""
        result = data.copy()
        sensitive_fields = StorageConfigResponseHandler.SENSITIVE_FIELDS.get(storage_type, [])
        
        for field in sensitive_fields:
            if field in result:
                result[field] = None  # 设置为null而不是删除，保持结构一致
        
        return result
    
    @staticmethod
    def mask_sensitive_value(value: str) -> str:
        """遮罩敏感值"""
        if not value or len(value) < 4:
            return "****"
        
        # 显示首尾各2个字符，中间用*代替
        start = value[:2]
        end = value[-2:]
        middle = "*" * (len(value) - 4)
        return f"{start}{middle}{end}"
    
    @staticmethod
    def _parse_json_path(path_value: Optional[str]) -> Union[str, List[str], None]:
        """智能解析路径值，如果是JSON数组则返回数组，否则返回原值"""
        if path_value is None:
            return None
        
        # 尝试解析为JSON数组
        try:
            parsed = json.loads(path_value)
            if isinstance(parsed, list):
                return parsed
            else:
                return path_value
        except (json.JSONDecodeError, ValueError):
            # 如果不是有效的JSON，返回原值
            return path_value
    
    @staticmethod
    def sanitize_storage_config(storage_config: Any) -> Dict[str, Any]:
        """对存储配置进行脱敏处理"""
        # 处理字典类型数据
        if isinstance(storage_config, dict):
            result = {
                "id": storage_config.get("id"),
                "user_id": storage_config.get("user_id"),
                "name": storage_config.get("name"),
                "storage_type": storage_config.get("storage_type"),
                "is_active": storage_config.get("is_active"),
                "priority": storage_config.get("priority"),
                "created_at": storage_config.get("created_at").isoformat() if hasattr(storage_config.get("created_at"), 'isoformat') else str(storage_config.get("created_at")),
                "updated_at": storage_config.get("updated_at").isoformat() if hasattr(storage_config.get("updated_at"), 'isoformat') else str(storage_config.get("updated_at"))
            }
            
            # 添加详细配置信息（包含WebDAV等存储类型的具体配置）
            detail_config = storage_config.get("detail")
            if detail_config:
                if isinstance(detail_config, dict):
                    # 处理字典类型的详细配置
                    result.update({
                        "hostname": detail_config.get("hostname"),
                        "login": detail_config.get("login"),
                        "root_path": detail_config.get("root_path"),
                        "select_path": detail_config.get("select_path"),
                        "timeout_seconds": detail_config.get("timeout_seconds"),
                        "verify_ssl": detail_config.get("verify_ssl"),
                        "pool_connections": detail_config.get("pool_connections"),
                        "pool_maxsize": detail_config.get("pool_maxsize"),
                        "retries_total": detail_config.get("retries_total"),
                        "retries_backoff_factor": detail_config.get("retries_backoff_factor"),
                        "retries_status_forcelist": detail_config.get("retries_status_forcelist")
                    })
                else:
                    # 处理ORM对象类型的详细配置
                    result.update({
                        "hostname": getattr(detail_config, "hostname", None),
                        "login": getattr(detail_config, "login", None),
                        "root_path": getattr(detail_config, "root_path", None),
                        "select_path": StorageConfigResponseHandler._parse_json_path(getattr(detail_config, "select_path", None)),
                        "timeout_seconds": getattr(detail_config, "timeout_seconds", None),
                        "verify_ssl": getattr(detail_config, "verify_ssl", None),
                        "pool_connections": getattr(detail_config, "pool_connections", None),
                        "pool_maxsize": getattr(detail_config, "pool_maxsize", None),
                        "retries_total": getattr(detail_config, "retries_total", None),
                        "retries_backoff_factor": getattr(detail_config, "retries_backoff_factor", None),
                        "retries_status_forcelist": getattr(detail_config, "retries_status_forcelist", None)
                    })
            
            return result
        
        # 处理ORM对象类型数据
        result = {
            "id": storage_config.id,
            "user_id": storage_config.user_id,
            "name": storage_config.name,
            "storage_type": storage_config.storage_type,
            "is_active": storage_config.is_active,
            "priority": storage_config.priority,
            "created_at": storage_config.created_at.isoformat() if hasattr(storage_config.created_at, 'isoformat') else str(storage_config.created_at),
            "updated_at": storage_config.updated_at.isoformat() if hasattr(storage_config.updated_at, 'isoformat') else str(storage_config.updated_at)
        }
        
        # 添加详细配置信息
        if hasattr(storage_config, 'detail') and storage_config.detail:
            detail_config = storage_config.detail
            result.update({
                "hostname": getattr(detail_config, "hostname", None),
                "login": getattr(detail_config, "login", None),
                "root_path": getattr(detail_config, "root_path", None),
                "select_path": StorageConfigResponseHandler._parse_json_path(getattr(detail_config, "select_path", None)),
                "timeout_seconds": getattr(detail_config, "timeout_seconds", None),
                "verify_ssl": getattr(detail_config, "verify_ssl", None),
                "pool_connections": getattr(detail_config, "pool_connections", None),
                "pool_maxsize": getattr(detail_config, "pool_maxsize", None),
                "retries_total": getattr(detail_config, "retries_total", None),
                "retries_backoff_factor": getattr(detail_config, "retries_backoff_factor", None),
                "retries_status_forcelist": getattr(detail_config, "retries_status_forcelist", None)
            })
        
        return result


class UserResponseHandler:
    """用户响应处理器"""
    
    @staticmethod
    def to_response(user) -> Dict[str, Any]:
        """转换为用户响应（脱敏）"""
        return {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat()
            # 不包含密码等敏感字段
        }


class ErrorResponseHandler:
    """错误响应处理器"""
    
    @staticmethod
    def create_validation_error(field: str, message: str) -> Dict[str, Any]:
        """创建验证错误响应"""
        return {
            "success": False,
            "message": "数据验证失败",
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "field": field,
                "details": None
            },
            "timestamp": "2024-01-01T00:00:00Z"  # 实际使用时应该使用当前时间
        }
    
    @staticmethod
    def create_not_found_error(resource: str, id: Any) -> Dict[str, Any]:
        """创建未找到错误响应"""
        return {
            "success": False,
            "message": f"{resource}不存在",
            "error": {
                "code": "NOT_FOUND",
                "message": f"未找到ID为{id}的{resource}",
                "field": None,
                "details": {"resource": resource, "id": id}
            },
            "timestamp": "2024-01-01T00:00:00Z"
        }
    
    @staticmethod
    def create_permission_error(message: str = "权限不足") -> Dict[str, Any]:
        """创建权限错误响应"""
        return {
            "success": False,
            "message": message,
            "error": {
                "code": "PERMISSION_DENIED",
                "message": message,
                "field": None,
                "details": None
            },
            "timestamp": "2024-01-01T00:00:00Z"
        }