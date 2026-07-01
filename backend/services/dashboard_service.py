"""Dashboard aggregation queries."""
import asyncio
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .settlement_service import query_income_settlement, query_payment_settlement


def _month_range(count=2, end=None):
    """Return [prev_month, prev_prev_month, ...] newest first."""
    if end is None:
        today = date.today()
        end = date(today.year, today.month, 1) - timedelta(days=1)
    months = []
    d = date(end.year, end.month, 1)
    for _ in range(count):
        months.append(f"{d.year}-{d.month:02d}")
        d = date(d.year, d.month - 1, 1) if d.month > 1 else date(d.year - 1, 12, 1)
    return months


def _agg(results, dimension):
    """Aggregate settlement results by dimension, return {key: {real_revenue, settlement_amount}}."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"real_revenue": 0.0, "settlement_amount": 0.0})
    for r in results:
        if dimension == "channel":
            key = r["channel_name"]
        elif dimension == "game":
            key = r["game_name"]
        elif dimension == "project":
            key = r["project_name"] or "(空)"
        elif dimension == "publisher":
            key = r["publisher_name"]
        else:
            key = r["channel_name"]
        agg[key]["real_revenue"] += float(r["real_revenue"])
        agg[key]["settlement_amount"] += float(r["settlement_amount"] or 0)
    return agg


async def query_available_months(db: AsyncSession):
    """Return all distinct months from raw_settlements, newest first."""
    from ..models import RawSettlement
    rows = (await db.execute(
        select(RawSettlement.month).distinct().order_by(RawSettlement.month.desc())
    )).all()
    return [r[0] for r in rows]


async def query_ranking(db: AsyncSession, dimension: str, metric: str, count: int = 20, month: str = None):
    """Return {rows, current_month, previous_month}."""
    end = date(int(month[:4]), int(month[5:7]), 1) if month else None
    months = _month_range(2, end=end)

    current = await _query_by_dimension(db, dimension, months[0])
    previous = await _query_by_dimension(db, dimension, months[1])

    cur_agg = _agg(current, dimension)
    prev_agg = _agg(previous, dimension)

    rows = []
    for key, cv in cur_agg.items():
        pv = prev_agg.get(key, {"real_revenue": 0.0, "settlement_amount": 0.0})
        cur_val = float(cv[metric])
        prev_val = float(pv[metric])
        growth = ((cur_val - prev_val) / prev_val * 100) if prev_val else None
        rows.append({
            "name": key,
            "current_value": round(cur_val, 2),
            "previous_value": round(prev_val, 2),
            "growth_rate": round(growth, 2) if growth is not None else None,
        })

    rows.sort(key=lambda x: x["current_value"], reverse=True)
    return {
        "rows": rows[:count],
        "current_month": months[0],
        "previous_month": months[1],
    }


async def query_trend(db: AsyncSession, level1_type: str, level1_value: str, level2_value: str = None):
    """Return 6-month trend: [{month, real_revenue, settlement_amount}, ...]."""
    months = _month_range(6)

    series = []
    for m in months:
        results = await _query_by_dimension(db, level1_type, m)
        # Filter by level1 value
        matched = [r for r in results if (
            r.get("publisher_name") == level1_value or
            r.get("channel_name") == level1_value
        )]
        if level2_value:
            matched = [r for r in matched if r.get("game_name") == level2_value or r.get("project_name") == level2_value]

        total_rev = sum(r["real_revenue"] for r in matched)
        total_settle = sum(r["settlement_amount"] or 0 for r in matched)
        series.append({
            "month": m,
            "real_revenue": round(float(total_rev), 2),
            "settlement_amount": round(float(total_settle), 2),
        })

    return series


async def query_level2_options(db: AsyncSession, level1_type: str, level1_value: str):
    """Return level2 dropdown options (game names or project names)."""
    months = _month_range(1)
    results = await _query_by_dimension(db, level1_type, months[0])
    matched = [r for r in results if (
        r.get("publisher_name") == level1_value or
        r.get("channel_name") == level1_value
    )]
    seen = set()
    options = []
    for r in matched:
        name = r.get("project_name") or r.get("game_name")
        if name and name not in seen:
            seen.add(name)
            options.append(name)
    return options


async def query_trend_summary(db: AsyncSession):
    """Return 6-month aggregate trend (all channels/publishers combined)."""
    months = _month_range(6)
    series = []
    for m in months:
        chan = await query_income_settlement(db, start_month=m, end_month=m)
        total_rev = sum(r["real_revenue"] for r in chan)
        total_settle = sum(r["settlement_amount"] or 0 for r in chan)
        series.append({
            "month": m,
            "real_revenue": round(float(total_rev), 2),
            "settlement_amount": round(float(total_settle), 2),
        })
    return series


async def query_level1_options(db: AsyncSession, level1_type: str):
    """Return list of channel names or publisher names for trend dropdown."""
    from .. import models
    if level1_type == "channel":
        rows = await db.execute(models.ChannelCategory.__table__.select().order_by(models.ChannelCategory.channel_name))
        return [r.channel_name for r in rows]
    elif level1_type == "publisher":
        rows = await db.execute(models.Publisher.__table__.select().order_by(models.Publisher.publisher_name))
        return [r.publisher_name for r in rows]
    return []


async def query_summary(db: AsyncSession):
    """Return dashboard summary: totals, counts, and MoM growth."""
    months = _month_range(2)
    cur_data = await query_income_settlement(db, start_month=months[0], end_month=months[0])
    prev_data = await query_income_settlement(db, start_month=months[1], end_month=months[1])

    total_rev = sum(r["real_revenue"] for r in cur_data)
    total_settle = sum(r["settlement_amount"] or 0 for r in cur_data)
    prev_settle = sum(r["settlement_amount"] or 0 for r in prev_data)

    channels = set(r["channel_name"] for r in cur_data)
    games = set(r["game_name"] for r in cur_data)
    pub_data = await query_payment_settlement(db, start_month=months[0], end_month=months[0])
    pubs = set(r["publisher_name"] for r in pub_data)

    mom = ((total_settle - prev_settle) / prev_settle * 100) if prev_settle else None

    return {
        "current_month": months[0],
        "total_real_revenue": round(float(total_rev), 2),
        "total_settlement_amount": round(float(total_settle), 2),
        "channel_count": len(channels),
        "game_count": len(games),
        "publisher_count": len(pubs),
        "mom_growth": round(mom, 2) if mom is not None else None,
    }


async def _query_by_dimension(db, dimension, month):
    if dimension == "publisher":
        return await query_payment_settlement(db, start_month=month, end_month=month)
    return await query_income_settlement(db, start_month=month, end_month=month)


async def _query_profit_summary(db: AsyncSession, month: str):
    """Lazy-import profit summary to avoid circular deps."""
    from .profit_service import get_profit_summary
    return await get_profit_summary(db, month)


async def query_init(db: AsyncSession):
    """Return aggregated initial payload for dashboard first paint.

    Runs summary, three default ranking blocks, trend summary, and level1 options
    concurrently via asyncio.gather so total time ≈ max(individual query times).
    """
    summary, trend_summary, rankings, level1_chan, level1_pub, profit_summary = await asyncio.gather(
        query_summary(db),
        query_trend_summary(db),
        asyncio.gather(
            query_ranking(db, "channel", "settlement_amount", 20),
            query_ranking(db, "game", "real_revenue", 20),
            query_ranking(db, "publisher", "settlement_amount", 20),
        ),
        query_level1_options(db, "channel"),
        query_level1_options(db, "publisher"),
        _query_profit_summary(db, _month_range(1)[0]),
    )
    return {
        "summary": summary,
        "rankings": [
            {"dimension": "channel", "metric": "settlement_amount", "rows": rankings[0]["rows"], "current_month": rankings[0]["current_month"], "previous_month": rankings[0]["previous_month"]},
            {"dimension": "game", "metric": "real_revenue", "rows": rankings[1]["rows"], "current_month": rankings[1]["current_month"], "previous_month": rankings[1]["previous_month"]},
            {"dimension": "publisher", "metric": "settlement_amount", "rows": rankings[2]["rows"], "current_month": rankings[2]["current_month"], "previous_month": rankings[2]["previous_month"]},
        ],
        "trend_summary": trend_summary,
        "level1_options": {
            "channel": level1_chan,
            "publisher": level1_pub,
        },
        "profit_summary": profit_summary,
    }
