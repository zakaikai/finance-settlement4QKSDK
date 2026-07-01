"""Tests for FK resolution (resolve_foreign_keys)."""
import pytest
from decimal import Decimal
from backend.services.template_import import resolve_foreign_keys
from backend import models


@pytest.mark.asyncio
async def test_raw_transactions_missing_game(db_session):
    """raw_transactions with non-existent game_id should be flagged."""
    # Add a sub channel so FK resolution can find it
    cat = models.ChannelCategory(channel_name="商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()

    rows = [
        {"sub_channel_name": "华为-游戏", "game_id": "NONEXISTENT",
         "amount": Decimal("100"), "record_date": "2024-01-01"},
    ]
    result = await resolve_foreign_keys(db_session, "raw_transactions", rows)
    game_errors = [e for e in result["errors"] if "game" in e["error"].lower()]
    assert len(game_errors) >= 1


@pytest.mark.asyncio
async def test_raw_transactions_valid_game(db_session):
    """raw_transactions with existing game_id should pass FK resolution."""
    # Add a game
    game = models.Game(game_id="G001", game_name="Test Game", discount_rate=Decimal("0.7"))
    db_session.add(game)
    # Add a sub channel
    cat = models.ChannelCategory(channel_name="商店")
    db_session.add(cat)
    await db_session.flush()
    bk = models.BackendChannel(backend_channel_name="华为", channel_id=cat.channel_id)
    db_session.add(bk)
    await db_session.flush()
    sub = models.SubChannel(sub_channel_name="华为-游戏", backend_channel_id=bk.backend_channel_id)
    db_session.add(sub)
    await db_session.flush()

    rows = [
        {"sub_channel_name": "华为-游戏", "game_id": "G001",
         "amount": Decimal("100"), "record_date": "2024-01-01"},
    ]
    result = await resolve_foreign_keys(db_session, "raw_transactions", rows)
    game_errors = [e for e in result["errors"] if "game" in e["error"].lower()]
    assert len(game_errors) == 0
