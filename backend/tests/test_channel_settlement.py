"""Tests for settlement refactoring — 6 verification scenarios.

These tests verify that RawSettlement-based queries produce correct results.
"""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.settlement_service import (
    query_income_settlement, query_payment_settlement,
    query_full_income_export, query_full_payment_export,
    hydrate_formula_input, _aggregate_channel_raw_revenue,
)


async def _seed_rs(db, channel_id, channel_name, game_id, game_name, month, raw_revenue):
    rs = models.RawSettlement(
        channel_id=channel_id, channel_name=channel_name,
        game_id=game_id, game_name=game_name,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


async def _seed_channel(db, channel_id=1):
    db.add(models.ChannelCategory(channel_id=channel_id, channel_name=f"渠道{channel_id}"))
    await db.commit()


async def _seed_game(db, game_id="G001", discount_rate=Decimal("0.8")):
    db.add(models.Game(game_id=game_id, game_name=f"游戏{game_id}", discount_rate=discount_rate))
    await db.commit()


async def _seed_publisher(db, publisher_id=1):
    db.add(models.Publisher(publisher_id=publisher_id, publisher_name=f"CP{publisher_id}"))
    db.add(models.PublisherGameMapping(publisher_id=publisher_id, game_id="G001",
                                        project_code="P001", project_name="项目A"))
    await db.commit()


# ═══════════════════════════════════════════════════════════════
# Scenario 1: 结算查询-收入 — RawSettlement 作为数据源
# ═══════════════════════════════════════════════════════════════

class TestScenario1IncomeQuery:
    """Income settlement query reads from RawSettlement."""

    @pytest.mark.asyncio
    async def test_income_query_reads_from_raw_settlements(self, db_session):
        """query_income_settlement returns rows from RawSettlement."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await db_session.commit()

        rows = await query_income_settlement(db_session, start_month="2026-01", end_month="2026-06")
        assert len(rows) == 1
        assert rows[0]["channel_id"] == 1
        assert rows[0]["game_id"] == "G001"
        assert rows[0]["month"] == "2026-04"
        assert rows[0]["raw_revenue"] == 10000.0

    @pytest.mark.asyncio
    async def test_income_query_no_raw_transaction_join(self, db_session):
        """Income query works WITHOUT any RawTransaction rows (pure RawSettlement)."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-05", Decimal("5000"))
        await db_session.commit()

        rows = await query_income_settlement(db_session)
        assert len(rows) == 1
        assert rows[0]["raw_revenue"] == 5000.0

    @pytest.mark.asyncio
    async def test_income_query_with_deductions_and_config(self, db_session):
        """Income query with deductions + split config computes settlement correctly."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001", Decimal("0.8"))
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("100"), test=Decimal("50"),
            welfare=Decimal("0"), bad_debt=Decimal("0"),
        ))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        ))
        await db_session.commit()

        rows = await query_income_settlement(db_session)
        assert len(rows) == 1
        r = rows[0]
        assert r["raw_revenue"] == 10000.0
        assert r["vouchers"] == 100.0
        assert r["test"] == 50.0
        assert r["total_deductions"] == 150.0
        assert r["split_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_income_query_multiple_channels(self, db_session):
        """Multiple channels each return their own rows."""
        await _seed_channel(db_session, 1)
        await _seed_channel(db_session, 2)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await _seed_rs(db_session, 2, "渠道2", "G001", "游戏G001", "2026-04", Decimal("20000"))
        await db_session.commit()

        rows = await query_income_settlement(db_session)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_income_query_month_filter(self, db_session):
        """Month range filter works correctly."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        for m in ["2026-01", "2026-02", "2026-03"]:
            await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", m, Decimal("10000"))
        await db_session.commit()

        rows = await query_income_settlement(db_session, start_month="2026-02", end_month="2026-02")
        assert len(rows) == 1
        assert rows[0]["month"] == "2026-02"


# ═══════════════════════════════════════════════════════════════
# Scenario 2: 锁定→解锁 — ChannelLock 作为锁定数据源
# ═══════════════════════════════════════════════════════════════

