"""Tests for full export queries: query_full_income_export, query_full_payment_export.

NOTE: These now delegate to query_income_settlement / query_payment_settlement
which aggregate at (channel, game, month) granularity via RawSettlement.
"""
import pytest
from datetime import date
from decimal import Decimal

from backend import models
from backend.services.settlement_service import query_full_income_export, query_full_payment_export


async def _seed_rs(db, channel_id, channel_name, game_id, game_name, month, raw_revenue, **kw):
    rs = models.RawSettlement(
        channel_id=channel_id, channel_name=channel_name,
        game_id=game_id, game_name=game_name,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


async def _seed_income_setup(db):
    """Seed: channel + game."""
    db.add(models.ChannelCategory(channel_id=1, channel_name="应用商店"))
    db.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.8")))
    await db.commit()


async def _seed_payment_setup(db):
    """Seed: publisher + game + mapping + company."""
    db.add(models.ChannelCategory(channel_id=1, channel_name="应用商店"))
    db.add(models.Publisher(publisher_id=1, publisher_name="测试CP"))
    db.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.8")))
    db.add(models.PublisherGameMapping(publisher_id=1, game_id="G001"))
    db.add(models.Company(company_id=1, company_name="测试公司"))
    db.add(models.CompanyGameMapping(company_id=1, game_id="G001"))
    await db.commit()


class TestFullIncomeExport:
    """Tests for query_full_income_export (aggregated at (channel, game, month))."""

    @pytest.mark.asyncio
    async def test_empty_no_data(self, db_session):
        assert await query_full_income_export(db_session) == []

    @pytest.mark.asyncio
    async def test_single_transaction_basic(self, db_session):
        await _seed_income_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        ))
        await db_session.commit()

        result = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-04")
        assert len(result) == 1
        r = result[0]
        assert r["game_id"] == "G001"
        assert r["game_name"] == "王者荣耀"
        assert r["month"] == "2026-04"
        assert r["raw_revenue"] == 10000.0
        assert r["real_revenue"] == 8000.0  # 10000 * 0.8
        assert r["settlement_amount"] == 4000.0  # (8000-0)*0.5

    @pytest.mark.asyncio
    async def test_multiple_transactions_proration(self, db_session):
        """Aggregated: single row per (channel, game, month) — no proration."""
        await _seed_income_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("1000"), test=Decimal("0"),
            welfare=Decimal("0"), bad_debt=Decimal("0"),
        ))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        ))
        await db_session.commit()

        result = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-04")
        assert len(result) == 1  # aggregated
        assert result[0]["total_deductions"] == 1000.0
        assert result[0]["settlement_amount"] == 3500.0  # (8000-1000)*0.5

    @pytest.mark.asyncio
    async def test_no_config_settlement_none(self, db_session):
        await _seed_income_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        await db_session.commit()

        result = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-04")
        assert len(result) == 1
        assert result[0]["settlement_amount"] is None
        assert result[0]["real_revenue"] == 8000.0

    @pytest.mark.asyncio
    async def test_month_filter(self, db_session):
        await _seed_income_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-05", Decimal("20000"))
        db_session.add(models.IncomeSplitConfig(
            channel_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"), tax_rate=Decimal("0"),
        ))
        await db_session.commit()

        result = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-04")
        assert len(result) == 1
        assert result[0]["month"] == "2026-04"

        result2 = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-05")
        assert len(result2) == 2

    @pytest.mark.asyncio
    async def test_channel_hierarchy_in_result(self, db_session):
        await _seed_income_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        await db_session.commit()

        result = await query_full_income_export(db_session, start_month="2026-04", end_month="2026-04")
        assert result[0]["channel_name"] == "应用商店"


class TestFullPaymentExport:
    """Tests for query_full_payment_export (aggregated at (publisher, game, month))."""

    @pytest.mark.asyncio
    async def test_empty_no_data(self, db_session):
        assert await query_full_payment_export(db_session) == []

    @pytest.mark.asyncio
    async def test_basic_payment_export(self, db_session):
        await _seed_payment_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        db_session.add(models.PaymentSplitConfig(
            publisher_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"),
            tax_rate=Decimal("0"), fixed_fee=Decimal("0"),
        ))
        await db_session.commit()

        result = await query_full_payment_export(db_session, start_month="2026-04", end_month="2026-04")
        assert len(result) == 1
        r = result[0]
        assert r["game_id"] == "G001"
        assert r["real_revenue"] == 8000.0  # 10000 * 0.8
        assert r["settlement_amount"] == 4000.0  # (8000-0)*0.5

    @pytest.mark.asyncio
    async def test_payment_with_fixed_fee(self, db_session):
        await _seed_payment_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        db_session.add(models.PaymentSplitConfig(
            publisher_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"),
            tax_rate=Decimal("0"), fixed_fee=Decimal("1000"),
        ))
        await db_session.commit()

        result = await query_full_payment_export(db_session, start_month="2026-04", end_month="2026-04")
        assert result[0]["settlement_amount"] == 5000.0  # (8000-0)*0.5 + 1000
        assert result[0]["fixed_fee"] == 1000.0

    @pytest.mark.asyncio
    async def test_payment_cross_channel_deductions(self, db_session):
        await _seed_payment_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        db_session.add(models.Deduction(
            channel_id=1, game_id="G001", month="2026-04",
            vouchers=Decimal("500"), test=Decimal("200"),
            welfare=Decimal("0"), bad_debt=Decimal("0"),
        ))
        db_session.add(models.PaymentSplitConfig(
            publisher_id=1, game_id="G001",
            effective_from=date(2026, 1, 1), effective_to=None,
            split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0"),
            tax_rate=Decimal("0"), fixed_fee=Decimal("0"),
        ))
        await db_session.commit()

        result = await query_full_payment_export(db_session, start_month="2026-04", end_month="2026-04")
        # net = 8000 - 700 = 7300; settlement = 7300 * 0.5 = 3650
        assert result[0]["settlement_amount"] == 3650.0

    @pytest.mark.asyncio
    async def test_payment_no_config_settlement_none(self, db_session):
        await _seed_payment_setup(db_session)
        await _seed_rs(db_session, 1, "应用商店", "G001", "王者荣耀", "2026-04", Decimal("10000"))
        await db_session.commit()

        result = await query_full_payment_export(db_session, start_month="2026-04", end_month="2026-04")
        assert result[0]["settlement_amount"] is None
