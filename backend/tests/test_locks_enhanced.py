"""Tests for enhanced locking: channel_locks + publisher_locks + audit."""
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from backend import models
from backend.services.settlement_service import query_income_settlement
from backend.routers.settlement import lock_settlement_value
from backend.schemas import LockRequest


async def _seed_rs(db, channel_id, game_id, month, raw_revenue, **kw):
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=kw.get("channel_name", "测试渠道"),
        game_name=kw.get("game_name", "测试游戏"),
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


@pytest.mark.asyncio
async def test_channel_lock_persisted_and_queried(db_session):
    """Lock via API writes to channel_locks; query sees the locked value."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    req = LockRequest(game_id="G001", channel_id=1, month="2026-05",
                      field="settlement_amount", value="4200")
    result = await lock_settlement_value(req, db_session)
    assert result["status"] == "locked"
    assert result["value"] == 4200.0

    ded = await db_session.execute(
        select(models.Deduction).where(
            models.Deduction.channel_id == 1,
            models.Deduction.game_id == "G001",
            models.Deduction.month == "2026-05",
        )
    )
    assert ded.scalar_one_or_none() is None

    lock = await db_session.execute(
        select(models.ChannelLock).where(
            models.ChannelLock.channel_id == 1,
            models.ChannelLock.game_id == "G001",
            models.ChannelLock.month == "2026-05",
        )
    )
    assert lock.scalar_one().locked_settlement_amount == Decimal("4200")


@pytest.mark.asyncio
async def test_channel_lock_unlock_returns_formula_value(db_session):
    """Unlock returns the formula-calculated real_revenue."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("10000"))
    await db_session.commit()

    req = LockRequest(game_id="G001", channel_id=1, month="2026-06",
                      field="real_revenue", value="7000")
    await lock_settlement_value(req, db_session)

    req2 = LockRequest(game_id="G001", channel_id=1, month="2026-06",
                       field="real_revenue", value="=")
    result = await lock_settlement_value(req2, db_session)
    assert result["status"] == "unlocked"
    assert result["formula_value"] == 8000.0  # 10000 * 0.8


@pytest.mark.asyncio
async def test_publisher_lock_returns_formula_on_unlock(db_session):
    """Publisher unlock returns formula_value."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ch"))
    db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    db_session.add(models.PublisherGameMapping(publisher_id=1, game_id="G001"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("20000"))
    db_session.add(models.PaymentSplitConfig(
        publisher_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        fixed_fee=Decimal("0"),
    ))
    await db_session.commit()

    req = LockRequest(game_id="G001", publisher_name="测试CP", month="2026-06",
                      field="settlement_amount", value="5000")
    result = await lock_settlement_value(req, db_session)
    assert result["status"] == "locked"

    lock = (await db_session.execute(
        select(models.PublisherLock).where(
            models.PublisherLock.publisher_id == 1,
            models.PublisherLock.game_id == "G001",
            models.PublisherLock.month == "2026-06",
        )
    )).scalar_one()
    assert lock.locked_settlement_amount == Decimal("5000")

    req2 = LockRequest(game_id="G001", publisher_name="测试CP", month="2026-06",
                       field="settlement_amount", value="=")
    result2 = await lock_settlement_value(req2, db_session)
    assert result2["status"] == "unlocked"
    assert result2["formula_value"] == 8000.0  # 20000*0.8=16000, 16000*0.5=8000


@pytest.mark.asyncio
async def test_publisher_lock_creates_row_when_missing(db_session):
    """Publisher lock auto-creates PublisherLock row."""
    db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    await db_session.commit()

    req = LockRequest(game_id="G001", publisher_name="测试CP", month="2026-07",
                      field="real_revenue", value="3000")
    result = await lock_settlement_value(req, db_session)
    assert result["status"] == "locked"
    assert result["value"] == 3000.0

    lock = (await db_session.execute(
        select(models.PublisherLock).where(
            models.PublisherLock.publisher_id == 1,
            models.PublisherLock.game_id == "G001",
            models.PublisherLock.month == "2026-07",
        )
    )).scalar_one()
    assert lock.locked_real_revenue == Decimal("3000")


@pytest.mark.asyncio
async def test_lock_writes_audit_log(db_session):
    """Lock and unlock operations write audit_logs entries."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    await db_session.commit()

    req = LockRequest(game_id="G001", channel_id=1, month="2026-08",
                      field="real_revenue", value="5500")
    await lock_settlement_value(req, db_session)

    req2 = LockRequest(game_id="G001", channel_id=1, month="2026-08",
                       field="real_revenue", value="=")
    await lock_settlement_value(req2, db_session)

    logs = (await db_session.execute(
        select(models.AuditLog).order_by(models.AuditLog.id)
    )).scalars().all()
    assert len(logs) == 2
    assert logs[0].action == "settlement.lock"
    assert "5500" in logs[0].detail
    assert logs[1].action == "settlement.unlock"


@pytest.mark.asyncio
async def test_query_income_reads_channel_locks(db_session):
    """ChannelLock locked_real_revenue overrides formula-calculated value."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("10000"))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-06",
        vouchers=0, test=0, welfare=0, bad_debt=0,
    ))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-06",
        locked_real_revenue=Decimal("7000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    await db_session.commit()

    results = await query_income_settlement(db_session, "2026-06", "2026-06")
    assert len(results) == 1
    r = results[0]
    assert r["real_revenue"] == 7000.0  # locked, not 8000
    assert r["locked_real_revenue"] == 7000.0
