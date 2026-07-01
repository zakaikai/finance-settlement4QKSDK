"""Tests for settlement inline editing: query → save → re-query."""
import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import select
from backend import models


async def _seed_rs(db, channel_id, game_id, month, raw_revenue, **kw):
    """Seed RawSettlement for settlement query tests (replacement for ChannelSettlement)."""
    from sqlalchemy import select
    game_row = (await db.execute(
        select(models.Game.game_name).where(models.Game.game_id == game_id)
    )).first()
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=kw.get("channel_name", "应用商店"),
        game_name=game_row[0] if game_row else game_id,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)
    return rs


@pytest.mark.asyncio
async def test_income_settlement_returns_deduction_fields(db_session):
    """收入结算查询应返回分项扣除字段及分成配置字段."""
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "G001", "2025-01", Decimal("10000"))

    ded = models.Deduction(
        channel_id=cat.channel_id, game_id="G001", month="2025-01",
        vouchers=Decimal("500"), test=Decimal("200"), welfare=Decimal("100"), bad_debt=Decimal("50"),
    )
    db_session.add(ded)

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
    r = results[0]

    assert r["vouchers"] == 500.0
    assert r["test"] == 200.0
    assert r["welfare"] == 100.0
    assert r["bad_debt"] == 50.0
    assert r["total_deductions"] == 850.0

    assert r["split_rate"] == 0.5
    assert r["channel_fee_rate"] == 0.05
    assert r["tax_rate"] == 0.06


@pytest.mark.asyncio
async def test_income_save_deductions_then_requery(db_session):
    """保存扣除后重新查询应反映更新值."""
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "G001", "2025-01", Decimal("10000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(2025, 1, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    from backend.services.settlement_service import query_income_settlement

    results = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")
    r = results[0]
    assert r["vouchers"] == 0.0
    assert r["test"] == 0.0
    assert r["welfare"] == 0.0
    assert r["bad_debt"] == 0.0
    assert r["total_deductions"] == 0.0

    existing = (await db_session.execute(
        select(models.Deduction).where(
            models.Deduction.channel_id == cat.channel_id,
            models.Deduction.game_id == "G001",
            models.Deduction.month == "2025-01",
        )
    )).scalar_one_or_none()

    if existing:
        existing.vouchers = Decimal("500")
        existing.test = Decimal("200")
        existing.welfare = Decimal("100")
        existing.bad_debt = Decimal("50")
    else:
        ded = models.Deduction(
            channel_id=cat.channel_id, game_id="G001", month="2025-01",
            vouchers=Decimal("500"), test=Decimal("200"),
            welfare=Decimal("100"), bad_debt=Decimal("50"),
        )
        db_session.add(ded)
    await db_session.commit()

    results2 = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")
    r2 = results2[0]
    assert r2["vouchers"] == 500.0
    assert r2["test"] == 200.0
    assert r2["welfare"] == 100.0
    assert r2["bad_debt"] == 50.0
    assert r2["total_deductions"] == 850.0


@pytest.mark.asyncio
async def test_income_save_split_config_then_requery(db_session):
    """保存收入分成配置后重新查询应反映更新值."""
    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "G001", "2025-01", Decimal("10000"))
    await db_session.commit()

    from backend.services.settlement_service import query_income_settlement

    results = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")
    r = results[0]
    assert r["split_rate"] is None
    assert r["channel_fee_rate"] is None
    assert r["tax_rate"] is None
    assert r["settlement_amount"] is None

    existing = (await db_session.execute(
        select(models.IncomeSplitConfig).where(
            models.IncomeSplitConfig.channel_id == cat.channel_id,
            models.IncomeSplitConfig.game_id == "G001",
        )
    )).scalar_one_or_none()

    if existing:
        existing.split_rate = Decimal("0.5")
        existing.channel_fee_rate = Decimal("0.05")
        existing.tax_rate = Decimal("0.06")
    else:
        cfg = models.IncomeSplitConfig(
            channel_id=cat.channel_id, game_id="G001",
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
            effective_from=date(2025, 1, 1),
        )
        db_session.add(cfg)
    await db_session.commit()

    results2 = await query_income_settlement(db_session, start_month="2025-01", end_month="2025-01")
    r2 = results2[0]
    assert r2["split_rate"] == 0.5
    assert r2["channel_fee_rate"] == 0.05
    assert r2["tax_rate"] == 0.06
    assert r2["settlement_amount"] is not None


