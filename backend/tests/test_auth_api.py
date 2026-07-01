"""Integration tests for auth API endpoints: status, setup, login, logout."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import auth


@pytest.fixture
def client():
    """Provide TestClient with isolated auth config."""
    # Point auth to a temp config file so tests don't touch real config.env
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".env", mode="w")
    tmp.write("LAN_ENABLED=true\n")
    tmp.close()
    auth._CONFIG_PATH = tmp.name
    auth._attempts.clear()
    auth._tokens.clear()
    yield TestClient(app, raise_server_exceptions=False)
    os.unlink(tmp.name)
    auth._CONFIG_PATH = None


class TestAuthStatus:
    """GET /api/auth/status"""

    def test_no_password_returns_false(self, client):
        """未设密码时返回 password_set=false"""
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        data = r.json()
        assert data["password_set"] is False


class TestSetup:
    """POST /api/auth/setup"""

    def test_setup_creates_password(self, client):
        """设置密码后返回 token 且 status 变为 true"""
        r = client.post("/api/auth/setup", json={"password": "test1234"})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert len(data["token"]) == 64

        # Status should now report password is set
        r2 = client.get("/api/auth/status")
        assert r2.json()["password_set"] is True

    def test_setup_rejects_short_password(self, client):
        """密码长度不足4位时返回 400"""
        r = client.post("/api/auth/setup", json={"password": "ab"})
        assert r.status_code == 400


class TestLogin:
    """POST /api/auth/login"""

    def _setup_password(self, client, pwd="test1234"):
        client.post("/api/auth/setup", json={"password": pwd})

    def test_login_succeeds_with_correct_password(self, client):
        """正确密码登录成功并返回 token"""
        self._setup_password(client)
        r = client.post("/api/auth/login", json={"password": "test1234"})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert len(data["token"]) == 64

    def test_login_fails_with_wrong_password(self, client):
        """错误密码返回 401"""
        self._setup_password(client)
        r = client.post("/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401
        assert "detail" in r.json()


class TestAuthMiddleware:
    """Auth middleware — protected routes require token"""

    def test_no_token_returns_401(self, client):
        """设密后无 token 访问保护接口返回 401"""
        r_setup = client.post("/api/auth/setup", json={"password": "test1234"})
        assert r_setup.status_code == 200
        r = client.get("/api/basic/games")
        assert r.status_code == 401

    def test_health_is_public(self, client):
        """健康检查接口不需要 token"""
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_token_allows_access(self, client):
        """有效 token 可访问保护接口"""
        r_setup = client.post("/api/auth/setup", json={"password": "test1234"})
        assert r_setup.status_code == 200
        login = client.post("/api/auth/login", json={"password": "test1234"})
        token = login.json()["token"]

        r = client.get("/api/basic/games", headers={"X-Auth-Token": token})
        assert r.status_code == 200
