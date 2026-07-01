"""OCR-related API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..database import get_db
from ..services.ocr_service import match_game_names, get_game_dictionary
from ..services.ocr.engine import run_ocr, bridge_health, start_bridge, stop_bridge, wait_bridge_ready

router = APIRouter(prefix="/api/ocr", tags=["OCR识别"])

COLUMN_TYPE_OPTIONS = [
    "game_name",
    "amount_vouchers",
    "amount_test",
    "amount_welfare",
    "amount_bad_debt",
    "amount_total",          # 月流水/充值总额（用于匹配消歧）
    "ratio",                 # 分成比例（用于匹配消歧）
    "settlement_amount",     # 结算金额（用于匹配消歧）
    "month",
    "ignore",
]

AMOUNT_COL_TYPES = {
    "amount_vouchers", "amount_test", "amount_welfare",
    "amount_bad_debt", "amount_total", "settlement_amount",
}


class OcrMatchRequest(BaseModel):
    channel_name: str
    table_data: list[list[str]]          # 2D table: rows × cols
    column_mapping: list[str]            # one type per column


class OcrMatchResponse(BaseModel):
    channel_name: str
    rows: list[dict]
    summary: dict


@router.get("/status")
async def ocr_status():
    """检查 OCR 桥接服务是否在线."""
    health = await bridge_health()
    return {"online": health is not None, "detail": health}


@router.post("/bridge/start")
async def ocr_bridge_start():
    """手动启动 OCR 桥接服务."""
    health = await bridge_health()
    if health:
        return {"status": "already_running", "detail": health}
    start_bridge()
    ready = await wait_bridge_ready()
    if ready:
        return {"status": "started"}
    raise HTTPException(500, "OCR 桥接服务启动超时（60秒），请检查 ocr_venv 环境")


@router.post("/bridge/stop")
async def ocr_bridge_stop():
    """手动停止 OCR 桥接服务，释放内存."""
    stop_bridge()
    return {"status": "stopped"}


@router.post("/parse")
async def ocr_parse(file: UploadFile = File(...)):
    """上传图片 → PaddleOCR 识别 → 返回文字块列表.

    Returns [{text, bbox: {x0,y0,x1,y1}, confidence}, …]
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "仅支持图片文件")
    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 20MB")
    try:
        words = await run_ocr(image_bytes)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"data": words}


@router.get("/dictionary")
async def ocr_dictionary(db: AsyncSession = Depends(get_db)):
    """Return all game names for OCR post-processing dictionary."""
    games = await get_game_dictionary(db)
    return {"data": games}


@router.post("/match")
async def ocr_match(body: OcrMatchRequest, db: AsyncSession = Depends(get_db)):
    """Match OCR table data against DB games.

    Multi-pass cascade:
      1. Game name fuzzy match → top-3
      2. Monthly amount consistency scoring
      3. Ratio / settlement amount tiebreaker
    """
    cols = body.column_mapping
    if len(set(cols) - {"ignore"}) == 0:
        raise HTTPException(400, "至少需要指定一列数据")
    if body.table_data and len(cols) != len(body.table_data[0]):
        raise HTTPException(400, "列映射数量与表格列数不匹配")

    n_cols = len(cols)
    game_col_idx = [i for i, t in enumerate(cols) if t == "game_name"]

    # Normalize table rows
    normalized = []
    for r in body.table_data:
        if len(r) < n_cols:
            normalized.append(r + [""] * (n_cols - len(r)))
        else:
            normalized.append(r[:n_cols])

    # Collect game name candidates + per-candidate context
    candidates = []
    seen = set()
    context_list = []

    for row in normalized:
        for idx in game_col_idx:
            v = row[idx].strip() if idx < len(row) else ""
            if v and v not in seen:
                seen.add(v)
                candidates.append(v)

                # Build context dict for multi-pass scoring
                ctx = {}
                total_amount = 0.0
                for i, t in enumerate(cols):
                    if t in AMOUNT_COL_TYPES and t not in ("amount_vouchers", "amount_test", "amount_welfare", "amount_bad_debt"):
                        val = _parse_num(row[i]) if i < len(row) else None
                        if t == "amount_total" and val is not None:
                            ctx["amount"] = val
                        elif t == "settlement_amount" and val is not None:
                            ctx["settlement_amount"] = val
                    elif t == "ratio":
                        val = _parse_num(row[i]) if i < len(row) else None
                        if val is not None:
                            ctx["ratio"] = val

                # If no explicit amount_total, sum deduction columns as fallback
                if "amount" not in ctx:
                    for i, t in enumerate(cols):
                        if t in ("amount_vouchers", "amount_test", "amount_welfare", "amount_bad_debt"):
                            val = _parse_num(row[i]) if i < len(row) else 0
                            total_amount += val or 0
                    if total_amount > 0:
                        ctx["amount"] = total_amount

                context_list.append(ctx if ctx else None)

    # Match against DB with context
    matches = await match_game_names(db, candidates, context_list if any(c for c in context_list) else None)

    # Build lookup
    match_map = {m["candidate"]: m for m in matches}

    # Build per-row results
    rows_out = []
    for row in normalized:
        cells = {}
        game_candidate = ""
        for i, t in enumerate(cols):
            val = row[i].strip() if i < len(row) else ""
            if t == "ignore":
                continue
            cells[t] = val
            if t == "game_name":
                game_candidate = val

        game_match = match_map.get(game_candidate)
        rows_out.append({"cells": cells, "game_match": game_match})

    # Summary
    statuses = [m["status"] for m in matches]
    summary = {
        "total": len(matches),
        "high": statuses.count("high"),
        "medium": statuses.count("medium"),
        "low": statuses.count("low"),
        "none": statuses.count("none"),
    }

    return {"channel_name": body.channel_name, "rows": rows_out, "summary": summary}


def _parse_num(v) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        return float(s)
    except (ValueError, TypeError):
        return None
