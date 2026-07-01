"""Regression tests for income split config same-month re-save (UPDATE, not INSERT).

Verifies H1: same-month re-save UPDATEs existing config instead of creating duplicates.
Verifies H2: UniqueConstraint is enforced (duplicate keys raise IntegrityError).
Verifies H3: all overlapping configs are closed (not just .first()).
"""

import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend import models
from backend.services.settlement_service import _save_income_split_config


@pytest.mark.asyncio
async def test_same_month_save_twice_updates_in_place(db_session):
    """同月分成配置保存两次 → UPDATE 已有行，不创建重复。"""
    # Setup: existing config for an earlier month
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.20"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
    ))
    await db_session.commit()

    # 第一次保存：month=2026-04
    await _save_income_split_config(
        db_session, 1, "G001", "2026-04",
        split_rate=Decimal("0.25"),
    )
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()
    assert len(configs) == 2
    # Old config correctly closed
    assert configs[0].effective_to == date(2026, 3, 31)

    # 第二次保存：同月，只改 split_rate + channel_fee_rate
    await _save_income_split_config(
        db_session, 1, "G001", "2026-04",
        split_rate=Decimal("0.30"), channel_fee_rate=Decimal("0.07"),
    )
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    # 期望：仍只有 2 条（旧关闭 + 新更新），不是 3 条
    assert len(configs) == 2, f"Expected 2 configs, got {len(configs)}"
    # 旧配置保持关闭
    assert configs[0].effective_to == date(2026, 3, 31)
    assert configs[0].split_rate == Decimal("0.20")
    # 新配置被原地更新
    assert configs[1].effective_from == date(2026, 4, 1)
    assert configs[1].effective_to is None
    assert configs[1].split_rate == Decimal("0.30")          # updated
    assert configs[1].channel_fee_rate == Decimal("0.07")    # updated
    assert configs[1].tax_rate == Decimal("0.06")            # inherited from old


@pytest.mark.asyncio
async def test_different_month_still_closes_and_creates(db_session):
    """不同月份保存 → 关旧建新（原有逻辑保持不变）。"""
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.20"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
    ))
    await db_session.commit()

    # 保存 month=2026-04
    await _save_income_split_config(db_session, 1, "G001", "2026-04",
        split_rate=Decimal("0.25"))
    await db_session.commit()

    # 保存 month=2026-07（不同月）
    await _save_income_split_config(db_session, 1, "G001", "2026-07",
        split_rate=Decimal("0.35"), channel_fee_rate=Decimal("0.08"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 3
    # 第一个被 4月关
    assert configs[0].effective_to == date(2026, 3, 31)
    # 第二个被 7月关
    assert configs[1].effective_from == date(2026, 4, 1)
    assert configs[1].effective_to == date(2026, 6, 30)
    # 第三个新建
    assert configs[2].effective_from == date(2026, 7, 1)
    assert configs[2].effective_to is None
    assert configs[2].split_rate == Decimal("0.35")
    assert configs[2].channel_fee_rate == Decimal("0.08")
    assert configs[2].tax_rate == Decimal("0.06")  # inherited


@pytest.mark.asyncio
async def test_same_month_update_preserves_effective_to(db_session):
    """同月 UPDATE 不修改 effective_to（保持原值）。"""
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 4, 1), effective_to=None,
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
    ))
    await db_session.commit()

    await _save_income_split_config(db_session, 1, "G001", "2026-04",
        split_rate=Decimal("0.30"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
    )).scalars().all()

    assert len(configs) == 1
    assert configs[0].effective_from == date(2026, 4, 1)
    assert configs[0].effective_to is None           # preserved
    assert configs[0].split_rate == Decimal("0.30")  # updated


@pytest.mark.asyncio
async def test_no_prev_config_creates_new(db_session):
    """无旧配置时正常创建新配置（不 crash）。"""
    await _save_income_split_config(db_session, 1, "G001", "2026-04",
        split_rate=Decimal("0.25"))
    await db_session.commit()

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
    )).scalars().all()

    assert len(configs) == 1
    assert configs[0].effective_from == date(2026, 4, 1)
    assert configs[0].effective_to is None
    assert configs[0].split_rate == Decimal("0.25")
    assert configs[0].channel_fee_rate == Decimal("0")  # default
    assert configs[0].tax_rate == Decimal("0")           # default


