"""Tests for company-game mapping (project-code driven)."""
import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend import models
from backend.main import app
from backend.database import get_db


@pytest.mark.asyncio
async def test_batch_creates_mappings_from_project_code(db_session):
    """POST /basic/companies/games/batch 根据 project_code 展开所有 game_id 批量关联."""
    # Setup: company, publisher, 2 games under same project
    company = models.Company(company_name="测试公司")
    db_session.add(company)
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)
    game1 = models.Game(game_id="G001", game_name="游戏1", discount_rate=Decimal("0.7"))
    game2 = models.Game(game_id="G002", game_name="游戏2", discount_rate=Decimal("0.7"))
    db_session.add_all([game1, game2])
    await db_session.flush()

    # Create publisher_game_mapping with same project_code for both games
    db_session.add_all([
        models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001",
                                    project_code="PROJ-001", project_name="测试项目A"),
        models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G002",
                                    project_code="PROJ-001", project_name="测试项目A"),
    ])
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/companies/games/batch", json=[{
            "company_id": company.company_id,
            "project_code": "PROJ-001",
        }])
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["game_count"] == 2
    finally:
        app.dependency_overrides.clear()

    # Verify both mappings exist
    mappings = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == company.company_id,
        )
    )).scalars().all()
    assert len(mappings) == 2
    game_ids = {m.game_id for m in mappings}
    assert game_ids == {"G001", "G002"}


@pytest.mark.asyncio
async def test_batch_idempotent(db_session):
    """重复调用不应创建重复映射."""
    company = models.Company(company_name="测试公司")
    pub = models.Publisher(publisher_name="测试研发")
    game = models.Game(game_id="G001", game_name="游戏1", discount_rate=Decimal("0.7"))
    db_session.add_all([company, pub, game])
    await db_session.flush()
    db_session.add(models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    ))
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        # Call twice
        for _ in range(2):
            resp = client.post("/api/basic/companies/games/batch", json=[{
                "company_id": company.company_id,
                "project_code": "PROJ-001",
            }])
            assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Only one mapping should exist
    count = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == company.company_id,
        )
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_batch_overwrite_reassigns_game_to_new_company(db_session):
    """项目级覆盖模式：绑定到其他公司的游戏被覆盖为新公司."""
    comp_a = models.Company(company_name="公司A")
    comp_b = models.Company(company_name="公司B")
    pub = models.Publisher(publisher_name="测试研发")
    game = models.Game(game_id="G001", game_name="游戏1", discount_rate=Decimal("0.7"))
    db_session.add_all([comp_a, comp_b, pub, game])
    await db_session.flush()
    db_session.add(models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    ))
    db_session.add(models.CompanyGameMapping(company_id=comp_a.company_id, game_id="G001"))
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/companies/games/batch", json=[{
            "company_id": comp_b.company_id,
            "project_code": "PROJ-001",
        }])
        assert resp.status_code == 200
        assert resp.json()["game_count"] == 1
    finally:
        app.dependency_overrides.clear()

    # Company A no longer has G001 (overwritten)
    a_maps = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == comp_a.company_id,
        )
    )).scalars().all()
    assert len(a_maps) == 0

    # Company B now has G001
    b_maps = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == comp_b.company_id,
        )
    )).scalars().all()
    assert len(b_maps) == 1


