"""Bill template CRUD management."""
import os
import hashlib
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from fastapi.responses import FileResponse

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/bill-templates", tags=["对账模板"])

BILL_TPL_DIR = os.environ.get(
    "BILL_TPL_DIR",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "backend", "templates", "bills",
    ),
)
os.makedirs(BILL_TPL_DIR, exist_ok=True)

_ALLOWED_TYPES = ("income", "payment", "all")


def _tpl_dict(r):
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description or "",
        "bill_type": r.bill_type,
        "is_default": bool(r.is_default),
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _file_path(tpl_id: int, name: str) -> str:
    """Generate a deterministic file path for a template."""
    safe = hashlib.md5(name.encode()).hexdigest()[:8]
    return os.path.join(BILL_TPL_DIR, f"{tpl_id}_{safe}.xlsx")


@router.get("")
async def list_templates(
    bill_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    """List bill templates, optionally filtered by type."""
    stmt = select(models.BillTemplate).order_by(models.BillTemplate.is_default.desc(),
                                                  models.BillTemplate.updated_at.desc())
    if bill_type and bill_type in _ALLOWED_TYPES:
        stmt = stmt.where(
            (models.BillTemplate.bill_type == bill_type) |
            (models.BillTemplate.bill_type == "all")
        )
    rows = (await db.execute(stmt)).scalars().all()
    return {"data": [_tpl_dict(r) for r in rows]}


@router.post("")
async def create_template(
    name: str = Form(...),
    description: str = Form(""),
    bill_type: str = Form(...),
    is_default: str = Form("false"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new bill template."""
    if bill_type not in _ALLOWED_TYPES:
        raise HTTPException(400, f"无效模板类型: {bill_type}，可用: {', '.join(_ALLOWED_TYPES)}")

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "仅支持 .xlsx / .xls 文件")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_default_flag = is_default.lower() in ("true", "1")

    # If setting as default, clear other defaults of same type
    if is_default_flag:
        existing_defaults = (await db.execute(
            select(models.BillTemplate).where(
                models.BillTemplate.is_default == 1,
                models.BillTemplate.bill_type == bill_type,
            )
        )).scalars().all()
        for ed in existing_defaults:
            ed.is_default = 0

    record = models.BillTemplate(
        name=name,
        description=description,
        bill_type=bill_type,
        file_path="",  # temporary, will update after we know the id
        is_default=1 if is_default_flag else 0,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Save file with known id
    fpath = _file_path(record.id, name)
    content = await file.read()
    with open(fpath, "wb") as f:
        f.write(content)
    record.file_path = fpath
    await db.commit()

    return {"data": _tpl_dict(record)}


@router.put("/{tpl_id}")
async def update_template(
    tpl_id: int,
    body: schemas.BillTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update template metadata (name, description, bill_type, is_default)."""
    record = (await db.execute(
        select(models.BillTemplate).where(models.BillTemplate.id == tpl_id)
    )).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "模板不存在")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old_file = record.file_path

    if body.name is not None:
        record.name = body.name
    if body.description is not None:
        record.description = body.description
    if body.bill_type is not None:
        if body.bill_type not in _ALLOWED_TYPES:
            raise HTTPException(400, f"无效模板类型: {body.bill_type}")
        record.bill_type = body.bill_type
    if body.is_default is not None:
        if body.is_default:
            # Clear other defaults of same type
            existing = (await db.execute(
                select(models.BillTemplate).where(
                    models.BillTemplate.is_default == 1,
                    models.BillTemplate.bill_type == (body.bill_type or record.bill_type),
                    models.BillTemplate.id != tpl_id,
                )
            )).scalars().all()
            for ed in existing:
                ed.is_default = 0
        record.is_default = 1 if body.is_default else 0

    record.updated_at = now
    await db.commit()

    # If name changed, rename file
    if body.name is not None and old_file and os.path.exists(old_file):
        new_path = _file_path(record.id, body.name)
        if new_path != old_file:
            try:
                os.rename(old_file, new_path)
                record.file_path = new_path
                await db.commit()
            except OSError:
                pass

    await db.refresh(record)
    return {"data": _tpl_dict(record)}


@router.put("/{tpl_id}/file")
async def update_template_file(
    tpl_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Replace the template file without changing metadata."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "仅支持 .xlsx / .xls 文件")

    record = (await db.execute(
        select(models.BillTemplate).where(models.BillTemplate.id == tpl_id)
    )).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "模板不存在")

    content = await file.read()
    with open(record.file_path, "wb") as f:
        f.write(content)

    record.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.commit()
    return {"data": _tpl_dict(record)}


@router.delete("/{tpl_id}")
async def delete_template(
    tpl_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a bill template (removes file + DB record)."""
    record = (await db.execute(
        select(models.BillTemplate).where(models.BillTemplate.id == tpl_id)
    )).scalar_one_or_none()
    if not record:
        raise HTTPException(404, "模板不存在")

    # Remove file
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)

    await db.execute(delete(models.BillTemplate).where(models.BillTemplate.id == tpl_id))
    await db.commit()
    return {"data": {"id": tpl_id}}


@router.get("/{tpl_id}/download")
async def download_template(
    tpl_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download the template file."""
    record = (await db.execute(
        select(models.BillTemplate).where(models.BillTemplate.id == tpl_id)
    )).scalar_one_or_none()
    if not record or not record.file_path or not os.path.exists(record.file_path):
        raise HTTPException(404, "模板文件不存在")

    return FileResponse(
        record.file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{record.name}.xlsx",
    )
