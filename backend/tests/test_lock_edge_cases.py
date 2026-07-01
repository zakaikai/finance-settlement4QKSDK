"""Edge-case tests for locking behavior not covered by existing test files."""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.lock_service import (
    apply_lock,
    remove_lock,
    get_lock,
    resolve_locked_values,
)


# ── Helpers ──

async def _seed_rs(db, channel_id, game_id, month, raw_revenue, **kw):
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=f"渠道{channel_id}",
        game_name=kw.get("game_name", "测试游戏"),
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


# ═══════════════════════════════════════════════════════════════
# Lock Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestLockEdgeCases:
    """Additional lock edge cases beyond the 30 existing lock tests."""

    @pytest.mark.asyncio
    async def test_lock_unlock_relock_cycle(self, db_session):
        """Lock → unlock → re-lock the same field returns correct values."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()
        await _seed_rs(db_session, 1, "G001", "2026-04", Decimal("10000"))
        await db_session.commit()

        now = "2026-01-01 00:00:00"

        r1 = await apply_lock(db_session, "channel", 1, "G001", "2026-04",
                              "real_revenue", Decimal("7000"), now=now, audit_name="test")
        assert r1["status"] == "locked"
        assert r1["value"] == 7000.0

        r2 = await remove_lock(db_session, "channel", 1, "G001", "2026-04",
                               "real_revenue", now=now, audit_name="test")
        assert r2["status"] == "unlocked"
        assert r2["formula_value"] == 8000.0  # 10000 * 0.8

        r3 = await apply_lock(db_session, "channel", 1, "G001", "2026-04",
                              "real_revenue", Decimal("9000"), now=now, audit_name="test")
        assert r3["status"] == "locked"
        assert r3["value"] == 9000.0

    @pytest.mark.asyncio
    async def test_both_fields_locked_independently(self, db_session):
        """Lock real_revenue then settlement_amount on same entity/game/month."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        now = "2026-02-01 00:00:00"

        await apply_lock(db_session, "channel", 1, "G001", "2026-05",
                        "real_revenue", Decimal("5000"), now=now, audit_name="test")
        await apply_lock(db_session, "channel", 1, "G001", "2026-05",
                        "settlement_amount", Decimal("3000"), now=now, audit_name="test")

        lock = await get_lock(db_session, "channel", 1, "G001", "2026-05")
        assert lock.locked_real_revenue == Decimal("5000")
        assert lock.locked_settlement_amount == Decimal("3000")

    @pytest.mark.asyncio
    async def test_unlock_one_field_preserves_other(self, db_session):
        """Unlocking real_revenue leaves settlement_amount locked."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        now = "2026-03-01 00:00:00"

        await apply_lock(db_session, "channel", 1, "G001", "2026-06",
                        "real_revenue", Decimal("5000"), now=now, audit_name="test")
        await apply_lock(db_session, "channel", 1, "G001", "2026-06",
                        "settlement_amount", Decimal("3000"), now=now, audit_name="test")

        await remove_lock(db_session, "channel", 1, "G001", "2026-06",
                         "real_revenue", now=now, audit_name="test")

        lock = await get_lock(db_session, "channel", 1, "G001", "2026-06")
        assert lock.locked_real_revenue is None
        assert lock.locked_settlement_amount == Decimal("3000")

    @pytest.mark.asyncio
    async def test_remove_lock_nonexistent_returns_formula(self, db_session):
        """Removing a lock that doesn't exist returns formula value gracefully."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        now = "2026-04-01 00:00:00"
        # No lock exists — remove_lock should not crash
        result = await remove_lock(db_session, "channel", 1, "G001", "2026-07",
                                   "real_revenue", now=now, audit_name="test")
        assert result["status"] == "unlocked"
        # No RawSettlement → raw_rev=0, 0*0.8=0
        assert result["formula_value"] == 0.0

    @pytest.mark.asyncio
    async def test_publisher_lock_with_fixed_fee(self, db_session):
        """Publisher lock/unlock correctly handles fixed_fee in formula."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        db_session.add(models.PaymentSplitConfig(
            publisher_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"),
            tax_rate=Decimal("0"), fixed_fee=Decimal("1000"),
        ))
        await db_session.commit()
        await _seed_rs(db_session, 1, "G001", "2026-06", Decimal("20000"))
        await db_session.commit()

        now = "2026-05-01 00:00:00"

        r1 = await apply_lock(db_session, "publisher", 1, "G001", "2026-06",
                              "settlement_amount", Decimal("9000"), now=now, audit_name="test")
        assert r1["status"] == "locked"

        # Unlock → formula: (20000*0.8=16000, 16000*0.5+1000=9000)
        r2 = await remove_lock(db_session, "publisher", 1, "G001", "2026-06",
                               "settlement_amount", now=now, audit_name="test")
        assert r2["formula_value"] == 9000.0

    @pytest.mark.asyncio
    async def test_lock_value_zero_not_none(self, db_session):
        """Locking with Decimal('0') is stored (not confused with None)."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        await db_session.commit()

        now = "2026-06-01 00:00:00"
        result = await apply_lock(db_session, "channel", 1, "G001", "2026-08",
                                  "real_revenue", Decimal("0"), now=now, audit_name="test")
        assert result["status"] == "locked"
        assert result["value"] == 0.0

        lock = await get_lock(db_session, "channel", 1, "G001", "2026-08")
        assert lock.locked_real_revenue == Decimal("0")  # not None!

    def test_resolve_locked_values_publisher_lock(self):
        """resolve_locked_values works for PublisherLock in the map."""
        lock = models.PublisherLock(
            publisher_id=2, game_id="G002", month="2026-09",
            locked_real_revenue=Decimal("6000"),
            locked_settlement_amount=Decimal("3500"),
            created_at="now", updated_at="now",
        )
        lock_map = {(2, "G002", "2026-09"): lock}
        real, amt = resolve_locked_values(lock_map, (2, "G002", "2026-09"))
        assert real == Decimal("6000")
        assert amt == Decimal("3500")

    def test_resolve_locked_values_wrong_key_returns_none(self):
        """Mismatched key returns (None, None)."""
        lock = models.ChannelLock(
            channel_id=1, game_id="G001", month="2026-10",
            locked_real_revenue=Decimal("100"),
            created_at="now", updated_at="now",
        )
        lock_map = {(1, "G001", "2026-10"): lock}
        real, amt = resolve_locked_values(lock_map, (1, "G002", "2026-10"))
        assert real is None
        assert amt is None
