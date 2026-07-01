"""AR/AP snapshot service — pivot data, monthly close, snapshot upsert."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from .company_resolver import resolve_companies_batch
from .payment_service import get_payment_history


async def is_month_closed(db: AsyncSession, month: str) -> bool:
    row = (await db.execute(
        select(models.MonthlyClose).where(models.MonthlyClose.month == month)
    )).scalar_one_or_none()
    return row is not None


async def current_working_month(db: AsyncSession) -> str:
    """Latest unclosed month (YYYY-MM). Defaults to current system month."""
    row = (await db.execute(
        select(func.max(models.MonthlyClose.month))
    )).scalar_one()
    if row:
        y, m = int(row[:4]), int(row[5:7])
        if m == 12:
            return f"{y + 1}-01"
        return f"{y}-{m + 1:02d}"
    today = date.today()
    return f"{today.year}-{today.month:02d}"


async def close_month(db: AsyncSession, month: str, now: str) -> dict:
    """Close a month (idempotent)."""
    exists = await is_month_closed(db, month)
    if exists:
        return {"status": "already_closed", "month": month}
    db.add(models.MonthlyClose(month=month, closed_at=now))
    await db.commit()
    return {"status": "closed", "month": month, "closed_at": now}


async def get_closed_months(db: AsyncSession) -> list[str]:
    rows = (await db.execute(
        select(models.MonthlyClose.month).order_by(models.MonthlyClose.month.asc())
    )).scalars().all()
    return list(rows)


async def _resolve_entity_name(db: AsyncSession, entity_type: str, entity_id: int) -> str:
    if entity_type == "channel":
        row = (await db.execute(
            select(models.ChannelCategory.channel_name).where(
                models.ChannelCategory.channel_id == entity_id
            )
        )).scalar_one_or_none()
        return row or f"channel_{entity_id}"
    else:
        row = (await db.execute(
            select(models.Publisher.publisher_name).where(
                models.Publisher.publisher_id == entity_id
            )
        )).scalar_one_or_none()
        return row or f"publisher_{entity_id}"


async def _resolve_company_name(db: AsyncSession, company_id: int | None) -> str:
    if company_id is None:
        return "未关联"
    row = (await db.execute(
        select(models.Company.company_name).where(
            models.Company.company_id == company_id
        )
    )).scalar_one_or_none()
    return row or f"company_{company_id}"


async def _compute_credit_totals(db: AsyncSession, entity_type: str) -> dict:
    """Return {(entity_id, company_id): credit_total} for all paid amounts.

    Credit = SUM(payment_allocations.allocated_amount) grouped by the ARAP
    record's (entity_id, company_id), joined via payment_records.
    """
    result = {}
    rows = (await db.execute(
        select(
            models.ArapRecord.entity_id,
            models.ArapRecord.company_id,
            func.coalesce(func.sum(models.PaymentAllocation.allocated_amount), 0).label("credit"),
        )
        .select_from(models.PaymentAllocation)
        .join(models.ArapRecord, models.PaymentAllocation.arap_id == models.ArapRecord.id)
        .join(models.PaymentRecord, models.PaymentAllocation.payment_id == models.PaymentRecord.id)
        .where(models.ArapRecord.entity_type == entity_type)
        .group_by(models.ArapRecord.entity_id, models.ArapRecord.company_id)
    )).all()
    for eid, cid, credit in rows:
        result[(eid, cid)] = float(credit or 0)
    return result


async def _compute_debit_totals(db: AsyncSession, entity_type: str) -> dict:
    """Return {(entity_id, company_id): debit_total} for all snapshot amounts.

    Debit = SUM(arap_records.settlement_amount) globally, not filtered by confirmed_month.
    """
    result = {}
    rows = (await db.execute(
        select(
            models.ArapRecord.entity_id,
            models.ArapRecord.company_id,
            func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0).label("debit"),
        )
        .where(models.ArapRecord.entity_type == entity_type)
        .group_by(models.ArapRecord.entity_id, models.ArapRecord.company_id)
    )).all()
    for eid, cid, debit in rows:
        result[(eid, cid)] = float(debit or 0)
    return result


async def get_pivot(db: AsyncSession, entity_type: str,
                    month_from: str, month_to: str) -> dict:
    """Return pivot table with debit/credit columns.

    columns: flow months (流水月份) within the confirmed_month range
    rows: each with cells, total (filtered sum), debit_total (global), credit_total (global)

    Filters by confirmed_month (收款月份) in [month_from, month_to] for
    flow-month columns and total. Debit/credit totals are global (unfiltered).
    """
    rows = (await db.execute(
        select(models.ArapRecord).where(
            models.ArapRecord.entity_type == entity_type,
            models.ArapRecord.confirmed_month >= month_from,
            models.ArapRecord.confirmed_month <= month_to,
        )
    )).scalars().all()

    # Resolve names
    entity_names = {}
    company_names = {}
    for r in rows:
        if r.entity_id not in entity_names:
            entity_names[r.entity_id] = await _resolve_entity_name(db, entity_type, r.entity_id)
        if r.company_id not in company_names:
            company_names[r.company_id] = await _resolve_company_name(db, r.company_id)

    # Generate month columns from actual flow months (流水月份) in the result set
    flow_months = sorted({r.month for r in rows})
    columns = list(flow_months)

    # Pivot — aggregate by month (流水月份), not confirmed_month
    pivot = defaultdict(lambda: {"cells": {}, "total": Decimal("0")})
    for r in rows:
        key = (r.entity_id, r.company_id)
        prev = pivot[key]["cells"].get(r.month, 0)
        pivot[key]["cells"][r.month] = prev + float(r.settlement_amount)
        pivot[key]["total"] += r.settlement_amount
        pivot[key]["entity_name"] = entity_names.get(r.entity_id, "")
        # Use stored company_name when company_id is NULL (Priority 4 resolution
        # via ChannelCompanyMapping → PartyInfo provides name without ID)
        pivot[key]["company_name"] = (r.company_name if r.company_id is None and r.company_name
                                      else company_names.get(r.company_id, ""))

    # Apply company overrides (payment/publisher side only)
    override_set = set()
    if entity_type == "publisher":
        override_rows = (await db.execute(
            select(models.ArapCompanyOverride).where(
                models.ArapCompanyOverride.entity_type == "publisher",
            )
        )).scalars().all()
        for ov in override_rows:
            key = (ov.entity_id, ov.original_company_id)
            override_set.add(key)
            if key in pivot:
                pivot[key]["company_name"] = ov.override_company_name

    # Global debit/credit totals
    debit_map = await _compute_debit_totals(db, entity_type)
    credit_map = await _compute_credit_totals(db, entity_type)

    # Build rows, filter empty
    all_keys = set(pivot.keys()) | set(debit_map.keys())
    result_rows = []
    for (eid, cid) in all_keys:
        data = pivot.get((eid, cid), {})
        cells = data.get("cells", {})
        has_balance = any(
            v is not None and abs(float(v)) > 0.005
            for v in cells.values()
        )
        if not has_balance:
            continue
        debit_total = debit_map.get((eid, cid), 0)
        credit_total = credit_map.get((eid, cid), 0)
        result_rows.append({
            "entity_id": eid,
            "entity_name": data.get("entity_name", await _resolve_entity_name(db, entity_type, eid)),
            "company_id": cid,
            "company_name": data.get("company_name", await _resolve_company_name(db, cid)),
            "is_overridden": (eid, cid) in override_set,
            "cells": {m: cells.get(m) for m in columns},
            "total": float(data.get("total", 0)),
            "debit_total": debit_total,
            "credit_total": credit_total,
        })

    # Sort: non-empty first → total desc → entity_name → company_name
    result_rows.sort(key=lambda r: (
        0 if any(
            v is not None and abs(v) > 0.005
            for v in r["cells"].values()
        ) else 1,
        -(r["total"] or 0),
        r["entity_name"],
        r["company_name"],
    ))

    return {"columns": columns, "rows": result_rows}


async def get_breakdown(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    company_id: int,
) -> dict:
    """Return debit breakdown by confirmed_month + payment records for one row.

    Returns {debit_items: [{confirmed_month, amount}], payment_items: [...]}.
    """
    # Debit breakdown: SUM(settlement_amount) GROUP BY confirmed_month
    debit_rows = (await db.execute(
        select(
            models.ArapRecord.confirmed_month,
            func.sum(models.ArapRecord.settlement_amount).label("amount"),
        )
        .where(
            models.ArapRecord.entity_type == entity_type,
            models.ArapRecord.entity_id == entity_id,
            models.ArapRecord.company_id == company_id,
        )
        .group_by(models.ArapRecord.confirmed_month)
        .order_by(models.ArapRecord.confirmed_month)
    )).all()

    debit_items = [
        {"confirmed_month": month, "amount": float(amount)}
        for month, amount in debit_rows
    ]

    # Payment records for this entity+company
    payment_items = await get_payment_history(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        company_id=company_id,
    )

    return {
        "debit_items": debit_items,
        "payment_items": payment_items,
    }


async def get_snapshot_balances(db: AsyncSession, month: str | None = None) -> dict:
    """Dashboard 4 indicators from snapshot (AR/AP) + ledger (revenue/cost)."""
    if month is None:
        today = date.today()
        d = date(today.year, today.month, 1) - timedelta(days=1)
        month = f"{d.year}-{d.month:02d}"

    ar = (await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(models.ArapRecord.entity_type == "channel")
    )).scalar()

    ap = (await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(models.ArapRecord.entity_type == "publisher")
    )).scalar()

    # Revenue/cost from arap_records (channel side, by confirmed_month)
    ch_total = (await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(models.ArapRecord.entity_type == "channel", models.ArapRecord.confirmed_month == month)
    )).scalar()
    pub_total = (await db.execute(
        select(func.coalesce(func.sum(models.ArapRecord.settlement_amount), 0))
        .where(models.ArapRecord.entity_type == "publisher", models.ArapRecord.confirmed_month == month)
    )).scalar()

    return {
        "ar_balance": round(float(ar) if ar else 0, 2),
        "ap_balance": round(float(ap) if ap else 0, 2),
        "monthly_revenue": round(float(ch_total) if ch_total else 0, 2),
        "monthly_cost": round(float(pub_total) if pub_total else 0, 2),
    }


async def get_working_month(db: AsyncSession) -> str:
    """Return the current working month string (next month after latest closed)."""
    return await current_working_month(db)


async def get_pending_count(db: AsyncSession) -> list[dict]:
    """Return per-month unlocked-item counts for the last 6 months.
    Only includes months with actual pending items."""
    from collections import defaultdict
    from .. import models

    today = date.today()
    end_d = date(today.year, today.month, 1) - timedelta(days=1)
    d = date(end_d.year, end_d.month, 1)
    months = []
    for _ in range(6):
        months.append(f"{d.year}-{d.month:02d}")
        d = date(d.year, d.month - 1, 1) if d.month > 1 else date(d.year - 1, 12, 1)

    from .settlement_service import query_income_settlement, query_payment_settlement

    result = []
    for m in months:
        income = await query_income_settlement(db, m, m)
        if income:
            ch_keys = set((r["channel_id"], r["game_id"]) for r in income)
            ch_lock_rows = (await db.execute(
                select(models.ChannelLock.channel_id, models.ChannelLock.game_id).where(
                    models.ChannelLock.month == m,
                    models.ChannelLock.locked_settlement_amount.isnot(None),
                )
            )).all()
            ch_locked = set(ch_lock_rows)
            ch_pending = len(ch_keys - ch_locked)
        else:
            ch_pending = 0

        payment = await query_payment_settlement(db, m, m)
        if payment:
            pub_keys = set((r["publisher_id"], r["game_id"]) for r in payment)
            pub_lock_rows = (await db.execute(
                select(models.PublisherLock.publisher_id, models.PublisherLock.game_id).where(
                    models.PublisherLock.month == m,
                    models.PublisherLock.locked_settlement_amount.isnot(None),
                )
            )).all()
            pub_locked = set(pub_lock_rows)
            pub_pending = len(pub_keys - pub_locked)
        else:
            pub_pending = 0

        if ch_pending > 0 or pub_pending > 0:
            result.append({
                "month": m,
                "channel_pending": ch_pending,
                "publisher_pending": pub_pending,
            })

    return result


async def reopen_month(db: AsyncSession, month: str, now: str) -> dict:
    """Remove a MonthlyClose row (undo monthly close)."""
    row = (await db.execute(
        select(models.MonthlyClose).where(models.MonthlyClose.month == month)
    )).scalar_one_or_none()
    if not row:
        raise ValueError(f"月份 {month} 未关闭")
    await db.delete(row)
    await db.commit()
    return {"status": "reopened", "month": month, "reopened_at": now}


async def snapshot_from_locks(db: AsyncSession, now: str, confirmed_month: str) -> dict:
    """从 channel_locks + publisher_locks 增量快照到 arap_records。

    只处理 confirmed_month IS NULL 的锁（未快照过的），已快照的跳过。
    按 (entity_type, entity_id, company_id, month) 聚合后写入 arap_records。
    月结路由：已关闭月份的锁 → 路由到当前工作月。
    """
    from collections import defaultdict

    # ── Helpers ──
    # _resolve_companies delegated to company_resolver.resolve_companies_batch
    async def _resolve_companies(gids: list, channel_id: int | None = None) -> dict:
        return await resolve_companies_batch(db, gids, channel_id=channel_id)

    # ── 1. Channel side (AR) ──
    ch_rows = (await db.execute(
        select(
            models.ChannelLock.id,
            models.ChannelLock.channel_id,
            models.ChannelLock.game_id,
            models.ChannelLock.month,
            models.ChannelLock.locked_settlement_amount,
            models.RawSettlement.channel_name,
        )
        .select_from(models.ChannelLock)
        .join(models.RawSettlement,
              (models.ChannelLock.channel_id == models.RawSettlement.channel_id) &
              (models.ChannelLock.game_id == models.RawSettlement.game_id) &
              (models.ChannelLock.month == models.RawSettlement.month))
        .where(models.ChannelLock.locked_settlement_amount.isnot(None),
               models.ChannelLock.confirmed_month.is_(None))
    )).all()

    # Resolve companies per (game_id, channel_id)
    ch_groups = defaultdict(list)
    for r in ch_rows:
        ch_groups[r.channel_id].append(r.game_id)
    comp_map = {}  # {(gid, ch_id): (company_id, company_name)}
    for ch_id, gids in ch_groups.items():
        gids_unique = list(set(gids))
        partial = await _resolve_companies(gids_unique, channel_id=ch_id)
        for gid, val in partial.items():
            comp_map[(gid, ch_id)] = val

    ch_processed_ids = []
    agg = defaultdict(Decimal)
    meta_map = {}
    for r in ch_rows:
        lock_id, ch_id, gid, lock_month, locked_amt, ch_name = r
        target_month = lock_month
        if await is_month_closed(db, lock_month):
            target_month = await current_working_month(db)
        cid, cname = comp_map.get((gid, ch_id), (None, ""))
        key = ("channel", ch_id, cid, target_month)
        agg[key] += locked_amt
        meta_map[key] = (ch_name or "", cname or "")
        ch_processed_ids.append(lock_id)

    # ── 2. Publisher side (AP) ──
    pub_rows = (await db.execute(
        select(
            models.PublisherLock.id,
            models.PublisherLock.publisher_id,
            models.PublisherLock.game_id,
            models.PublisherLock.month,
            models.PublisherLock.locked_settlement_amount,
            models.Publisher.publisher_name,
        )
        .select_from(models.PublisherLock)
        .join(models.Publisher,
              models.PublisherLock.publisher_id == models.Publisher.publisher_id)
        .where(models.PublisherLock.locked_settlement_amount.isnot(None),
               models.PublisherLock.confirmed_month.is_(None))
    )).all()

    pub_gids = list({r.game_id for r in pub_rows})
    pub_comp_map = await _resolve_companies(pub_gids)

    pub_processed_ids = []
    for r in pub_rows:
        lock_id, pub_id, gid, lock_month, locked_amt, pub_name = r
        target_month = lock_month
        if await is_month_closed(db, lock_month):
            target_month = await current_working_month(db)
        cid, cname = pub_comp_map.get(gid, (None, ""))
        key = ("publisher", pub_id, cid, target_month)
        agg[key] += locked_amt
        meta_map[key] = (pub_name or "", cname or "")
        pub_processed_ids.append(lock_id)

    # ── 3. Upsert aggregated rows ──
    inserted = 0
    for (entity_type, entity_id, cid, target_month), total in agg.items():
        ename, cname = meta_map.get((entity_type, entity_id, cid, target_month), ("", ""))
        # Check existing row for same (entity_type, entity_id, company_id, month, confirmed_month)
        existing = (await db.execute(
            select(models.ArapRecord).where(
                models.ArapRecord.entity_type == entity_type,
                models.ArapRecord.entity_id == entity_id,
                models.ArapRecord.company_id == cid,
                models.ArapRecord.month == target_month,
                models.ArapRecord.confirmed_month == confirmed_month,
            )
        )).scalar_one_or_none()

        quantized = total.quantize(Decimal("0.01"))
        if existing:
            existing.settlement_amount += quantized
            existing.locked_amount += quantized
            existing.entity_name = ename
            existing.company_name = cname
            existing.snapshot_at = now
        else:
            db.add(models.ArapRecord(
                entity_type=entity_type, entity_id=entity_id,
                entity_name=ename,
                company_id=cid, company_name=cname,
                game_id="", game_name="",
                month=target_month,
                confirmed_month=confirmed_month,
                settlement_amount=quantized,
                locked_amount=quantized,
                snapshot_at=now,
            ))
        inserted += 1

    # ── 4. Mark processed locks as confirmed ──
    if ch_processed_ids:
        await db.execute(
            models.ChannelLock.__table__.update()
            .where(models.ChannelLock.id.in_(ch_processed_ids))
            .values(confirmed_month=confirmed_month)
        )
    if pub_processed_ids:
        await db.execute(
            models.PublisherLock.__table__.update()
            .where(models.PublisherLock.id.in_(pub_processed_ids))
            .values(confirmed_month=confirmed_month)
        )

    await db.commit()
    return {
        "inserted": inserted,
        "channel_locks_processed": len(ch_processed_ids),
        "publisher_locks_processed": len(pub_processed_ids),
        "confirmed_month": confirmed_month,
        "snapshot_at": now,
    }


# ── ARAP company overrides (payment-side only) ──


async def list_arap_company_overrides(
    db: AsyncSession, entity_type: str = "publisher",
) -> list[dict]:
    """List all company overrides for the given entity_type."""
    rows = (await db.execute(
        select(models.ArapCompanyOverride).where(
            models.ArapCompanyOverride.entity_type == entity_type,
        )
    )).scalars().all()
    return [
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "original_company_id": r.original_company_id,
            "override_company_id": r.override_company_id,
            "override_company_name": r.override_company_name,
        }
        for r in rows
    ]


async def upsert_arap_company_override(
    db: AsyncSession,
    entity_id: int,
    original_company_id: int,
    override_company_id: int,
    now: str,
) -> dict:
    """UPSERT a company override for a publisher."""
    # Resolve override company name
    cname = (await db.execute(
        select(models.Company.company_name).where(
            models.Company.company_id == override_company_id,
        )
    )).scalar_one_or_none()
    if not cname:
        raise ValueError(f"公司 ID {override_company_id} 不存在")

    existing = (await db.execute(
        select(models.ArapCompanyOverride).where(
            models.ArapCompanyOverride.entity_type == "publisher",
            models.ArapCompanyOverride.entity_id == entity_id,
            models.ArapCompanyOverride.original_company_id == original_company_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.override_company_id = override_company_id
        existing.override_company_name = cname
        existing.updated_at = now
    else:
        db.add(models.ArapCompanyOverride(
            entity_type="publisher",
            entity_id=entity_id,
            original_company_id=original_company_id,
            override_company_id=override_company_id,
            override_company_name=cname,
            created_at=now,
            updated_at=now,
        ))

    await db.commit()
    return {"success": True}


async def delete_arap_company_override(
    db: AsyncSession,
    entity_id: int,
    original_company_id: int,
) -> bool:
    """Remove a company override, reverting to snapshot default."""
    result = await db.execute(
        delete(models.ArapCompanyOverride).where(
            models.ArapCompanyOverride.entity_type == "publisher",
            models.ArapCompanyOverride.entity_id == entity_id,
            models.ArapCompanyOverride.original_company_id == original_company_id,
        )
    )
    await db.commit()
    return result.rowcount > 0
