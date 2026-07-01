"""Tests for income/payment split config GET endpoints."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db
from backend import models


@pytest.mark.asyncio
async def test_income_split_config_empty(db_session):
    """GET /api/settlement/income-split-configs 无数据时返回空列表."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/settlement/income-split-configs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_income_split_config_with_data(db_session):
    """GET income-split-configs 返回含渠道名称、游戏名称的数据."""
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=1.0)
    channel = models.ChannelCategory(channel_name="测试渠道")
    db_session.add_all([game, channel])
    await db_session.commit()

    cfg = models.IncomeSplitConfig(
        channel_id=channel.channel_id,
        game_id="G001",
        split_rate=0.5,
        channel_fee_rate=0.1,
        tax_rate=0.05,
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )
    db_session.add(cfg)
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/settlement/income-split-configs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        row = data[0]
        assert row["channel_name"] == "测试渠道"
        assert row["game_id"] == "G001"
        assert row["game_name"] == "测试游戏"
        assert row["split_rate"] == 0.5
        assert row["channel_fee_rate"] == 0.1
        assert row["tax_rate"] == 0.05
        assert row["effective_from"] == "2026-01-01"
        assert row["effective_to"] is None
        assert "id" in row
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_payment_split_config_empty(db_session):
    """GET /api/settlement/payment-split-configs 无数据时返回空列表."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/settlement/payment-split-configs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_payment_split_config_with_data(db_session):
    """GET payment-split-configs 返回含研发商名称、游戏名称的数据."""
    game = models.Game(game_id="G002", game_name="另一款游戏", discount_rate=0.9)
    publisher = models.Publisher(publisher_name="测试研发商")
    db_session.add_all([game, publisher])
    await db_session.commit()

    cfg = models.PaymentSplitConfig(
        publisher_id=publisher.publisher_id,
        game_id="G002",
        split_rate=0.4,
        channel_fee_rate=0.05,
        tax_rate=0.03,
        fixed_fee=1000.00,
        effective_from=date(2026, 3, 1),
        effective_to=date(2026, 12, 31),
    )
    db_session.add(cfg)
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/settlement/payment-split-configs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        row = data[0]
        assert row["publisher_name"] == "测试研发商"
        assert row["game_id"] == "G002"
        assert row["game_name"] == "另一款游戏"
        assert row["split_rate"] == 0.4
        assert row["channel_fee_rate"] == 0.05
        assert row["tax_rate"] == 0.03
        assert row["fixed_fee"] == 1000.00
        assert row["effective_from"] == "2026-03-01"
        assert row["effective_to"] == "2026-12-31"
        assert "id" in row
    finally:
        app.dependency_overrides.clear()
