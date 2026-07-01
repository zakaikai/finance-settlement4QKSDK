"""Direct tests for hydrate_formula_input — the single-row data hydrator for unlock recomputation.

UPDATED for RawSettlement: reads raw_revenue from raw_settlements table.
"""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.settlement_service import (
    hydrate_formula_input, _aggregate_channel_raw_revenue,
)


async def _seed_rs(db, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("0")):
    """Seed RawSettlement for formula hydration tests."""
    from sqlalchemy import select
    game_row = (await db.execute(
        select(models.Game.game_name).where(models.Game.game_id == game_id)
    )).first()
    rs = models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=f"渠道{channel_id}",
        game_name=game_row[0] if game_row else game_id,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


# ═══════════════════════════════════════════════════════════════
# hydrate_formula_input
# ═══════════════════════════════════════════════════════════════

class TestHydrateFormulaInput:
    """Tests for hydrate_formula_input — reads from RawSettlement."""

    @pytest.mark.asyncio
    async def test_channel_complete(self, db_session):
        """Full channel setup → all FormulaInput fields populated."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("10000"))

        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("100"), test=Decimal("0"),
            welfare=Decimal("0"), bad_debt=Decimal("0"),
        ))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        ))
        db_session.add(models.ChannelLock(
            channel_id=1, game_id="G001", month="2026-04",
            locked_real_revenue=Decimal("7000"),
            created_at="now", updated_at="now",
        ))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-04")
        assert fi.raw_revenue == Decimal("10000")
        assert fi.discount_rate == Decimal("0.8")
        assert fi.total_deductions == Decimal("100")
        assert fi.split_rate == Decimal("0.5")
        assert fi.channel_fee_rate == Decimal("0.05")
        assert fi.tax_rate == Decimal("0.06")
        assert fi.locked_real_revenue == Decimal("7000")
        assert fi.locked_settlement_amount is None
        assert fi.fixed_fee is None

    @pytest.mark.asyncio
    async def test_channel_no_config(self, db_session):
        """No IncomeSplitConfig → config fields are None."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("10000"))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-04")
        assert fi.raw_revenue == Decimal("10000")
        assert fi.split_rate is None
        assert fi.channel_fee_rate is None
        assert fi.tax_rate is None

    @pytest.mark.asyncio
    async def test_channel_no_deductions(self, db_session):
        """No Deduction row → total_deductions = 0."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("10000"))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-04")
        assert fi.total_deductions == Decimal("0")

    @pytest.mark.asyncio
    async def test_channel_no_lock(self, db_session):
        """No ChannelLock → locked values are None."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        # No RawSettlement row → raw_revenue defaults to 0 via _aggregate_channel_raw_revenue
        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-04")
        assert fi.locked_real_revenue is None
        assert fi.locked_settlement_amount is None

    @pytest.mark.asyncio
    async def test_publisher_complete(self, db_session):
        """Full publisher setup → all fields including fixed_fee. Raw_revenue from RawSettlement."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-06", raw_revenue=Decimal("20000"))

        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-06",
            vouchers=Decimal("200"), test=Decimal("0"),
            welfare=Decimal("0"), bad_debt=Decimal("0"),
        ))
        db_session.add(models.PaymentSplitConfig(
            publisher_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"),
            tax_rate=Decimal("0.06"), fixed_fee=Decimal("500"),
        ))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "publisher", 1, "G001", "2026-06")
        assert fi.raw_revenue == Decimal("20000")
        assert fi.discount_rate == Decimal("0.8")
        assert fi.total_deductions == Decimal("200")
        assert fi.split_rate == Decimal("0.5")
        assert fi.channel_fee_rate == Decimal("0.05")
        assert fi.tax_rate == Decimal("0.06")
        assert fi.fixed_fee == Decimal("500")

    @pytest.mark.asyncio
    async def test_publisher_no_config(self, db_session):
        """No PaymentSplitConfig → all config fields None."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "publisher", 1, "G001", "2026-04")
        assert fi.split_rate is None
        assert fi.fixed_fee is None

    @pytest.mark.asyncio
    async def test_game_not_found_defaults_discount_zero(self, db_session):
        """When game is not in DB, discount_rate defaults to 0."""
        fi = await hydrate_formula_input(db_session, "channel", 1, "G999", "2026-04")
        assert fi.discount_rate == Decimal("0")
        assert fi.raw_revenue == Decimal("0")  # no RawSettlement

    @pytest.mark.asyncio
    async def test_expired_config_not_used(self, db_session):
        """Config with effective_to before month_start is not used."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-06", raw_revenue=Decimal("10000"))

        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31),
            split_rate=Decimal("0.3"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        ))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-06")
        assert fi.split_rate is None  # config expired, not used


# ═══════════════════════════════════════════════════════════════
# _aggregate_channel_raw_revenue — reads from raw_settlements
# ═══════════════════════════════════════════════════════════════

class TestAggregateChannelRawRevenue:
    """Tests for _aggregate_channel_raw_revenue — reads from RawSettlement."""

    @pytest.mark.asyncio
    async def test_reads_from_raw_settlements(self, db_session):
        """Reads raw_revenue from RawSettlement (not old ChannelSettlement)."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("15000"))
        await db_session.commit()

        result = await _aggregate_channel_raw_revenue(db_session, ["G001"], "2026-04", 1)
        assert result["G001"] == 15000.0

    @pytest.mark.asyncio
    async def test_multiple_games_aggregated_separately(self, db_session):
        """Multiple game_ids each get their own aggregation from RawSettlement."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.8")))
        db_session.add(models.Game(game_id="G002", game_name="游戏B", discount_rate=Decimal("0.7")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=1, game_id="G001", month="2026-04", raw_revenue=Decimal("10000"))
        await _seed_rs(db_session, channel_id=1, game_id="G002", month="2026-04", raw_revenue=Decimal("20000"))
        await db_session.commit()

        result = await _aggregate_channel_raw_revenue(db_session, ["G001", "G002"], "2026-04", 1)
        assert result["G001"] == 10000.0
        assert result["G002"] == 20000.0

    @pytest.mark.asyncio
    async def test_empty_game_ids_returns_empty(self, db_session):
        """Empty game_ids list returns empty dict."""
        result = await _aggregate_channel_raw_revenue(db_session, [], "2026-04", 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_matching_raw_settlement_returns_empty(self, db_session):
        """No matching RawSettlement rows returns empty dict."""
        result = await _aggregate_channel_raw_revenue(db_session, ["G999"], "2026-04", 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_different_channel_not_returned(self, db_session):
        """Only channel_id=X data is returned, not other channels."""
        db_session.add(models.ChannelCategory(channel_id=1, channel_name="渠道1"))
        db_session.add(models.ChannelCategory(channel_id=2, channel_name="渠道2"))
        db_session.add(models.Game(game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")))
        await db_session.commit()

        await _seed_rs(db_session, channel_id=2, game_id="G001", month="2026-04", raw_revenue=Decimal("5000"))
        await db_session.commit()

        # Query channel 1 → should be empty (data is on channel 2)
        result = await _aggregate_channel_raw_revenue(db_session, ["G001"], "2026-04", 1)
        assert result == {}
