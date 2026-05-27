"""共享测试 fixture"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    """创建 mock DB session，供路由级集成测试使用"""
    db = MagicMock()

    # 默认 query chain 返回空结果
    query_mock = MagicMock()
    db.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.first.return_value = None
    query_mock.all.return_value = []
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock

    return db


@pytest.fixture
def test_client(mock_db):
    """创建 FastAPI TestClient，注入 mock DB"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
