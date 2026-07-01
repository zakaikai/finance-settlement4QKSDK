"""Tests for payment_service — open items query, FIFO payment registration."""
import pytest
from decimal import Decimal

from backend import models
from backend.services.payment_service import get_open_items, register_payment


# ═══════════════════════════════════════════════════════════════
#  get_open_items
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_open_items_empty_when_no_arap_records(db_session):
    """Empty list when no ARAP records exist."""
    items = await get_open_items(db_session)
    assert items == []


@pytest.mark.asyncio
async def test_open_items_uses_settlement_amount_when_no_payments(db_session):
    """Each ARAP record's open_balance equals its settlement_amount when unpaid."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"))

    items = await get_open_items(db_session, entity_type="channel")

    assert len(items) == 1
    assert items[0]["open_balance"] == 5000.0
    assert items[0]["entity_type"] == "channel"
    assert items[0]["entity_id"] == 1
    assert items[0]["month"] == "2026-04"


@pytest.mark.asyncio
async def test_open_items_deducts_paid_amount(db_session):
    """open_balance = settlement_amount - SUM(allocated)."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    arap = await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                            month="2026-04", confirmed_month="2026-05",
                            settlement_amount=Decimal("5000.00"))
    await _seed_payment(db_session, entity_type="channel", entity_id=1, company_id=1,
                        amount=Decimal("2000.00"), collection_month="2026-06",
                        allocations=[(arap.id, Decimal("2000.00"))])

    items = await get_open_items(db_session, entity_type="channel")

    assert len(items) == 1
    assert items[0]["open_balance"] == 3000.0


@pytest.mark.asyncio
async def test_open_items_excludes_fully_paid(db_session):
    """Items with open_balance <= 0.005 are excluded."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    arap = await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                            month="2026-04", confirmed_month="2026-05",
                            settlement_amount=Decimal("5000.00"))
    await _seed_payment(db_session, entity_type="channel", entity_id=1, company_id=1,
                        amount=Decimal("5000.00"), collection_month="2026-06",
                        allocations=[(arap.id, Decimal("5000.00"))])

    items = await get_open_items(db_session, entity_type="channel")

    assert len(items) == 0


@pytest.mark.asyncio
async def test_open_items_sorted_by_month_asc(db_session):
    """FIFO: items sorted by month ASC regardless of insertion order."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-06", confirmed_month="2026-07",
                     settlement_amount=Decimal("3000.00"))
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("1000.00"))
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-05", confirmed_month="2026-06",
                     settlement_amount=Decimal("2000.00"))

    items = await get_open_items(db_session, entity_type="channel")

    months = [i["month"] for i in items]
    assert months == ["2026-04", "2026-05", "2026-06"]


@pytest.mark.asyncio
async def test_open_items_filters_by_entity_type(db_session):
    """Only return items matching the requested entity_type."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_publisher(db_session, publisher_id=1, name="测试研发")
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"))
    await _seed_arap(db_session, entity_type="publisher", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("3000.00"))

    ch_items = await get_open_items(db_session, entity_type="channel")
    pub_items = await get_open_items(db_session, entity_type="publisher")

    assert len(ch_items) == 1
    assert ch_items[0]["entity_type"] == "channel"
    assert len(pub_items) == 1
    assert pub_items[0]["entity_type"] == "publisher"


# ═══════════════════════════════════════════════════════════════
#  register_payment
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_payment_fifo_splits_across_months(db_session):
    """Payment splits across multiple months via FIFO."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("3000.00"), game_id="G001")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-05", confirmed_month="2026-06",
                     settlement_amount=Decimal("3000.00"), game_id="G002")

    result = await register_payment(
        db_session, entity_type="channel", entity_id=1, company_id=1,
        amount=4000.0, collection_month="2026-07",
        now="2026-07-01 10:00:00",
    )

    assert result["amount"] == 4000.0
    assert result["collection_month"] == "2026-07"
    assert len(result["allocations"]) == 2
    assert result["allocations"][0]["month"] == "2026-04"
    assert result["allocations"][0]["allocated"] == 3000.0
    assert result["allocations"][1]["month"] == "2026-05"
    assert result["allocations"][1]["allocated"] == 1000.0


