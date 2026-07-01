"""Tests for Channel-Party Mapping CRUD API."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db
from backend import models


def _setup_client(db_session):
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    return TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))


def _teardown():
    app.dependency_overrides.clear()


async def _seed_channel(db, channel_id, name):
    existing = (await db.execute(
        __import__('sqlalchemy').select(models.ChannelCategory).where(
            models.ChannelCategory.channel_id == channel_id)
    )).scalar_one_or_none()
    if not existing:
        db.add(models.ChannelCategory(channel_id=channel_id, channel_name=name))
        await db.commit()


async def _seed_party(db, party_id, name):
    existing = (await db.execute(
        __import__('sqlalchemy').select(models.PartyInfo).where(
            models.PartyInfo.id == party_id)
    )).scalar_one_or_none()
    if not existing:
        db.add(models.PartyInfo(
            id=party_id, party_type='our_company', name=name,
            address='', phone='', bank_name='', bank_account='', tax_id='',
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_list_empty_when_no_mappings(db_session):
    client = _setup_client(db_session)
    try:
        resp = client.get("/api/basic/channel-company-mappings")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        _teardown()


@pytest.mark.asyncio
async def test_create_and_list_mapping(db_session):
    await _seed_channel(db_session, 1, "华为")
    await _seed_party(db_session, 1, "上海科技有限公司")

    client = _setup_client(db_session)
    try:
        resp = client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": 1,
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp2 = client.get("/api/basic/channel-company-mappings")
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert len(data) == 1
        assert data[0]["channel_id"] == 1
        assert data[0]["channel_name"] == "华为"
        assert data[0]["party_info_id"] == 1
        assert data[0]["party_name"] == "上海科技有限公司"
    finally:
        _teardown()


@pytest.mark.asyncio
async def test_update_existing_mapping(db_session):
    await _seed_channel(db_session, 1, "华为")
    await _seed_party(db_session, 1, "上海科技有限公司")
    await _seed_party(db_session, 2, "北京科技有限公司")

    client = _setup_client(db_session)
    try:
        client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": 1,
        })

        resp = client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": 2,
        })
        assert resp.status_code == 200

        resp2 = client.get("/api/basic/channel-company-mappings")
        data = resp2.json()["data"]
        assert len(data) == 1
        assert data[0]["party_info_id"] == 2
        assert data[0]["party_name"] == "北京科技有限公司"
    finally:
        _teardown()


@pytest.mark.asyncio
async def test_delete_mapping(db_session):
    await _seed_channel(db_session, 1, "华为")
    await _seed_party(db_session, 1, "上海科技有限公司")

    client = _setup_client(db_session)
    try:
        client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": 1,
        })

        resp = client.delete("/api/basic/channel-company-mappings/1")
        assert resp.status_code == 200

        resp2 = client.get("/api/basic/channel-company-mappings")
        assert resp2.json()["data"] == []
    finally:
        _teardown()


@pytest.mark.asyncio
async def test_delete_nonexistent_is_idempotent(db_session):
    client = _setup_client(db_session)
    try:
        resp = client.delete("/api/basic/channel-company-mappings/999")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
    finally:
        _teardown()


@pytest.mark.asyncio
async def test_post_without_party_info_id_deletes_mapping(db_session):
    await _seed_channel(db_session, 1, "华为")
    await _seed_party(db_session, 1, "上海科技有限公司")

    client = _setup_client(db_session)
    try:
        client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": 1,
        })

        resp = client.post("/api/basic/channel-company-mappings", json={
            "channel_id": 1, "party_info_id": None,
        })
        assert resp.status_code == 200

        resp2 = client.get("/api/basic/channel-company-mappings")
        assert resp2.json()["data"] == []
    finally:
        _teardown()
