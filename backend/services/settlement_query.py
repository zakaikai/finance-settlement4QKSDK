"""Settlement calculation queries for income and payment directions.

Deep module: two parameterized query functions sharing common helpers.
All callers (routers, dashboard, snapshot) get full settlement data through a single seam.
"""
from collections import defaultdict
from decimal import Decimal
from datetime import date

import sqlalchemy as sa
from sqlalchemy import select, func, or_, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..utils.dates import month_bounds, month_start as _ms
from .settlement_formula import (
    compute as compute_settlement,
)
from .lock_service import resolve_locked_values
from .company_resolver import build_company_name_subquery


# ── Shared helpers ──


def _month_range(months: set[str]) -> tuple[date, date]:
    """Return (global_min, global_max) date range spanning all given months."""
    gmin = min([_ms(m) for m in months])
    max_m = max(months)
    max_y, max_mo = int(max_m[:4]), int(max_m[5:7])
    gmax = date(max_y, max_mo + 1, 1) if max_mo == 12 else date(max_y, max_mo + 1, 1)
    return gmin, gmax


def _find_active_config(cfg_map: dict, entity_key: tuple, month: str):
    """Find the config row active during `month` from cfg_map[entity_key].
    Returns None if no config covers the month.
    """
    ms_, me_ = month_bounds(month)
    for c in cfg_map.get(entity_key, []):
        if c.effective_from < me_ and (c.effective_to is None or c.effective_to >= ms_):
            return c
    return None


# ── Income settlement query ──


