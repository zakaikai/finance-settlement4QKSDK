"""Tests for snapshot_service: snapshot, pivot, monthly close, end-to-end."""
import pytest
from datetime import date
from decimal import Decimal
from collections import defaultdict
from sqlalchemy import select

from backend import models
from backend.services.snapshot_service import (
    snapshot_from_locks,
    get_pivot,
    is_month_closed,
    current_working_month,
    close_month,
    reopen_month,
    _resolve_entity_name,
    _resolve_company_name,
    get_snapshot_balances,
    get_pending_count,
)
from backend.services.company_resolver import resolve_companies_batch

# ── Helpers ──

async def _seed_game(db, game_id="G001", name="TestGame", discount=Decimal("1.0")):
    db.add(models.Game(game_id=game_id, game_name=name, discount_rate=discount))

async def _seed_company(db, company_id=1, name="测试公司"):
    db.add(models.Company(company_id=company_id, company_name=name))

async def _seed_channel_category(db, channel_id=1, name="渠道1"):
    db.add(models.ChannelCategory(channel_id=channel_id, channel_name=name))

async def _seed_publisher(db, publisher_id=1, name="研发商1"):
    db.add(models.Publisher(publisher_id=publisher_id, publisher_name=name))

async def _seed_company_game_mapping(db, company_id=1, game_id="G001", channel_id=None):
    db.add(models.CompanyGameMapping(
        company_id=company_id, game_id=game_id, channel_id=channel_id))

async def _seed_publisher_game_mapping(db, publisher_id=1, game_id="G001",
                                        project_code="PROJ001", project_name="测试项目"):
    db.add(models.PublisherGameMapping(
        publisher_id=publisher_id, game_id=game_id,
        project_code=project_code, project_name=project_name))

