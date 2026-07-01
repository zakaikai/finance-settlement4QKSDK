"""Settlement service — re-export layer.

Backward-compatible re-exports from specialized deep modules:
  settlement_query   — query_income_settlement, query_payment_settlement, etc.
  split_config_service — batch_upsert, upsert_split_configs, save_income_split_config
  flexible_import    — compare_imported_rows
"""
# ── Formula (re-exported for test backward compat) ──
from .settlement_formula import hydrate_formula_input, _aggregate_channel_raw_revenue

# ── Queries ──
from .settlement_query import (
    query_income_settlement,
    query_payment_settlement,
    query_channel_settlements,
    query_settlement_channels,
)

# Backward-compat aliases for full-export
query_full_income_export = query_income_settlement
query_full_payment_export = query_payment_settlement

# ── Split config CRUD ──
from .split_config_service import (
    batch_upsert,
    upsert_split_configs,
    save_income_split_config,
    _save_income_split_config,  # backward-compat alias
)

# ── Import comparison (lives in flexible_import) ──
from .flexible_import import compare_imported_rows


# ── Lock dispatcher (kept here — thin delegation to lock_service) ──


async def lock_settlement(db, game_id, channel_id, publisher_name, month, field, value):
    """Lock or unlock real_revenue / settlement_amount."""
    from datetime import datetime
    from decimal import Decimal as D
    from .lock_service import apply_lock, remove_lock
    from .. import models
    from sqlalchemy import select

    raw = value
    unlock = raw is None or str(raw).strip() in ("", "=")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if publisher_name:
        pub = (await db.execute(
            select(models.Publisher.publisher_id).where(
                models.Publisher.publisher_name == publisher_name
            )
        )).scalar_one_or_none()
        if not pub:
            raise ValueError(f"研发商户 '{publisher_name}' 不存在")
        entity_id = pub
        lock_type = "publisher"
        audit_name = publisher_name
    else:
        entity_id = channel_id
        lock_type = "channel"
        audit_name = str(channel_id)

    if unlock:
        return await remove_lock(db, lock_type, entity_id, game_id, month, field, now=now, audit_name=audit_name)
    else:
        try:
            locked_val = D(str(raw))
        except Exception:
            raise ValueError("value 必须为有效数字")
        return await apply_lock(db, lock_type, entity_id, game_id, month, field, locked_val, now=now, audit_name=audit_name)