@pytest.mark.asyncio
async def test_income_settlement_shows_company_name(db_session):
    """收入结算结果应包含我方公司名称."""
    company = models.Company(company_name="测试公司")
    pub = models.Publisher(publisher_name="测试研发")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add_all([company, pub, game])
    await db_session.flush()

    # Link company → game
    db_session.add(models.CompanyGameMapping(company_id=company.company_id, game_id="G001"))
    # Publisher mapping for project
    db_session.add(models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    ))
    # Channel hierarchy
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏中心", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()
    # Raw settlement + split config (no hierarchy needed)
    db_session.add(models.RawSettlement(
        channel_id=cat.channel_id, channel_name="应用商店",
        game_id="G001", game_name="测试游戏", month="2025-01",
        raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    db_session.add(models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(2025, 1, 1),
    ))
    await db_session.commit()

    from backend.services.settlement_service import query_income_settlement
    results = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")

    assert len(results) == 1
    assert results[0]["company_name"] == "测试公司"


@pytest.mark.asyncio
async def test_payment_settlement_shows_company_name(db_session):
    """付款结算结果应包含我方公司名称."""
    company = models.Company(company_name="测试公司")
    pub = models.Publisher(publisher_name="测试研发")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add_all([company, pub, game])
    await db_session.flush()

    db_session.add(models.CompanyGameMapping(company_id=company.company_id, game_id="G001"))
    db_session.add(models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    ))
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏中心", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()
    db_session.add(models.RawSettlement(
        channel_id=cat.channel_id, channel_name="应用商店",
        game_id="G001", game_name="测试游戏", month="2025-01",
        raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    db_session.add(models.PaymentSplitConfig(
        publisher_id=pub.publisher_id, game_id="G001",
        split_rate=Decimal("0.7"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.05"),
        effective_from=date(2025, 1, 1),
    ))
    await db_session.commit()

    from backend.services.settlement_service import query_payment_settlement
    results = await query_payment_settlement(db_session, start_month="2025-01", end_month="2025-01")

    match = [r for r in results if r["game_id"] == "G001" and r["publisher_name"] == "测试研发"]
    assert len(match) == 1
    assert match[0]["company_name"] == "测试公司"


@pytest.mark.asyncio
async def test_settlement_company_empty_when_no_mapping(db_session):
    """未建立 company_game_mapping 时 company_name 应为空字符串."""
    pub = models.Publisher(publisher_name="测试研发")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add_all([pub, game])
    await db_session.flush()
    db_session.add(models.PublisherGameMapping(
        publisher_id=pub.publisher_id, game_id="G001",
        project_code="PROJ-001", project_name="测试项目A",
    ))
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏中心", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()
    db_session.add(models.RawSettlement(
        channel_id=cat.channel_id, channel_name="应用商店",
        game_id="G001", game_name="测试游戏", month="2025-01",
        raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    db_session.add(models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(2025, 1, 1),
    ))
    await db_session.commit()

    from backend.services.settlement_service import query_income_settlement
    results = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")

    assert len(results) == 1
    assert results[0]["company_name"] == ""


@pytest.mark.asyncio
async def test_delete_company_game_removes_mapping(db_session):
    """POST /basic/companies/games/delete 删除已有关联."""
    company = models.Company(company_name="测试公司")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add_all([company, game])
    await db_session.flush()
    db_session.add(models.CompanyGameMapping(company_id=company.company_id, game_id="G001"))
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.post("/api/basic/companies/games/delete", json=[{
            "company_id": company.company_id,
            "game_id": "G001",
        }])
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.clear()

    remaining = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == company.company_id,
        )
    )).scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_project_codes_endpoint(db_session):
    """GET /basic/project-codes 返回所有去重 project_code."""
    pub = models.Publisher(publisher_name="测试研发")
    game1 = models.Game(game_id="G001", game_name="游戏1", discount_rate=Decimal("0.7"))
    game2 = models.Game(game_id="G002", game_name="游戏2", discount_rate=Decimal("0.7"))
    db_session.add_all([pub, game1, game2])
    await db_session.flush()
    db_session.add_all([
        models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001",
                                    project_code="PROJ-A", project_name="项目A"),
        models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G002",
                                    project_code="PROJ-B", project_name="项目B"),
    ])
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        resp = client.get("/api/basic/project-codes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        codes = {d["project_code"] for d in data}
        assert "PROJ-A" in codes
        assert "PROJ-B" in codes
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_company_game_with_channel_id(db_session):
    """DELETE 按渠道粒度: 只删除指定 channel 的绑定, 不影响 NULL 兜底."""
    company = models.Company(company_name="测试公司")
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    cat = models.ChannelCategory(channel_id=5, channel_name="特定渠道")
    db_session.add_all([company, game, cat])
    await db_session.flush()

    # 创建两个绑定: channel=NULL (兜底) + channel=5 (渠道级)
    db_session.add(models.CompanyGameMapping(company_id=company.company_id, game_id="G001", channel_id=None))
    db_session.add(models.CompanyGameMapping(company_id=company.company_id, game_id="G001", channel_id=5))
    await db_session.commit()

    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))
    try:
        # 删除 channel=5 的绑定
        resp = client.post("/api/basic/companies/games/delete", json=[{
            "company_id": company.company_id,
            "game_id": "G001",
            "channel_id": 5,
        }])
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    finally:
        app.dependency_overrides.clear()

    # NULL 兜底应该还在
    remaining = (await db_session.execute(
        select(models.CompanyGameMapping).where(
            models.CompanyGameMapping.company_id == company.company_id,
        )
    )).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].channel_id is None
