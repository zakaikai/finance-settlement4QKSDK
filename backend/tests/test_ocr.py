"""Tests for OCR service and API — dictionary, match_game_names, parse, endpoints."""
import io
import json
import pytest
import httpx
from unittest.mock import patch, MagicMock
from decimal import Decimal
from backend import models
from backend.database import get_db
from backend.main import app
from backend.services.ocr_service import get_game_dictionary, match_game_names
from backend.services.ocr import engine
from backend.services.ocr.engine import run_ocr, bridge_health, start_bridge, stop_bridge


# ── Slice 1+2: get_game_dictionary ──

@pytest.mark.asyncio
async def test_dictionary_empty_when_no_games(db_session):
    """空数据库时返回空列表."""
    result = await get_game_dictionary(db_session)
    assert result == []
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_dictionary_returns_all_games(db_session):
    """返回数据库中所有游戏的 game_id 和 game_name."""
    db_session.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.7")))
    db_session.add(models.Game(game_id="G002", game_name="和平精英", discount_rate=Decimal("0.7")))
    await db_session.commit()

    result = await get_game_dictionary(db_session)
    assert len(result) == 2
    names = {g["game_name"] for g in result}
    ids = {g["game_id"] for g in result}
    assert names == {"王者荣耀", "和平精英"}
    assert ids == {"G001", "G002"}


# ── Slice 3: match_game_names — exact match ──

@pytest.mark.asyncio
async def test_match_exact_name_returns_high_confidence(db_session):
    """精确匹配 → 100% 置信度，status high."""
    db_session.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.7")))
    await db_session.commit()

    results = await match_game_names(db_session, ["王者荣耀"])
    assert len(results) == 1
    r = results[0]
    assert r["candidate"] == "王者荣耀"
    assert r["matched_game_id"] == "G001"
    assert r["matched_game_name"] == "王者荣耀"
    assert r["confidence"] == 100.0
    assert r["status"] == "high"


@pytest.mark.asyncio
async def test_fuzzy_match_lower_confidence(db_session):
    """OCR 错字应得到较低置信度（<100），但仍匹配到正确游戏."""
    db_session.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.7")))
    db_session.add(models.Game(game_id="G002", game_name="和平精英", discount_rate=Decimal("0.7")))
    await db_session.commit()

    # Simulate OCR typo: 王者荣耀 → 王者荣罐
    results = await match_game_names(db_session, ["王者荣罐"])
    assert len(results) == 1
    r = results[0]
    assert r["matched_game_id"] == "G001"
    assert r["matched_game_name"] == "王者荣耀"
    assert 70 <= r["confidence"] < 100
    assert r["status"] in ("high", "medium")


@pytest.mark.asyncio
async def test_empty_name_returns_none_status(db_session):
    """空字符串/纯空格 → status none，无匹配."""
    db_session.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.7")))
    await db_session.commit()

    results = await match_game_names(db_session, ["", "   ", "王者荣耀"])
    assert len(results) == 3
    assert results[0]["status"] == "none"
    assert results[0]["matched_game_id"] is None
    assert results[0]["confidence"] == 0
    assert results[1]["status"] == "none"
    # Third one should still match
    assert results[2]["status"] == "high"


# ── Slice 6: POST /api/ocr/match — validation ──

def _make_client(db_session):
    """Create httpx.AsyncClient with get_db overridden and local IP."""
    async def override():
        yield db_session
    app.dependency_overrides[get_db] = override
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


def _clear_overrides():
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_match_rejects_all_ignore_columns(db_session):
    """全部 ignore 列 → 400."""
    async with _make_client(db_session) as client:
        r = await client.post("/api/ocr/match", json={
            "channel_name": "应用商店",
            "table_data": [["游戏A", "1000"]],
            "column_mapping": ["ignore", "ignore"],
        })
        assert r.status_code == 400, f"Got {r.status_code}: {r.text}"
    _clear_overrides()


@pytest.mark.asyncio
async def test_match_rejects_column_count_mismatch(db_session):
    """列映射长度 ≠ 表格列数 → 400."""
    async with _make_client(db_session) as client:
        r = await client.post("/api/ocr/match", json={
            "channel_name": "应用商店",
            "table_data": [["游戏A", "1000", "500"]],
            "column_mapping": ["game_name", "amount_total"],
        })
        assert r.status_code == 400, f"Got {r.status_code}: {r.text}"
    _clear_overrides()


