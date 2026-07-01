import os
import shutil
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/memos", tags=["备忘录"])

ATTACH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "attachments")
os.makedirs(ATTACH_DIR, exist_ok=True)


def _memo_dict(r):
    return {
        "id": r.id,
        "title": r.title,
        "content": r.content or "",
        "party_type": r.party_type or "",
        "party_name": r.party_name or "",
        "attachment_name": r.attachment_name or "",
        "has_attachment": bool(r.attachment_path and os.path.exists(r.attachment_path)),
        "is_reminder": bool(r.is_reminder),
        "reminder_cycle": r.reminder_cycle or "none",
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@router.get("")
async def list_memos(is_reminder: str = None, db: AsyncSession = Depends(get_db)):
    q = select(models.Memo).order_by(models.Memo.updated_at.desc())
    if is_reminder is not None:
        q = q.where(models.Memo.is_reminder == (1 if is_reminder.lower() in ("true", "1") else 0))
    rows = (await db.execute(q)).scalars().all()
    return {"data": [_memo_dict(r) for r in rows]}


@router.get("/{memo_id}")
async def get_memo(memo_id: int, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(models.Memo).where(models.Memo.id == memo_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "备忘录不存在")
    return {"data": _memo_dict(r)}


@router.post("")
async def create_memo(
    title: str = Form(...),
    content: str = Form(""),
    party_type: str = Form(None),
    party_name: str = Form(None),
    is_reminder: str = Form("false"),
    reminder_cycle: str = Form("none"),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    attachment_name = ""
    attachment_path = ""
    if file and file.filename:
        attachment_name = file.filename
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        attachment_path = os.path.join(ATTACH_DIR, filename)
        with open(attachment_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    record = models.Memo(
        title=title,
        content=content or "",
        party_type=party_type or "",
        party_name=party_name or "",
        attachment_name=attachment_name,
        attachment_path=attachment_path,
        is_reminder=1 if is_reminder and is_reminder.lower() in ("true", "1") else 0,
        reminder_cycle=reminder_cycle or "none",
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"data": _memo_dict(record)}


@router.put("/{memo_id}")
async def update_memo(
    memo_id: int,
    title: str = Form(None),
    content: str = Form(None),
    party_type: str = Form(None),
    party_name: str = Form(None),
    is_reminder: str = Form(None),
    reminder_cycle: str = Form(None),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    record = (await db.execute(select(models.Memo).where(models.Memo.id == memo_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "备忘录不存在")

    if title is not None:
        record.title = title
    if content is not None:
        record.content = content
    if party_type is not None:
        record.party_type = party_type
    if party_name is not None:
        record.party_name = party_name
    if is_reminder is not None:
        record.is_reminder = 1 if is_reminder.lower() in ("true", "1") else 0
    if reminder_cycle is not None:
        record.reminder_cycle = reminder_cycle

    if file and file.filename:
        # Remove old attachment
        if record.attachment_path and os.path.exists(record.attachment_path):
            os.remove(record.attachment_path)
        record.attachment_name = file.filename
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        record.attachment_path = os.path.join(ATTACH_DIR, filename)
        with open(record.attachment_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    record.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.commit()
    await db.refresh(record)
    return {"data": _memo_dict(record)}


@router.delete("/{memo_id}")
async def delete_memo(memo_id: int, db: AsyncSession = Depends(get_db)):
    record = (await db.execute(select(models.Memo).where(models.Memo.id == memo_id))).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "备忘录不存在")
    if record.attachment_path and os.path.exists(record.attachment_path):
        os.remove(record.attachment_path)
    await db.execute(delete(models.Memo).where(models.Memo.id == memo_id))
    await db.commit()
    return {"data": {"id": memo_id}}


@router.get("/{memo_id}/attachment")
async def download_attachment(memo_id: int, db: AsyncSession = Depends(get_db)):
    record = (await db.execute(select(models.Memo).where(models.Memo.id == memo_id))).scalar_one_or_none()
    if not record or not record.attachment_path or not os.path.exists(record.attachment_path):
        raise HTTPException(404, "附件不存在")
    from fastapi.responses import FileResponse
    return FileResponse(
        record.attachment_path,
        filename=record.attachment_name or os.path.basename(record.attachment_path),
    )
