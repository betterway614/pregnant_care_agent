"""共享测试 fixture"""
import pytest
from unittest.mock import MagicMock
from app.core.auth import TokenPayload, create_token


def make_test_token(sub="test-admin", role="admin", pregnant_id=""):
    """生成测试用 JWT token"""
    payload = TokenPayload(sub=sub, role=role, pregnant_id=pregnant_id)
    return create_token(payload)


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
def mock_user():
    """创建默认测试用户（admin 角色，可访问所有数据）"""
    return TokenPayload(
        sub="test-admin",
        role="admin",
        pregnant_id="",
    )


@pytest.fixture
def mock_pregnant_user():
    """创建孕妇测试用户"""
    return TokenPayload(
        sub="test-pregnant-001",
        role="pregnant",
        pregnant_id="test-pregnant-001",
    )


@pytest.fixture
def mock_doctor_user():
    """创建医生测试用户"""
    return TokenPayload(
        sub="test-doctor",
        role="doctor",
        pregnant_id="",
    )


@pytest.fixture
def mock_nurse_user():
    """创建护士测试用户"""
    return TokenPayload(
        sub="test-nurse",
        role="nurse",
        pregnant_id="",
    )


@pytest.fixture
def admin_auth_headers():
    """生成 admin 认证 headers"""
    token = make_test_token(sub="test-admin", role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def doctor_auth_headers():
    """生成 doctor 认证 headers"""
    token = make_test_token(sub="test-doctor", role="doctor")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def nurse_auth_headers():
    """生成 nurse 认证 headers"""
    token = make_test_token(sub="test-nurse", role="nurse")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pregnant_auth_headers():
    """生成 pregnant 认证 headers"""
    token = make_test_token(sub="test-pregnant-001", role="pregnant", pregnant_id="test-pregnant-001")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_client(mock_db, mock_user):
    """创建 FastAPI TestClient，注入 mock DB 和认证"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db
    from app.core.auth import get_current_user

    def override_get_db():
        yield mock_db

    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    token = make_test_token(sub=mock_user.sub, role=mock_user.role, pregnant_id=mock_user.pregnant_id)
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_client_no_auth(mock_db):
    """创建无认证的 TestClient（仅用于不需要认证的测试）"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """生成认证 headers（用于需要手动传递 token 的测试）"""
    token = make_test_token()
    return {"Authorization": f"Bearer {token}"}