async def query_income_settlement(
    db: AsyncSession,
    start_month: str = None,
    end_month: str = None,
    channel_name: str = None,
    game_id: str = None,
):
    """收入结算查询: 原始流水表 (channel_id, game_id, month) 聚合粒度。

    数据源: raw_settlements（导入时已解析渠道层级+聚合）。
    """
    filters = []
    if start_month:
        filters.append(models.RawSettlement.month >= start_month)
    if end_month:
        filters.append(models.RawSettlement.month <= end_month)
    if game_id:
        filters.append(models.RawSettlement.game_id == game_id)
    if channel_name:
        filters.append(models.RawSettlement.channel_name == channel_name)

    # ── 子查询: 维度数据 ──
    project_code_subq = (
        select(models.PublisherGameMapping.project_code)
        .where(models.PublisherGameMapping.game_id == models.Game.game_id)
        .limit(1).correlate(models.Game).scalar_subquery()
    )
    project_name_subq = (
        select(models.PublisherGameMapping.project_name)
        .where(models.PublisherGameMapping.game_id == models.Game.game_id)
        .limit(1).correlate(models.Game).scalar_subquery()
    )
    company_name_subq = build_company_name_subquery(models.Game, models.RawSettlement)

    # Channel party name (from channel_company_mappings → PartyInfo)
    party_name_subq = (
        select(models.PartyInfo.name)
        .select_from(models.ChannelCompanyMapping)
        .join(models.PartyInfo,
              models.ChannelCompanyMapping.party_info_id == models.PartyInfo.id)
        .where(models.ChannelCompanyMapping.channel_id == models.RawSettlement.channel_id)
        .limit(1)
        .correlate(models.RawSettlement)
        .scalar_subquery()
    )

    # ── 主查询 ──
    stmt = (
        select(
            models.RawSettlement.channel_id,
            models.RawSettlement.channel_name,
            models.RawSettlement.game_id,
            models.RawSettlement.game_name,
            models.Game.discount_rate,
            project_code_subq.label("project_code"),
            project_name_subq.label("project_name"),
            company_name_subq.label("company_name"),
            party_name_subq.label("party_name"),
            models.RawSettlement.month,
            models.RawSettlement.raw_revenue,
        )
        .select_from(models.RawSettlement)
        .join(models.Game, models.RawSettlement.game_id == models.Game.game_id)
        .order_by(models.RawSettlement.month, models.RawSettlement.channel_name)
    )
    if filters:
        stmt = stmt.where(*filters)

    rows = list(await db.execute(stmt))
    if not rows:
        return []

    # ── Batch load dimensions ──
    pc_subq = (
        select(models.PublisherGameMapping.project_code)
        .where(models.PublisherGameMapping.game_id == models.Game.game_id)
        .limit(1).correlate(models.Game).scalar_subquery()
    )
    pn_subq = (
        select(models.PublisherGameMapping.project_name)
        .where(models.PublisherGameMapping.game_id == models.Game.game_id)
        .limit(1).correlate(models.Game).scalar_subquery()
    )
    gids = list({r.game_id for r in rows})
    dim_data = {}
    if gids:
        dim_rows = (await db.execute(
            select(models.Game.game_id,
                   pc_subq.label("pc"), pn_subq.label("pn"))
            .where(models.Game.game_id.in_(gids))
        )).all()
        for d in dim_rows:
            dim_data[d.game_id] = {"project_code": d.pc, "project_name": d.pn}

    # ── Batch prefetch: Deductions (3D key) ──
    ded_keys = list({(r.channel_id, r.game_id, r.month) for r in rows})
    ded_map = {}
    if ded_keys:
        ded_rows = (await db.execute(
            select(models.Deduction).where(
                tuple_(models.Deduction.channel_id, models.Deduction.game_id, models.Deduction.month).in_(ded_keys)
            )
        )).scalars().all()
        for d in ded_rows:
            ded_map[(d.channel_id, d.game_id, d.month)] = d

    # ── Batch prefetch: IncomeSplitConfig ──
    all_months = {r.month for r in rows}
    gmin, gmax = _month_range(all_months)
    cfg_keys = list({(r.channel_id, r.game_id) for r in rows})
    cfg_map = {}
    if cfg_keys:
        cfg_rows = (await db.execute(
            select(models.IncomeSplitConfig).where(
                tuple_(models.IncomeSplitConfig.channel_id, models.IncomeSplitConfig.game_id).in_(cfg_keys),
                models.IncomeSplitConfig.effective_from < gmax,
                or_(models.IncomeSplitConfig.effective_to >= gmin, models.IncomeSplitConfig.effective_to.is_(None)),
            ).order_by(models.IncomeSplitConfig.effective_from.desc(), models.IncomeSplitConfig.id.desc())
        )).scalars().all()
        for c in cfg_rows:
            cfg_map.setdefault((c.channel_id, c.game_id), []).append(c)

    # ── Batch prefetch: ChannelLocks ──
    lock_map = {}
    if ded_keys:
        lock_rows = (await db.execute(
            select(models.ChannelLock).where(
                tuple_(models.ChannelLock.channel_id, models.ChannelLock.game_id, models.ChannelLock.month).in_(ded_keys)
            )
        )).scalars().all()
        for lk in lock_rows:
            lock_map[(lk.channel_id, lk.game_id, lk.month)] = lk

    # ── Build results ──
    results = []
    for row in rows:
        cid = row.channel_id
        gid = row.game_id
        m = row.month
        dim = dim_data.get(gid, {})

        raw_rev = Decimal(str(row.raw_revenue))
        discount = row.discount_rate

        # Deduction breakdown
        ded_row = ded_map.get((cid, gid, m))
        if ded_row:
            v_val, t_val, w_val, b_val = ded_row.vouchers, ded_row.test, ded_row.welfare, ded_row.bad_debt
            total_ded = (v_val + t_val + w_val + b_val).quantize(Decimal("0.01"))
        else:
            v_val = t_val = w_val = b_val = total_ded = Decimal("0.00")

        # Config lookup (shared helper)
        cfg_row = _find_active_config(cfg_map, (cid, gid), m)
        lock_row = lock_map.get((cid, gid, m))
        locked_real = lock_row.locked_real_revenue if lock_row else None
        locked_amt = lock_row.locked_settlement_amount if lock_row else None

        if cfg_row:
            real_rev, settlement = compute_settlement(
                raw_revenue=raw_rev, discount_rate=discount, total_deductions=total_ded,
                split_rate=cfg_row.split_rate, channel_fee_rate=cfg_row.channel_fee_rate,
                tax_rate=cfg_row.tax_rate, locked_real_revenue=locked_real,
                locked_settlement_amount=locked_amt, direction="income",
            )
            sr, cfr, tr = float(cfg_row.split_rate), float(cfg_row.channel_fee_rate), float(cfg_row.tax_rate)
        else:
            real_rev = (discount * raw_rev).quantize(Decimal("0.01"))
            settlement = None
            sr = cfr = tr = None

        results.append({
            "channel_name": row.channel_name,
            "channel_id": cid,
            "game_id": gid,
            "game_name": row.game_name,
            "company_name": row.company_name or "",
            "party_name": row.party_name if hasattr(row, 'party_name') else "",
            "project_code": dim.get("project_code"),
            "project_name": dim.get("project_name"),
            "month": m,
            "raw_revenue": float(raw_rev),
            "real_revenue": float(real_rev),
            "vouchers": float(v_val),
            "test": float(t_val),
            "welfare": float(w_val),
            "bad_debt": float(b_val),
            "total_deductions": float(total_ded),
            "split_rate": sr,
            "channel_fee_rate": cfr,
            "tax_rate": tr,
            "settlement_amount": float(settlement) if settlement is not None else None,
            "locked_real_revenue": float(locked_real) if locked_real is not None else None,
            "locked_settlement_amount": float(locked_amt) if locked_amt is not None else None,
        })

    return results