@pytest.mark.asyncio
async def test_match_roundtrip_with_valid_data(db_session):
    """完整流程：上传表格数据 → 匹配成功 → 返回结构化结果."""
    db_session.add(models.Game(game_id="G001", game_name="王者荣耀", discount_rate=Decimal("0.7")))
    db_session.add(models.Game(game_id="G002", game_name="和平精英", discount_rate=Decimal("0.7")))
    await db_session.commit()

    async with _make_client(db_session) as client:
        r = await client.post("/api/ocr/match", json={
            "channel_name": "应用商店",
            "table_data": [
                ["王者荣耀", "10000", "8000"],
                ["和平精英", "5000", "4000"],
            ],
            "column_mapping": ["game_name", "amount_total", "settlement_amount"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["channel_name"] == "应用商店"
        assert len(data["rows"]) == 2
        assert data["summary"]["total"] == 2
        assert data["summary"]["high"] == 2
    _clear_overrides()


# ── Slice 9-11: POST /api/ocr/parse ──

@pytest.mark.asyncio
async def test_parse_rejects_non_image(db_session):
    """非图片 Content-Type → 400."""
    async with _make_client(db_session) as client:
        r = await client.post("/api/ocr/parse",
            files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")})
        assert r.status_code == 400
    _clear_overrides()


@pytest.mark.asyncio
async def test_parse_rejects_oversized_file(db_session):
    """超过 20MB → 400."""
    big = b"x" * (21 * 1024 * 1024)
    async with _make_client(db_session) as client:
        r = await client.post("/api/ocr/parse",
            files={"file": ("big.png", io.BytesIO(big), "image/png")})
        assert r.status_code == 400
    _clear_overrides()


@pytest.mark.asyncio
async def test_run_ocr_parses_response():
    """bridge 返回 200 → 正确解析 data 列表."""
    mock_post = MagicMock()
    mock_post.status_code = 200
    mock_post.json.return_value = {"data": [
        {"text": "王者荣耀", "bbox": {"x0": 10, "y0": 20, "x1": 100, "y1": 40}, "confidence": 99.5},
        {"text": "10000", "bbox": {"x0": 120, "y0": 20, "x1": 180, "y1": 40}, "confidence": 98.0},
    ]}
    with patch.object(engine._get_client(), "get", return_value=MagicMock(status_code=200, json=MagicMock(return_value={"status":"ok"}))):
        with patch.object(engine._get_client(), "post", return_value=mock_post):
            result = await run_ocr(b"fake-bytes")
            assert len(result) == 2
            assert result[0]["text"] == "王者荣耀"


@pytest.mark.asyncio
async def test_run_ocr_raises_when_bridge_offline():
    """bridge 未启动 → RuntimeError."""
    with patch.object(engine._get_client(), "get", side_effect=Exception("offline")):
        try:
            await run_ocr(b"bad-bytes")
            assert False
        except RuntimeError as e:
            assert "未启动" in str(e)


# ── Slice 13-14: bridge control API ──

@pytest.mark.asyncio
async def test_status_returns_online_when_bridge_up(db_session):
    """bridge 在线时 status 返回 online: true."""
    async with _make_client(db_session) as client:
        with patch.object(engine._get_client(), "get", return_value=MagicMock(
            status_code=200, json=MagicMock(return_value={"status": "ok", "model_loaded": True})
        )):
            r = await client.get("/api/ocr/status")
            assert r.status_code == 200
            assert r.json()["online"] is True
    _clear_overrides()


@pytest.mark.asyncio
async def test_status_returns_offline_when_bridge_down(db_session):
    """bridge 离线时 status 返回 online: false."""
    async with _make_client(db_session) as client:
        with patch.object(engine._get_client(), "get", side_effect=Exception("refused")):
            r = await client.get("/api/ocr/status")
            assert r.status_code == 200
            assert r.json()["online"] is False
    _clear_overrides()


@pytest.mark.asyncio
async def test_bridge_start_returns_already_running(db_session):
    """bridge 已在运行 → start 返回 already_running."""
    async with _make_client(db_session) as client:
        with patch("backend.routers.ocr.bridge_health", return_value={"status": "ok"}):
            r = await client.post("/api/ocr/bridge/start")
            assert r.status_code == 200
            assert r.json()["status"] == "already_running"
    _clear_overrides()
