# -*- coding: utf-8 -*-
"""Basic data business logic extracted from routers/basic_data.py."""
from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from .. import models
from . import fk_resolver

# ── FK dependency registry ──
# Each entity declares which tables reference it, so delete checks are data-driven.

FK_DEPENDENCIES = {
    "Game": [
        (models.CompanyGameMapping, models.CompanyGameMapping.game_id),
        (models.PublisherGameMapping, models.PublisherGameMapping.game_id),
        (models.IncomeSplitConfig, models.IncomeSplitConfig.game_id),
        (models.PaymentSplitConfig, models.PaymentSplitConfig.game_id),
        #(models.RawTransaction, models.RawTransaction.game_id),  # 废止 2026-06
        (models.RawSettlement, models.RawSettlement.game_id),
        (models.Deduction, models.Deduction.game_id),
        (models.ChannelLock, models.ChannelLock.game_id),
        (models.PublisherLock, models.PublisherLock.game_id),
    ],
    "Company": [
        (models.CompanyGameMapping, models.CompanyGameMapping.company_id),
    ],
    "Publisher": [
        (models.PublisherGameMapping, models.PublisherGameMapping.publisher_id),
        (models.PaymentSplitConfig, models.PaymentSplitConfig.publisher_id),
        (models.PublisherLock, models.PublisherLock.publisher_id),
    ],
    "ChannelCategory": [
        (models.ChannelLock, models.ChannelLock.channel_id),
    ],
}


async def check_fk_deps(db: AsyncSession, entity_type: str, fk_value, label: str | None = None):
    """Raise 409 if any dependent rows reference *fk_value*."""
    deps = FK_DEPENDENCIES.get(entity_type, [])
    lbl = label or entity_type
    for dep_model, dep_col in deps:
        stmt = select(func.count()).select_from(dep_model).where(dep_col == fk_value)
        count = (await db.execute(stmt)).scalar() or 0
        if count > 0:
            raise HTTPException(
                409,
                f"{lbl} 存在 {count} 条关联数据，请先删除关联数据再重试",
            )


# ── Channel batch save ──


