"""Tests for publisher game mapping (project_code / project_name)."""
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend import models
from backend.main import app
from backend.database import get_db


@pytest.mark.asyncio
async def test_project_fields_default_to_null(db_session):
    """New publisher-game mapping should have null project_code and project_name."""
    pub = models.Publisher(publisher_name="测试研发商户")
    db_session.add(pub)
    await db_session.flush()

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001")
    db_session.add(mapping)
    await db_session.commit()

    row = (await db_session.execute(
        select(models.PublisherGameMapping).where(
            models.PublisherGameMapping.publisher_id == pub.publisher_id,
            models.PublisherGameMapping.game_id == "G001",
        )
    )).scalar_one()

    assert row.project_code is None
    assert row.project_name is None


@pytest.mark.asyncio
async def test_update_project_fields(db_session):
    """Updating project_code and project_name should persist."""
    pub = models.Publisher(publisher_name="测试研发商户")
    db_session.add(pub)
    await db_session.flush()

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001")
    db_session.add(mapping)
    await db_session.commit()

    # Update project fields
    mapping.project_code = "PROJ-001"
    mapping.project_name = "测试项目A"
    await db_session.commit()
    await db_session.refresh(mapping)

    assert mapping.project_code == "PROJ-001"
    assert mapping.project_name == "测试项目A"


@pytest.mark.asyncio
async def test_channel_settlement_shows_project_fields(db_session):
    """Channel settlement results should include project_code and project_name from mapping."""
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    )
    db_session.add(mapping)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏中心", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()

    txn = models.RawSettlement(
        channel_id=cat.channel_id, channel_name="应用商店",
        game_id="G001", game_name="测试游戏", month="2025-01",
        raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db_session.add(txn)
    await db_session.flush()

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(2025, 1, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    from backend.services.settlement_service import query_income_settlement
    results = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")

    assert len(results) == 1
    assert results[0]["game_id"] == "G001"
    assert results[0]["project_code"] == "PROJ-001"
    assert results[0]["project_name"] == "测试项目A"


@pytest.mark.asyncio
async def test_publisher_settlement_shows_project_fields(db_session):
    """Publisher settlement results should include project_code and project_name expanded by project."""
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    )
    db_session.add(mapping)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏中心", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()

    txn = models.RawSettlement(
        channel_id=cat.channel_id, channel_name="应用商店",
        game_id="G001", game_name="测试游戏", month="2025-01",
        raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db_session.add(txn)
    await db_session.flush()

    cfg = models.PaymentSplitConfig(
        publisher_id=pub.publisher_id, game_id="G001",
        split_rate=Decimal("0.7"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.05"),
        effective_from=date(2025, 1, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    from backend.services.settlement_service import query_payment_settlement
    results = await query_payment_settlement(db_session, start_month="2025-01", end_month="2025-01")

    assert len(results) >= 1
    match = [r for r in results if r["game_id"] == "G001" and r["publisher_name"] == "测试研发"]
    assert len(match) == 1
    assert match[0]["project_code"] == "PROJ-001"
    assert match[0]["project_name"] == "测试项目A"


@pytest.mark.asyncio
async def test_batch_create_new_mapping(db_session):
    """POST /basic/publishers/games/batch 无已有映射时创建新记录."""
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=1.0)
    publisher = models.Publisher(publisher_name="测试研发商")
    db_session.add_all([game, publisher])
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/publishers/games/batch", json=[{
            "publisher_id": publisher.publisher_id,
            "game_id": "G001",
            "project_code": "25001",
            "project_name": "测试项目",
        }])
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.clear()

    mapping = (await db_session.execute(
        select(models.PublisherGameMapping).where(
            models.PublisherGameMapping.publisher_id == publisher.publisher_id,
            models.PublisherGameMapping.game_id == "G001",
        )
    )).scalar_one_or_none()
    assert mapping is not None
    assert mapping.project_code == "25001"
    assert mapping.project_name == "测试项目"


@pytest.mark.asyncio
async def test_batch_update_existing_mapping(db_session):
    """POST /basic/publishers/games/batch 已有映射时更新 project 字段."""
    pub = models.Publisher(publisher_name="测试研发商")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=1.0)
    db_session.add_all([pub, game])
    await db_session.flush()

    mapping = models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="旧编号", project_name="旧名称",
    )
    db_session.add(mapping)
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/publishers/games/batch", json=[{
            "publisher_id": pub.publisher_id,
            "game_id": "G001",
            "project_code": "新编号",
            "project_name": "新名称",
        }])
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    await db_session.refresh(mapping)
    assert mapping.project_code == "新编号"
    assert mapping.project_name == "新名称"



@pytest.mark.asyncio
async def test_delete_existing_mapping(db_session):
    """POST /basic/publishers/games/delete 删除已有映射后列表不再返回."""
    pub = models.Publisher(publisher_name="测试研发商")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=1.0)
    db_session.add_all([pub, game])
    await db_session.flush()

    mapping = models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ", project_name="待删除项目",
    )
    db_session.add(mapping)
    await db_session.commit()
    mapping_id = mapping.id

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/publishers/games/delete", json=[{
            "publisher_id": pub.publisher_id,
            "game_id": "G001",
        }])
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.clear()

    remaining = (await db_session.execute(
        select(models.PublisherGameMapping).where(
            models.PublisherGameMapping.publisher_id == pub.publisher_id,
        )
    )).scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_mapping(db_session):
    """POST /basic/publishers/games/delete 删除不存在的映射应返回成功(幂等)."""
    pub = models.Publisher(publisher_name="测试研发商")
    db_session.add(pub)
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/publishers/games/delete", json=[{
            "publisher_id": pub.publisher_id,
            "game_id": "NOT_EXIST",
        }])
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.clear()
