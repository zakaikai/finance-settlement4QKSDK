# -*- coding: utf-8 -*-
"""QuickSDK third-party data import API.

Conditionally registered in main.py — only when QK_KEYS or QK_OPEN_ID is configured.
All QuickSDK config (keys, product→game mapping) lives in env vars, not in the database.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services import template_import, quicksdk_service

router = APIRouter(prefix="/api/quicksdk", tags=["QuickSDK"])


# ── Request/Response models ──

class FetchRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    product_code: str | None = None
    game_id: str
    key_index: int = 0


class ConfirmRequest(BaseModel):
    rows: list[dict]
    overwrite: bool = False


class BatchImportRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    key_index: int = 0
    overwrite: bool = False


class PreviewTotalRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    product_code: str
    key_index: int = 0


# ── Endpoints ──

@router.get("/status")
async def quicksdk_status():
    """Check if QuickSDK integration is available."""
    try:
        quicksdk_service._load_keys_raw()
        return {"available": True, "reason": None}
    except RuntimeError:
        return {"available": False, "reason": "QuickSDK credentials not configured"}


@router.get("/keys")
async def list_keys():
    """List configured AppKey labels (no secrets)."""
    try:
        keys = quicksdk_service.get_key_labels()
    except RuntimeError:
        keys = []
    return {"keys": keys}


@router.get("/products")
async def list_products(key_index: int = 0):
    """Fetch product list from QuickSDK."""
    try:
        products = await quicksdk_service.fetch_product_list(key_index)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"products": products}


@router.post("/preview-total")
async def preview_total(req: PreviewTotalRequest):
    """Fetch aggregate summary for a product in the selected date range."""
    if not req.product_code:
        raise HTTPException(status_code=400, detail="product_code is required")

    try:
        summary = await quicksdk_service.preview_total(
            start_date=req.start_date or "",
            end_date=req.end_date or "",
            product_code=req.product_code,
            key_index=req.key_index,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return summary


@router.post("/fetch")
async def fetch_data(req: FetchRequest, db: AsyncSession = Depends(get_db)):
    """Fetch daily report from QuickSDK and return preview with validation."""
    if not req.game_id:
        raise HTTPException(status_code=400, detail="game_id is required")

    product_code = req.product_code or ""
    if not product_code:
        raise HTTPException(status_code=400, detail="product_code is required")

    try:
        rows = await quicksdk_service.fetch_day_report(
            start_date=req.start_date or "",
            end_date=req.end_date or "",
            product_code=product_code,
            game_id=req.game_id,
            key_index=req.key_index,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not rows:
        return {
            "total_rows": 0, "preview_rows": [], "all_rows": [],
            "errors": [], "has_conflict": False, "conflict_count": 0,
        }

    fk_errors = await quicksdk_service.resolve_qk_foreign_keys(db, rows)
    val_result = await template_import.validate_values("raw_transactions", rows)
    all_errors = fk_errors + val_result["errors"]
    conflict_result = await template_import.check_conflicts(db, "raw_transactions", rows)

    return {
        "total_rows": len(rows),
        "preview_rows": rows[:5],
        "all_rows": rows,
        "errors": all_errors,
        "has_conflict": conflict_result["has_conflict"],
        "conflict_count": conflict_result["conflict_count"],
    }


@router.post("/batch-import")
async def batch_import(req: BatchImportRequest, db: AsyncSession = Depends(get_db)):
    """Fetch all mapped products and import their dayReport data at once."""
    try:
        batch_result = await quicksdk_service.batch_import_all(
            start_date=req.start_date or "",
            end_date=req.end_date or "",
            key_index=req.key_index,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    rows = batch_result["rows"]
    if not rows:
        return {
            "success": True,
            "imported": 0,
            "per_game": batch_result["per_game"],
            "errors": batch_result["errors"],
        }

    # FK resolution and validation
    fk_errors = await quicksdk_service.resolve_qk_foreign_keys(db, rows)
    if fk_errors:
        raise HTTPException(status_code=400, detail={"errors": fk_errors, "per_game": batch_result["per_game"]})

    val_result = await template_import.validate_values("raw_transactions", rows)
    if val_result["errors"]:
        raise HTTPException(status_code=400, detail={"errors": val_result["errors"], "per_game": batch_result["per_game"]})

    import_result = await template_import.import_data(db, "raw_transactions", rows, req.overwrite)

    return {
        "success": True,
        "imported": import_result["imported"],
        "per_game": batch_result["per_game"],
        "errors": batch_result["errors"],
    }


@router.post("/confirm")
async def confirm_import(req: ConfirmRequest, db: AsyncSession = Depends(get_db)):
    """Confirm QuickSDK data import after user review."""
    rows = req.rows
    if not rows:
        raise HTTPException(status_code=400, detail="No rows to import")

    fk_errors = await quicksdk_service.resolve_qk_foreign_keys(db, rows)
    if fk_errors:
        raise HTTPException(status_code=400, detail={"errors": fk_errors})

    val_result = await template_import.validate_values("raw_transactions", rows)
    if val_result["errors"]:
        raise HTTPException(status_code=400, detail={"errors": val_result["errors"]})

    import_result = await template_import.import_data(db, "raw_transactions", rows, req.overwrite)
    return {"success": True, "imported": import_result["imported"]}
