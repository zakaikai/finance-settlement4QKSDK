"""Test raw_transactions import overwrite vs accumulate behavior."""

import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import select

from backend import models
from backend.services.template_import import import_raw_transactions


def _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=10000):
    return [{"channel_id": channel_id, "game_id": game_id, "month": month, "amount": amount}]


@pytest.mark.asyncio
async def test_overwrite_clears_old_games(db_session):
    """覆盖模式：旧数据中本次未出现的 game 应被清除。"""
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.Game(game_id="G002", game_name="Game2", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    await db_session.commit()

    # 先写入两条旧数据
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("100"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G002", game_name="Game2",
        month="2026-04", raw_revenue=Decimal("200"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    # 覆盖导入：只有 G001，没有 G002
    rows = _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=500)
    await import_raw_transactions(db_session, rows, overwrite=True)

    # 验证
    all_rows = (await db_session.execute(
        select(models.RawSettlement).where(
            models.RawSettlement.channel_id == 1,
            models.RawSettlement.month == "2026-04",
        ).order_by(models.RawSettlement.game_id)
    )).scalars().all()

    assert len(all_rows) == 1, f"Expected 1 row, got {len(all_rows)}"
    assert all_rows[0].game_id == "G001"
    assert all_rows[0].raw_revenue == Decimal("500")


@pytest.mark.asyncio
async def test_overwrite_replaces_same_game(db_session):
    """覆盖模式：同 game 的值被替换。"""
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    await db_session.commit()

    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("100"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    rows = _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=999)
    await import_raw_transactions(db_session, rows, overwrite=True)

    all_rows = (await db_session.execute(
        select(models.RawSettlement).where(
            models.RawSettlement.channel_id == 1, models.RawSettlement.month == "2026-04")
    )).scalars().all()

    assert len(all_rows) == 1
    assert all_rows[0].raw_revenue == Decimal("999")


@pytest.mark.asyncio
async def test_overwrite_other_month_untouched(db_session):
    """覆盖模式：只清除导入涉及的月份，其他月份不受影响。"""
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    await db_session.commit()

    # 4月数据
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("100"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    # 5月数据（不应被影响）
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-05", raw_revenue=Decimal("200"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    # 只导入 4月
    rows = _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=500)
    await import_raw_transactions(db_session, rows, overwrite=True)

    # 4月应为新值，5月应不变
    apr = (await db_session.execute(
        select(models.RawSettlement).where(models.RawSettlement.month == "2026-04")
    )).scalars().all()
    may = (await db_session.execute(
        select(models.RawSettlement).where(models.RawSettlement.month == "2026-05")
    )).scalars().all()

    assert len(apr) == 1
    assert apr[0].raw_revenue == Decimal("500")
    assert len(may) == 1
    assert may[0].raw_revenue == Decimal("200")  # untouched


@pytest.mark.asyncio
async def test_overwrite_clears_all_channels_for_month(db_session):
    """覆盖模式：清空该月份所有渠道数据，不管导入的是哪个渠道。"""
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.Game(game_id="G002", game_name="Game2", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    db_session.add(models.ChannelCategory(channel_id=2, channel_name="ChB"))
    await db_session.commit()

    # 两个渠道的 4月数据
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("100"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    db_session.add(models.RawSettlement(
        channel_id=2, channel_name="ChB", game_id="G002", game_name="Game2",
        month="2026-04", raw_revenue=Decimal("200"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    # 只导入 ch=1 的数据
    rows = _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=500)
    await import_raw_transactions(db_session, rows, overwrite=True)

    all_rows = (await db_session.execute(
        select(models.RawSettlement).where(models.RawSettlement.month == "2026-04")
    )).scalars().all()

    # ch=2 也应被清空
    assert len(all_rows) == 1, f"Expected 1, got {len(all_rows)}"
    assert all_rows[0].channel_id == 1
    assert all_rows[0].raw_revenue == Decimal("500")


@pytest.mark.asyncio
async def test_accumulate_adds_to_existing(db_session):
    """累计模式：新金额叠加到已有值。"""
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    await db_session.commit()

    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("100"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    rows = _make_rows(channel_id=1, game_id="G001", month="2026-04", amount=50)
    await import_raw_transactions(db_session, rows, overwrite=False)

    all_rows = (await db_session.execute(
        select(models.RawSettlement).where(
            models.RawSettlement.channel_id == 1, models.RawSettlement.month == "2026-04")
    )).scalars().all()

    assert len(all_rows) == 1
    assert all_rows[0].raw_revenue == Decimal("150")  # 100 + 50