# ── Payment settlement query ──


async def query_payment_settlement(
    db: AsyncSession,
    start_month: str = None,
    end_month: str = None,
    publisher_name: str = None,
    game_id: str = None,
):
    """付款结算查询: 原始流水表跨渠道聚合 (publisher_id, game_id, month)。

    数据源: raw_settlements 跨渠道 SUM，通过 publisher_game_mapping 关联。
    """
    filters = []
    if start_month:
        filters.append(models.RawSettlement.month >= start_month)
    if end_month:
        filters.append(models.RawSettlement.month <= end_month)
    if game_id:
        filters.append(models.RawSettlement.game_id == game_id)
    if publisher_name:
        filters.append(models.Publisher.publisher_name == publisher_name)

    # ── 维度子查询 ──
    company_name_subq = build_company_name_subquery(models.Game)

    # ── 主查询 ──
    stmt = (
        select(
            models.Publisher.publisher_id,
            models.Publisher.publisher_name,
            models.Game.game_id,
            models.Game.game_name,
            models.Game.discount_rate,
            models.PublisherGameMapping.project_code,
            models.PublisherGameMapping.project_name,
            company_name_subq.label("company_name"),
            models.RawSettlement.month,
            func.sum(models.RawSettlement.raw_revenue).label("raw_revenue"),
        )
        .select_from(models.RawSettlement)
        .join(models.Game, models.RawSettlement.game_id == models.Game.game_id)
        .join(models.PublisherGameMapping, models.Game.game_id == models.PublisherGameMapping.game_id)
        .join(models.Publisher, models.PublisherGameMapping.publisher_id == models.Publisher.publisher_id)
        .where(*filters)
        .group_by(models.Publisher.publisher_id, models.Game.game_id, models.RawSettlement.month)
        .order_by(models.RawSettlement.month, models.Publisher.publisher_name)
    )

    rows = list(await db.execute(stmt))
    if not rows:
        return []

    # ── Batch load company names ──
    cn_subq = build_company_name_subquery(models.Game)
    gids = list({r.game_id for r in rows})
    cn_map = {}
    if gids:
        cn_rows = (await db.execute(
            select(models.Game.game_id, cn_subq.label("cn")).where(models.Game.game_id.in_(gids))
        )).all()
        for r in cn_rows:
            cn_map[r.game_id] = r.cn or ""

    # ── Batch prefetch: Deductions (cross-channel SUM, 2D key) ──
    ded_keys = list({(r.game_id, r.month) for r in rows})
    ded_map = {}
    if ded_keys:
        ded_rows = (await db.execute(
            select(
                models.Deduction.game_id, models.Deduction.month,
                func.coalesce(func.sum(models.Deduction.vouchers), 0).label("vouchers"),
                func.coalesce(func.sum(models.Deduction.test), 0).label("test"),
                func.coalesce(func.sum(models.Deduction.welfare), 0).label("welfare"),
                func.coalesce(func.sum(models.Deduction.bad_debt), 0).label("bad_debt"),
            ).where(tuple_(models.Deduction.game_id, models.Deduction.month).in_(ded_keys))
            .group_by(models.Deduction.game_id, models.Deduction.month)
        )).all()
        for d in ded_rows:
            ded_map[(d.game_id, d.month)] = d

    # ── Batch prefetch: PublisherLocks ──
    pub_lock_map = {}
    lock_keys = list({(r.publisher_id, r.game_id, r.month) for r in rows})
    if lock_keys:
        lock_rows = (await db.execute(
            select(models.PublisherLock).where(
                tuple_(models.PublisherLock.publisher_id, models.PublisherLock.game_id, models.PublisherLock.month).in_(lock_keys)
            )
        )).scalars().all()
        for lk in lock_rows:
            pub_lock_map[(lk.publisher_id, lk.game_id, lk.month)] = lk

    # ── Batch prefetch: PaymentSplitConfig ──
    all_months = {r.month for r in rows}
    gmin, gmax = _month_range(all_months)
    cfg_keys = list({(r.publisher_id, r.game_id) for r in rows})
    cfg_map = {}
    if cfg_keys:
        cfg_rows = (await db.execute(
            select(models.PaymentSplitConfig).where(
                tuple_(models.PaymentSplitConfig.publisher_id, models.PaymentSplitConfig.game_id).in_(cfg_keys),
                models.PaymentSplitConfig.effective_from < gmax,
                or_(models.PaymentSplitConfig.effective_to >= gmin, models.PaymentSplitConfig.effective_to.is_(None)),
            ).order_by(models.PaymentSplitConfig.effective_from.desc(), models.PaymentSplitConfig.id.desc())
        )).scalars().all()
        for c in cfg_rows:
            cfg_map.setdefault((c.publisher_id, c.game_id), []).append(c)

    # ── Build results ──
    results = []
    for row in rows:
        pid = row.publisher_id
        gid = row.game_id
        m = row.month
        discount = row.discount_rate
        raw_rev = Decimal(str(row.raw_revenue))

        d = ded_map.get((gid, m))
        if d:
            v_val, t_val, w_val, b_val = Decimal(str(d.vouchers)), Decimal(str(d.test)), Decimal(str(d.welfare)), Decimal(str(d.bad_debt))
            total_ded = (v_val + t_val + w_val + b_val).quantize(Decimal("0.01"))
        else:
            v_val = t_val = w_val = b_val = total_ded = Decimal("0.00")

        cfg_row = _find_active_config(cfg_map, (pid, gid), m)
        locked_real, locked_amt = resolve_locked_values(pub_lock_map, (pid, gid, m))

        if cfg_row:
            real_rev, settlement = compute_settlement(
                raw_revenue=raw_rev, discount_rate=discount, total_deductions=total_ded,
                split_rate=cfg_row.split_rate, channel_fee_rate=cfg_row.channel_fee_rate,
                tax_rate=cfg_row.tax_rate, fixed_fee=cfg_row.fixed_fee,
                locked_real_revenue=locked_real, locked_settlement_amount=locked_amt,
                direction="payment",
            )
            sr, cfr, tr, ff = float(cfg_row.split_rate), float(cfg_row.channel_fee_rate), float(cfg_row.tax_rate), float(cfg_row.fixed_fee)
        else:
            real_rev = (discount * raw_rev).quantize(Decimal("0.01"))
            settlement = None
            sr = cfr = tr = ff = None

        results.append({
            "publisher_name": row.publisher_name,
            "publisher_id": pid,
            "game_id": gid,
            "game_name": row.game_name,
            "company_name": cn_map.get(gid, ""),
            "project_code": row.project_code,
            "project_name": row.project_name,
            "month": m,
            "raw_revenue": float(raw_rev),
            "real_revenue": float(real_rev),
            "vouchers": float(v_val),
            "test": float(t_val),
            "welfare": float(w_val),
            "bad_debt": float(b_val),
            "total_deductions": float(total_ded),
            "split_rate": sr,
            "channel_fee_rate": cfr,
            "tax_rate": tr,
            "fixed_fee": ff,
            "settlement_amount": float(settlement) if settlement is not None else None,
            "effective_from": cfg_row.effective_from.isoformat() if cfg_row else None,
            "effective_to": cfg_row.effective_to.isoformat() if cfg_row and cfg_row.effective_to else None,
            "locked_real_revenue": float(locked_real) if locked_real is not None else None,
            "locked_settlement_amount": float(locked_amt) if locked_amt is not None else None,
        })

    return results


