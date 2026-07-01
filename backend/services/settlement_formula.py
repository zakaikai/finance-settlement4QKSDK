"""Settlement formula — single authority for channel and publisher settlement computation.

Also houses FormulaInput + hydrate_formula_input (moved from settlement_service)
so lock_service can import them at top level without circular dependency.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models


@dataclass
class FormulaInput:
    """All data needed to compute settlement formula for one (entity, game, month)."""
    raw_revenue: Decimal
    discount_rate: Decimal
    total_deductions: Decimal
    split_rate: Decimal | None        # None = no active config found
    channel_fee_rate: Decimal | None
    tax_rate: Decimal | None
    fixed_fee: Decimal | None
    locked_real_revenue: Decimal | None
    locked_settlement_amount: Decimal | None


def compute(
    *,
    raw_revenue: Decimal,
    discount_rate: Decimal,
    total_deductions: Decimal,
    split_rate: Decimal,
    channel_fee_rate: Decimal,
    tax_rate: Decimal,
    fixed_fee: Decimal = Decimal("0"),
    locked_real_revenue: Decimal | None = None,
    locked_settlement_amount: Decimal | None = None,
    direction: str,
) -> tuple[Decimal, Decimal]:
    """Return (real_revenue, settlement_amount).

    Locked values override formula-computed values when present.
    direction: "income" → split_rate * (1 - channel_fee_rate) * (1 - tax_rate)
    direction: "payment" → split_rate * (1 - channel_fee_rate) * (1 - tax_rate) + fixed_fee
    """
    if locked_real_revenue is not None:
        real_revenue = locked_real_revenue
    else:
        real_revenue = (discount_rate * raw_revenue).quantize(Decimal("0.01"))

    if locked_settlement_amount is not None:
        return real_revenue, locked_settlement_amount

    net_revenue = real_revenue - total_deductions

    if direction == "income":
        settlement = (
            net_revenue
            * split_rate
            * (Decimal("1") - channel_fee_rate)
            * (Decimal("1") - tax_rate)
        ).quantize(Decimal("0.01"))
    else:
        settlement = (
            net_revenue
            * split_rate
            * (Decimal("1") - channel_fee_rate)
            * (Decimal("1") - tax_rate)
            + fixed_fee
        ).quantize(Decimal("0.01"))

    return real_revenue, settlement


async def _aggregate_channel_raw_revenue(
    db: AsyncSession,
    game_ids: list[str],
    month: str,
    channel_id: int,
) -> dict[str, float]:
    """Return {game_id: raw_revenue} from 原始流水表."""
    if not game_ids:
        return {}

    rows = (
        await db.execute(
            select(
                models.RawSettlement.game_id,
                models.RawSettlement.raw_revenue,
            )
            .where(
                models.RawSettlement.channel_id == channel_id,
                models.RawSettlement.game_id.in_(game_ids),
                models.RawSettlement.month == month,
            )
        )
    ).all()
    return {r.game_id: float(r.raw_revenue) for r in rows if r.raw_revenue}


async def hydrate_formula_input(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    game_id: str,
    month: str,
) -> FormulaInput:
    """Single-row: query all data needed by compute().

    Used by lock_service._compute_* (after unlock) to get the formula-based value.
    """
    from ..utils.dates import month_bounds as _mb

    # Discount rate
    game_row = (await db.execute(
        select(models.Game.discount_rate).where(models.Game.game_id == game_id)
    )).scalar_one_or_none()
    discount = game_row if game_row else Decimal("0")

    month_start_date, month_end_date = _mb(month)

    if entity_type == "channel":
        raw_map = await _aggregate_channel_raw_revenue(db, [game_id], month, entity_id)
        raw_rev = Decimal(str(raw_map.get(game_id, 0)))

        ded_row = (await db.execute(
            select(models.Deduction).where(
                models.Deduction.channel_id == entity_id,
                models.Deduction.game_id == game_id,
                models.Deduction.month == month,
            )
        )).scalar_one_or_none()

        v_val = Decimal(str(ded_row.vouchers)) if ded_row else Decimal("0")
        t_val = Decimal(str(ded_row.test)) if ded_row else Decimal("0")
        w_val = Decimal(str(ded_row.welfare)) if ded_row else Decimal("0")
        b_val = Decimal(str(ded_row.bad_debt)) if ded_row else Decimal("0")
        total_ded = (v_val + t_val + w_val + b_val).quantize(Decimal("0.01"))

        cfg = (await db.execute(
            select(models.IncomeSplitConfig)
            .where(
                models.IncomeSplitConfig.channel_id == entity_id,
                models.IncomeSplitConfig.game_id == game_id,
                models.IncomeSplitConfig.effective_from < month_end_date,
            )
            .order_by(models.IncomeSplitConfig.effective_from.desc(), models.IncomeSplitConfig.id.desc())
        )).scalars().first()

        lock_row = (await db.execute(
            select(models.ChannelLock).where(
                models.ChannelLock.channel_id == entity_id,
                models.ChannelLock.game_id == game_id,
                models.ChannelLock.month == month,
            )
        )).scalar_one_or_none()

        cfg_valid = cfg and (cfg.effective_to is None or cfg.effective_to >= month_start_date)
        return FormulaInput(
            raw_revenue=raw_rev,
            discount_rate=discount,
            total_deductions=total_ded,
            split_rate=cfg.split_rate if cfg_valid else None,
            channel_fee_rate=cfg.channel_fee_rate if cfg_valid else None,
            tax_rate=cfg.tax_rate if cfg_valid else None,
            fixed_fee=None,
            locked_real_revenue=lock_row.locked_real_revenue if lock_row else None,
            locked_settlement_amount=lock_row.locked_settlement_amount if lock_row else None,
        )

    else:  # publisher
        # Aggregate raw_revenue across all channels from raw_settlements
        raw_row = (await db.execute(
            select(func.sum(models.RawSettlement.raw_revenue)).where(
                models.RawSettlement.game_id == game_id,
                models.RawSettlement.month == month,
            )
        )).scalar_one()
        raw_rev = Decimal(str(raw_row)) if raw_row else Decimal("0")

        ded_row = (await db.execute(
            select(
                func.coalesce(func.sum(models.Deduction.vouchers), 0),
                func.coalesce(func.sum(models.Deduction.test), 0),
                func.coalesce(func.sum(models.Deduction.welfare), 0),
                func.coalesce(func.sum(models.Deduction.bad_debt), 0),
            ).where(
                models.Deduction.game_id == game_id,
                models.Deduction.month == month,
            )
        )).one()
        total_ded = Decimal(str(sum(ded_row)))

        cfg = (await db.execute(
            select(models.PaymentSplitConfig)
            .where(
                models.PaymentSplitConfig.publisher_id == entity_id,
                models.PaymentSplitConfig.game_id == game_id,
                models.PaymentSplitConfig.effective_from < month_end_date,
            )
            .order_by(models.PaymentSplitConfig.effective_from.desc(), models.PaymentSplitConfig.id.desc())
        )).scalars().first()

        lock_row = (await db.execute(
            select(models.PublisherLock).where(
                models.PublisherLock.publisher_id == entity_id,
                models.PublisherLock.game_id == game_id,
                models.PublisherLock.month == month,
            )
        )).scalar_one_or_none()

        cfg_valid = cfg and (cfg.effective_to is None or cfg.effective_to >= month_start_date)
        return FormulaInput(
            raw_revenue=raw_rev,
            discount_rate=discount,
            total_deductions=total_ded,
            split_rate=cfg.split_rate if cfg_valid else None,
            channel_fee_rate=cfg.channel_fee_rate if cfg_valid else None,
            tax_rate=cfg.tax_rate if cfg_valid else None,
            fixed_fee=cfg.fixed_fee if cfg_valid else None,
            locked_real_revenue=lock_row.locked_real_revenue if lock_row else None,
            locked_settlement_amount=lock_row.locked_settlement_amount if lock_row else None,
        )
