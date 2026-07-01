"""Lock/unlock real_revenue and settlement_amount for channel and publisher settlements.

Single deep module — parameterizes the Channel/Publisher difference via _LockCfg registry.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("finance-settlement")

from .. import models
from .settlement_formula import compute as compute_settlement, hydrate_formula_input
from .snapshot_service import is_month_closed, current_working_month

LockTypeStr = Literal["channel", "publisher"]
FieldName = Literal["real_revenue", "settlement_amount"]


# ── Lock config registry ──


@dataclass(frozen=True)
class _LockCfg:
    model_cls: type
    identity_field: str
    source_type: str
    config_cls: type
    config_fk_field: str
    direction: str
    extra_config_fields: tuple[str, ...]
    audit_entity_label: str
    compute_fn: Callable


_CHANNEL = _LockCfg(
    model_cls=models.ChannelLock,
    identity_field="channel_id",
    source_type="channel_lock",
    config_cls=models.IncomeSplitConfig,
    config_fk_field="channel_id",
    direction="income",
    extra_config_fields=(),
    audit_entity_label="channel_id",
    compute_fn=None,  # set after _compute_channel is defined
)

_PUBLISHER = _LockCfg(
    model_cls=models.PublisherLock,
    identity_field="publisher_id",
    source_type="publisher_lock",
    config_cls=models.PaymentSplitConfig,
    config_fk_field="publisher_id",
    direction="payment",
    extra_config_fields=("fixed_fee",),
    audit_entity_label="publisher",
    compute_fn=None,  # set after _compute_publisher is defined
)

_REGISTRY: dict[str, _LockCfg] = {
    "channel": _CHANNEL,
    "publisher": _PUBLISHER,
}


def _get_cfg(lock_type: str) -> _LockCfg:
    if lock_type not in _REGISTRY:
        raise ValueError(f"Unknown lock_type: {lock_type}")
    return _REGISTRY[lock_type]


# ── Private helpers ──


def _field_to_col(field: str) -> str:
    return "locked_real_revenue" if field == "real_revenue" else "locked_settlement_amount"


async def _add_audit(db: AsyncSession, action: str, detail: str, now: str):
    db.add(models.AuditLog(action=action, detail=detail, user="", created_at=now))
    await db.commit()


# ── Formula recomputation (moved from settlement_service) ──


async def _compute_channel(db: AsyncSession, game_id: str, entity_id: int, month: str, field: str):
    """Compute formula value for channel/income after unlock. Returns float or None."""
    inp = await hydrate_formula_input(db, "channel", entity_id, game_id, month)
    if field == "real_revenue":
        return float(inp.discount_rate * inp.raw_revenue)
    if inp.split_rate is None:
        return None
    _, settlement = compute_settlement(
        raw_revenue=inp.raw_revenue, discount_rate=inp.discount_rate,
        total_deductions=inp.total_deductions,
        split_rate=inp.split_rate,
        channel_fee_rate=inp.channel_fee_rate or Decimal("0"),
        tax_rate=inp.tax_rate or Decimal("0"),
        direction="income",
    )
    return float(settlement)


async def _compute_publisher(db: AsyncSession, game_id: str, entity_id: int, month: str, field: str):
    """Compute formula value for publisher/payment after unlock. Returns float or None."""
    inp = await hydrate_formula_input(db, "publisher", entity_id, game_id, month)
    if field == "real_revenue":
        return float(inp.discount_rate * inp.raw_revenue)
    if inp.split_rate is None:
        return None
    _, settlement = compute_settlement(
        raw_revenue=inp.raw_revenue, discount_rate=inp.discount_rate,
        total_deductions=inp.total_deductions,
        split_rate=inp.split_rate,
        channel_fee_rate=inp.channel_fee_rate or Decimal("0"),
        tax_rate=inp.tax_rate or Decimal("0"),
        fixed_fee=inp.fixed_fee or Decimal("0"),
        direction="payment",
    )
    return float(settlement)


# Wire up compute_fn references (couldn't do it before the functions were defined)
_CHANNEL = _LockCfg(
    model_cls=models.ChannelLock,
    identity_field="channel_id",
    source_type="channel_lock",
    config_cls=models.IncomeSplitConfig,
    config_fk_field="channel_id",
    direction="income",
    extra_config_fields=(),
    audit_entity_label="channel_id",
    compute_fn=_compute_channel,
)

_PUBLISHER = _LockCfg(
    model_cls=models.PublisherLock,
    identity_field="publisher_id",
    source_type="publisher_lock",
    config_cls=models.PaymentSplitConfig,
    config_fk_field="publisher_id",
    direction="payment",
    extra_config_fields=("fixed_fee",),
    audit_entity_label="publisher",
    compute_fn=_compute_publisher,
)

_REGISTRY["channel"] = _CHANNEL
_REGISTRY["publisher"] = _PUBLISHER


# ── Public API ──


def resolve_locked_values(lock_map: dict, key: tuple):
    """Pure function: extract (locked_real_revenue, locked_settlement_amount) from prefetched lock map.

    Works with both ChannelLock and PublisherLock since both share the same column names.
    """
    lock_row = lock_map.get(key)
    if lock_row is not None:
        return (lock_row.locked_real_revenue, lock_row.locked_settlement_amount)
    return (None, None)


async def write_lock_inline(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
    field: FieldName,
    value: Decimal,
    *,
    now: str,
) -> dict:
    """Core lock write — no commit, no audit. Embeddable inside larger transactions.

    Only writes to lock table. ARAP snapshot is triggered separately by user action.
    """
    cfg = _get_cfg(lock_type)
    identity_col = getattr(cfg.model_cls, cfg.identity_field)

    lock_row = (await db.execute(
        select(cfg.model_cls).where(
            identity_col == entity_id,
            cfg.model_cls.game_id == game_id,
            cfg.model_cls.month == month,
        )
    )).scalar_one_or_none()

    old_val = getattr(lock_row, _field_to_col(field), None) if lock_row else None

    if lock_row is None:
        lock_row = cfg.model_cls(
            **{cfg.identity_field: entity_id},
            game_id=game_id, month=month,
            created_at=now, updated_at=now,
        )
        db.add(lock_row)
        await db.flush()

    setattr(lock_row, _field_to_col(field), value)
    lock_row.updated_at = now
    # Clear confirmed_month so the next snapshot re-processes this lock
    if lock_row.confirmed_month is not None:
        lock_row.confirmed_month = None

    return {
        "lock_row_id": lock_row.id,
        "old_val": old_val,
        "field": field,
        "value": float(value),
    }


async def apply_lock(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
    field: FieldName,
    value: Decimal,
    *,
    now: str,
    audit_name: str = "",
) -> dict:
    """Lock real_revenue or settlement_amount, creating journal entries, snapshot, and audit log."""
    cfg = _get_cfg(lock_type)
    result = await write_lock_inline(
        db, lock_type, entity_id, game_id, month, field, value, now=now,
    )
    await db.commit()
    logger.info(f"[lock] apply: type={lock_type} entity={entity_id} game={game_id} month={month} field={field} value={value} old={result['old_val']}")
    detail = f"{cfg.audit_entity_label}={audit_name or entity_id} game={game_id} month={month} field={field} new={value} old={result['old_val']}"
    await _add_audit(db, "settlement.lock", detail, now)
    return {"status": "locked", "field": field, "value": float(value)}


async def _get_snapshot_diff(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
) -> dict | None:
    """Compare settlement snapshot against current live formula-input state.

    ChannelSettlement 已废止 (2026-06)，diff 比较不再可用。
    返回 None 表示无历史快照。
    """
    return None


async def remove_lock(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
    field: FieldName,
    *,
    now: str,
    audit_name: str = "",
) -> dict:
    """Unlock real_revenue or settlement_amount, returning formula value."""
    cfg = _get_cfg(lock_type)
    identity_col = getattr(cfg.model_cls, cfg.identity_field)

    lock_row = (await db.execute(
        select(cfg.model_cls).where(
            identity_col == entity_id,
            cfg.model_cls.game_id == game_id,
            cfg.model_cls.month == month,
        )
    )).scalar_one_or_none()

    old_val = getattr(lock_row, _field_to_col(field), None) if lock_row else None

    if lock_row:
        setattr(lock_row, _field_to_col(field), None)
        lock_row.updated_at = now
        if lock_row.confirmed_month is not None:
            lock_row.confirmed_month = None

    await db.commit()
    formula_val = await cfg.compute_fn(db, game_id, entity_id, month, field)
    logger.info(f"[lock] remove: type={lock_type} entity={entity_id} game={game_id} month={month} field={field} old={old_val} formula={formula_val}")
    detail = f"{cfg.audit_entity_label}={audit_name or entity_id} game={game_id} month={month} field={field} old={old_val}"
    await _add_audit(db, "settlement.unlock", detail, now)
    return {
        "status": "unlocked",
        "field": field,
        "formula_value": formula_val,
    }


async def compute_unlocked_value(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
    field: FieldName,
) -> float | None:
    """Compute formula-based value without touching any lock row. Read-only."""
    cfg = _get_cfg(lock_type)
    return await cfg.compute_fn(db, game_id, entity_id, month, field)


async def get_lock(
    db: AsyncSession,
    lock_type: LockTypeStr,
    entity_id: int,
    game_id: str,
    month: str,
):
    """Fetch existing lock row, or None."""
    cfg = _get_cfg(lock_type)
    identity_col = getattr(cfg.model_cls, cfg.identity_field)
    return (await db.execute(
        select(cfg.model_cls).where(
            identity_col == entity_id,
            cfg.model_cls.game_id == game_id,
            cfg.model_cls.month == month,
        )
    )).scalar_one_or_none()


async def diagnose_lock_cs_consistency(db: AsyncSession) -> list[dict]:
    """Lock consistency check — ChannelLock table is the single authoritative source.

    No longer compares with ChannelSettlement (table removed).
    Returns empty list (consistent by construction).
    """
    return []


# ── Backward-compat alias ──
_write_lock_inline = write_lock_inline
