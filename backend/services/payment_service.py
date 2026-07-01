"""Payment registration service — open items query, FIFO allocation, payment tracking."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models


async def get_open_items(
    db: AsyncSession,
    entity_type: str | None = None,
) -> list[dict]:
    """Return open (unpaid) ARAP items with remaining balance.

    open_balance = settlement_amount - SUM(allocated_amount)
    Only items with open_balance > 0.005 are returned.
    Sorted by month ASC (FIFO order).
    """
    paid_sub = (
        select(
            models.PaymentAllocation.arap_id,
            func.coalesce(func.sum(models.PaymentAllocation.allocated_amount), 0).label("paid"),
        )
        .group_by(models.PaymentAllocation.arap_id)
        .subquery()
    )

    stmt = (
        select(
            models.ArapRecord,
            (models.ArapRecord.settlement_amount - func.coalesce(paid_sub.c.paid, 0)).label("open_balance"),
        )
        .outerjoin(paid_sub, models.ArapRecord.id == paid_sub.c.arap_id)
        .order_by(models.ArapRecord.month.asc(), models.ArapRecord.entity_name.asc())
    )

    if entity_type:
        stmt = stmt.where(models.ArapRecord.entity_type == entity_type)

    rows = (await db.execute(stmt)).all()

    result = []
    for arap, open_bal in rows:
        bal = float(open_bal)
        if bal <= 0.005:
            continue
        result.append({
            "arap_id": arap.id,
            "entity_type": arap.entity_type,
            "entity_id": arap.entity_id,
            "entity_name": arap.entity_name,
            "company_id": arap.company_id,
            "company_name": arap.company_name,
            "game_id": arap.game_id,
            "month": arap.month,
            "confirmed_month": arap.confirmed_month,
            "open_balance": round(bal, 2),
        })

    return result


async def register_payment(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    company_id: int,
    amount: float,
    collection_month: str,
    now: str | None = None,
    note: str | None = None,
) -> dict:
    """Register a payment and allocate via FIFO against open items.

    Returns {"transaction_no": ..., "allocations": [...]}.
    Raises ValueError if amount <= 0 or no open items to allocate.
    """
    if amount <= 0:
        raise ValueError("金额必须大于 0")

    if now is None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Fetch open items for this entity, sorted by month (FIFO)
    open_items = await get_open_items(db, entity_type=entity_type)
    candidates = [
        i for i in open_items
        if i["entity_type"] == entity_type
        and i["entity_id"] == entity_id
        and i["company_id"] == company_id
    ]

    if not candidates:
        raise ValueError(f"未找到 {entity_type} entity_id={entity_id} company_id={company_id} 的未结项")

    # 2. FIFO allocate
    remaining = Decimal(str(amount))
    allocations = []
    for item in candidates:
        if remaining <= Decimal("0.005"):
            break
        open_bal = Decimal(str(item["open_balance"]))
        alloc = min(remaining, open_bal)
        allocations.append({
            "arap_id": item["arap_id"],
            "game_id": item["game_id"],
            "month": item["month"],
            "open_balance": float(open_bal),
            "allocated": float(alloc),
        })
        remaining -= alloc

    if remaining > Decimal("0.005"):
        raise ValueError(
            f"金额 {amount} 超过未结总额，剩余 {float(remaining):.2f} 无法分配"
        )

    # 3. Resolve names
    ename = ""
    cname = ""
    if entity_type == "channel":
        ename = await _resolve_channel_name(db, entity_id)
    else:
        ename = await _resolve_publisher_name(db, entity_id)
    cname = await _resolve_company_name(db, company_id)

    # 5. Generate transaction number
    prefix = "RCV" if entity_type == "channel" else "PMT"
    # Use 'now' parameter for deterministic date in tests
    date_part = datetime.strptime(now, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d") if now else datetime.now().strftime("%Y%m%d")
    count = (await db.execute(
        select(func.count()).select_from(models.PaymentRecord).where(
            models.PaymentRecord.transaction_no.like(f"{prefix}-{date_part}-%")
        )
    )).scalar() or 0
    transaction_no = f"{prefix}-{date_part}-{count + 1:03d}"

    # 6. Insert PaymentRecord
    payment = models.PaymentRecord(
        transaction_no=transaction_no,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=ename,
        company_id=company_id,
        company_name=cname,
        amount=Decimal(str(amount)).quantize(Decimal("0.01")),
        collection_month=collection_month,
        note=note,
        created_at=now,
    )
    db.add(payment)
    await db.flush()  # get payment.id

    # 7. Insert PaymentAllocations
    for alloc in allocations:
        if alloc["arap_id"] is None:
            continue
        db.add(models.PaymentAllocation(
            payment_id=payment.id,
            arap_id=alloc["arap_id"],
            allocated_amount=Decimal(str(alloc["allocated"])).quantize(Decimal("0.01")),
        ))

    await db.commit()

    return {
        "transaction_no": transaction_no,
        "amount": amount,
        "collection_month": collection_month,
        "allocations": [
            {k: v for k, v in a.items() if k != "arap_id"}
            for a in allocations
        ],
        "created_at": now,
    }


async def get_payment_history(
    db: AsyncSession,
    entity_type: str | None = None,
    entity_id: int | None = None,
    company_id: int | None = None,
    month_from: str | None = None,
    month_to: str | None = None,
) -> list[dict]:
    """Query payment records with optional filters."""
    stmt = select(models.PaymentRecord).order_by(models.PaymentRecord.created_at.desc())

    if entity_type:
        stmt = stmt.where(models.PaymentRecord.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(models.PaymentRecord.entity_id == entity_id)
    if company_id is not None:
        stmt = stmt.where(models.PaymentRecord.company_id == company_id)
    if month_from:
        stmt = stmt.where(models.PaymentRecord.collection_month >= month_from)
    if month_to:
        stmt = stmt.where(models.PaymentRecord.collection_month <= month_to)

    rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": r.id,
            "transaction_no": r.transaction_no,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "entity_name": r.entity_name,
            "company_id": r.company_id,
            "company_name": r.company_name,
            "amount": float(r.amount),
            "collection_month": r.collection_month,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def delete_payment(db: AsyncSession, payment_id: int) -> dict:
    """Delete a payment record and its allocations.

    Raises ValueError if payment not found.
    Returns {success: True, deleted_allocations: N}.
    """
    payment = (await db.execute(
        select(models.PaymentRecord).where(models.PaymentRecord.id == payment_id)
    )).scalar_one_or_none()
    if not payment:
        raise ValueError(f"付款记录 {payment_id} 不存在")

    # Count and delete allocations
    alloc_result = await db.execute(
        select(func.count()).select_from(models.PaymentAllocation).where(
            models.PaymentAllocation.payment_id == payment_id
        )
    )
    alloc_count = alloc_result.scalar() or 0

    await db.execute(
        delete(models.PaymentAllocation).where(
            models.PaymentAllocation.payment_id == payment_id
        )
    )

    await db.delete(payment)
    await db.commit()

    return {"success": True, "deleted_allocations": alloc_count}


# ── Internal helpers ──

async def _resolve_channel_name(db: AsyncSession, entity_id: int) -> str:
    row = (await db.execute(
        select(models.ChannelCategory.channel_name).where(
            models.ChannelCategory.channel_id == entity_id
        )
    )).scalar_one_or_none()
    return row or f"channel_{entity_id}"


async def _resolve_publisher_name(db: AsyncSession, entity_id: int) -> str:
    row = (await db.execute(
        select(models.Publisher.publisher_name).where(
            models.Publisher.publisher_id == entity_id
        )
    )).scalar_one_or_none()
    return row or f"publisher_{entity_id}"


async def _resolve_company_name(db: AsyncSession, company_id: int | None) -> str:
    if company_id is None:
        return ""
    row = (await db.execute(
        select(models.Company.company_name).where(
            models.Company.company_id == company_id
        )
    )).scalar_one_or_none()
    return row or f"company_{company_id}"