async def _seed_raw_settlement(db, channel_id=1, game_id="G001", month="2026-06",
                                channel_name="渠道1", game_name="TestGame",
                                raw_revenue=Decimal("10000")):
    db.add(models.RawSettlement(
        channel_id=channel_id, game_id=game_id,
        channel_name=channel_name, game_name=game_name,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01"))

async def _seed_channel_lock(db, channel_id=1, game_id="G001", month="2026-06",
                              locked_amount=Decimal("5000")):
    db.add(models.ChannelLock(
        channel_id=channel_id, game_id=game_id, month=month,
        locked_real_revenue=Decimal("5000"),
        locked_settlement_amount=locked_amount,
        confirmed_month=None,
        created_at="now", updated_at="now"))

async def _seed_publisher_lock(db, publisher_id=1, game_id="G001", month="2026-06",
                                locked_amount=Decimal("3000")):
    db.add(models.PublisherLock(
        publisher_id=publisher_id, game_id=game_id, month=month,
        locked_real_revenue=Decimal("3000"),
        locked_settlement_amount=locked_amount,
        confirmed_month=None,
        created_at="now", updated_at="now"))


# ═══════════════════════════════════════════════
# Round 1: Core snapshot & pivot
# ═══════════════════════════════════════════════

class TestSnapshotFromLocks:

    async def _setup_basic(self, db):
        await _seed_game(db)
        await _seed_company(db)
        await _seed_company_game_mapping(db)
        await _seed_channel_category(db, channel_id=1, name="渠道1")
        await _seed_raw_settlement(db, channel_id=1, month="2026-06")
        await _seed_channel_lock(db, channel_id=1, locked_amount=Decimal("5000"))
        await db.commit()

    @pytest.mark.asyncio
    async def test_snapshot_creates_arap_record(self, db_session):
        """锁定一条记录 → 快照 → arap_records 创建一行，金额正确"""
        db = db_session
        await self._setup_basic(db)
        result = await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        assert result["inserted"] == 1
        assert result["channel_locks_processed"] == 1
        rows = (await db.execute(select(models.ArapRecord))).scalars().all()
        assert len(rows) == 1
        assert rows[0].entity_type == "channel"
        assert rows[0].entity_id == 1
        assert rows[0].company_name == "测试公司"
        assert rows[0].month == "2026-06"
        assert rows[0].confirmed_month == "2026-06"
        assert rows[0].settlement_amount == Decimal("5000.00")

    @pytest.mark.asyncio
    async def test_snapshot_marks_lock_confirmed(self, db_session):
        """快照后 channel_lock 的 confirmed_month 被设置"""
        db = db_session
        await self._setup_basic(db)
        await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        lock = (await db.execute(select(models.ChannelLock))).scalar_one()
        assert lock.confirmed_month == "2026-06"

    @pytest.mark.asyncio
    async def test_snapshot_skips_already_confirmed(self, db_session):
        """已快照过的锁被跳过，不重复处理"""
        db = db_session
        await self._setup_basic(db)
        await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        result2 = await snapshot_from_locks(db, "2026-06-02 12:00:00", "2026-06")
        assert result2["inserted"] == 0
        assert result2["channel_locks_processed"] == 0
        rows = (await db.execute(select(models.ArapRecord))).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_upsert_same_channel_diff_game(self, db_session):
        """同一渠道下不同游戏的锁，聚合到同一行后快照 → upsert 累加金额"""
        db = db_session
        await _seed_game(db, game_id="G001")
        await _seed_company_game_mapping(db, game_id="G001")
        await _seed_raw_settlement(db, channel_id=1, game_id="G001", month="2026-06")
        await _seed_channel_lock(db, channel_id=1, game_id="G001", month="2026-06", locked_amount=Decimal("5000"))
        await _seed_game(db, game_id="G002", name="TestGame2")
        await _seed_company_game_mapping(db, game_id="G002")
        await _seed_raw_settlement(db, channel_id=1, game_id="G002", month="2026-06", channel_name="渠道1", game_name="TestGame2")
        await _seed_channel_lock(db, channel_id=1, game_id="G002", month="2026-06", locked_amount=Decimal("3000"))
        await _seed_channel_category(db, channel_id=1, name="渠道1")
        await _seed_company(db)
        await db.commit()
        result = await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        assert result["inserted"] == 1
        assert result["channel_locks_processed"] == 2
        rows = (await db.execute(select(models.ArapRecord))).scalars().all()
        assert len(rows) == 1
        assert rows[0].settlement_amount == Decimal("8000.00")

    @pytest.mark.asyncio
    async def test_publisher_side_snapshot(self, db_session):
        """快照 publisher_locks → arap_records publisher 侧记录正确"""
        db = db_session
        await _seed_game(db)
        await _seed_company(db)
        await _seed_company_game_mapping(db)
        await _seed_publisher(db, publisher_id=1, name="研发商1")
        await _seed_publisher_game_mapping(db, publisher_id=1)
        await _seed_raw_settlement(db, channel_id=1, month="2026-06")
        await _seed_publisher_lock(db, publisher_id=1, locked_amount=Decimal("3000"))
        await db.commit()
        result = await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        assert result["inserted"] == 1
        assert result["publisher_locks_processed"] == 1
        rows = (await db.execute(select(models.ArapRecord))).scalars().all()
        assert len(rows) == 1
        assert rows[0].entity_type == "publisher"
        assert rows[0].entity_id == 1
        assert rows[0].month == "2026-06"
        assert rows[0].settlement_amount == Decimal("3000.00")


# ── 2. Monthly close routing ──

class TestMonthlyClose:

    @pytest.mark.asyncio
    async def test_close_does_not_affect_debit_credit_totals(self, db_session):
        """月结只写入 monthly_closes 表，不修改 arap_records 或 payment_allocations。

        因此 pivot 的 debit_total / credit_total 全局汇总不受月结影响。
        """
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        db_session.add(models.ArapRecord(
            entity_type="channel", entity_id=1, entity_name="渠道1",
            company_id=1, company_name="测试公司",
            game_id="", game_name="", month="2026-04",
            confirmed_month="2026-06", settlement_amount=Decimal("5000"),
            locked_amount=Decimal("5000"), snapshot_at="2026-06-01"))
        db_session.add(models.ArapRecord(
            entity_type="channel", entity_id=1, entity_name="渠道1",
            company_id=1, company_name="测试公司",
            game_id="", game_name="", month="2026-05",
            confirmed_month="2026-07", settlement_amount=Decimal("3000"),
            locked_amount=Decimal("3000"), snapshot_at="2026-07-01"))
        await db_session.commit()

        before = await get_pivot(db_session, "channel", "2026-06", "2026-07")
        assert before["rows"][0]["debit_total"] == 8000.0

        # 月结 2026-06
        await close_month(db_session, "2026-06", "2026-06-15 12:00:00")

        after = await get_pivot(db_session, "channel", "2026-06", "2026-07")
        assert after["rows"][0]["debit_total"] == 8000.0, "debit_total unchanged by close"
        assert after["rows"][0]["credit_total"] == before["rows"][0]["credit_total"]
        # total (筛选范围内) 也不变，因为 arap_records 未变
        assert after["rows"][0]["total"] == before["rows"][0]["total"]

    @pytest.mark.asyncio
    async def test_is_month_closed_returns_false(self, db_session):
        assert await is_month_closed(db_session, "2026-06") is False

    @pytest.mark.asyncio
    async def test_is_month_closed_after_close(self, db_session):
        await close_month(db_session, "2026-06", "2026-06-10 12:00:00")
        assert await is_month_closed(db_session, "2026-06") is True

    @pytest.mark.asyncio
    async def test_close_month_idempotent(self, db_session):
        r1 = await close_month(db_session, "2026-06", "2026-06-10 12:00:00")
        r2 = await close_month(db_session, "2026-06", "2026-06-10 12:00:00")
        assert r1["status"] == "closed"
        assert r2["status"] == "already_closed"

    @pytest.mark.asyncio
    async def test_current_working_month_no_close(self, db_session):
        wm = await current_working_month(db_session)
        import datetime
        today = datetime.date.today()
        assert wm == f"{today.year}-{today.month:02d}"

    @pytest.mark.asyncio
    async def test_current_working_month_after_close(self, db_session):
        await close_month(db_session, "2026-05", "2026-05-31 23:59:59")
        wm = await current_working_month(db_session)
        assert wm == "2026-06"

    @pytest.mark.asyncio
    async def test_reopen_month(self, db_session):
        await close_month(db_session, "2026-06", "2026-06-10 12:00:00")
        assert await is_month_closed(db_session, "2026-06") is True
        await reopen_month(db_session, "2026-06", "2026-06-10 13:00:00")
        assert await is_month_closed(db_session, "2026-06") is False


# ── 3. get_pivot ──

class TestGetPivot:

    async def _seed_arap_row(self, db, entity_type="channel", entity_id=1,
                               company_id=1, company_name="测试公司",
                               month="2026-06", amount=Decimal("1000"),
                               confirmed_month="2026-06"):
        db.add(models.ArapRecord(
            entity_type=entity_type, entity_id=entity_id,
            entity_name="渠道1", company_id=company_id,
            company_name=company_name, game_id="", game_name="",
            month=month, confirmed_month=confirmed_month,
            settlement_amount=amount, locked_amount=amount,
            snapshot_at="2026-06-01 12:00:00",
        ))

    @pytest.mark.asyncio
    async def test_pivot_single_row(self, db_session):
        await _seed_company(db_session, company_id=1, name="测试公司")
        await self._seed_arap_row(db_session, amount=Decimal("5000"))
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await db_session.commit()
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        rows = result["rows"]
        assert len(rows) == 1
        assert rows[0]["entity_name"] == "渠道1"
        assert rows[0]["company_name"] == "测试公司"
        assert rows[0]["cells"]["2026-06"] == 5000.0

    @pytest.mark.asyncio
    async def test_pivot_accumulates_multi_row(self, db_session):
        await _seed_company(db_session, company_id=1, name="测试公司")
        await self._seed_arap_row(db_session, entity_id=1, month="2026-06", amount=Decimal("3000"))
        await self._seed_arap_row(db_session, entity_id=1, month="2026-06", amount=Decimal("2000"))
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await db_session.commit()
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        assert len(result["rows"]) == 1
        assert result["rows"][0]["cells"]["2026-06"] == 5000.0

    @pytest.mark.asyncio
    async def test_pivot_filters_zero_balance(self, db_session):
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_company(db_session, company_id=2, name="测试公司2")
        await self._seed_arap_row(db_session, amount=Decimal("0"))
        await self._seed_arap_row(db_session, entity_id=2, company_id=2, amount=Decimal("100"))
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await _seed_channel_category(db_session, channel_id=2, name="渠道2")
        await db_session.commit()
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        assert len(result["rows"]) == 1
        assert result["rows"][0]["entity_id"] == 2

    @pytest.mark.asyncio
    async def test_pivot_separates_by_company(self, db_session):
        await _seed_company(db_session, company_id=1, name="公司A")
        await _seed_company(db_session, company_id=2, name="公司B")
        await self._seed_arap_row(db_session, entity_id=1, company_id=1, amount=Decimal("3000"))
        await self._seed_arap_row(db_session, entity_id=1, company_id=2, amount=Decimal("2000"))
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await db_session.commit()
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        assert len(result["rows"]) == 2
        companies = {r["company_name"] for r in result["rows"]}
        assert companies == {"公司A", "公司B"}

    @pytest.mark.asyncio
    async def test_pivot_entity_name_resolved(self, db_session):
        await _seed_company(db_session, company_id=1, name="测试公司")
        await self._seed_arap_row(db_session, entity_id=99)
        await _seed_channel_category(db_session, channel_id=99, name="特殊渠道")
        await db_session.commit()
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        assert len(result["rows"]) == 1
        assert result["rows"][0]["entity_name"] == "特殊渠道"

    @pytest.mark.asyncio
    async def test_pivot_includes_debit_credit_totals(self, db_session):
        """debit_total = global snapshot sum; credit_total = global paid sum.

        total only covers the filtered confirmed_month range, but debit/credit
        are global (unfiltered).
        """
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        # confirmed_month 2026-06 (inside filter) → total includes this
        await self._seed_arap_row(db_session, entity_id=1, company_id=1,
                                   month="2026-04", confirmed_month="2026-06",
                                   amount=Decimal("3000"))
        # confirmed_month 2026-07 (outside filter) → debit_total includes this, total does not
        await self._seed_arap_row(db_session, entity_id=1, company_id=1,
                                   month="2026-05", confirmed_month="2026-07",
                                   amount=Decimal("2000"))
        await db_session.commit()

        # Query only 2026-06 confirmed_month
        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")

        assert len(result["rows"]) == 1
        row = result["rows"][0]
        # total only the 2026-06 record
        assert row["total"] == 3000.0
        # debit_total = global: both records
        assert row["debit_total"] == 5000.0
        # credit_total = 0 since no payments registered
        assert row["credit_total"] == 0.0

    @pytest.mark.asyncio
    async def test_pivot_credit_total_global_ignores_collection_month_filter(self, db_session):
        """credit_total is global, not affected by confirmed_month range.

        Two ARAP records with different confirmed_months, two payments with
        different collection_months. Narrow query → total is filtered,
        debit/credit are global.
        """
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await self._seed_arap_row(db_session, entity_id=1, company_id=1,
                                   month="2026-04", confirmed_month="2026-06",
                                   amount=Decimal("5000"))
        await self._seed_arap_row(db_session, entity_id=1, company_id=1,
                                   month="2026-05", confirmed_month="2026-07",
                                   amount=Decimal("3000"))
        await db_session.commit()

        from backend.services.payment_service import register_payment
        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=2000.0, collection_month="2026-06",
            now="2026-06-01 10:00:00",
        )
        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=1000.0, collection_month="2026-09",
            now="2026-09-01 10:00:00",
        )

        result = await get_pivot(db_session, "channel", "2026-06", "2026-06")
        assert len(result["rows"]) == 1
        row = result["rows"][0]
        assert row["total"] == 5000.0, "total: only confirmed_month=2026-06"
        assert row["debit_total"] == 8000.0, "debit_total: global, both months"
        assert row["credit_total"] == 3000.0, "credit_total: global, both payments"


