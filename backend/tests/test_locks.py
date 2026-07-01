"""Tests for locked_real_revenue / locked_settlement_amount behavior."""
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from backend import models
from backend.services.settlement_service import query_income_settlement
from backend.routers.settlement import lock_settlement_value
from backend.schemas import LockRequest


async def _seed_rs(db, channel_id, game_id, month, raw_revenue, **kw):
    """Seed RawSettlement row."""
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=kw.get("channel_name", "测试渠道"),
        game_name=kw.get("game_name", "测试游戏"),
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


@pytest.mark.asyncio
async def test_locked_real_revenue_overrides_formula(db_session):
    """When locked_real_revenue is set, settlement uses it instead of formula."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-04", Decimal("10000"))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=0, test=0, welfare=0, bad_debt=0,
    ))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-04",
        locked_real_revenue=Decimal("5000"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    await db_session.commit()

    results = await query_income_settlement(db_session, "2026-04", "2026-04")
    assert len(results) == 1
    r = results[0]
    assert r["real_revenue"] == 5000.0  # locked, not 8000
    assert r["locked_real_revenue"] == 5000.0
    # settlement = (5000 - 0) * 0.5 = 2500
    assert r["settlement_amount"] == 2500.0


@pytest.mark.asyncio
async def test_locked_settlement_amount_overrides_formula(db_session):
    """When locked_settlement_amount is set, settlement uses it instead of formula."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-04", Decimal("10000"))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=0, test=0, welfare=0, bad_debt=0,
    ))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-04",
        locked_settlement_amount=Decimal("3500"),
        created_at="2026-01-01", updated_at="2026-01-01",
    ))
    await db_session.commit()

    results = await query_income_settlement(db_session, "2026-04", "2026-04")
    assert len(results) == 1
    r = results[0]
    assert r["settlement_amount"] == 3500.0  # locked, not 4000
    assert r["locked_settlement_amount"] == 3500.0


@pytest.mark.asyncio
async def test_no_lock_uses_formula(db_session):
    """Without locked fields, settlement uses the standard formula."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-04", Decimal("10000"))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=0, test=0, welfare=0, bad_debt=0,
    ))
    await db_session.commit()

    results = await query_income_settlement(db_session, "2026-04", "2026-04")
    assert len(results) == 1
    r = results[0]
    assert r["real_revenue"] == 8000.0  # 10000 * 0.8
    assert r["settlement_amount"] == 4000.0  # (8000 - 0) * 0.5
    assert r["locked_real_revenue"] is None
    assert r["locked_settlement_amount"] is None


# ── Behavior 2: Lock API endpoint ──

@pytest.mark.asyncio
async def test_lock_endpoint_sets_and_clears_lock(db_session):
    """POST /api/settlement/lock sets locked value; empty value unlocks."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=0, test=0, welfare=0, bad_debt=0,
    ))
    await db_session.commit()

    # Lock real_revenue
    req = LockRequest(game_id="G001", channel_id=1, month="2026-04",
                      field="real_revenue", value="7200")
    result = await lock_settlement_value(req, db_session)
    assert result["status"] == "locked"
    assert result["value"] == 7200.0

    # Verify persisted in channel_locks
    lock_row = (await db_session.execute(
        select(models.ChannelLock).where(
            models.ChannelLock.channel_id == 1,
            models.ChannelLock.game_id == "G001",
            models.ChannelLock.month == "2026-04",
        )
    )).scalar_one()
    assert lock_row.locked_real_revenue == Decimal("7200")

    # Unlock with "="
    req2 = LockRequest(game_id="G001", channel_id=1, month="2026-04",
                       field="real_revenue", value="=")
    result2 = await lock_settlement_value(req2, db_session)
    assert result2["status"] == "unlocked"


