"""Tests for Memo CRUD API."""
import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db


@pytest.mark.asyncio
async def test_create_and_list_memo(db_session):
    """Creating a memo makes it visible in the list."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/memos", data={
            "title": "测试备忘录",
            "content": "这是一条测试备忘内容",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert data["title"] == "测试备忘录"
        assert data["content"] == "这是一条测试备忘内容"
        created_id = data["id"]

        # List and verify
        resp2 = client.get("/api/memos")
        assert resp2.status_code == 200
        items = resp2.json()["data"]
        match = [i for i in items if i["id"] == created_id]
        assert len(match) == 1
        assert match[0]["title"] == "测试备忘录"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_with_party_and_get_by_id(db_session):
    """Creating a memo with party reference, then fetching by id returns correct fields."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/memos", data={
            "title": "华为特殊条款",
            "content": "预付款 50 万，服务费 5%",
            "party_type": "channel",
            "party_name": "华为应用市场",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        mid = data["id"]

        # Get by id
        resp2 = client.get(f"/api/memos/{mid}")
        assert resp2.status_code == 200
        detail = resp2.json()["data"]
        assert detail["title"] == "华为特殊条款"
        assert detail["content"] == "预付款 50 万，服务费 5%"
        assert detail["party_type"] == "channel"
        assert detail["party_name"] == "华为应用市场"
        assert detail["has_attachment"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_nonexistent_memo(db_session):
    """Fetching a non-existent memo returns 404."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/memos/99999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_memo(db_session):
    """Updating a memo changes its fields."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/memos", data={"title": "旧标题", "content": "旧内容"})
        mid = resp.json()["data"]["id"]

        resp2 = client.put(f"/api/memos/{mid}", data={
            "title": "新标题",
            "content": "新内容",
            "party_type": "publisher",
            "party_name": "测试研发",
        })
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert data["title"] == "新标题"
        assert data["content"] == "新内容"
        assert data["party_type"] == "publisher"
        assert data["party_name"] == "测试研发"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_memo(db_session):
    """Deleting a memo removes it from the list."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/memos", data={"title": "待删除备忘录"})
        mid = resp.json()["data"]["id"]

        resp2 = client.delete(f"/api/memos/{mid}")
        assert resp2.status_code == 200

        # List should not contain it
        resp3 = client.get("/api/memos")
        ids = [i["id"] for i in resp3.json()["data"]]
        assert mid not in ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_nonexistent_memo(db_session):
    """Deleting a non-existent memo returns 404."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.delete("/api/memos/99999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_attachment(db_session):
    """Uploading a file attachment sets has_attachment and allows download."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/memos", data={"title": "带附件备忘录"},
                           files={"file": ("report.pdf", b"%PDF-1.4 fake pdf content")})
        assert resp.status_code == 200
        data = resp.json()["data"]
        mid = data["id"]
        assert data["has_attachment"] is True
        assert data["attachment_name"] == "report.pdf"

        # Download
        resp2 = client.get(f"/api/memos/{mid}/attachment")
        assert resp2.status_code == 200
        assert resp2.content == b"%PDF-1.4 fake pdf content"
    finally:
        app.dependency_overrides.clear()