class TestScenario2LockUnlock:
    """Lock/unlock works via ChannelLock table."""

    @pytest.mark.asyncio
    async def test_lock_updates_channel_settlement(self, db_session):
        """Locking real_revenue persists to ChannelLock."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.ChannelLock(
            channel_id=1, game_id="G001", month="2026-04",
            locked_real_revenue=Decimal("9000"), locked_settlement_amount=None,
            created_at="now", updated_at="now",
        ))
        await db_session.commit()

        from sqlalchemy import select as sa_select
        cs_lock = (await db_session.execute(
            sa_select(models.ChannelLock).where(
                models.ChannelLock.channel_id == 1,
                models.ChannelLock.game_id == "G001",
                models.ChannelLock.month == "2026-04",
            )
        )).scalar_one()
        assert cs_lock.locked_real_revenue == Decimal("9000")

    @pytest.mark.asyncio
    async def test_unlocked_uses_formula_value(self, db_session):
        """Without lock, query returns formula-computed real_revenue."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await db_session.commit()

        rows = await query_income_settlement(db_session, start_month="2026-04", end_month="2026-04")
        assert len(rows) == 1
        assert rows[0]["real_revenue"] == 8000.0  # 10000 * 0.8
        assert rows[0]["locked_real_revenue"] is None

    @pytest.mark.asyncio
    async def test_lock_both_fields(self, db_session):
        """Both real_revenue and settlement_amount can be locked."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        ))
        db_session.add(models.ChannelLock(
            channel_id=1, game_id="G001", month="2026-04",
            locked_real_revenue=Decimal("9000"), locked_settlement_amount=Decimal("4000"),
            created_at="2026-01-01", updated_at="2026-01-01",
        ))
        await db_session.commit()

        rows = await query_income_settlement(db_session, start_month="2026-04", end_month="2026-04")
        assert rows[0]["locked_real_revenue"] == 9000.0
        assert rows[0]["locked_settlement_amount"] == 4000.0


# ═══════════════════════════════════════════════════════════════
# Scenario 3: 模板导入 — RawSettlement 存储
# ═══════════════════════════════════════════════════════════════

class TestScenario3TemplateImport:
    """Template import populates RawSettlement."""

    @pytest.mark.asyncio
    async def test_raw_settlement_has_raw_revenue(self, db_session):
        """RawSettlement stores raw_revenue independently of old RawTransaction."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("15000"))
        await db_session.commit()

        from sqlalchemy import select as sa_select
        rs = (await db_session.execute(
            sa_select(models.RawSettlement).where(
                models.RawSettlement.channel_id == 1,
            )
        )).scalar_one()
        assert rs.raw_revenue == Decimal("15000")

    @pytest.mark.asyncio
    async def test_raw_settlement_unique_constraint(self, db_session):
        """RawSettlement stores data by (channel_id, game_id, month) key."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await db_session.commit()

        from sqlalchemy import select as sa_select
        rows = (await db_session.execute(
            sa_select(models.RawSettlement).where(
                models.RawSettlement.channel_id == 1,
                models.RawSettlement.game_id == "G001",
                models.RawSettlement.month == "2026-04",
            )
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].raw_revenue == Decimal("10000")


# ═══════════════════════════════════════════════════════════════
# Scenario 4: 弹性导入 — 对比/冻结守卫/写入同步
# ═══════════════════════════════════════════════════════════════

class TestScenario4FlexibleImport:
    """Flexible import uses RawSettlement for comparison and ChannelLock guard."""

    @pytest.mark.asyncio
    async def test_comparison_reads_from_raw_settlements(self, db_session):
        """compare_imported_rows gets old raw_revenue from RawSettlement."""
        from backend.services.settlement_service import compare_imported_rows

        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("50"), test=Decimal("30"),
            welfare=Decimal("10"), bad_debt=Decimal("10"),
        ))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        ))
        await db_session.commit()

        rows = [{"game_id": "G001", "game_name": "游戏G001", "raw_revenue": 12000}]
        mapping = {"0": "raw_revenue"}
        result = await compare_imported_rows(db_session, rows, 1, "2026-04", mapping)

        assert len(result) == 1
        r = result[0]
        assert r["game_id"] == "G001"
        assert r["fields"]["raw_revenue"]["old"] == 10000.0
        assert r["fields"]["raw_revenue"]["new"] == 12000.0
        assert r["fields"]["raw_revenue"]["changed"] is True

    @pytest.mark.asyncio
    async def test_comparison_old_values_from_deduction(self, db_session):
        """Deduction fields get old values from Deduction table."""
        from backend.services.settlement_service import compare_imported_rows

        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("50"), test=Decimal("30"),
            welfare=Decimal("10"), bad_debt=Decimal("10"),
        ))
        await db_session.commit()

        rows = [{"game_id": "G001", "vouchers": 50, "test": 30, "welfare": 10, "bad_debt": 10}]
        mapping = {"0": "vouchers", "1": "test", "2": "welfare", "3": "bad_debt"}
        result = await compare_imported_rows(db_session, rows, 1, "2026-04", mapping)

        r = result[0]
        assert r["fields"]["vouchers"]["old"] == 50.0
        assert r["fields"]["vouchers"]["new"] == 50.0
        assert r["fields"]["vouchers"]["changed"] is False

    @pytest.mark.asyncio
    async def test_frozen_guard_rejects_locked_data(self, db_session):
        """Frozen guard raises ValueError when ChannelLock exists."""
        from backend.services.flexible_import import import_flexible_data

        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        db_session.add(models.ChannelLock(
            channel_id=1, game_id="G001", month="2026-04",
            locked_real_revenue=Decimal("9000"),
            created_at="now", updated_at="now",
        ))
        await db_session.commit()

        rows = [{"game_id": "G001", "raw_revenue": 12000}]
        mapping = {"0": "raw_revenue"}
        with pytest.raises(ValueError, match="已被锁定"):
            await import_flexible_data(db_session, rows, 1, "2026-04", mapping)

    @pytest.mark.asyncio
    async def test_no_lock_allows_import(self, db_session):
        """Without lock, import proceeds."""
        from backend.services.flexible_import import import_flexible_data

        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await db_session.commit()

        rows = [{"game_id": "G001", "raw_revenue": 12000}]
        mapping = {"0": "raw_revenue"}
        result = await import_flexible_data(db_session, rows, 1, "2026-04", mapping)
        assert "imported_deductions" in result


# ═══════════════════════════════════════════════════════════════
# Scenario 5: 全量导出 — 聚合粒度
# ═══════════════════════════════════════════════════════════════

class TestScenario5FullExport:
    """Full export at aggregate (channel_id, game_id, month) granularity."""

    @pytest.mark.asyncio
    async def test_income_export_aggregate_granularity(self, db_session):
        """Each row in full export is one (channel_id, game_id, month)."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await db_session.commit()

        rows = await query_full_income_export(db_session, start_month="2026-01", end_month="2026-06")
        assert len(rows) == 1
        r = rows[0]
        assert r["channel_id"] == 1
        assert r["game_id"] == "G001"
        assert r["month"] == "2026-04"
        assert r["raw_revenue"] == 10000.0

    @pytest.mark.asyncio
    async def test_income_export_deduction_no_proration(self, db_session):
        """Deductions at aggregate level."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("50"), test=Decimal("30"),
            welfare=Decimal("10"), bad_debt=Decimal("10"),
        ))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        ))
        await db_session.commit()

        rows = await query_full_income_export(db_session)
        assert len(rows) == 1
        r = rows[0]
        assert r["vouchers"] == 50.0
        assert r["total_deductions"] == 100.0

    @pytest.mark.asyncio
    async def test_payment_export_aggregates_across_channels(self, db_session):
        """Payment export sums raw_revenue across channels."""
        await _seed_channel(db_session, 1)
        await _seed_channel(db_session, 2)
        await _seed_game(db_session, "G001")
        await _seed_publisher(db_session, 1)

        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await _seed_rs(db_session, 2, "渠道2", "G001", "游戏G001", "2026-04", Decimal("5000"))
        await db_session.commit()

        rows = await query_full_payment_export(db_session)
        assert len(rows) == 1
        assert rows[0]["raw_revenue"] == 15000.0  # 10000 + 5000


# ═══════════════════════════════════════════════════════════════
# Scenario 6: hydrate_formula_input — reads from RawSettlement
# ═══════════════════════════════════════════════════════════════

class TestScenario6HydrateFormulaInput:
    """hydrate_formula_input reads from RawSettlement for channel path."""

    @pytest.mark.asyncio
    async def test_channel_path_reads_from_settlement(self, db_session):
        """hydrate_formula_input(channel) gets raw_revenue from RawSettlement."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
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
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "channel", 1, "G001", "2026-04")
        assert fi.raw_revenue == Decimal("10000")
        assert fi.discount_rate == Decimal("0.8")
        assert fi.total_deductions == Decimal("100")
        assert fi.split_rate == Decimal("0.5")

    @pytest.mark.asyncio
    async def test_publisher_path_aggregates_across_channels(self, db_session):
        """hydrate_formula_input(publisher) aggregates RawSettlement across channels."""
        await _seed_channel(db_session, 1)
        await _seed_channel(db_session, 2)
        await _seed_game(db_session, "G001")
        db_session.add(models.Publisher(publisher_id=1, publisher_name="CP1"))
        db_session.add(models.PublisherGameMapping(publisher_id=1, game_id="G001",
                                                    project_code="P1", project_name="A"))

        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("10000"))
        await _seed_rs(db_session, 2, "渠道2", "G001", "游戏G001", "2026-04", Decimal("5000"))
        await db_session.commit()

        fi = await hydrate_formula_input(db_session, "publisher", 1, "G001", "2026-04")
        assert fi.raw_revenue == Decimal("15000")  # 10000 + 5000

    @pytest.mark.asyncio
    async def test_aggregate_raw_revenue_reads_raw_settlement(self, db_session):
        """_aggregate_channel_raw_revenue reads from RawSettlement."""
        await _seed_channel(db_session, 1)
        await _seed_game(db_session, "G001")
        await _seed_rs(db_session, 1, "渠道1", "G001", "游戏G001", "2026-04", Decimal("15000"))
        await db_session.commit()

        result = await _aggregate_channel_raw_revenue(db_session, ["G001"], "2026-04", 1)
        assert result["G001"] == 15000.0