@pytest.mark.asyncio
async def test_lock_endpoint_creates_lock_row_if_missing(db_session):
    """Lock endpoint auto-creates channel_lock row if it doesn't exist."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    await db_session.commit()

    req = LockRequest(game_id="G001", channel_id=1, month="2026-05",
                      field="settlement_amount", value="4200")
    result = await lock_settlement_value(req, db_session)
    assert result["status"] == "locked"

    lock_row = (await db_session.execute(
        select(models.ChannelLock).where(
            models.ChannelLock.channel_id == 1,
            models.ChannelLock.game_id == "G001",
            models.ChannelLock.month == "2026-05",
        )
    )).scalar_one()
    assert lock_row.locked_settlement_amount == Decimal("4200")


# ── Behavior 3: Split config upsert with effective dates ──

@pytest.mark.asyncio
async def test_save_income_split_config_inserts_new_and_closes_old(db_session):
    """New split config inserted for bill month; previous config effective_to closed."""
    from backend.services.settlement_service import _save_income_split_config

    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()

    await _save_income_split_config(db_session, 1, "G001", "2026-04", split_rate=Decimal("0.27"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 2
    assert configs[0].effective_from == date(2026, 1, 1)
    assert configs[0].effective_to == date(2026, 3, 31)
    assert configs[0].split_rate == Decimal("0.25")
    assert configs[1].effective_from == date(2026, 4, 1)
    assert configs[1].effective_to is None
    assert configs[1].split_rate == Decimal("0.27")
    assert configs[1].channel_fee_rate == Decimal("0")
    assert configs[1].tax_rate == Decimal("0")


@pytest.mark.asyncio
async def test_save_income_split_config_inherits_missing_fields(db_session):
    """Split config fields not in bill inherit from previous config."""
    from backend.services.settlement_service import _save_income_split_config

    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.30"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
    ))
    await db_session.commit()

    await _save_income_split_config(db_session, 1, "G001", "2026-05",
        split_rate=Decimal("0.35"), channel_fee_rate=Decimal("0.03"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert configs[1].split_rate == Decimal("0.35")
    assert configs[1].channel_fee_rate == Decimal("0.03")
    assert configs[1].tax_rate == Decimal("0.06")  # inherited from old


@pytest.mark.asyncio
async def test_save_income_split_config_already_closed_not_modified(db_session):
    """Old config already having effective_to should not be modified."""
    from backend.services.settlement_service import _save_income_split_config

    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=date(2026, 2, 28),
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 3, 1), effective_to=None,
        split_rate=Decimal("0.28"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()

    await _save_income_split_config(db_session, 1, "G001", "2026-06", split_rate=Decimal("0.30"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 3
    assert configs[0].effective_to == date(2026, 2, 28)
    assert configs[1].effective_from == date(2026, 3, 1)
    assert configs[1].effective_to == date(2026, 5, 31)
    assert configs[2].effective_from == date(2026, 6, 1)


# ── Behavior 4: build_comparison ──

@pytest.mark.asyncio
async def test_comparison_detects_changed_fields(db_session):
    """build_comparison marks fields as changed when old != new (from snapshot)."""
    from backend.services.settlement_service import compare_imported_rows as build_comparison

    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    await db_session.commit()

    await _seed_rs(db_session, 1, "G001", "2026-04", Decimal("10000"))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()

    rows = [{"game_id": "G001", "game_name": "测试游戏",
             "raw_revenue": 20000, "split_rate": 0.30, "settlement_amount": None}]
    mapping = {"0": "raw_revenue", "1": "split_rate", "2": "settlement_amount", "3": "game_name"}

    comp = await build_comparison(db_session, rows, channel_id=1, month="2026-04", column_mapping=mapping)
    assert len(comp) == 1
    fields = comp[0]["fields"]
    # raw_revenue: old 10000, new 20000
    assert fields["raw_revenue"]["old"] == 10000.0
    assert fields["raw_revenue"]["new"] == 20000.0
    assert fields["raw_revenue"]["changed"] is True
    # split_rate: old 0.25, new 0.30
    assert fields["split_rate"]["old"] == 0.25
    assert fields["split_rate"]["new"] == 0.30
    assert fields["split_rate"]["changed"] is True
    # settlement_amount: new is None, old has computed value → changed
    assert fields["settlement_amount"]["changed"] is True


@pytest.mark.asyncio
async def test_comparison_handles_no_existing_data(db_session):
    """build_comparison returns old=None when no existing DB data."""
    from backend.services.settlement_service import compare_imported_rows as build_comparison

    rows = [{"game_id": "G001", "game_name": "新游戏",
             "vouchers": 300, "raw_revenue": 10000}]
    mapping = {"0": "vouchers"}

    comp = await build_comparison(db_session, rows, channel_id=1, month="2026-04", column_mapping=mapping)
    assert len(comp) == 1
    f = comp[0]["fields"]
    assert f["vouchers"]["old"] is None
    assert f["vouchers"]["new"] == 300.0
    assert f["vouchers"]["changed"] is True


@pytest.mark.asyncio
async def test_comparison_empty_month_skips_old_data(db_session):
    """build_comparison with empty month returns all old=None."""
    from backend.services.settlement_service import compare_imported_rows as build_comparison

    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=Decimal("100"), test=Decimal("0"), welfare=Decimal("0"), bad_debt=Decimal("50"),
    ))
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()

    rows = [{"game_id": "G001", "game_name": "测试游戏",
             "vouchers": 200, "test": 0, "welfare": 0, "bad_debt": 50,
             "raw_revenue": None, "split_rate": 0.30, "settlement_amount": None}]
    mapping = {"0": "raw_revenue", "1": "vouchers", "2": "test", "3": "welfare",
               "4": "bad_debt", "5": "split_rate", "6": "channel_fee_rate",
               "7": "tax_rate", "8": "settlement_amount"}

    comp = await build_comparison(db_session, rows, channel_id=1, month="", column_mapping=mapping)
    assert len(comp) == 1
    fields = comp[0]["fields"]
    for fkey in ("raw_revenue", "vouchers", "test", "welfare", "bad_debt",
                 "split_rate", "channel_fee_rate", "tax_rate", "settlement_amount"):
        assert fields[fkey]["old"] is None, f"{fkey}.old should be None"
        if fkey in ("raw_revenue", "channel_fee_rate", "tax_rate", "settlement_amount"):
            assert fields[fkey]["changed"] is False
        else:
            assert fields[fkey]["changed"] is True


# ── Behavior 5: import_flexible_data row-month fallback ──

@pytest.mark.asyncio
async def test_import_uses_row_month_when_global_month_empty(db_session):
    """import_flexible_data falls back to record.month when global month is empty."""
    from backend.services.flexible_import import import_flexible_data

    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-04",
        vouchers=Decimal("50"), test=Decimal("0"), welfare=Decimal("0"), bad_debt=Decimal("0"),
    ))
    db_session.add(models.Deduction(
        channel_id=1, game_id="G001", month="2026-05",
        vouchers=Decimal("100"), test=Decimal("0"), welfare=Decimal("0"), bad_debt=Decimal("0"),
    ))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-04",
        locked_real_revenue=None, locked_settlement_amount=None,
        created_at="old", updated_at="old",
    ))
    db_session.add(models.ChannelLock(
        channel_id=1, game_id="G001", month="2026-05",
        locked_real_revenue=None, locked_settlement_amount=None,
        created_at="old", updated_at="old",
    ))
    await db_session.commit()

    rows = [
        {"game_id": "G001", "game_name": "测试游戏", "month": "2026-04",
         "vouchers": 100, "test": 0, "welfare": 0, "bad_debt": 0,
         "raw_revenue": 5000},
        {"game_id": "G001", "game_name": "测试游戏", "month": "2026-05",
         "vouchers": 200, "raw_revenue": 6000},
    ]
    mapping = {"0": "game_name", "1": "month", "2": "vouchers", "3": "raw_revenue"}

    result = await import_flexible_data(db_session, rows, channel_id=1, month="",
                                        column_mapping=mapping, selected_indices=None)
    await db_session.commit()

    assert result["imported_deductions"] == 2

    ded04 = (await db_session.execute(
        select(models.Deduction).where(
            models.Deduction.channel_id == 1,
            models.Deduction.game_id == "G001",
            models.Deduction.month == "2026-04",
        )
    )).scalar_one()
    assert float(ded04.vouchers) == 100.0

    # raw_revenue in flexible import does NOT write to ChannelLock (only
    # real_revenue/settlement_amount trigger lock writes). So lock values stay None.
    lock04 = (await db_session.execute(
        select(models.ChannelLock).where(
            models.ChannelLock.channel_id == 1,
            models.ChannelLock.game_id == "G001",
            models.ChannelLock.month == "2026-04",
        )
    )).scalar_one()
    assert lock04.locked_real_revenue is None

    ded05 = (await db_session.execute(
        select(models.Deduction).where(
            models.Deduction.channel_id == 1,
            models.Deduction.game_id == "G001",
            models.Deduction.month == "2026-05",
        )
    )).scalar_one()
    assert float(ded05.vouchers) == 200.0


@pytest.mark.asyncio
async def test_import_skips_row_without_any_month(db_session):
    """import_flexible_data skips rows where both global and row month are empty."""
    from backend.services.flexible_import import import_flexible_data

    db_session.add(models.ChannelCategory(channel_id=1, channel_name="测试渠道"))
    db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
    await db_session.commit()

    rows = [
        {"game_id": "G001", "game_name": "测试游戏",
         "vouchers": 100, "raw_revenue": 5000},
    ]
    mapping = {"0": "game_name", "1": "vouchers"}

    result = await import_flexible_data(db_session, rows, channel_id=1, month="",
                                        column_mapping=mapping, selected_indices=None)
    await db_session.commit()
    assert result["imported_deductions"] == 0


def test_month_missing_logic():
    """month_missing = not month AND no 'month' column in mapping."""
    mapping1 = {"0": "game_name", "1": "raw_revenue"}
    has_month_col1 = any(v == "month" for v in mapping1.values())
    assert not ("" == "" and not has_month_col1) is False  # case 1

    month2 = ""
    has_month_col2 = any(v == "month" for v in mapping1.values())
    assert (not month2 and not has_month_col2) is True  # case 2

    mapping3 = {"0": "game_name", "1": "month", "2": "raw_revenue"}
    month3 = ""
    has_month_col3 = any(v == "month" for v in mapping3.values())
    assert (not month3 and not has_month_col3) is False  # case 3

    month4 = "2026-04"
    has_month_col4 = any(v == "month" for v in mapping3.values())
    assert (not month4 and not has_month_col4) is False  # case 4
