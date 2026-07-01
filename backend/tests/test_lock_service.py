"""Direct unit tests for lock_service module."""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.lock_service import (
    apply_lock,
    remove_lock,
    compute_unlocked_value,
    resolve_locked_values,
    get_lock,
    _get_cfg,
)


async def _seed_rs(db, channel_id=1, game_id="G001", month="2026-06", raw_revenue=Decimal("10000"), **kw):
    """Seed RawSettlement for lock tests."""
    from sqlalchemy import select
    game = (await db.execute(
        select(models.Game.game_name, models.Game.discount_rate)
        .where(models.Game.game_id == game_id)
    )).first()
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=f"渠道{channel_id}",
        game_name=game[0] if game else game_id, month=month,
        raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


# ── resolve_locked_values (pure function) ──

def test_resolve_locked_values_returns_locked_values():
    lock = models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-06",
        locked_real_revenue=Decimal("7000"),
        locked_settlement_amount=Decimal("4200"),
        created_at="now", updated_at="now",
    )
    lock_map = {(1, "G001", "2026-06"): lock}
    real, amt = resolve_locked_values(lock_map, (1, "G001", "2026-06"))
    assert real == Decimal("7000")
    assert amt == Decimal("4200")


def test_resolve_locked_values_returns_none_for_missing():
    lock_map = {}
    real, amt = resolve_locked_values(lock_map, (1, "G001", "2026-06"))
    assert real is None
    assert amt is None


def test_resolve_locked_values_handles_partial_nulls():
    lock = models.PublisherLock(
        publisher_id=1, game_id="G001", month="2026-07",
        locked_real_revenue=Decimal("5000"),
        locked_settlement_amount=None,
        created_at="now", updated_at="now",
    )
    lock_map = {(1, "G001", "2026-07"): lock}
    real, amt = resolve_locked_values(lock_map, (1, "G001", "2026-07"))
    assert real == Decimal("5000")
    assert amt is None


# ── Channel lock (apply + remove) ──

@pytest.mark.asyncio
async def test_apply_lock_channel_creates_row(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    await db_session.commit()

    result = await apply_lock(
        db_session, "channel", entity_id=1, game_id="G001",
        month="2026-05", field="real_revenue", value=Decimal("7000"),
        now="2026-01-01 00:00:00", audit_name="channel_id=1",
    )
    assert result["status"] == "locked"
    assert result["value"] == 7000.0

    lock = await get_lock(db_session, "channel", 1, "G001", "2026-05")
    assert lock is not None
    assert lock.locked_real_revenue == Decimal("7000")
    assert lock.locked_settlement_amount is None


@pytest.mark.asyncio
async def test_apply_lock_channel_updates_existing(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-06",
        locked_real_revenue=Decimal("3000"),
        created_at="old", updated_at="old",
    ))
    await db_session.commit()

    result = await apply_lock(
        db_session, "channel", entity_id=1, game_id="G001",
        month="2026-06", field="real_revenue", value=Decimal("9999"),
        now="2026-02-01 00:00:00", audit_name="channel_id=1",
    )
    assert result["value"] == 9999.0

    lock = await get_lock(db_session, "channel", 1, "G001", "2026-06")
    assert lock.locked_real_revenue == Decimal("9999")


@pytest.mark.asyncio
async def test_remove_lock_channel_returns_formula(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-06",
        locked_real_revenue=Decimal("7000"),
        created_at="now", updated_at="now",
    ))
    await db_session.commit()
    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("10000"))
    await db_session.commit()

    result = await remove_lock(
        db_session, "channel", entity_id=1, game_id="G001",
        month="2026-06", field="real_revenue",
        now="2026-03-01 00:00:00", audit_name="channel_id=1",
    )
    assert result["status"] == "unlocked"
    assert result["formula_value"] == 8000.0  # 10000 * 0.8

    lock = await get_lock(db_session, "channel", 1, "G001", "2026-06")
    assert lock.locked_real_revenue is None


# ── Publisher lock (apply + remove) ──

@pytest.mark.asyncio
async def test_apply_lock_publisher_creates_row(db_session):
    db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    await db_session.commit()

    result = await apply_lock(
        db_session, "publisher", entity_id=1, game_id="G001",
        month="2026-05", field="settlement_amount", value=Decimal("5000"),
        now="2026-01-01 00:00:00", audit_name="测试CP",
    )
    assert result["status"] == "locked"
    assert result["value"] == 5000.0

    lock = await get_lock(db_session, "publisher", 1, "G001", "2026-05")
    assert lock.locked_settlement_amount == Decimal("5000")


@pytest.mark.asyncio
async def test_remove_lock_publisher_returns_formula(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ch"))
    db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.PaymentSplitConfig(
        publisher_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        fixed_fee=Decimal("0"),
    ))
    db_session.add(models.PublisherLock(
        publisher_id=1, game_id="G001", month="2026-06",
        locked_settlement_amount=Decimal("5000"),
        created_at="now", updated_at="now",
    ))
    await db_session.commit()
    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("20000"))
    await db_session.commit()

    result = await remove_lock(
        db_session, "publisher", entity_id=1, game_id="G001",
        month="2026-06", field="settlement_amount",
        now="2026-04-01 00:00:00", audit_name="测试CP",
    )
    assert result["status"] == "unlocked"
    assert result["formula_value"] == 8000.0  # 20000*0.8=16000, 16000*0.5=8000


# ── compute_unlocked_value (read-only) ──

@pytest.mark.asyncio
async def test_compute_unlocked_value_channel(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()
    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("10000"))
    await db_session.commit()

    val = await compute_unlocked_value(db_session, "channel", 1, "G001", "2026-06", "settlement_amount")
    assert val == 4000.0  # 10000*0.8=8000, 8000*0.5=4000


@pytest.mark.asyncio
async def test_compute_unlocked_value_publisher(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ch"))
    db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.PaymentSplitConfig(
        publisher_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        fixed_fee=Decimal("0"),
    ))
    await db_session.commit()
    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("20000"))
    await db_session.commit()

    val = await compute_unlocked_value(db_session, "publisher", 1, "G001", "2026-06", "real_revenue")
    assert val == 16000.0  # 20000 * 0.8


# ── get_lock ──

@pytest.mark.asyncio
async def test_get_lock_returns_none_when_missing(db_session):
    lock = await get_lock(db_session, "channel", 999, "G999", "2099-01")
    assert lock is None


@pytest.mark.asyncio
async def test_get_lock_returns_existing(db_session):
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-09",
        locked_real_revenue=Decimal("1234"),
        created_at="now", updated_at="now",
    ))
    await db_session.commit()

    lock = await get_lock(db_session, "channel", 1, "G001", "2026-09")
    assert lock.locked_real_revenue == Decimal("1234")


# ── Error handling ──

def test_unknown_lock_type_raises():
    with pytest.raises(ValueError, match="Unknown lock_type"):
        _get_cfg("invalid")
