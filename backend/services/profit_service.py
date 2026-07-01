"""Profit statement service — P&L table, expense management."""

from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models


async def get_profit_table(db: AsyncSession, company_id: int | None,
                           month_from: str, month_to: str) -> dict:
    """Return P&L table grouped by confirmed_month (收款月份).

    Each confirmed_month is one row.  All flow months within that confirmed_month
    are aggregated into that row.  A totals row is appended at the end.
    Expenses are matched by month (ProfitExpense.month == confirmed_month).
    """
    # ---- Base filters on confirmed_month range ----
    base_filters = [
        models.ArapRecord.confirmed_month >= month_from,
        models.ArapRecord.confirmed_month <= month_to,
    ]
    ch_filters = base_filters + [models.ArapRecord.entity_type == "channel"]
    pub_filters = base_filters + [models.ArapRecord.entity_type == "publisher"]
    if company_id is not None:
        ch_filters.append(models.ArapRecord.company_id == company_id)
        pub_filters.append(models.ArapRecord.company_id == company_id)

    # ---- Revenue per confirmed_month (channel) ----
    ch_rows = (await db.execute(
        select(
            models.ArapRecord.confirmed_month,
            func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0),
        )
        .where(*ch_filters)
        .group_by(models.ArapRecord.confirmed_month)
        .order_by(models.ArapRecord.confirmed_month)
    )).all()
    revenue_map = {r.confirmed_month: float(r[1]) for r in ch_rows}

    # ---- Cost per confirmed_month (publisher) ----
    pub_rows = (await db.execute(
        select(
            models.ArapRecord.confirmed_month,
            func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0),
        )
        .where(*pub_filters)
        .group_by(models.ArapRecord.confirmed_month)
        .order_by(models.ArapRecord.confirmed_month)
    )).all()
    cost_map = {r.confirmed_month: float(r[1]) for r in pub_rows}

    # Merge all confirmed_months present in either revenue or cost
    confirmed_months = sorted(set(list(revenue_map.keys()) + list(cost_map.keys())))

    # ---- Expenses per month (ProfitExpense.month == confirmed_month) ----
    exp_query = select(
        models.ProfitExpense.month,
        func.coalesce(func.sum(models.ProfitExpense.expense_amount), 0),
        func.coalesce(func.sum(models.ProfitExpense.other_income), 0),
    ).where(
        models.ProfitExpense.month >= month_from,
        models.ProfitExpense.month <= month_to,
    )
    if company_id is not None:
        exp_query = exp_query.where(
            (models.ProfitExpense.company_id == company_id) |
            (models.ProfitExpense.company_id.is_(None))
        )
    else:
        exp_query = exp_query.where(models.ProfitExpense.company_id.is_(None))
    exp_query = exp_query.group_by(models.ProfitExpense.month)
    exp_rows = (await db.execute(exp_query)).all()
    exp_map = {r[0]: (float(r[1]), float(r[2])) for r in exp_rows}

    # ---- Build rows ----
    rows = []
    total_revenue = total_cost = total_expense = total_other_income = 0.0
    for m in confirmed_months:
        revenue = revenue_map.get(m, 0)
        cost = cost_map.get(m, 0)
        expense, other_income = exp_map.get(m, (0, 0))
        gprofit = round(revenue - cost, 2)
        nprofit = round(gprofit + other_income - expense, 2)
        rows.append({
            "month": m,
            "revenue": revenue,
            "cost": cost,
            "gross_profit": gprofit,
            "other_income": other_income,
            "expense": expense,
            "net_profit": nprofit,
        })
        total_revenue += revenue
        total_cost += cost
        total_expense += expense
        total_other_income += other_income

    # ---- Totals ----
    totals = {
        "month": "合计",
        "revenue": round(total_revenue, 2),
        "cost": round(total_cost, 2),
        "gross_profit": round(total_revenue - total_cost, 2),
        "other_income": round(total_other_income, 2),
        "expense": round(total_expense, 2),
        "net_profit": round((total_revenue - total_cost) + total_other_income - total_expense, 2),
    }

    return {"months": confirmed_months, "rows": rows, "totals": totals}


async def save_expense(db: AsyncSession, month: str,
                       company_id: int | None,
                       expense_amount: float, now: str,
                       other_income: float = 0) -> dict:
    """Upsert an expense row (including other_income) for a single month."""
    exp_amt = Decimal(str(expense_amount)).quantize(Decimal("0.01"))
    inc_amt = Decimal(str(other_income)).quantize(Decimal("0.01"))

    filters = [models.ProfitExpense.month == month]
    if company_id is not None:
        filters.append(models.ProfitExpense.company_id == company_id)
    else:
        filters.append(models.ProfitExpense.company_id.is_(None))

    row = (await db.execute(
        select(models.ProfitExpense).where(*filters)
    )).scalar_one_or_none()

    if row:
        row.expense_amount = exp_amt
        row.other_income = inc_amt
        row.updated_at = now
    else:
        db.add(models.ProfitExpense(
            month=month,
            company_id=company_id,
            expense_amount=exp_amt,
            other_income=inc_amt,
            updated_at=now,
        ))
    await db.commit()
    return {"month": month, "company_id": company_id,
            "expense_amount": float(exp_amt), "other_income": float(inc_amt)}


async def get_profit_summary(db: AsyncSession, month: str,
                              company_id: int | None = None) -> dict:
    """Return {gross_profit, net_profit} for dashboard. Queries by confirmed_month."""
    ch_filters = [models.ArapRecord.entity_type == "channel",
                  models.ArapRecord.confirmed_month == month]
    pub_filters = [models.ArapRecord.entity_type == "publisher",
                   models.ArapRecord.confirmed_month == month]
    if company_id is not None:
        ch_filters.append(models.ArapRecord.company_id == company_id)
        pub_filters.append(models.ArapRecord.company_id == company_id)

    revenue = float((await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(*ch_filters)
    )).scalar())
    cost = float((await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(*pub_filters)
    )).scalar())
    gprofit = round(revenue - cost, 2)

    exp_query = select(
        func.coalesce(func.sum(models.ProfitExpense.expense_amount), 0),
        func.coalesce(func.sum(models.ProfitExpense.other_income), 0),
    ).where(models.ProfitExpense.month == month)
    if company_id is not None:
        exp_query = exp_query.where(
            (models.ProfitExpense.company_id == company_id) |
            (models.ProfitExpense.company_id.is_(None))
        )
    else:
        exp_query = exp_query.where(models.ProfitExpense.company_id.is_(None))
    exp_row = (await db.execute(exp_query)).one()
    expense = float(exp_row[0])
    other_income = float(exp_row[1])
    nprofit = round(gprofit + other_income - expense, 2)

    return {"gross_profit": gprofit, "net_profit": nprofit}
