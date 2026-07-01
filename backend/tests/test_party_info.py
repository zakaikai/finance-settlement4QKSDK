"""Tests for PartyInfo CRUD API."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db


@pytest.mark.asyncio
async def test_create_and_list_party_info(db_session):
    """Creating a party info record makes it visible in the list."""
    # Inject test DB session
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        payload = {
            "party_type": "our_company",
            "name": "测试科技有限公司",
            "address": "北京市朝阳区测试路100号",
            "phone": "010-88888888",
            "bank_name": "中国银行北京测试支行",
            "bank_account": "6222021234567890",
            "tax_id": "91110000MA12345678",
            "notes": "测试用主体",
        }
        resp = client.post("/api/party-info", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        created_id = data["id"]

        # List and verify
        resp2 = client.get("/api/party-info")
        assert resp2.status_code == 200
        items = resp2.json()["data"]
        match = [i for i in items if i["id"] == created_id]
        assert len(match) == 1
        assert match[0]["name"] == "测试科技有限公司"
        assert match[0]["party_type"] == "our_company"
        assert match[0]["bank_account"] == "6222021234567890"
        assert match[0]["tax_id"] == "91110000MA12345678"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_party_info(db_session):
    """Updating a party info record changes its fields in the list."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        # Create
        payload = {
            "party_type": "channel",
            "name": "旧名称",
            "address": "旧地址",
            "bank_name": "旧银行",
            "bank_account": "旧账号",
            "tax_id": "旧税号",
        }
        resp = client.post("/api/party-info", json=payload)
        pid = resp.json()["data"]["id"]

        # Update
        update = {
            "party_type": "publisher",
            "name": "新名称",
            "address": "新地址",
            "phone": "0755-99999999",
            "bank_name": "新银行",
            "bank_account": "新账号",
            "tax_id": "新税号",
            "notes": "已更新",
        }
        resp2 = client.put(f"/api/party-info/{pid}", json=update)
        assert resp2.status_code == 200

        # Verify
        resp3 = client.get("/api/party-info")
        items = resp3.json()["data"]
        match = [i for i in items if i["id"] == pid]
        assert len(match) == 1
        assert match[0]["name"] == "新名称"
        assert match[0]["party_type"] == "publisher"
        assert match[0]["phone"] == "0755-99999999"
        assert match[0]["notes"] == "已更新"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_party_info(db_session):
    """Deleting a party info record removes it from the list."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        payload = {
            "party_type": "channel",
            "name": "待删除主体",
            "address": "地址",
            "bank_name": "银行",
            "bank_account": "账号",
            "tax_id": "税号",
        }
        resp = client.post("/api/party-info", json=payload)
        pid = resp.json()["data"]["id"]

        resp2 = client.delete(f"/api/party-info/{pid}")
        assert resp2.status_code == 200

        resp3 = client.get("/api/party-info")
        ids = [i["id"] for i in resp3.json()["data"]]
        assert pid not in ids
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_party_info_by_type(db_session):
    """party_type query param filters results."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        for t in ("our_company", "channel", "publisher"):
            client.post("/api/party-info", json={
                "party_type": t,
                "name": f"Test {t}",
                "address": "addr",
                "bank_name": "bank",
                "bank_account": "acct",
                "tax_id": "tax",
            })

        resp = client.get("/api/party-info?party_type=channel")
        items = resp.json()["data"]
        assert all(i["party_type"] == "channel" for i in items)
        assert len(items) >= 1
    finally:
        app.dependency_overrides.clear()