async def batch_save_channels(db: AsyncSession, items: list, skip_duplicates: bool = False) -> None:
    """Create / update / delete channel 3-level hierarchy entries.

    When skip_duplicates=True (used by template import), existing SubChannels are
    silently skipped instead of raising 409. UI-driven saves leave it False for
    immediate user feedback.
    """
    await fk_resolver.reset()

    for item in items:
        if item.action == "create":
            if not item.channel_name or not item.channel_name.strip():
                raise HTTPException(400, "一级渠道名称不能为空")
            if not item.backend_channel_name or not item.backend_channel_name.strip():
                raise HTTPException(400, "二级渠道名称不能为空")
            if not item.sub_channel_name or not item.sub_channel_name.strip():
                raise HTTPException(400, "三级渠道名称不能为空")

        if item.action == "delete":
            orig_ch_id = await fk_resolver.resolve(
                db, models.ChannelCategory, "channel_name",
                item.orig_channel_name, "channel_categories",
            )
            if orig_ch_id is None:
                continue
            orig_bk = await db.execute(
                select(models.BackendChannel).where(
                    and_(
                        models.BackendChannel.channel_id == orig_ch_id,
                        models.BackendChannel.backend_channel_name == item.orig_backend_channel_name,
                    )
                )
            )
            orig_bk_row = orig_bk.scalar_one_or_none()
            if orig_bk_row is None:
                continue
            sub = await db.execute(
                select(models.SubChannel).where(
                    and_(
                        models.SubChannel.backend_channel_id == orig_bk_row.backend_channel_id,
                        models.SubChannel.sub_channel_name == item.orig_sub_channel_name,
                    )
                )
            )
            sub_row = sub.scalar_one_or_none()
            if sub_row:
                await db.delete(sub_row)
            continue

        if item.action == "create":
            ch_id = await fk_resolver.resolve(
                db, models.ChannelCategory, "channel_name",
                item.channel_name, "channel_categories",
            )
            if ch_id is None:
                cat = models.ChannelCategory(channel_name=item.channel_name)
                db.add(cat)
                await db.flush()
                ch_id = cat.channel_id
                await fk_resolver.cache_set(("channel_categories", item.channel_name), ch_id)

            bk = await db.execute(
                select(models.BackendChannel).where(
                    and_(
                        models.BackendChannel.channel_id == ch_id,
                        models.BackendChannel.backend_channel_name == item.backend_channel_name,
                    )
                )
            )
            bk_row = bk.scalar_one_or_none()
            if bk_row is None:
                bk_row = models.BackendChannel(
                    backend_channel_name=item.backend_channel_name, channel_id=ch_id,
                )
                db.add(bk_row)
                await db.flush()

            # Check duplicate SubChannel
            sub_existing = await db.execute(
                select(models.SubChannel).where(
                    and_(
                        models.SubChannel.backend_channel_id == bk_row.backend_channel_id,
                        models.SubChannel.sub_channel_name == item.sub_channel_name,
                    )
                )
            )
            if sub_existing.scalar_one_or_none():
                if skip_duplicates:
                    continue
                raise HTTPException(
                    409,
                    f"三级渠道 '{item.sub_channel_name}' 在 '{item.backend_channel_name}' 下已存在",
                )

            sub = models.SubChannel(
                sub_channel_name=item.sub_channel_name,
                backend_channel_id=bk_row.backend_channel_id,
            )
            db.add(sub)
            continue

        # ── Update ──
        if item.action == "update":
            orig_ch_name = item.orig_channel_name or item.channel_name
            orig_bk_name = item.orig_backend_channel_name or item.backend_channel_name
            orig_sub_name = item.orig_sub_channel_name or item.sub_channel_name

            ch_id = None
            if item.channel_name != orig_ch_name:
                new_ch_id = await fk_resolver.resolve(
                    db, models.ChannelCategory, "channel_name",
                    item.channel_name, "channel_categories",
                )
                if new_ch_id is not None:
                    ch_id = new_ch_id
                else:
                    orig_ch_id = await fk_resolver.resolve(
                        db, models.ChannelCategory, "channel_name",
                        orig_ch_name, "channel_categories",
                    )
                    if orig_ch_id is None:
                        continue
                    cat = (await db.execute(
                        select(models.ChannelCategory).where(
                            models.ChannelCategory.channel_id == orig_ch_id,
                        )
                    )).scalar_one_or_none()
                    if cat:
                        cat.channel_name = item.channel_name
                        ch_id = orig_ch_id
            else:
                ch_id = await fk_resolver.resolve(
                    db, models.ChannelCategory, "channel_name",
                    item.channel_name, "channel_categories",
                )
            if ch_id is None:
                continue

            bk = await db.execute(
                select(models.BackendChannel).where(
                    and_(
                        models.BackendChannel.channel_id == ch_id,
                        models.BackendChannel.backend_channel_name == item.backend_channel_name,
                    )
                )
            )
            bk_row = bk.scalar_one_or_none()
            if bk_row is None:
                bk_row = models.BackendChannel(
                    backend_channel_name=item.backend_channel_name, channel_id=ch_id,
                )
                db.add(bk_row)
                await db.flush()
            target_bk_id = bk_row.backend_channel_id

            orig_ch_id2 = await fk_resolver.resolve(
                db, models.ChannelCategory, "channel_name",
                orig_ch_name, "channel_categories",
            )
            if orig_ch_id2 is None:
                continue
            orig_bk = await db.execute(
                select(models.BackendChannel).where(
                    and_(
                        models.BackendChannel.channel_id == orig_ch_id2,
                        models.BackendChannel.backend_channel_name == orig_bk_name,
                    )
                )
            )
            orig_bk_row2 = orig_bk.scalar_one_or_none()
            if orig_bk_row2 is None:
                continue
            sub = await db.execute(
                select(models.SubChannel).where(
                    and_(
                        models.SubChannel.backend_channel_id == orig_bk_row2.backend_channel_id,
                        models.SubChannel.sub_channel_name == orig_sub_name,
                    )
                )
            )
            sub_row = sub.scalar_one_or_none()
            if sub_row:
                sub_row.sub_channel_name = item.sub_channel_name
                if sub_row.backend_channel_id != target_bk_id:
                    sub_row.backend_channel_id = target_bk_id

    await db.commit()


