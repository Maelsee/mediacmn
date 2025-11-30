"""敏感数据加密服务 - 用于存储配置等敏感信息的加密存储"""
from __future__ import annotations

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC





class EncryptionService:
    """敏感数据加密服务
    
    提供应用层敏感数据加密，支持：
    - 密码/令牌等敏感信息加密存储
    - 密钥派生和轮换
    - 透明加密/解密操作
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """初始化加密服务
        
        Args:
            master_key: 主密钥，如果未提供则从环境变量获取
        """
        self.master_key = master_key or os.getenv("MASTER_KEY")
        if not self.master_key:
            # 如果没有提供主密钥，生成一个用于开发的临时密钥
            self.master_key = Fernet.generate_key().decode()
            logger.warning("未设置MASTER_KEY，使用临时生成的密钥。生产环境请设置强密钥！")
        
        self._cipher = self._get_cipher()
    
    def _get_cipher(self) -> Fernet:
        """获取Fernet加密实例"""
        # 使用PBKDF2从主密钥派生加密密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'media_server_salt_2024',  # 固定盐值，确保相同主密钥产生相同结果
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
        return Fernet(key)
    
    def encrypt(self, data: str) -> str:
        """加密字符串数据
        
        Args:
            data: 要加密的明文字符串
            
        Returns:
            str: Base64编码的加密结果
            
        Raises:
            ValueError: 加密失败时抛出
        """
        try:
            encrypted = self._cipher.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"加密数据失败: {e}")
            raise ValueError(f"加密失败: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """解密字符串数据
        
        Args:
            encrypted_data: Base64编码的加密字符串
            
        Returns:
            str: 解密后的明文字符串
            
        Raises:
            ValueError: 解密失败时抛出
        """
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"解密数据失败: {e}")
            raise ValueError(f"解密失败: {e}")
    
    def encrypt_dict(self, data: dict) -> str:
        """加密字典数据（先转为JSON字符串）"""
        import json
        json_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return self.encrypt(json_str)
    
    def decrypt_dict(self, encrypted_data: str) -> dict:
        """解密字典数据"""
        import json
        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)


# 全局加密服务实例
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """获取全局加密服务实例"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_sensitive_data(data: str) -> str:
    """加密敏感数据的便捷函数"""
    return get_encryption_service().encrypt(data)


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """解密敏感数据的便捷函数"""
    return get_encryption_service().decrypt(encrypted_data)