# ── Lightweight queries ──


async def query_channel_settlements(
    db: AsyncSession,
    start_month: str = None,
    end_month: str = None,
    channel_name: str = None,
    game_id: str = None,
) -> list[dict]:
    """原始流水表: raw_settlements 直接读取 (导入时已聚合)。"""
    filters = []
    if start_month:
        filters.append(models.RawSettlement.month >= start_month)
    if end_month:
        filters.append(models.RawSettlement.month <= end_month)
    if game_id:
        filters.append(models.RawSettlement.game_id == game_id)
    if channel_name:
        filters.append(models.RawSettlement.channel_name == channel_name)

    stmt = (
        select(
            models.RawSettlement.channel_name,
            models.RawSettlement.channel_id,
            models.RawSettlement.game_id,
            models.RawSettlement.game_name,
            models.RawSettlement.month,
            models.RawSettlement.raw_revenue,
        )
        .select_from(models.RawSettlement)
    )

    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(models.RawSettlement.month.desc(), models.RawSettlement.channel_name)

    rows = list(await db.execute(stmt))
    return [
        {
            "id": i + 1,
            "channel_name": r.channel_name,
            "channel_id": r.channel_id,
            "game_id": r.game_id,
            "game_name": r.game_name,
            "month": r.month,
            "raw_revenue": float(r.raw_revenue) if r.raw_revenue else 0.0,
            "created_at": "",
            "updated_at": "",
        }
        for i, r in enumerate(rows)
    ]


async def query_settlement_channels(db: AsyncSession) -> list[dict]:
    """返回原始流水表中存在的渠道列表（用于弹性导入的渠道选择器）。"""
    rows = (await db.execute(
        select(
            models.RawSettlement.channel_id,
            models.RawSettlement.channel_name,
        )
        .distinct()
        .order_by(models.RawSettlement.channel_name)
    )).all()
    return [{"channel_id": r.channel_id, "channel_name": r.channel_name} for r in rows]
