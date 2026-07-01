"""Tests for compare_imported_rows — the flexible import diff comparison."""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.settlement_service import compare_imported_rows


# ── Helpers ──

async def _seed_channel(db, channel_id=1):
    """Seed ChannelCategory."""
    db.add(models.ChannelCategory(channel_id=channel_id, channel_name=f"渠道{channel_id}"))
    await db.commit()


async def _seed_game(db, game_id="G001", game_name="测试游戏", discount_rate=Decimal("0.8")):
    db.add(models.Game(game_id=game_id, game_name=game_name, discount_rate=discount_rate))
    await db.commit()


async def _seed_rs(db, channel_id=1, game_id="G001", month="2026-04", **kw):
    """Seed RawSettlement for comparison tests (replaces old ChannelSettlement)."""
    rs = models.RawSettlement(
        channel_id=channel_id,
        game_id=game_id,
        channel_name=f"渠道{channel_id}",
        game_name=kw.get("game_name", "测试游戏"),
        month=month,
        raw_revenue=kw.get("raw_revenue", Decimal("0")),
        created_at="2026-06-01", updated_at="2026-06-01",
    )
    db.add(rs)
    await db.commit()
    return rs


async def _seed_ded(db, channel_id=1, game_id="G001", month="2026-04",
                    vouchers=Decimal("0"), test=Decimal("0"),
                    welfare=Decimal("0"), bad_debt=Decimal("0")):
    """Seed a Deduction row."""
    ded = models.Deduction(
        channel_id=channel_id, game_id=game_id, month=month,
        vouchers=vouchers, test=test, welfare=welfare, bad_debt=bad_debt,
    )
    db.add(ded)
    await db.commit()
    return ded


async def _seed_cfg(db, channel_id=1, game_id="G001",
                    split_rate=None, channel_fee_rate=None, tax_rate=None,
                    effective_from=date(2026, 1, 1)):
    """Seed an IncomeSplitConfig row."""
    if split_rate is not None:
        cfg = models.IncomeSplitConfig(
            channel_id=channel_id, game_id=game_id,
            split_rate=Decimal(str(split_rate)),
            channel_fee_rate=Decimal(str(channel_fee_rate)) if channel_fee_rate is not None else Decimal("0"),
            tax_rate=Decimal(str(tax_rate)) if tax_rate is not None else Decimal("0"),
            effective_from=effective_from,
        )
        db.add(cfg)
        await db.commit()


# ═══════════════════════════════════════════════════════════════
# compare_imported_rows
# ═══════════════════════════════════════════════════════════════