class TestGetBreakdown:

    async def _seed_arap(self, db, entity_type="channel", entity_id=1,
                          company_id=1, company_name="测试公司",
                          month="2026-04", confirmed_month="2026-06",
                          amount=Decimal("3000")):
        db.add(models.ArapRecord(
            entity_type=entity_type, entity_id=entity_id,
            entity_name="渠道1", company_id=company_id,
            company_name=company_name, game_id="G001", game_name="",
            month=month, confirmed_month=confirmed_month,
            settlement_amount=amount, locked_amount=amount,
            snapshot_at="2026-06-01 12:00:00",
        ))

    @pytest.mark.asyncio
    async def test_breakdown_returns_debit_by_month(self, db_session):
        """debit_items grouped by confirmed_month, sorted ASC."""
        from backend.services.snapshot_service import get_breakdown
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await self._seed_arap(db_session, confirmed_month="2026-06", amount=Decimal("3000"))
        await self._seed_arap(db_session, confirmed_month="2026-07", month="2026-05",
                               amount=Decimal("2000"))
        await db_session.commit()

        result = await get_breakdown(db_session, "channel", 1, 1)

        assert len(result["debit_items"]) == 2
        assert result["debit_items"][0] == {"confirmed_month": "2026-06", "amount": 3000.0}
        assert result["debit_items"][1] == {"confirmed_month": "2026-07", "amount": 2000.0}
        assert result["payment_items"] == []

    @pytest.mark.asyncio
    async def test_breakdown_includes_payment_history(self, db_session):
        """payment_items lists registered payments for the entity+company."""
        from backend.services.snapshot_service import get_breakdown
        from backend.services.payment_service import register_payment
        await _seed_company(db_session, company_id=1, name="测试公司")
        await _seed_channel_category(db_session, channel_id=1, name="渠道1")
        await self._seed_arap(db_session, amount=Decimal("5000"))
        await db_session.commit()

        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=3000.0, collection_month="2026-08",
            now="2026-08-01 10:00:00", note="测试备注",
        )

        result = await get_breakdown(db_session, "channel", 1, 1)

        assert len(result["payment_items"]) == 1
        p = result["payment_items"][0]
        assert p["entity_type"] == "channel"
        assert p["entity_id"] == 1
        assert p["company_id"] == 1
        assert p["amount"] == 3000.0
        assert p["collection_month"] == "2026-08"
        assert p["note"] == "测试备注"