@pytest.mark.asyncio
async def test_duplicate_key_raises_integrity_error(db_session):
    """直接 INSERT 同 key → IntegrityError (UC 生效)。"""
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 4, 1), effective_to=None,
        split_rate=Decimal("0.1"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    await db_session.commit()

    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 4, 1), effective_to=None,
        split_rate=Decimal("0.2"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ═══════════════════════════════════════════════════════════════
# Batch path: upsert_split_configs (Settlement.vue / BasicData.vue)
# ═══════════════════════════════════════════════════════════════

from backend.schemas import IncomeSplitConfigUpdate, PaymentSplitConfigUpdate
from backend.services.settlement_service import upsert_split_configs


async def _seed_channel(db_session, channel_id=1, channel_name="TestChannel"):
    """Ensure a ChannelCategory exists for FK resolution."""
    from sqlalchemy import select as _sel
    existing = (await db_session.execute(
        _sel(models.ChannelCategory).where(models.ChannelCategory.channel_id == channel_id)
    )).scalar_one_or_none()
    if not existing:
        db_session.add(models.ChannelCategory(channel_id=channel_id, channel_name=channel_name))
        await db_session.commit()


async def _seed_publisher(db_session, publisher_id=1, publisher_name="TestPublisher"):
    """Ensure a Publisher exists for FK resolution."""
    from sqlalchemy import select as _sel
    existing = (await db_session.execute(
        _sel(models.Publisher).where(models.Publisher.publisher_id == publisher_id)
    )).scalar_one_or_none()
    if not existing:
        db_session.add(models.Publisher(publisher_id=publisher_id, publisher_name=publisher_name))
        await db_session.commit()


@pytest.mark.asyncio
async def test_upsert_income_same_month_updates_in_place(db_session):
    """同月批量保存两次 → UPDATE，不产生重复行。"""
    await _seed_channel(db_session, 1, "ChA")

    # 首次保存 month=2026-04
    items = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=Decimal("0.25"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    # 同月再次保存：改 split_rate
    items2 = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=Decimal("0.30"), channel_fee_rate=Decimal("0.07"), tax_rate=Decimal("0.08"),
        effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items2,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 1, f"Expected 1, got {len(configs)}"
    assert configs[0].effective_from == date(2026, 4, 1)
    assert configs[0].effective_to is None
    assert configs[0].split_rate == Decimal("0.30")
    assert configs[0].channel_fee_rate == Decimal("0.07")
    assert configs[0].tax_rate == Decimal("0.08")


@pytest.mark.asyncio
async def test_upsert_income_different_month_closes_and_creates(db_session):
    """批量不同月保存 → 关旧建新。"""
    await _seed_channel(db_session, 1, "ChA")

    # month=2026-04
    items = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=Decimal("0.25"), effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    # month=2026-07
    items2 = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=Decimal("0.35"), effective_from=date(2026, 7, 1),
    )]
    await upsert_split_configs(db_session, items2,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 2
    assert configs[0].effective_from == date(2026, 4, 1)
    assert configs[0].effective_to == date(2026, 6, 30)
    assert configs[0].split_rate == Decimal("0.25")
    assert configs[1].effective_from == date(2026, 7, 1)
    assert configs[1].effective_to is None
    assert configs[1].split_rate == Decimal("0.35")


@pytest.mark.asyncio
async def test_upsert_income_none_fields_inherit_from_prev(db_session):
    """批量保存时 None 字段从旧配置继承。"""
    await _seed_channel(db_session, 1, "ChA")

    # 旧配置
    db_session.add(models.IncomeSplitConfig(
        channel_id=1, game_id="G001",
        effective_from=date(2026, 1, 1), effective_to=None,
        split_rate=Decimal("0.20"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
    ))
    await db_session.commit()

    # 新配置: split_rate=None, channel_fee_rate=None → 应继承旧值
    items = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=None, channel_fee_rate=None, tax_rate=Decimal("0.09"),
        effective_from=date(2026, 5, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig)
        .where(models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
        .order_by(models.IncomeSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 2
    new_cfg = configs[1]
    assert new_cfg.effective_from == date(2026, 5, 1)
    assert new_cfg.split_rate == Decimal("0.20")          # inherited
    assert new_cfg.channel_fee_rate == Decimal("0.05")    # inherited
    assert new_cfg.tax_rate == Decimal("0.09")            # provided


@pytest.mark.asyncio
async def test_upsert_payment_same_month_updates_in_place(db_session):
    """Payment 批量同月保存两次 → UPDATE + fixed_fee。"""
    await _seed_publisher(db_session, 1, "PubA")
    db_session.add(models.Game(game_id="G001", game_name="TestGame", discount_rate=Decimal("0.8")))
    await db_session.commit()

    items = [PaymentSplitConfigUpdate(
        publisher_name="PubA", game_id="G001",
        split_rate=Decimal("0.30"), channel_fee_rate=Decimal("0.05"),
        tax_rate=Decimal("0.06"), fixed_fee=Decimal("1000"),
        effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.Publisher, fk_name_field="publisher_name",
        fk_cache_key="publishers", fk_col_name="publisher_id",
        config_cls=models.PaymentSplitConfig, extra_fields=("fixed_fee",))

    # 同月再次
    items2 = [PaymentSplitConfigUpdate(
        publisher_name="PubA", game_id="G001",
        split_rate=Decimal("0.40"), channel_fee_rate=Decimal("0.06"),
        tax_rate=Decimal("0.07"), fixed_fee=Decimal("2000"),
        effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items2,
        fk_model_cls=models.Publisher, fk_name_field="publisher_name",
        fk_cache_key="publishers", fk_col_name="publisher_id",
        config_cls=models.PaymentSplitConfig, extra_fields=("fixed_fee",))

    configs = (await db_session.execute(
        select(models.PaymentSplitConfig)
        .where(models.PaymentSplitConfig.publisher_id == 1, models.PaymentSplitConfig.game_id == "G001")
        .order_by(models.PaymentSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 1, f"Expected 1, got {len(configs)}"
    assert configs[0].effective_from == date(2026, 4, 1)
    assert configs[0].effective_to is None
    assert configs[0].split_rate == Decimal("0.40")
    assert configs[0].channel_fee_rate == Decimal("0.06")
    assert configs[0].tax_rate == Decimal("0.07")
    assert configs[0].fixed_fee == Decimal("2000")


@pytest.mark.asyncio
async def test_upsert_payment_different_month_closes_and_creates(db_session):
    """Payment 批量不同月保存 → 关旧建新。"""
    await _seed_publisher(db_session, 1, "PubA")
    db_session.add(models.Game(game_id="G001", game_name="TestGame", discount_rate=Decimal("0.8")))
    await db_session.commit()

    items = [PaymentSplitConfigUpdate(
        publisher_name="PubA", game_id="G001",
        split_rate=Decimal("0.30"), fixed_fee=Decimal("500"),
        effective_from=date(2026, 3, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.Publisher, fk_name_field="publisher_name",
        fk_cache_key="publishers", fk_col_name="publisher_id",
        config_cls=models.PaymentSplitConfig, extra_fields=("fixed_fee",))

    items2 = [PaymentSplitConfigUpdate(
        publisher_name="PubA", game_id="G001",
        split_rate=Decimal("0.50"), fixed_fee=Decimal("800"),
        effective_from=date(2026, 8, 1),
    )]
    await upsert_split_configs(db_session, items2,
        fk_model_cls=models.Publisher, fk_name_field="publisher_name",
        fk_cache_key="publishers", fk_col_name="publisher_id",
        config_cls=models.PaymentSplitConfig, extra_fields=("fixed_fee",))

    configs = (await db_session.execute(
        select(models.PaymentSplitConfig)
        .where(models.PaymentSplitConfig.publisher_id == 1, models.PaymentSplitConfig.game_id == "G001")
        .order_by(models.PaymentSplitConfig.effective_from)
    )).scalars().all()

    assert len(configs) == 2
    assert configs[0].effective_from == date(2026, 3, 1)
    assert configs[0].effective_to == date(2026, 7, 31)
    assert configs[0].split_rate == Decimal("0.30")
    assert configs[1].effective_from == date(2026, 8, 1)
    assert configs[1].effective_to is None
    assert configs[1].split_rate == Decimal("0.50")
    assert configs[1].fixed_fee == Decimal("800")


@pytest.mark.asyncio
async def test_upsert_payment_duplicate_key_raises_integrity_error(db_session):
    """Payment 直接 INSERT 同 key → IntegrityError (UC 生效)。"""
    await _seed_publisher(db_session, 1, "PubA")
    db_session.add(models.Game(game_id="G001", game_name="TestGame", discount_rate=Decimal("0.8")))
    await db_session.commit()

    db_session.add(models.PaymentSplitConfig(
        publisher_id=1, game_id="G001",
        effective_from=date(2026, 4, 1), effective_to=None,
        split_rate=Decimal("0.3"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        fixed_fee=Decimal("0"),
    ))
    await db_session.commit()

    db_session.add(models.PaymentSplitConfig(
        publisher_id=1, game_id="G001",
        effective_from=date(2026, 4, 1), effective_to=None,
        split_rate=Decimal("0.4"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        fixed_fee=Decimal("0"),
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_upsert_delete_removes_row(db_session):
    """action='delete' + id -> 删除对应行。"""
    await _seed_channel(db_session, 1, "ChA")

    items = [IncomeSplitConfigUpdate(
        channel_name="ChA", game_id="G001",
        split_rate=Decimal("0.25"), effective_from=date(2026, 4, 1),
    )]
    await upsert_split_configs(db_session, items,
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig).where(
            models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
    )).scalars().all()
    assert len(configs) == 1
    cfg_id = configs[0].id

    delete_item = IncomeSplitConfigUpdate(
        id=cfg_id, action="delete",
        channel_name="ChA", game_id="G001",
    )
    await upsert_split_configs(db_session, [delete_item],
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)

    configs = (await db_session.execute(
        select(models.IncomeSplitConfig).where(
            models.IncomeSplitConfig.channel_id == 1, models.IncomeSplitConfig.game_id == "G001")
    )).scalars().all()
    assert len(configs) == 0, f"Expected 0 after delete, got {len(configs)}"


@pytest.mark.asyncio
async def test_upsert_delete_nonexistent_id_no_error(db_session):
    """删除不存在的 id 不报错（幂等）。"""
    await _seed_channel(db_session, 1, "ChA")

    delete_item = IncomeSplitConfigUpdate(
        id=99999, action="delete",
        channel_name="ChA", game_id="G001",
    )
    await upsert_split_configs(db_session, [delete_item],
        fk_model_cls=models.ChannelCategory, fk_name_field="channel_name",
        fk_cache_key="channel_categories", fk_col_name="channel_id",
        config_cls=models.IncomeSplitConfig)
