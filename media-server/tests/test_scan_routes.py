import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from main import create_app
from core.security import get_current_subject

# 模拟数据库模型
class MockStorageConfig:
    def __init__(self, id, user_id, root_path, is_active=True):
        self.id = id
        self.user_id = user_id
        self.root_path = root_path
        self.is_active = is_active

@pytest.fixture
def app():
    app = create_app()
    # 覆盖认证依赖，模拟已登录用户
    # 注意：get_user_id 会尝试将 subject 转为 int，所以这里必须返回数字字符串
    app.dependency_overrides[get_current_subject] = lambda: "1"
    return app

@pytest.fixture
def client(app):
    return TestClient(app)

@pytest.mark.asyncio
async def test_start_scan_full(client):
    """测试全量扫描"""
    with patch("api.routes_scan.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        # 显式创建一个 MagicMock 作为 exec 的返回值
        mock_result = MagicMock()
        mock_storage1 = MockStorageConfig(1, 1, "/mnt/s1")
        mock_storage2 = MockStorageConfig(2, 1, "/mnt/s2")
        mock_result.all.return_value = [mock_storage1, mock_storage2]
        
        # 关键：设置 mock_session.exec 的返回值
        mock_session.exec.return_value = mock_result
        
        with patch("services.task.producer.create_scan_task", new_callable=AsyncMock) as mock_create_task:
            mock_create_task.return_value = "task-full-123"
            
            response = client.post("/api/scan/start", json={"priority": "normal"})
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["task_type"] == "scan_batch"
            
            assert mock_create_task.await_count == 2
            calls = mock_create_task.await_args_list
            assert calls[0].kwargs['storage_id'] == 1
            assert calls[0].kwargs['scan_path'] == mock_storage1.root_path
            assert calls[1].kwargs['storage_id'] == 2
            assert calls[1].kwargs['scan_path'] == mock_storage2.root_path

@pytest.mark.asyncio
async def test_start_scan_single_storage(client):
    """测试单个存储全量扫描"""
    with patch("api.routes_scan.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        mock_result = MagicMock()
        mock_storage = MockStorageConfig(1, 1, "/mnt/s1")
        mock_result.first.return_value = mock_storage
        mock_session.exec.return_value = mock_result
        
        with patch("services.task.producer.create_scan_task", new_callable=AsyncMock) as mock_create_task:
            mock_create_task.return_value = "task-single-123"
            
            response = client.post("/api/scan/start", json={
                "storage_id": 1,
                "priority": "high"
            })
            
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            mock_create_task.assert_awaited_once()
            assert mock_create_task.await_args.kwargs['storage_id'] == 1
            # 单个存储如果不传路径，默认从配置根路径开始扫描
            assert mock_create_task.await_args.kwargs['scan_path'] == mock_storage.root_path

@pytest.mark.asyncio
async def test_start_scan_multiple_paths(client):
    """测试单个存储多路径扫描"""
    with patch("api.routes_scan.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        mock_result = MagicMock()
        mock_storage = MockStorageConfig(1, 1, "/mnt/s1")
        mock_result.first.return_value = mock_storage
        mock_session.exec.return_value = mock_result
        
        with patch("services.task.producer.create_scan_task", new_callable=AsyncMock) as mock_create_task:
            mock_create_task.return_value = "task-path-123"
            
            paths = ["/mnt/s1/movies", "/mnt/s1/tv"]
            response = client.post("/api/scan/start", json={
                "storage_id": 1,
                "scan_path": paths
            })
            
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            assert mock_create_task.await_count == 2
            calls = mock_create_task.await_args_list
            assert calls[0].kwargs['scan_path'] == paths[0]
            assert calls[1].kwargs['scan_path'] == paths[1]

@pytest.mark.asyncio
async def test_start_scan_invalid_storage(client):
    """测试无效存储ID"""
    with patch("api.routes_scan.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        mock_result = MagicMock()
        # first() 返回 None
        mock_result.first.return_value = None
        mock_session.exec.return_value = mock_result
        
        response = client.post("/api/scan/start", json={"storage_id": 999})
        
        assert response.status_code == 404
        # 只要状态码对就行，detail 内容可能有变