@pytest.mark.asyncio
async def test_register_payment_exact_match_single_item(db_session):
    """Payment that exactly matches one open item creates one allocation."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"), game_id="G001")

    result = await register_payment(
        db_session, entity_type="channel", entity_id=1, company_id=1,
        amount=5000.0, collection_month="2026-06",
        now="2026-06-01 10:00:00",
    )

    assert len(result["allocations"]) == 1
    assert result["allocations"][0]["allocated"] == 5000.0

    items = await get_open_items(db_session, entity_type="channel")
    assert len(items) == 0


@pytest.mark.asyncio
async def test_register_payment_sequential_transaction_no(db_session):
    """Transaction numbers are sequential within the same day."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("10000.00"), game_id="G001")

    r1 = await register_payment(
        db_session, entity_type="channel", entity_id=1, company_id=1,
        amount=3000.0, collection_month="2026-06",
        now="2026-06-15 10:00:00",
    )
    r2 = await register_payment(
        db_session, entity_type="channel", entity_id=1, company_id=1,
        amount=2000.0, collection_month="2026-06",
        now="2026-06-15 11:00:00",
    )

    assert r1["transaction_no"] != r2["transaction_no"]
    assert r1["transaction_no"].startswith("RCV-20260615-")
    assert r2["transaction_no"].startswith("RCV-20260615-")
    assert r1["transaction_no"].endswith("001")
    assert r2["transaction_no"].endswith("002")


@pytest.mark.asyncio
async def test_register_payment_publisher_uses_pmt_prefix(db_session):
    """Publisher payments use PMT- prefix."""
    await _seed_publisher(db_session, publisher_id=1, name="测试研发")
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="publisher", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"), game_id="G001")

    result = await register_payment(
        db_session, entity_type="publisher", entity_id=1, company_id=1,
        amount=5000.0, collection_month="2026-06",
        now="2026-06-15 10:00:00",
    )

    assert result["transaction_no"].startswith("PMT-")


@pytest.mark.asyncio
async def test_register_payment_rejects_zero_amount(db_session):
    """Zero or negative amount raises ValueError."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"))

    with pytest.raises(ValueError, match="金额必须大于 0"):
        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=0, collection_month="2026-06",
        )


@pytest.mark.asyncio
async def test_register_payment_rejects_when_no_open_items(db_session):
    """No matching open items raises ValueError."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")

    with pytest.raises(ValueError, match="未找到"):
        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=1000.0, collection_month="2026-06",
        )


@pytest.mark.asyncio
async def test_register_payment_rejects_amount_exceeding_open_balance(db_session):
    """Amount > total open balance raises ValueError."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("1000.00"))

    with pytest.raises(ValueError, match="超过未结总额"):
        await register_payment(
            db_session, entity_type="channel", entity_id=1, company_id=1,
            amount=2000.0, collection_month="2026-06",
        )


@pytest.mark.asyncio
async def test_register_payment_stores_collection_month(db_session):
    """collection_month is persisted correctly."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                     month="2026-04", confirmed_month="2026-05",
                     settlement_amount=Decimal("5000.00"))

    result = await register_payment(
        db_session, entity_type="channel", entity_id=1, company_id=1,
        amount=5000.0, collection_month="2026-08",
        now="2026-08-10 10:00:00",
    )

    assert result["collection_month"] == "2026-08"


# ═══════════════════════════════════════════════════════════════
#  delete_payment
# ═══════════════════════════════════════════════════════════════

from backend.services.payment_service import delete_payment