# ── Company-Game mapping batch save ──


async def batch_save_company_games(db: AsyncSession, items: list) -> int:
    """Expand project_code → game_ids, overwrite mode.

    Deletes ALL existing CompanyGameMapping rows for the project's (game_id, channel_id)
    combinations, then creates new rows for the specified company. This includes
    overwriting any game-level exceptions — project-level save is authoritative.

    Returns total number of mappings created.
    """
    total = 0
    for item in items:
        rows = (await db.execute(
            select(models.PublisherGameMapping.game_id).where(
                models.PublisherGameMapping.project_code == item.project_code,
                models.PublisherGameMapping.project_code.isnot(None),
                models.PublisherGameMapping.project_code != "",
            )
        )).all()
        game_ids = [r.game_id for r in rows if r.game_id]
        if not game_ids:
            raise HTTPException(400, f"项目编号 '{item.project_code}' 下没有关联的游戏")

        ch_id = getattr(item, "channel_id", None)

        # Delete ALL existing mappings for these (game_id, channel_id) combos
        # — overwrites other companies' bindings AND game-level exceptions
        delete_where = [
            models.CompanyGameMapping.game_id.in_(game_ids),
        ]
        if ch_id is not None:
            delete_where.append(models.CompanyGameMapping.channel_id == ch_id)
        else:
            delete_where.append(models.CompanyGameMapping.channel_id.is_(None))
        await db.execute(
            delete(models.CompanyGameMapping).where(*delete_where)
        )
        # Create new mappings for the specified company
        for gid in game_ids:
            db.add(models.CompanyGameMapping(
                company_id=item.company_id,
                game_id=gid,
                channel_id=ch_id,
            ))
            total += 1

    await db.commit()
    return total


# ── Game-level company override ──


async def save_company_game_override(db: AsyncSession, company_id: int, game_id: str,
                                      channel_id: int | None = None) -> None:
    """UPSERT a game-level company override. Deletes any existing mapping for
    the (game_id, channel_id) key and creates a new override entry.
    """
    # 1. Delete existing mapping for (game_id, channel_id) regardless of company
    delete_where = [models.CompanyGameMapping.game_id == game_id]
    if channel_id is not None:
        delete_where.append(models.CompanyGameMapping.channel_id == channel_id)
    else:
        delete_where.append(models.CompanyGameMapping.channel_id.is_(None))
    await db.execute(
        delete(models.CompanyGameMapping).where(*delete_where)
    )

    # 2. Create new override
    db.add(models.CompanyGameMapping(
        company_id=company_id,
        game_id=game_id,
        channel_id=channel_id,
    ))
    await db.commit()


async def delete_company_game_override(db: AsyncSession, company_id: int, game_id: str,
                                        channel_id: int | None = None) -> bool:
    """Delete a game-level company override. Returns True if a row was deleted."""
    delete_where = [
        models.CompanyGameMapping.company_id == company_id,
        models.CompanyGameMapping.game_id == game_id,
    ]
    if channel_id is not None:
        delete_where.append(models.CompanyGameMapping.channel_id == channel_id)
    else:
        delete_where.append(models.CompanyGameMapping.channel_id.is_(None))
    result = await db.execute(
        delete(models.CompanyGameMapping).where(*delete_where)
    )
    await db.commit()
    return result.rowcount > 0
