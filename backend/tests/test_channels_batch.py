"""Tests for the batch_channels endpoint (basic_data.py)."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.routers.basic_data import batch_channels
from backend.schemas import ChannelRowUpdate
from backend import models


async def count(db_session, model):
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar()


async def create_hierarchy(db_session, channel_name, backend_name, sub_name):
    """Helper: insert a channel hierarchy directly into the DB."""
    cat = models.ChannelCategory(channel_name=channel_name)
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name=backend_name, channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name=sub_name, backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()
    return cat, bk, sub


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_single_row(self, db_session):
        """One create item creates one category, one backend, one sub."""
        items = [
            ChannelRowUpdate(
                row_key="r1", action="create",
                channel_name="应用商店", backend_channel_name="华为",
                sub_channel_name="华为-游戏中心",
            )
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        assert await count(db_session, models.ChannelCategory) == 1
        assert await count(db_session, models.BackendChannel) == 1
        assert await count(db_session, models.SubChannel) == 1

    @pytest.mark.asyncio
    async def test_create_empty_channel_name_raises_400(self, db_session):
        """Create with empty channel_name should raise HTTP 400."""
        items = [
            ChannelRowUpdate(
                row_key="r1", action="create",
                channel_name="", backend_channel_name="华为",
                sub_channel_name="华为-游戏中心",
            )
        ]
        with pytest.raises(HTTPException) as exc:
            await batch_channels(body=items, db=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_empty_backend_name_raises_400(self, db_session):
        """Create with empty backend_channel_name should raise HTTP 400."""
        items = [
            ChannelRowUpdate(
                row_key="r1", action="create",
                channel_name="应用商店", backend_channel_name="",
                sub_channel_name="华为-游戏中心",
            )
        ]
        with pytest.raises(HTTPException) as exc:
            await batch_channels(body=items, db=db_session)
        assert exc.value.status_code == 400

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_sub_channel_name(self, db_session):
        """Update renames the sub channel."""
        await create_hierarchy(db_session, "商店", "华为", "旧子渠道")
        items = [
            ChannelRowUpdate(
                row_key="r1", action="update",
                channel_name="商店", backend_channel_name="华为",
                sub_channel_name="新子渠道",
                orig_channel_name="商店", orig_backend_channel_name="华为",
                orig_sub_channel_name="旧子渠道",
            )
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        # Verify sub was renamed
        subs = (await db_session.execute(
            select(models.SubChannel).where(models.SubChannel.sub_channel_name == "新子渠道")
        )).scalars().all()
        assert len(subs) == 1

    @pytest.mark.asyncio
    async def test_update_backend_channel_name_creates_new_backend(self, db_session):
        """Update backend_channel_name: creates new BackendChannel if needed."""
        await create_hierarchy(db_session, "商店", "华为", "子渠道")
        items = [
            ChannelRowUpdate(
                row_key="r1", action="update",
                channel_name="商店", backend_channel_name="小米",
                sub_channel_name="子渠道",
                orig_channel_name="商店", orig_backend_channel_name="华为",
                orig_sub_channel_name="子渠道",
            )
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        assert await count(db_session, models.BackendChannel) == 2  # 华为 + 小米
        # Sub should be linked to "小米" now
        bk = (await db_session.execute(
            select(models.BackendChannel).where(models.BackendChannel.backend_channel_name == "小米")
        )).scalar_one()
        subs = (await db_session.execute(
            select(models.SubChannel).where(models.SubChannel.backend_channel_id == bk.backend_channel_id)
        )).scalars().all()
        assert len(subs) == 1
        assert subs[0].sub_channel_name == "子渠道"

    @pytest.mark.asyncio
    async def test_update_channel_name_renames_category(self, db_session):
        """Update channel_name renames the category in-place."""
        await create_hierarchy(db_session, "旧渠道", "后端", "子渠道")
        items = [
            ChannelRowUpdate(
                row_key="r1", action="update",
                channel_name="新渠道", backend_channel_name="后端",
                sub_channel_name="子渠道",
                orig_channel_name="旧渠道", orig_backend_channel_name="后端",
                orig_sub_channel_name="子渠道",
            )
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        assert await count(db_session, models.ChannelCategory) == 1
        cat = (await db_session.execute(
            select(models.ChannelCategory).where(models.ChannelCategory.channel_name == "新渠道")
        )).scalar_one_or_none()
        assert cat is not None
        assert (await db_session.execute(
            select(models.ChannelCategory).where(models.ChannelCategory.channel_name == "旧渠道")
        )).scalar_one_or_none() is None


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_sub_channel(self, db_session):
        """Delete removes the sub channel but keeps category and backend."""
        await create_hierarchy(db_session, "商店", "华为", "子渠道")
        items = [
            ChannelRowUpdate(
                row_key="r1", action="delete",
                channel_name="", backend_channel_name="", sub_channel_name="",
                orig_channel_name="商店", orig_backend_channel_name="华为",
                orig_sub_channel_name="子渠道",
            )
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        assert await count(db_session, models.SubChannel) == 0
        # Category and backend should remain
        assert await count(db_session, models.ChannelCategory) == 1
        assert await count(db_session, models.BackendChannel) == 1


class TestMixed:
    @pytest.mark.asyncio
    async def test_create_update_delete_in_one_batch(self, db_session):
        """Multiple operations in a single batch are all applied."""
        await create_hierarchy(db_session, "商店", "华为", "旧子渠道")

        items = [
            ChannelRowUpdate(
                row_key="c1", action="create",
                channel_name="新分类", backend_channel_name="后端A",
                sub_channel_name="子A",
            ),
            ChannelRowUpdate(
                row_key="u1", action="update",
                channel_name="商店", backend_channel_name="华为",
                sub_channel_name="新子渠道",
                orig_channel_name="商店", orig_backend_channel_name="华为",
                orig_sub_channel_name="旧子渠道",
            ),
            ChannelRowUpdate(
                row_key="d1", action="delete",
                channel_name="", backend_channel_name="", sub_channel_name="",
                orig_channel_name="商店", orig_backend_channel_name="华为",
                orig_sub_channel_name="新子渠道",
            ),
        ]
        result = await batch_channels(body=items, db=db_session)

        assert result == {"success": True}
        assert await count(db_session, models.SubChannel) == 1  # only the new one
        assert await count(db_session, models.ChannelCategory) == 2
