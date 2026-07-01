"""Test profit service — other_income, expense, P&L formula."""

from datetime import datetime

import pytest
import pytest_asyncio

from backend import models
from backend.services.profit_service import (
    save_expense,
    get_profit_table,
    get_profit_summary,
)

NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _seed_arap(db, channel_id, publisher_id, company_id, month, revenue, cost):
    """Create arap_records for one month's revenue and cost."""
    db.add(models.ArapRecord(
        entity_type="channel", entity_id=channel_id, entity_name="测试渠道",
        company_id=company_id, company_name="测试公司",
        game_id="", game_name="", month=month, confirmed_month=month,
        settlement_amount=revenue, locked_amount=revenue, snapshot_at=NOW,
    ))
    db.add(models.ArapRecord(
        entity_type="publisher", entity_id=publisher_id, entity_name="测试研发商",
        company_id=company_id, company_name="测试公司",
        game_id="", game_name="", month=month, confirmed_month=month,
        settlement_amount=cost, locked_amount=cost, snapshot_at=NOW,
    ))
    await db.commit()


# ── Vertical slice 1: save_expense creates row with other_income ──

@pytest.mark.asyncio
async def test_save_expense_creates_row_with_other_income(db_session):
    """save_expense creates a profit_expenses row carrying both expense and other_income."""
    await save_expense(
        db_session, month_from="2026-06", month_to="2026-06", company_id=1,
        expense_amount=5000, other_income=2000, now=NOW,
    )

    row = (await db_session.execute(
        __import__("sqlalchemy").select(models.ProfitExpense).where(
            models.ProfitExpense.month == "2026-06",
            models.ProfitExpense.company_id == 1,
        )
    )).scalar_one_or_none()

    assert row is not None
    assert float(row.expense_amount) == 5000.0
    assert float(row.other_income) == 2000.0


# ── Vertical slice 2: save_expense updates existing row ──

@pytest.mark.asyncio
async def test_save_expense_updates_other_income(db_session):
    """save_expense upserts: updating an existing row changes both fields."""
    await save_expense(db_session, "2026-06", "2026-06", 1, 3000, NOW, other_income=1000)
    await save_expense(db_session, "2026-06", "2026-06", 1, 4000, NOW, other_income=2500)

    row = (await db_session.execute(
        __import__("sqlalchemy").select(models.ProfitExpense).where(
            models.ProfitExpense.month == "2026-06",
            models.ProfitExpense.company_id == 1,
        )
    )).scalar_one_or_none()

    assert float(row.expense_amount) == 4000.0
    assert float(row.other_income) == 2500.0


# ── Vertical slice 3: P&L formula uses other_income ──

@pytest.mark.asyncio
async def test_profit_table_net_profit_formula_with_other_income(db_session):
    """net_profit = revenue - cost + other_income - expense.

    revenue=100000, cost=60000 → gross=40000
    other_income=5000, expense=10000 → net=40000+5000-10000=35000
    """
    # Seed FK records
    db_session.add(models.Company(company_name="测试公司"))
    db_session.add(models.ChannelCategory(channel_name="测试渠道"))
    db_session.add(models.Publisher(publisher_name="测试研发商"))
    await db_session.commit()

    await _seed_arap(db_session, 1, 1, 1, "2026-06", 100000, 60000)
    await save_expense(db_session, "2026-06", "2026-06", 1, expense_amount=10000, other_income=5000, now=NOW)

    result = await get_profit_table(db_session, company_id=1, month_from="2026-06", month_to="2026-06")

    row = result["rows"][0]
    assert row["revenue"] == 100000.0
    assert row["cost"] == 60000.0
    assert row["gross_profit"] == 40000.0
    assert row["other_income"] == 5000.0
    assert row["expense"] == 10000.0
    assert row["net_profit"] == 35000.0

    # Totals row
    assert result["totals"]["other_income"] == 5000.0
    assert result["totals"]["net_profit"] == 35000.0


# ── Vertical slice 4: other_income defaults to 0 ──

@pytest.mark.asyncio
async def test_profit_table_other_income_defaults_to_zero(db_session):
    """When no profit_expenses row exists, other_income defaults to 0."""
    db_session.add(models.Company(company_name="测试公司"))
    db_session.add(models.ChannelCategory(channel_name="测试渠道"))
    db_session.add(models.Publisher(publisher_name="测试研发商"))
    await db_session.commit()

    await _seed_arap(db_session, 1, 1, 1, "2026-06", 50000, 30000)

    result = await get_profit_table(db_session, company_id=1, month_from="2026-06", month_to="2026-06")
    row = result["rows"][0]

    assert row["other_income"] == 0.0
    assert row["expense"] == 0.0
    assert row["net_profit"] == 20000.0  # 50000-30000+0-0


# ── Vertical slice 5: get_profit_summary includes other_income ──

