from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/party-info", tags=["主体信息管理"])


@router.get("")
async def list_party_info(
    party_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(models.PartyInfo)
    if party_type:
        stmt = stmt.where(models.PartyInfo.party_type == party_type)
    rows = (await db.execute(stmt.order_by(models.PartyInfo.id))).scalars().all()
    return {"data": [{
        "id": r.id,
        "party_type": r.party_type,
        "name": r.name,
        "address": r.address,
        "phone": r.phone or "",
        "bank_name": r.bank_name,
        "bank_account": r.bank_account,
        "tax_id": r.tax_id,
        "notes": r.notes or "",
    } for r in rows]}


@router.post("")
async def create_party_info(
    body: schemas.PartyInfoCreate,
    db: AsyncSession = Depends(get_db),
):
    record = models.PartyInfo(**body.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"data": {"id": record.id}}


@router.put("/{party_id}")
async def update_party_info(
    party_id: int,
    body: schemas.PartyInfoCreate,
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(
        select(models.PartyInfo).where(models.PartyInfo.id == party_id)
    )).scalar_one_or_none()
    if not record:
        from fastapi import HTTPException
        raise HTTPException(404, "主体信息不存在")
    for key, val in body.model_dump().items():
        setattr(record, key, val)
    await db.commit()
    return {"data": {"id": party_id}}


@router.delete("/{party_id}")
async def delete_party_info(
    party_id: int,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(models.PartyInfo).where(models.PartyInfo.id == party_id))
    await db.commit()
    return {"data": {"id": party_id}}