@pytest.mark.asyncio
async def test_delete_payment_success(db_session):
    """Deleting a payment removes both PaymentRecord and its PaymentAllocations."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    arap = await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                             month="2026-04", confirmed_month="2026-05",
                             settlement_amount=Decimal("5000.00"))
    pmt = await _seed_payment(db_session, entity_type="channel", entity_id=1, company_id=1,
                               amount=Decimal("2000.00"), collection_month="2026-06",
                               allocations=[(arap.id, Decimal("2000.00"))])

    result = await delete_payment(db_session, pmt.id)

    assert result["success"] is True
    assert result["deleted_allocations"] == 1

    # Verify records are gone
    from sqlalchemy import select as sa_select
    pmt_check = (await db_session.execute(
        sa_select(models.PaymentRecord).where(models.PaymentRecord.id == pmt.id)
    )).scalar_one_or_none()
    assert pmt_check is None

    alloc_check = (await db_session.execute(
        sa_select(models.PaymentAllocation).where(models.PaymentAllocation.payment_id == pmt.id)
    )).scalars().all()
    assert len(alloc_check) == 0


@pytest.mark.asyncio
async def test_delete_payment_not_found(db_session):
    """Deleting a non-existent payment raises ValueError."""
    with pytest.raises(ValueError, match="不存在"):
        await delete_payment(db_session, 99999)


@pytest.mark.asyncio
async def test_delete_payment_restores_open_balance(db_session):
    """After deleting a payment, open_items reflect the restored balance."""
    await _seed_channel(db_session, name="测试渠道", channel_id=1)
    await _seed_company(db_session, company_id=1, name="测试公司")
    arap = await _seed_arap(db_session, entity_type="channel", entity_id=1, company_id=1,
                             month="2026-04", confirmed_month="2026-05",
                             settlement_amount=Decimal("5000.00"))
    pmt = await _seed_payment(db_session, entity_type="channel", entity_id=1, company_id=1,
                               amount=Decimal("5000.00"), collection_month="2026-06",
                               allocations=[(arap.id, Decimal("5000.00"))])

    # Before delete: fully paid, no open items
    items_before = await get_open_items(db_session, entity_type="channel")
    assert len(items_before) == 0

    await delete_payment(db_session, pmt.id)

    # After delete: balance restored
    items_after = await get_open_items(db_session, entity_type="channel")
    assert len(items_after) == 1
    assert items_after[0]["open_balance"] == 5000.0


# ═══════════════════════════════════════════════════════════════
#  Seed helpers
# ═══════════════════════════════════════════════════════════════


async def _seed_channel(db, name, channel_id):
    """Seed a ChannelCategory row if not exists."""
    from sqlalchemy import select as sa_select
    existing = (await db.execute(
        sa_select(models.ChannelCategory).where(
            models.ChannelCategory.channel_id == channel_id)
    )).scalar_one_or_none()
    if existing:
        return existing
    obj = models.ChannelCategory(channel_id=channel_id, channel_name=name)
    db.add(obj)
    await db.commit()
    return obj


async def _seed_publisher(db, publisher_id, name):
    """Seed a Publisher row if not exists."""
    from sqlalchemy import select as sa_select
    existing = (await db.execute(
        sa_select(models.Publisher).where(
            models.Publisher.publisher_id == publisher_id)
    )).scalar_one_or_none()
    if existing:
        return existing
    obj = models.Publisher(publisher_id=publisher_id, publisher_name=name)
    db.add(obj)
    await db.commit()
    return obj


async def _seed_company(db, company_id, name):
    """Seed a Company row if not exists."""
    from sqlalchemy import select as sa_select
    existing = (await db.execute(
        sa_select(models.Company).where(
            models.Company.company_id == company_id)
    )).scalar_one_or_none()
    if existing:
        return existing
    obj = models.Company(company_id=company_id, company_name=name)
    db.add(obj)
    await db.commit()
    return obj


async def _seed_arap(db, entity_type, entity_id, company_id, month,
                     confirmed_month, settlement_amount, game_id=""):
    """Seed an ArapRecord row and return it."""
    obj = models.ArapRecord(
        entity_type=entity_type, entity_id=entity_id,
        entity_name=f"{entity_type}_{entity_id}",
        company_id=company_id, company_name=f"company_{company_id}",
        game_id=game_id, game_name=game_id,
        month=month, confirmed_month=confirmed_month,
        settlement_amount=settlement_amount,
        snapshot_at="2026-01-01 00:00:00",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def _seed_payment(db, entity_type, entity_id, company_id, amount,
                        collection_month, allocations, transaction_no=None):
    """Seed a PaymentRecord with allocations."""
    import time
    if transaction_no is None:
        transaction_no = f"TEST-{int(time.time() * 1000)}"
    pmt = models.PaymentRecord(
        transaction_no=transaction_no,
        entity_type=entity_type, entity_id=entity_id,
        entity_name=f"{entity_type}_{entity_id}",
        company_id=company_id, company_name=f"company_{company_id}",
        amount=amount, collection_month=collection_month,
        created_at="2026-01-01 00:00:00",
    )
    db.add(pmt)
    await db.flush()
    for arap_id, alloc_amt in allocations:
        db.add(models.PaymentAllocation(
            payment_id=pmt.id, arap_id=arap_id,
            allocated_amount=alloc_amt,
        ))
    await db.commit()
    return pmt