@pytest.mark.asyncio
async def test_profit_summary_net_profit_uses_other_income(db_session):
    """get_profit_summary net = gross + other_income - expense."""
    db_session.add(models.Company(company_name="测试公司"))
    db_session.add(models.ChannelCategory(channel_name="测试渠道"))
    db_session.add(models.Publisher(publisher_name="测试研发商"))
    await db_session.commit()

    await _seed_arap(db_session, 1, 1, 1, "2026-06", 80000, 50000)
    await save_expense(db_session, "2026-06", "2026-06", 1, expense_amount=8000, other_income=3000, now=NOW)

    summary = await get_profit_summary(db_session, "2026-06", company_id=1)

    assert summary["gross_profit"] == 30000.0  # 80000-50000
    assert summary["net_profit"] == 25000.0    # 30000+3000-8000


# ── Vertical slice 6: multi-month totals aggregate other_income ──

@pytest.mark.asyncio
async def test_profit_table_multi_month_aggregates_other_income(db_session):
    """Totals row sums other_income across months."""
    db_session.add(models.Company(company_name="测试公司"))
    db_session.add(models.ChannelCategory(channel_name="测试渠道"))
    db_session.add(models.Publisher(publisher_name="测试研发商"))
    await db_session.commit()

    await _seed_arap(db_session, 1, 1, 1, "2026-06", 100000, 50000)
    await _seed_arap(db_session, 1, 1, 1, "2026-07", 120000, 60000)
    await save_expense(db_session, "2026-06", "2026-06", 1, expense_amount=10000, other_income=2000, now=NOW)
    await save_expense(db_session, "2026-07", "2026-07", 1, expense_amount=8000, other_income=3000, now=NOW)

    result = await get_profit_table(db_session, company_id=1, month_from="2026-06", month_to="2026-07")

    assert result["totals"]["revenue"] == 220000.0
    assert result["totals"]["cost"] == 110000.0
    assert result["totals"]["gross_profit"] == 110000.0
    assert result["totals"]["other_income"] == 5000.0   # 2000+3000
    assert result["totals"]["expense"] == 18000.0        # 10000+8000
    assert result["totals"]["net_profit"] == 97000.0    # 110000+5000-18000


# ── Vertical slice 7: single aggregate row (not per-flow-month) ──

@pytest.mark.asyncio
async def test_profit_table_single_row_aggregate(db_session):
    """get_profit_table returns ONE aggregate row, not per-flow-month rows."""
    db_session.add(models.Company(company_name="测试公司"))
    db_session.add(models.ChannelCategory(channel_name="测试渠道"))
    db_session.add(models.Publisher(publisher_name="测试研发商"))
    await db_session.commit()

    await _seed_arap(db_session, 1, 1, 1, "2026-06", 100000, 50000)
    await _seed_arap(db_session, 1, 1, 1, "2026-07", 120000, 60000)
    await _seed_arap(db_session, 1, 1, 1, "2026-08", 80000, 40000)

    result = await get_profit_table(db_session, company_id=1, month_from="2026-06", month_to="2026-08")

    # Only one data row covering the full range
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["revenue"] == 300000.0   # 100000+120000+80000
    assert row["cost"] == 150000.0      # 50000+60000+40000
    assert row["gross_profit"] == 150000.0

    # Totals match the single aggregate row
    assert result["totals"]["revenue"] == row["revenue"]
    assert result["totals"]["cost"] == row["cost"]


# ── Vertical slice 8: save_expense zeros intermediate months ──

@pytest.mark.asyncio
async def test_save_expense_zeros_intermediate_months(db_session):
    """save_expense zeroes out months between month_from and month_to-1."""
    db_session.add(models.Company(company_name="测试公司"))
    await db_session.commit()

    # Save expenses for individual months first
    await save_expense(db_session, "2026-06", "2026-06", 1, 1000, NOW, other_income=100)
    await save_expense(db_session, "2026-07", "2026-07", 1, 2000, NOW, other_income=200)
    await save_expense(db_session, "2026-08", "2026-08", 1, 3000, NOW, other_income=300)

    # Now save a range — should write to 2026-08 and zero 2026-06, 2026-07
    await save_expense(db_session, "2026-06", "2026-08", 1, 9999, NOW, other_income=999)

    stmt = __import__("sqlalchemy").select(models.ProfitExpense)
    rows = {r.month: r for r in (await db_session.execute(stmt)).scalars().all()}

    assert float(rows["2026-06"].expense_amount) == 0
    assert float(rows["2026-06"].other_income) == 0
    assert float(rows["2026-07"].expense_amount) == 0
    assert float(rows["2026-07"].other_income) == 0
    assert float(rows["2026-08"].expense_amount) == 9999
    assert float(rows["2026-08"].other_income) == 999