# ── 4. Helper functions ──

class TestHelpers:

    @pytest.mark.asyncio
    async def test_resolve_entity_name_channel(self, db_session):
        await _seed_channel_category(db_session, channel_id=5, name="华为渠道")
        await db_session.commit()
        name = await _resolve_entity_name(db_session, "channel", 5)
        assert name == "华为渠道"

    @pytest.mark.asyncio
    async def test_resolve_entity_name_publisher(self, db_session):
        await _seed_publisher(db_session, publisher_id=3, name="成都研发")
        await db_session.commit()
        name = await _resolve_entity_name(db_session, "publisher", 3)
        assert name == "成都研发"

    @pytest.mark.asyncio
    async def test_resolve_company_name(self, db_session):
        await _seed_company(db_session, company_id=2, name="示例科技")
        await db_session.commit()
        name = await _resolve_company_name(db_session, 2)
        assert name == "示例科技"

    @pytest.mark.asyncio
    async def test_resolve_company_name_none(self, db_session):
        name = await _resolve_company_name(db_session, None)
        assert name == "未关联"


# ═══════════════════════════════════════════════
# Round 3: End-to-end integration
# ═══════════════════════════════════════════════

class TestEndToEnd:

    @pytest.mark.asyncio
    async def test_lock_snapshot_pivot_flow(self, db_session):
        db = db_session
        await _seed_game(db, game_id="G001")
        await _seed_company(db, company_id=1, name="测试公司")
        await _seed_company_game_mapping(db, game_id="G001")
        await _seed_channel_category(db, channel_id=1, name="端到端渠道")
        await _seed_raw_settlement(db, channel_id=1, month="2026-06")
        await _seed_channel_lock(db, channel_id=1, month="2026-06", locked_amount=Decimal("8888"))
        await db.commit()
        result = await snapshot_from_locks(db, "2026-06-10 12:00:00", "2026-06")
        assert result["inserted"] == 1
        pivot = await get_pivot(db, "channel", "2026-06", "2026-06")
        assert len(pivot["rows"]) == 1
        assert pivot["rows"][0]["cells"]["2026-06"] == 8888.0
        assert pivot["rows"][0]["entity_name"] == "端到端渠道"
        assert pivot["rows"][0]["company_name"] == "测试公司"

    @pytest.mark.asyncio
    async def test_incremental_snapshot_flow(self, db_session):
        db = db_session
        await _seed_game(db, game_id="G001")
        await _seed_company(db, company_id=1, name="测试公司")
        await _seed_company_game_mapping(db, game_id="G001")
        await _seed_channel_category(db, channel_id=1, name="增量渠道")
        await _seed_raw_settlement(db, channel_id=1, month="2026-06")
        await _seed_channel_lock(db, channel_id=1, month="2026-06", locked_amount=Decimal("3000"))
        await db.commit()
        r1 = await snapshot_from_locks(db, "2026-06-01 12:00:00", "2026-06")
        assert r1["inserted"] == 1

        await _seed_game(db, game_id="G002", name="Game2")
        await _seed_company_game_mapping(db, game_id="G002")
        await _seed_raw_settlement(db, channel_id=1, game_id="G002", month="2026-06", channel_name="增量渠道", game_name="Game2")
        await _seed_channel_lock(db, channel_id=1, game_id="G002", month="2026-06", locked_amount=Decimal("5000"))
        await db.commit()
        r2 = await snapshot_from_locks(db, "2026-06-02 12:00:00", "2026-06")
        assert r2["inserted"] == 1
        assert r2["channel_locks_processed"] == 1

        pivot = await get_pivot(db, "channel", "2026-06", "2026-06")
        assert len(pivot["rows"]) == 1
        assert pivot["rows"][0]["cells"]["2026-06"] == 8000.0
