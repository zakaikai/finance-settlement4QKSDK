"""Tests for LAN sharing feature: API toggle + middleware enforcement.

conftest.py's _auth_disabled autouse fixture provides a clean config.env
with LAN_ENABLED=true for each test.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import auth


@pytest.fixture
def lclient():
    """Localhost TestClient — bypasses readonly middleware (client=127.0.0.1)."""
    return TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))


@pytest.fixture
def rclient():
    """Remote / non-local TestClient — triggers readonly middleware."""
    return TestClient(app, raise_server_exceptions=False, client=("192.168.1.100", 5000))


# ── API: status & toggle ──

class TestLanAPI:
    """GET /api/system/lan-status  and  POST /api/system/lan-toggle."""

    def test_default_state(self, lclient):
        """Test config provides LAN_ENABLED=true by default."""
        resp = lclient.get("/api/system/lan-status")
        assert resp.status_code == 200
        assert resp.json()["data"]["lan_enabled"] is True

    def test_disable(self, lclient):
        """Toggle off → lan_enabled=false."""
        resp = lclient.post("/api/system/lan-toggle", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["data"]["lan_enabled"] is False
        assert auth.get_lan_enabled() is False

    def test_enable(self, lclient):
        """Toggle on → lan_enabled=true."""
        # First disable (test_default_state verified initial is True)
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = lclient.post("/api/system/lan-toggle", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["data"]["lan_enabled"] is True
        assert auth.get_lan_enabled() is True

    def test_toggle_twice_no_error(self, lclient):
        """Repeating the same toggle does not error."""
        r1 = lclient.post("/api/system/lan-toggle", json={"enabled": False})
        assert r1.status_code == 200
        r2 = lclient.post("/api/system/lan-toggle", json={"enabled": False})
        assert r2.status_code == 200
        assert r2.json()["data"]["lan_enabled"] is False

    def test_persists_to_config_file(self, lclient):
        """Toggle state survives by writing LAN_ENABLED into config.env."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        with open(auth._CONFIG_PATH) as f:
            assert "LAN_ENABLED=false" in f.read()

        lclient.post("/api/system/lan-toggle", json={"enabled": True})
        with open(auth._CONFIG_PATH) as f:
            assert "LAN_ENABLED=true" in f.read()


# ── Middleware: LAN OFF ──

class TestMiddlewareLANOff:
    """LAN sharing disabled → all non-local requests blocked."""

    def test_nonlocal_get_blocked(self, lclient, rclient):
        """LAN关闭: 非本机 GET → 403."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = rclient.get("/api/system/status")
        assert resp.status_code == 403
        assert "局域网分享未开启" in resp.json()["detail"]

    def test_nonlocal_post_blocked(self, lclient, rclient):
        """LAN关闭: 非本机 POST → 403."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = rclient.post("/api/basic/games", json={})
        assert resp.status_code == 403

    def test_local_get_allowed(self, lclient):
        """LAN关闭: 本机 GET 正常."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = lclient.get("/api/system/status")
        assert resp.status_code == 200

    def test_local_post_allowed(self, lclient):
        """LAN关闭: 本机 POST 正常."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = lclient.post("/api/system/lan-toggle", json={"enabled": True})
        assert resp.status_code == 200

    def test_auth_path_exempt_when_lan_off(self, lclient, rclient):
        """LAN关闭: 认证路径仍可访问."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = rclient.get("/api/auth/status")
        assert resp.status_code == 200

    def test_health_exempt_when_lan_off(self, lclient, rclient):
        """LAN关闭: 健康检查仍可访问."""
        lclient.post("/api/system/lan-toggle", json={"enabled": False})
        resp = rclient.get("/api/health")
        assert resp.status_code == 200


# ── Middleware: LAN ON ──

class TestMiddlewareLANOn:
    """LAN sharing enabled → non-local reads allowed, writes blocked as read-only."""

    def test_nonlocal_get_allowed_with_readonly_header(self, rclient):
        """LAN开启: 非本机 GET 放行, 带 X-Read-Only 响应头."""
        resp = rclient.get("/api/system/status")
        assert resp.status_code == 200
        assert resp.headers.get("X-Read-Only") == "1"

    def test_nonlocal_post_blocked_readonly(self, rclient):
        """LAN开启: 非本机 POST → 403 只读模式."""
        resp = rclient.post("/api/basic/games", json={})
        assert resp.status_code == 403
        assert "只读模式" in resp.json()["detail"]

    def test_nonlocal_put_blocked(self, rclient):
        """LAN开启: 非本机 PUT → 403."""
        resp = rclient.put("/api/party-info/1", json={})
        assert resp.status_code == 403
        assert "只读模式" in resp.json()["detail"]

    def test_nonlocal_delete_blocked(self, rclient):
        """LAN开启: 非本机 DELETE → 403."""
        resp = rclient.delete("/api/party-info/1")
        assert resp.status_code == 403

    def test_local_request_no_readonly_header(self, lclient):
        """LAN开启: 本机请求不带 X-Read-Only 头."""
        resp = lclient.get("/api/system/status")
        assert resp.status_code == 200
        assert resp.headers.get("X-Read-Only") is None

    def test_auth_path_no_readonly_header(self, rclient):
        """LAN开启: 认证路径不带 X-Read-Only 头."""
        resp = rclient.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.headers.get("X-Read-Only") is None
