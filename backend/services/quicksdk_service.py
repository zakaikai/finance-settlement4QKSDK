# -*- coding: utf-8 -*-
"""QuickSDK third-party API client.

Fetches daily report data and maps to settlement import format.
Supports multiple AppKey configurations via QK_KEYS JSON env var.
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models

# ── Aggregate channel names to skip ──
_AGGREGATE_CHANNELS = {"全部渠道"}


def _sign(params: dict, open_key: str) -> str:
    """Generate MD5 signature for QuickSDK API request."""
    filtered = {k: v for k, v in params.items() if k != "sign" and v is not None and v != ""}
    sorted_keys = sorted(filtered.keys())
    raw = "&".join(f"{k}={filtered[k]}" for k in sorted_keys)
    raw += "&" + open_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Key management ──

def _load_keys_raw() -> list[dict]:
    raw = os.environ.get("QK_KEYS", "")
    if raw:
        try:
            keys = json.loads(raw)
            if isinstance(keys, list) and keys:
                return keys
        except json.JSONDecodeError:
            pass
    # Fallback to legacy single-key config
    open_id = os.environ.get("QK_OPEN_ID", "")
    open_key = os.environ.get("QK_OPEN_KEY", "")
    base_url = os.environ.get("QK_BASE_URL", "https://www.quicksdk.com")
    if open_id and open_key:
        return [{"label": "默认", "openId": open_id, "openKey": open_key, "baseUrl": base_url}]
    return []


def get_key_labels() -> list[dict]:
    """Return key list without secrets for frontend display."""
    return [{"index": i, "label": k.get("label", f"Key{i+1}")} for i, k in enumerate(_load_keys_raw())]


def _get_key(key_index: int = 0) -> dict:
    keys = _load_keys_raw()
    if not keys:
        raise RuntimeError("QuickSDK credentials not configured")
    if key_index < 0 or key_index >= len(keys):
        raise RuntimeError(f"Invalid key_index: {key_index}")
    return keys[key_index]


def _load_product_map() -> dict[str, str]:
    """Load productCode → game_id mapping from config."""
    raw = os.environ.get("QK_PRODUCT_MAP", "")
    if raw:
        try:
            mapping = json.loads(raw)
            if isinstance(mapping, list):
                return {m["productCode"]: m["game_id"] for m in mapping if m.get("productCode") and m.get("game_id")}
        except json.JSONDecodeError:
            pass
    return {}


# ── API helpers ──

async def _post_api(path: str, params: dict, key_index: int = 0, timeout: int = 30) -> dict:
    key = _get_key(key_index)
    base_url = key.get("baseUrl", "https://www.quicksdk.com")
    params["openId"] = key["openId"]
    params["time"] = int(time.time())
    params["sign"] = _sign(params, key["openKey"])

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}{path}", data=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise RuntimeError(f"QuickSDK {path} request timed out")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"QuickSDK API returned HTTP {e.response.status_code}: {e.response.text[:500]}")
    except Exception as e:
        raise RuntimeError(f"QuickSDK {path} request failed: {e}")


# ── Product list ──

async def fetch_product_list(key_index: int = 0) -> list[dict]:
    body = await _post_api("/open/productList", {}, key_index)
    if body.get("status") is False:
        raise RuntimeError(f"QuickSDK productList failed: {body.get('message', 'unknown error')}")
    return body.get("data", [])


# ── Day report fetch ──

async def fetch_day_report(
    start_date: str,
    end_date: str,
    product_code: str,
    game_id: str,
    key_index: int = 0,
) -> list[dict]:
    """Fetch daily report and map to import rows. Skips aggregate channels."""
    if not product_code:
        raise RuntimeError("product_code is required")

    params: dict[str, Any] = {"productCode": product_code, "usermb": 0}

    if start_date:
        params["bTime"] = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    else:
        params["bTime"] = int((datetime.now() - timedelta(days=7)).timestamp())

    if end_date:
        params["eTime"] = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    body = await _post_api("/open/dayReport", params, key_index)

    code = body.get("code", 0)
    if code is not None and code != 0:
        raise RuntimeError(f"QuickSDK API error (code={code}): {body.get('msg', 'unknown error')}")

    data = body.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError("QuickSDK API returned unexpected data format")

    rows: list[dict] = []
    for item in data:
        channel_name = item.get("channelName", "").strip()
        if not channel_name or channel_name in _AGGREGATE_CHANNELS:
            continue

        date_str = item.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            record_date = dt.date()
            month = dt.strftime("%Y-%m")
        except (ValueError, TypeError):
            continue

        try:
            amount = Decimal(str(item.get("allPay", 0)))
        except Exception:
            continue

        if amount <= 0:
            continue

        rows.append({
            "backend_channel_name": channel_name,
            "sub_channel_name": "",
            "game_id": game_id,
            "amount": amount,
            "record_date": record_date,
            "month": month,
            "direction": "income",
        })

    return rows


# ── Total preview ──

async def preview_total(
    start_date: str,
    end_date: str,
    product_code: str,
    key_index: int = 0,
) -> dict:
    """Fetch dayReport and return aggregate summary without full row data."""
    rows = await fetch_day_report(start_date, end_date, product_code, "", key_index)

    channels: set[str] = set()
    total_amount = Decimal("0")
    date_min = None
    date_max = None

    for r in rows:
        total_amount += r["amount"]
        channels.add(r["backend_channel_name"])
        d = r["record_date"]
        if date_min is None or d < date_min:
            date_min = d
        if date_max is None or d > date_max:
            date_max = d

    return {
        "total_rows": len(rows),
        "total_amount": float(total_amount),
        "channel_count": len(channels),
        "channels": sorted(channels),
        "date_min": str(date_min) if date_min else None,
        "date_max": str(date_max) if date_max else None,
    }


# ── Batch import ──

async def batch_import_all(
    start_date: str,
    end_date: str,
    key_index: int = 0,
) -> dict:
    """Fetch all mapped products and return consolidated rows for import."""
    product_map = _load_product_map()
    if not product_map:
        raise RuntimeError("No product mapping configured (QK_PRODUCT_MAP)")

    all_rows: list[dict] = []
    per_game: dict[str, dict] = {}
    errors: list[str] = []
    total_fetched = 0

    for i, (product_code, game_id) in enumerate(product_map.items()):
        if i > 0:
            await asyncio.sleep(0.1)  # rate limit: ~600 req/min

        try:
            rows = await fetch_day_report(start_date, end_date, product_code, game_id, key_index)
        except RuntimeError as e:
            errors.append(f"productCode={product_code}: {e}")
            continue

        total_fetched += 1
        if rows:
            all_rows.extend(rows)
            per_game[game_id] = {
                "game_id": game_id,
                "product_code": product_code,
                "rows": len(rows),
                "total_amount": float(sum(r["amount"] for r in rows)),
            }

    return {
        "products_checked": len(product_map),
        "products_fetched": total_fetched,
        "total_rows": len(all_rows),
        "rows": all_rows,
        "per_game": list(per_game.values()),
        "errors": errors,
    }


# ── FK resolution ──

async def resolve_qk_foreign_keys(session: AsyncSession, rows: list[dict]) -> list[dict]:
    """Resolve FK references for QuickSDK-imported rows."""
    errors: list[dict] = []

    for ri, record in enumerate(rows):
        row_num = ri + 2

        bk_name = record.get("backend_channel_name", "")
        stmt = select(models.BackendChannel.backend_channel_id).where(
            models.BackendChannel.backend_channel_name == bk_name
        )
        result = await session.execute(stmt)
        bk_id = result.scalar_one_or_none()

        if bk_id is None:
            errors.append({"row": row_num, "error": f"Backend channel '{bk_name}' not found"})
            continue

        record["backend_channel_id"] = bk_id

        sub_stmt = select(models.SubChannel.sub_channel_id).where(
            models.SubChannel.backend_channel_id == bk_id
        ).order_by(models.SubChannel.sub_channel_id).limit(1)
        sub_result = await session.execute(sub_stmt)
        sub_id = sub_result.scalar_one_or_none()

        if sub_id is None:
            errors.append({"row": row_num, "error": f"No sub-channel found under '{bk_name}'"})
            continue

        record["sub_channel_id"] = sub_id

        game_id = record.get("game_id")
        if game_id:
            game_stmt = select(models.Game.game_id).where(models.Game.game_id == game_id)
            game_result = await session.execute(game_stmt)
            if game_result.scalar_one_or_none() is None:
                errors.append({"row": row_num, "error": f"Game '{game_id}' not found"})

    return errors
