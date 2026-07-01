"""Comprehensive tests for channels hierarchy import (import_data)."""
import pytest
from sqlalchemy import select, func
from backend.services.template_import import import_data
from backend import models


async def count(db_session, model):
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar()


async def get_tree(db_session):
    """Return the full channel tree as a dict for assertion."""
    cats = (await db_session.execute(select(models.ChannelCategory))).scalars().all()
    tree = {}
    for cat in cats:
        bks = (await db_session.execute(
            select(models.BackendChannel).where(models.BackendChannel.channel_id == cat.channel_id)
        )).scalars().all()
        tree[cat.channel_name] = {}
        for bk in bks:
            subs = (await db_session.execute(
                select(models.SubChannel).where(models.SubChannel.backend_channel_id == bk.backend_channel_id)
            )).scalars().all()
            tree[cat.channel_name][bk.backend_channel_name] = [s.sub_channel_name for s in subs]
    return tree


# ── 1. Basic single row ──

@pytest.mark.asyncio
async def test_import_single_row(db_session):
    """One row creates one category, one backend, one sub."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 1
    assert await count(db_session, models.ChannelCategory) == 1
    assert await count(db_session, models.BackendChannel) == 1
    assert await count(db_session, models.SubChannel) == 1


# ── 2. One category, one backend, multiple sub_channels ──

@pytest.mark.asyncio
async def test_one_backend_multiple_subs(db_session):
    """One backend_channel with multiple sub_channels."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-主题商店"},
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-阅读"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 3
    assert await count(db_session, models.ChannelCategory) == 1
    assert await count(db_session, models.BackendChannel) == 1
    assert await count(db_session, models.SubChannel) == 3

    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {
            "华为": ["华为-游戏中心", "华为-主题商店", "华为-阅读"]
        }
    }


# ── 3. One category, multiple backend_channels ──

@pytest.mark.asyncio
async def test_multiple_backends_one_category(db_session):
    """One category with multiple backend_channels, each with their own subs."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "小米", "sub_channel_name": "小米-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "OPPO", "sub_channel_name": "OPPO-游戏中心"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 3
    assert await count(db_session, models.ChannelCategory) == 1
    assert await count(db_session, models.BackendChannel) == 3
    assert await count(db_session, models.SubChannel) == 3

    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {
            "华为": ["华为-游戏中心"],
            "小米": ["小米-游戏中心"],
            "OPPO": ["OPPO-游戏中心"],
        }
    }


# ── 4. Multiple categories ──

@pytest.mark.asyncio
async def test_multiple_categories(db_session):
    """Multiple categories with distinct hierarchies."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
        {"channel_name": "广告平台", "backend_channel_name": "广点通", "sub_channel_name": "广点通-iOS"},
        {"channel_name": "社交平台", "backend_channel_name": "微信", "sub_channel_name": "微信-小游戏"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 3
    assert await count(db_session, models.ChannelCategory) == 3
    assert await count(db_session, models.BackendChannel) == 3
    assert await count(db_session, models.SubChannel) == 3

    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {"华为": ["华为-游戏中心"]},
        "广告平台": {"广点通": ["广点通-iOS"]},
        "社交平台": {"微信": ["微信-小游戏"]},
    }


# ── 5. Complex full tree ──

@pytest.mark.asyncio
async def test_complex_tree(db_session):
    """Full complex hierarchy: multi-category, multi-backend, multi-sub."""
    rows = [
        # 应用商店
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-主题商店"},
        {"channel_name": "应用商店", "backend_channel_name": "小米", "sub_channel_name": "小米-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "小米", "sub_channel_name": "小米-主题商店"},
        {"channel_name": "应用商店", "backend_channel_name": "小米", "sub_channel_name": "小米-视频"},
        # 广告平台
        {"channel_name": "广告平台", "backend_channel_name": "广点通", "sub_channel_name": "广点通-iOS"},
        {"channel_name": "广告平台", "backend_channel_name": "广点通", "sub_channel_name": "广点通-Android"},
        # 社交平台
        {"channel_name": "社交平台", "backend_channel_name": "微信", "sub_channel_name": "微信-小游戏"},
        {"channel_name": "社交平台", "backend_channel_name": "微信", "sub_channel_name": "微信-小程序"},
        {"channel_name": "社交平台", "backend_channel_name": "抖音", "sub_channel_name": "抖音-信息流"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 10
    assert await count(db_session, models.ChannelCategory) == 3
    assert await count(db_session, models.BackendChannel) == 5
    assert await count(db_session, models.SubChannel) == 10

    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {
            "华为": ["华为-游戏中心", "华为-主题商店"],
            "小米": ["小米-游戏中心", "小米-主题商店", "小米-视频"],
        },
        "广告平台": {
            "广点通": ["广点通-iOS", "广点通-Android"],
        },
        "社交平台": {
            "微信": ["微信-小游戏", "微信-小程序"],
            "抖音": ["抖音-信息流"],
        },
    }


# ── 6. Idempotent re-import ──

@pytest.mark.asyncio
async def test_reimport_idempotent(db_session):
    """Re-importing the same rows should not create duplicates."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-主题商店"},
    ]
    result1 = await import_data(db_session, "channels", rows)
    result2 = await import_data(db_session, "channels", rows)

    assert result1["imported"] == 2
    # Second import: all already exist, but import_data still counts them
    # (it uses get-or-create so imported count is always total rows processed)
    assert result2["imported"] == 2

    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {
            "华为": ["华为-游戏中心", "华为-主题商店"],
        }
    }


# ── 7. Incremental import ──

@pytest.mark.asyncio
async def test_incremental_import(db_session):
    """Importing new sub_channels to an existing hierarchy should add, not duplicate."""
    batch1 = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏中心"},
    ]
    await import_data(db_session, "channels", batch1)

    batch2 = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-主题商店"},
    ]
    result = await import_data(db_session, "channels", batch2)

    assert result["imported"] == 1
    assert await count(db_session, models.SubChannel) == 2
    tree = await get_tree(db_session)
    assert tree == {
        "应用商店": {
            "华为": ["华为-游戏中心", "华为-主题商店"],
        }
    }


# ── 8. BackendChannel scoped to category (regression) ──

@pytest.mark.asyncio
async def test_backend_scoped_to_category(db_session):
    """Same backend_channel name under different categories must be separate."""
    # Pre-setup
    cat = models.ChannelCategory(channel_name="商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.commit()

    rows = [
        {"channel_name": "游戏平台", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 1
    assert await count(db_session, models.BackendChannel) == 2

    tree = await get_tree(db_session)
    assert tree == {
        "商店": {"华为": []},
        "游戏平台": {"华为": ["华为-游戏"]},
    }


# ── 9. SubChannel scoped to backend (regression) ──

@pytest.mark.asyncio
async def test_sub_scoped_to_backend(db_session):
    """Same sub_channel name under different backends must be separate."""
    cat = models.ChannelCategory(channel_name="商店")
    db_session.add(cat)
    await db_session.flush()
    bk1 = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk1)
    bk2 = models.BackendChannel(backend_channel_name="小米", channel_id=cat.channel_id)
    db_session.add(bk2)
    await db_session.commit()

    rows = [
        {"channel_name": "商店", "backend_channel_name": "华为", "sub_channel_name": "游戏中心"},
        {"channel_name": "商店", "backend_channel_name": "小米", "sub_channel_name": "游戏中心"},
    ]
    result = await import_data(db_session, "channels", rows)

    assert result["imported"] == 2
    assert await count(db_session, models.SubChannel) == 2