@pytest.mark.asyncio
async def test_payment_settlement_returns_deduction_fields(db_session):
    """付款结算查询应返回分项扣除字段."""
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001")
    db_session.add(mapping)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "G001", "2025-01", Decimal("10000"))

    ded = models.Deduction(
        channel_id=cat.channel_id, game_id="G001", month="2025-01",
        vouchers=Decimal("300"), test=Decimal("100"), welfare=Decimal("50"), bad_debt=Decimal("20"),
    )
    db_session.add(ded)

    cfg = models.PaymentSplitConfig(
        publisher_id=pub.publisher_id, game_id="G001",
        split_rate=Decimal("0.7"), channel_fee_rate=Decimal("0.03"), tax_rate=Decimal("0.04"),
        effective_from=date(2025, 1, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    from backend.services.settlement_service import query_payment_settlement
    results = await query_payment_settlement(db_session, start_month="2025-01", end_month="2025-01")

    match = [r for r in results if r["game_id"] == "G001" and r["publisher_name"] == "测试研发"]
    assert len(match) == 1
    r = match[0]

    assert r["vouchers"] == 300.0
    assert r["test"] == 100.0
    assert r["welfare"] == 50.0
    assert r["bad_debt"] == 20.0
    assert r["total_deductions"] == 470.0
    assert r["split_rate"] == 0.7
    assert r["channel_fee_rate"] == 0.03
    assert r["tax_rate"] == 0.04


@pytest.mark.asyncio
async def test_payment_save_split_config_then_requery(db_session):
    """保存付款分成配置后重新查询应反映更新值."""
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)

    game = models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.7"))
    db_session.add(game)
    await db_session.flush()

    mapping = models.PublisherGameMapping(publisher_id=pub.publisher_id, game_id="G001")
    db_session.add(mapping)

    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "G001", "2025-01", Decimal("10000"))
    await db_session.commit()

    from backend.services.settlement_service import query_payment_settlement

    results = await query_payment_settlement(db_session, start_month="2025-01", end_month="2025-01")
    match = [r for r in results if r["game_id"] == "G001" and r["publisher_name"] == "测试研发"]
    assert len(match) == 1
    r = match[0]
    assert r["split_rate"] is None
    assert r["settlement_amount"] is None

    existing = (await db_session.execute(
        select(models.PaymentSplitConfig).where(
            models.PaymentSplitConfig.publisher_id == pub.publisher_id,
            models.PaymentSplitConfig.game_id == "G001",
        )
    )).scalar_one_or_none()

    if existing:
        existing.split_rate = Decimal("0.7")
        existing.channel_fee_rate = Decimal("0.03")
        existing.tax_rate = Decimal("0.04")
    else:
        cfg = models.PaymentSplitConfig(
            publisher_id=pub.publisher_id, game_id="G001",
            split_rate=Decimal("0.7"), channel_fee_rate=Decimal("0.03"), tax_rate=Decimal("0.04"),
            effective_from=date(2025, 1, 1),
        )
        db_session.add(cfg)
    await db_session.commit()

    results2 = await query_payment_settlement(db_session, start_month="2025-01", end_month="2025-01")
    match2 = [r for r in results2 if r["game_id"] == "G001" and r["publisher_name"] == "测试研发"]
    assert len(match2) == 1
    r2 = match2[0]
    assert r2["split_rate"] == 0.7
    assert r2["channel_fee_rate"] == 0.03
    assert r2["tax_rate"] == 0.04
    assert r2["settlement_amount"] is not None
