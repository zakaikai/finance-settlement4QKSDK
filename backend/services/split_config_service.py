"""Split config CRUD — date-range aware config management.

Deep module: three functions managing split config lifecycle.
- batch_upsert: generic FK-resolve + upsert helper
- upsert_split_configs: batch save with close-previous + create-new date-range logic
- save_income_split_config: single-row variant (delegates to same core as upsert_split_configs)
"""
from decimal import Decimal
from datetime import date

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..utils.dates import month_start, month_bounds, prev_month_end


# ── Core: single-row split config upsert (close-previous + create-new) ──


async def _upsert_one_split_config(
    db: AsyncSession,
    config_cls: type,
    identity_col,
    identity_val,
    game_id: str,
    month_first: date,
    field_updates: dict[str, Decimal | None],
    extra_fields: tuple[str, ...] = (),
):
    """Upsert a single split config row: exact-match UPDATE or close+create.

    Core logic shared by upsert_split_configs (batch, FK-resolved) and
    save_income_split_config (single-row, identity already known).
    """
    prev_last = prev_month_end(month_first.isoformat()[:7])
    _, next_month = month_bounds(month_first.isoformat()[:7])

    # Check for exact match — UPDATE instead of close+insert.
    # Prefer active (effective_to IS NULL) then latest id,
    # in case duplicate rows exist from before the UC fix.
    exact_match = (
        await db.execute(
            select(config_cls)
            .where(
                identity_col == identity_val,
                config_cls.game_id == game_id,
                config_cls.effective_from == month_first,
            )
            .order_by(config_cls.effective_to.is_(None).desc(), config_cls.id.desc())
        )
    ).scalars().first()

    if exact_match:
        for fname, fval in field_updates.items():
            if fval is not None:
                setattr(exact_match, fname, fval)
        for ef in extra_fields:
            v = field_updates.get(ef)
            if v is not None:
                setattr(exact_match, ef, v)
        # Reset stale effective_to from pre-fix corruption
        if exact_match.effective_to is not None:
            exact_match.effective_to = None
        return

    # No exact match — close all overlapping configs, create new
    existings = (
        await db.execute(
            select(config_cls)
            .where(
                identity_col == identity_val,
                config_cls.game_id == game_id,
                config_cls.effective_from < next_month,
            )
            .order_by(config_cls.effective_from.desc())
        )
    ).scalars().all()

    prev_config = existings[0] if existings else None
    for ex in existings:
        if ex.effective_to is None or ex.effective_to >= month_first:
            ex.effective_to = prev_last

    def _inherit(fname):
        v = field_updates.get(fname)
        if v is not None:
            return v
        return getattr(prev_config, fname) if prev_config else Decimal("0")

    kwargs = {
        identity_col.key: identity_val,
        "game_id": game_id,
        "effective_from": month_first,
        "effective_to": None,
        "split_rate": _inherit("split_rate"),
        "channel_fee_rate": _inherit("channel_fee_rate"),
        "tax_rate": _inherit("tax_rate"),
    }
    for ef in extra_fields:
        kwargs[ef] = _inherit(ef)

    db.add(config_cls(**kwargs))


# ── Generic FK-resolve + upsert ──


async def batch_upsert(db, items, fk_model, fk_col_name, fk_getter,
                       fk_cache_key, model_cls, match_keys, set_fields):
    """Generic FK-resolve + upsert across a list of items."""
    from . import fk_resolver

    await fk_resolver.reset()
    fk_col = getattr(model_cls, match_keys[0])

    for item in items:
        fk_val = await fk_resolver.resolve(db, fk_model, fk_col_name, fk_getter(item), fk_cache_key)
        if fk_val is None:
            continue

        conditions = [fk_col == fk_val]
        for k in match_keys[1:]:
            conditions.append(getattr(model_cls, k) == getattr(item, k))

        existing = (await db.execute(
            select(model_cls).where(and_(*conditions))
        )).scalar_one_or_none()

        if existing:
            for field in set_fields:
                setattr(existing, field, getattr(item, field))
        else:
            kwargs = {match_keys[0]: fk_val}
            for k in match_keys[1:]:
                kwargs[k] = getattr(item, k)
            for field in set_fields:
                kwargs[field] = getattr(item, field)
            db.add(model_cls(**kwargs))

    await db.commit()


# ── Split config batch save (close previous + create new) ──


async def upsert_split_configs(db, items, *, fk_model_cls, fk_name_field,
                                fk_cache_key, fk_col_name, config_cls,
                                extra_fields=()):
    """Batch save split configs — close previous active, create new.

    If a config already exists with the exact same effective_from, UPDATE in-place
    (avoiding UniqueConstraint violation). Otherwise close overlapping + create new.

    Delegates to _upsert_one_split_config for the per-row core logic.
    """
    from . import fk_resolver

    await fk_resolver.reset()
    for item in items:
        # Handle delete action — remove by id, no other processing needed
        if item.action == "delete" and item.id:
            existing = await db.get(config_cls, item.id)
            if existing:
                await db.delete(existing)
            continue

        fk_name = getattr(item, fk_name_field)
        fk_val = await fk_resolver.resolve(db, fk_model_cls, fk_name_field, fk_name, fk_cache_key)
        if fk_val is None:
            continue

        eff_month = item.effective_from.isoformat()[:7] if item.effective_from else ""
        mf = month_start(eff_month) if eff_month else None
        if not mf:
            continue

        identity_col = getattr(config_cls, fk_col_name)

        field_updates = {}
        if item.split_rate is not None:
            field_updates["split_rate"] = Decimal(str(item.split_rate))
        if item.channel_fee_rate is not None:
            field_updates["channel_fee_rate"] = Decimal(str(item.channel_fee_rate))
        if item.tax_rate is not None:
            field_updates["tax_rate"] = Decimal(str(item.tax_rate))
        for ef in extra_fields:
            v = getattr(item, ef, None)
            if v is not None:
                field_updates[ef] = Decimal(str(v))

        await _upsert_one_split_config(
            db, config_cls,
            identity_col=identity_col,
            identity_val=fk_val,
            game_id=item.game_id,
            month_first=mf,
            field_updates=field_updates,
            extra_fields=extra_fields,
        )

    await db.commit()


# ── Single-row split config save (used by flexible import) ──


async def save_income_split_config(
    db: AsyncSession, channel_id: int, game_id: str, month: str,
    split_rate: Decimal | None = None,
    channel_fee_rate: Decimal | None = None,
    tax_rate: Decimal | None = None,
):
    """Close previous active IncomeSplitConfig and create a new one for the given month.

    Delegates to the shared _upsert_one_split_config core (same as upsert_split_configs).
    Missing fields inherit from the previous active config.
    """
    mf = month_start(month)
    field_updates = {}
    if split_rate is not None:
        field_updates["split_rate"] = split_rate
    if channel_fee_rate is not None:
        field_updates["channel_fee_rate"] = channel_fee_rate
    if tax_rate is not None:
        field_updates["tax_rate"] = tax_rate

    await _upsert_one_split_config(
        db, models.IncomeSplitConfig,
        identity_col=models.IncomeSplitConfig.channel_id,
        identity_val=channel_id,
        game_id=game_id,
        month_first=mf,
        field_updates=field_updates,
    )


# ── Backward-compat alias (tests still reference underscore-prefixed name) ──
_save_income_split_config = save_income_split_config
