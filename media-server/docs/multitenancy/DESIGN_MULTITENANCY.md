# 多租户架构设计文档

## 1. 架构概述

### 1.1 设计目标
将现有的RBAC权限系统改为多租户架构，每个租户对自己的数据拥有全部权限，实现用户级别的数据隔离。

### 1.2 核心原则
- **用户隔离**：每个用户只能访问自己的数据
- **简化权限**：移除复杂的角色权限管理，采用简单的用户认证
- **数据安全**：通过数据库层面的用户ID过滤确保数据隔离
- **向后兼容**：保持现有API接口不变，仅修改权限验证逻辑

## 2. 数据隔离策略

### 2.1 数据库层面隔离
```sql
-- 所有业务表都包含user_id字段用于隔离
CREATE TABLE storage_configs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,  -- 用户隔离字段
    name VARCHAR(255),
    storage_type VARCHAR(50),
    -- 其他字段...
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 查询时始终添加user_id过滤
SELECT * FROM storage_configs WHERE user_id = :current_user_id;
```

### 2.2 应用层面隔离
- 所有数据库查询操作必须包含`user_id`条件
- API路由层通过JWT认证获取当前用户ID
- 服务层强制验证用户身份与数据所有权

## 3. 权限模型转换

### 3.1 移除RBAC组件
```python
# 移除的组件
- core/permissions.py 中的RBAC检查逻辑
- services/rbac_service.py 权限服务
- models/rbac_models.py 权限模型
- api/routes_rbac.py RBAC管理API
```

### 3.2 保留认证组件
```python
# 保留的组件
- core/security.py JWT认证
- core/db.py 数据库连接
- get_current_subject() 用户身份验证
```

## 4. API路由修改方案

### 4.1 存储配置API修改
```python
# 修改前（RBAC模式）
@router.get("/storages")
async def list_storages(
    _: bool = Depends(check_user_permission_dependency("storage", "read")),
    current_user: str = Depends(get_current_subject),
    db: Session = Depends(get_db)
):
    # 权限检查已通过装饰器完成
    return storage_service.list_storages(db)

# 修改后（多租户模式）
@router.get("/storages")
async def list_storages(
    current_user: str = Depends(get_current_subject),
    db: Session = Depends(get_db)
):
    user_id = int(current_user)
    return storage_service.list_user_storages(db, user_id)
```

### 4.2 统一修改模式
1. 移除所有`check_user_permission_dependency`依赖
2. 保留`get_current_subject`认证依赖
3. 在查询中添加`user_id`过滤条件
4. 确保用户只能访问自己的数据

## 5. 服务层修改方案

### 5.1 存储配置服务
```python
class StorageConfigService:
    def get_storage_config(self, db: Session, storage_id: int, user_id: int):
        """获取用户特定的存储配置"""
        return db.query(StorageConfig).filter(
            StorageConfig.id == storage_id,
            StorageConfig.user_id == user_id  # 用户隔离
        ).first()
    
    def list_user_storages(self, db: Session, user_id: int, storage_type: str = None):
        """列出用户的所有存储配置"""
        query = db.query(StorageConfig).filter(StorageConfig.user_id == user_id)
        if storage_type:
            query = query.filter(StorageConfig.storage_type == storage_type)
        return query.all()
```

### 5.2 WebDAV存储服务
```python
class WebdavStorageConfigService:
    def get_webdav_config(self, db: Session, storage_config_id: int, user_id: int):
        """获取用户特定的WebDAV配置"""
        return db.query(WebdavStorageConfig).join(StorageConfig).filter(
            WebdavStorageConfig.storage_config_id == storage_config_id,
            StorageConfig.user_id == user_id  # 用户隔离
        ).first()
```

## 6. 安全验证机制

### 6.1 数据所有权验证
```python
def verify_data_ownership(db: Session, resource_id: int, user_id: int, model):
    """验证用户是否拥有指定资源的访问权限"""
    resource = db.query(model).filter(
        model.id == resource_id,
        model.user_id == user_id
    ).first()
    
    if not resource:
        raise HTTPException(
            status_code=403,
            detail="无权访问该资源"
        )
    return resource
```

### 6.2 请求参数验证
```python
def validate_user_access(current_user: str, target_user_id: int):
    """验证当前用户是否有权限访问目标用户的数据"""
    current_user_id = int(current_user)
    if current_user_id != target_user_id:
        raise HTTPException(
            status_code=403,
            detail="无权访问其他用户的数据"
        )
```

## 7. 测试策略

### 7.1 隔离性测试
```python
# 测试用户A无法访问用户B的数据
def test_user_isolation():
    # 用户A创建存储配置
    token_a = login_user("user_a@example.com")
    storage_a = create_storage(token_a, {"name": "Storage A"})
    
    # 用户B尝试访问用户A的配置
    token_b = login_user("user_b@example.com")
    response = get_storage(token_b, storage_a["id"])
    
    assert response.status_code == 403
    assert "无权访问该资源" in response.json()["detail"]
```

### 7.2 数据完整性测试
```python
# 测试用户只能看到自己的数据
def test_user_data_visibility():
    token = login_user("user@example.com")
    
    # 创建多个存储配置
    create_storage(token, {"name": "Storage 1"})
    create_storage(token, {"name": "Storage 2"})
    
    # 列出所有存储
    storages = list_storages(token)
    
    # 验证只返回当前用户的数据
    for storage in storages:
        assert storage["user_id"] == current_user_id
```

## 8. 迁移计划

### 8.1 第一阶段：移除RBAC依赖
- [ ] 修改存储配置API路由，移除权限检查
- [ ] 修改WebDAV存储API路由，移除权限检查
- [ ] 更新服务层，添加用户ID过滤

### 8.2 第二阶段：清理RBAC组件
- [ ] 移除RBAC相关模型和服务
- [ ] 清理权限相关的测试用例
- [ ] 更新API文档

### 8.3 第三阶段：验证与优化
- [ ] 编写多租户隔离测试
- [ ] 性能测试与优化
- [ ] 安全审计

## 9. 风险与应对

### 9.1 数据安全风险
- **风险**：用户可能访问到其他用户的数据
- **应对**：所有查询必须包含user_id条件，通过代码审查和自动化测试确保

### 9.2 性能影响
- **风险**：添加user_id过滤可能影响查询性能
- **应对**：确保user_id字段有索引，必要时添加复合索引

### 9.3 向后兼容性
- **风险**：API行为变化可能影响现有客户端
- **应对**：保持API接口不变，仅修改内部权限逻辑

## 10. 监控与审计

### 10.1 访问日志
```python
# 记录所有数据访问操作
logger.info(f"User {user_id} accessed {resource_type} {resource_id}")
```

### 10.2 异常监控
```python
# 监控权限验证失败
if not resource:
    logger.warning(f"Access denied: User {user_id} tried to access {resource_type} {resource_id}")
    raise HTTPException(status_code=403, detail="无权访问该资源")
```