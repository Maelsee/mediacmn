import json

import pytest

from models.storage_models import StorageConfig, WebdavStorageConfig
from services.storage.storage_config_service import StorageConfigService


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, exec_results):
        self._exec_results = list(exec_results)
        self.added = []
        self.committed = False
        self.refreshed = []

    async def exec(self, _stmt):
        if not self._exec_results:
            raise AssertionError("exec 调用次数超出预期")
        return _FakeExecResult(self._exec_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.mark.anyio
async def test_update_storage_config_accepts_dict_config_and_updates_root_path():
    service = StorageConfigService()

    storage_config = StorageConfig(
        id=1,
        user_id=1,
        name="old",
        storage_type="webdav",
        root_path="/",
    )
    detail_config = WebdavStorageConfig(
        id=10,
        storage_config_id=1,
        hostname="https://example.com:5244/dav",
        login="u",
        password="p",
        root_path="/",
        select_path="[]",
        timeout_seconds=30,
        verify_ssl=True,
        pool_connections=10,
        pool_maxsize=10,
        retries_total=3,
        retries_backoff_factor=0.5,
        retries_status_forcelist="[429,500,502,503,504]",
        custom_headers=None,
        proxy_config=None,
    )

    db = _FakeAsyncSession([storage_config, detail_config])

    result = await service.update_storage_config(
        db=db,
        storage_id=1,
        user_id=1,
        name="new",
        config={"select_path": ["Movies"], "root_path": "/media"},
    )

    assert result is storage_config
    assert storage_config.name == "new"
    assert storage_config.root_path == "/media"
    assert detail_config.select_path == json.dumps(["Movies"])
    assert detail_config.root_path == "/media"
    assert db.committed is True