class TestCompareImportedRows:
    """Tests for compare_imported_rows."""

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty(self, db_session):
        """Empty rows list returns empty list."""
        result = await compare_imported_rows(db_session, [], channel_id=1, month="2026-04",
                                             column_mapping={})
        assert result == []

    @pytest.mark.asyncio
    async def test_no_game_ids_returns_empty(self, db_session):
        """Rows without game_id return empty list."""
        rows = [{"game_name": "某游戏", "vouchers": 100}]
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping={"0": "vouchers"})
        assert result == []

    @pytest.mark.asyncio
    async def test_all_new_no_existing_data(self, db_session):
        """When no existing DB data, all old values are None."""
        await _seed_game(db_session)

        rows = [{"game_id": "G001", "game_name": "测试游戏", "vouchers": 300}]
        mapping = {"0": "game_name", "1": "vouchers"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        assert len(result) == 1
        assert result[0]["game_id"] == "G001"
        fields = result[0]["fields"]
        assert fields["vouchers"]["old"] is None
        assert fields["vouchers"]["new"] == 300.0
        assert fields["vouchers"]["changed"] is True

    @pytest.mark.asyncio
    async def test_no_changes_when_identical(self, db_session):
        """When snapshot old and new values are identical, changed=False."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        # RawSettlement provides raw_revenue for hydrate_formula_input
        await _seed_rs(db_session, raw_revenue=Decimal("10000"))
        # Deduction provides total_deductions
        await _seed_ded(db_session, vouchers=Decimal("100"), test=Decimal("50"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "raw_revenue": 10000}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert fields["raw_revenue"]["changed"] is False

    @pytest.mark.asyncio
    async def test_field_changed_detected(self, db_session):
        """When a field value differs, changed=True."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_rs(db_session, raw_revenue=Decimal("10000"))
        await _seed_ded(db_session, vouchers=Decimal("100"), test=Decimal("50"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "raw_revenue": 20000}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert fields["raw_revenue"]["old"] == 10000.0
        assert fields["raw_revenue"]["new"] == 20000.0
        assert fields["raw_revenue"]["changed"] is True

    @pytest.mark.asyncio
    async def test_tolerance_below_threshold_not_changed(self, db_session):
        """Difference of 0.0005 (below 0.001 threshold) → changed=False."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_rs(db_session, raw_revenue=Decimal("100.0003"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "raw_revenue": 100.0005}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        assert result[0]["fields"]["raw_revenue"]["changed"] is False

    @pytest.mark.asyncio
    async def test_tolerance_exceeded_changed(self, db_session):
        """Difference of 0.002 (above 0.001 threshold) → changed=True."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_ded(db_session, vouchers=Decimal("100"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "vouchers": 100.002}]
        mapping = {"0": "vouchers"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        assert result[0]["fields"]["vouchers"]["changed"] is True

    @pytest.mark.asyncio
    async def test_month_missing_all_old_none(self, db_session):
        """When month is empty, all old values are None."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_ded(db_session, vouchers=Decimal("100"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "vouchers": 100}]
        mapping = {"0": "vouchers"}
        # Empty month → no old data queried
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert fields["vouchers"]["old"] is None
        assert fields["vouchers"]["new"] == 100.0
        assert fields["vouchers"]["changed"] is True

    @pytest.mark.asyncio
    async def test_duplicate_game_ids(self, db_session):
        """Rows with same game_id get is_duplicate=True."""
        await _seed_game(db_session)

        rows = [
            {"game_id": "G001", "game_name": "游戏A", "vouchers": 100},
            {"game_id": "G001", "game_name": "游戏A", "vouchers": 200},
        ]
        mapping = {"0": "vouchers"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="",
                                             column_mapping=mapping)

        assert len(result) == 2
        assert result[0]["is_duplicate"] is True
        assert result[1]["is_duplicate"] is True

    @pytest.mark.asyncio
    async def test_no_duplicate_unique_ids(self, db_session):
        """All unique game_ids → is_duplicate=False for all."""
        await _seed_game(db_session, "G001", "游戏A")
        await _seed_game(db_session, "G002", "游戏B")

        rows = [
            {"game_id": "G001", "game_name": "游戏A", "vouchers": 100},
            {"game_id": "G002", "game_name": "游戏B", "vouchers": 200},
        ]
        mapping = {"0": "vouchers"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="",
                                             column_mapping=mapping)

        assert result[0]["is_duplicate"] is False
        assert result[1]["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_column_mapping_filters_fields(self, db_session):
        """Only fields in column_mapping appear in result fields."""
        await _seed_game(db_session)

        rows = [{"game_id": "G001", "vouchers": 300, "test": 50}]
        # Only map vouchers, not test
        mapping = {"0": "vouchers", "3": "game_name"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert "vouchers" in fields
        assert "test" not in fields  # not in column_mapping
        assert "raw_revenue" not in fields  # not in column_mapping

    @pytest.mark.asyncio
    async def test_split_rate_detected_in_snapshot(self, db_session):
        """Old split_rate comes from IncomeSplitConfig."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_rs(db_session, raw_revenue=Decimal("10000"))
        await _seed_cfg(db_session, split_rate=0.25, channel_fee_rate=0.05, tax_rate=0.06)
        await db_session.commit()

        rows = [{"game_id": "G001", "split_rate": 0.30}]
        mapping = {"0": "split_rate"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert fields["split_rate"]["old"] == 0.25
        assert fields["split_rate"]["new"] == 0.30
        assert fields["split_rate"]["changed"] is True

    @pytest.mark.asyncio
    async def test_settlement_computed_with_old_data(self, db_session):
        """Old settlement_amount is computed from RawSettlement + IncomeSplitConfig + Deduction."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        # Seed RawSettlement + Deduction + IncomeSplitConfig
        await _seed_rs(db_session, raw_revenue=Decimal("10000"))
        await _seed_cfg(db_session, split_rate=0.5, channel_fee_rate=0, tax_rate=0)
        await db_session.commit()

        rows = [{"game_id": "G001", "settlement_amount": 5000}]
        mapping = {"0": "settlement_amount"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        # old settlement = 10000 * 0.8 * 0.5 = 4000
        assert fields["settlement_amount"]["old"] == 4000.0
        assert fields["settlement_amount"]["new"] == 5000.0
        assert fields["settlement_amount"]["changed"] is True

    @pytest.mark.asyncio
    async def test_game_not_in_db_old_values_none(self, db_session):
        """When game_id not in discount_map, old values stay None."""
        rows = [{"game_id": "G999", "game_name": "不存在的游戏", "raw_revenue": 10000}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert "raw_revenue" in fields
        # When no Game/RawSettlement exists, hydrate_formula_input returns 0
        assert fields["raw_revenue"]["old"] == 0.0
        assert fields["raw_revenue"]["new"] == 10000.0
        # Old is 0, new is 10000 → changed
        assert fields["raw_revenue"]["changed"] is True

    @pytest.mark.asyncio
    async def test_multiple_rows_comparison(self, db_session):
        """Multiple rows each get their own comparison result."""
        await _seed_game(db_session, "G001", "游戏A")
        await _seed_game(db_session, "G002", "游戏B")

        rows = [
            {"game_id": "G001", "game_name": "游戏A", "vouchers": 100},
            {"game_id": "G002", "game_name": "游戏B", "vouchers": 200},
        ]
        mapping = {"0": "vouchers"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="",
                                             column_mapping=mapping)

        assert len(result) == 2
        assert result[0]["game_id"] == "G001"
        assert result[1]["game_id"] == "G002"

    @pytest.mark.asyncio
    async def test_new_value_none_not_changed(self, db_session):
        """When new value is None and old exists in snapshot, changed=True."""
        await _seed_channel(db_session)
        await _seed_game(db_session)
        await _seed_rs(db_session, raw_revenue=Decimal("10000"))
        await _seed_ded(db_session, vouchers=Decimal("100"), test=Decimal("50"))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "测试游戏", "raw_revenue": None}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, channel_id=1, month="2026-04",
                                             column_mapping=mapping)

        fields = result[0]["fields"]
        assert fields["raw_revenue"]["old"] == 10000.0
        assert fields["raw_revenue"]["new"] is None
        assert fields["raw_revenue"]["changed"] is True
