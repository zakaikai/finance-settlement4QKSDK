"""Tests for dashboard service — ranking, trend, and aggregation queries."""
import pytest
from decimal import Decimal
from datetime import date
from backend import models
from backend.services.dashboard_service import query_ranking, query_trend_summary, query_level1_options, query_init, _month_range

_CURR = _month_range(1)[0]
_PREV = _month_range(2)[1]
_CURR_Y, _CURR_M = int(_CURR.split("-")[0]), int(_CURR.split("-")[1])
_PREV_Y, _PREV_M = int(_PREV.split("-")[0]), int(_PREV.split("-")[1])


async def _seed_rs(db, channel_id, channel_name, game_id, game_name, month, raw_revenue):
    """Helper: seed RawSettlement row."""
    rs = models.RawSettlement(
        channel_id=channel_id, channel_name=channel_name,
        game_id=game_id, game_name=game_name,
        month=month, raw_revenue=raw_revenue,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    db.add(rs)


@pytest.mark.asyncio
async def test_channel_ranking_returns_sorted_data(db_session):
    """query_ranking(channel, settlement_amount) 返回按结算金额降序排列."""
    game = models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.7"))
    db_session.add(game)
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _CURR, Decimal("10000"))
    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _PREV, Decimal("5000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(_PREV_Y, _PREV_M, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    data = await query_ranking(db_session, "channel", "settlement_amount", count=10)
    results = data["rows"]
    assert data["current_month"] == _CURR
    assert data["previous_month"] == _PREV

    assert len(results) >= 1
    r = results[0]
    assert r["name"] == "应用商店"
    assert r["current_value"] > 0
    assert r["previous_value"] > 0
    assert r["growth_rate"] is not None


@pytest.mark.asyncio
async def test_game_ranking_aggregates_by_game(db_session):
    """query_ranking(game) 按游戏名称聚合."""
    game = models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.7"))
    db_session.add(game)
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _CURR, Decimal("10000"))
    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _PREV, Decimal("5000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(_PREV_Y, _PREV_M, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    data = await query_ranking(db_session, "game", "real_revenue", count=10)
    results = data["rows"]

    assert len(results) >= 1
    r = results[0]
    assert r["name"] == "游戏A"
    assert r["current_value"] == 7000.0  # 10000 * 0.7
    assert r["previous_value"] == 3500.0  # 5000 * 0.7


@pytest.mark.asyncio
async def test_trend_summary_returns_months(db_session):
    """query_trend_summary() 返回近6月数据, 月份从近到远."""
    game = models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.7"))
    db_session.add(game)
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _CURR, Decimal("10000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(_CURR_Y, _CURR_M, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    results = await query_trend_summary(db_session)

    assert len(results) == 6
    months = [r["month"] for r in results]
    assert _CURR in months
    mar = [r for r in results if r["month"] == _CURR][0]
    assert mar["real_revenue"] > 0
    assert mar["settlement_amount"] > 0


@pytest.mark.asyncio
async def test_level1_options_returns_names(db_session):
    """query_level1_options 返回渠道/研发商名称列表."""
    cat = models.ChannelCategory(channel_name="测试渠道")
    db_session.add(cat)
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)
    await db_session.commit()

    channels = await query_level1_options(db_session, "channel")
    assert "测试渠道" in channels

    publishers = await query_level1_options(db_session, "publisher")
    assert "测试研发" in publishers


@pytest.mark.asyncio
async def test_ranking_growth_null_when_no_previous(db_session):
    """无上月数据时 growth_rate 为 None."""
    game = models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.7"))
    db_session.add(game)
    cat = models.ChannelCategory(channel_name="新渠道")
    db_session.add(cat)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "新渠道", "G001", "游戏A", _CURR, Decimal("10000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(_CURR_Y, _CURR_M, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    data = await query_ranking(db_session, "channel", "settlement_amount", count=10)
    results = data["rows"]

    match = [r for r in results if r["name"] == "新渠道"]
    assert len(match) == 1
    assert match[0]["current_value"] > 0
    assert match[0]["previous_value"] == 0
    assert match[0]["growth_rate"] is None


@pytest.mark.asyncio
async def test_init_returns_complete_payload(db_session):
    """query_init() 返回完整的初始化数据结构."""
    game = models.Game(game_id="G001", game_name="游戏A", discount_rate=Decimal("0.7"))
    db_session.add(game)
    cat = models.ChannelCategory(channel_name="应用商店")
    db_session.add(cat)
    pub = models.Publisher(publisher_name="测试研发")
    db_session.add(pub)
    await db_session.flush()

    await _seed_rs(db_session, cat.channel_id, "应用商店", "G001", "游戏A", _CURR, Decimal("10000"))

    cfg = models.IncomeSplitConfig(
        channel_id=cat.channel_id, game_id="G001",
        split_rate=Decimal("0.5"), channel_fee_rate=Decimal("0.05"), tax_rate=Decimal("0.06"),
        effective_from=date(_CURR_Y, _CURR_M, 1),
    )
    db_session.add(cfg)
    await db_session.commit()

    data = await query_init(db_session)

    assert "summary" in data
    assert data["summary"]["current_month"] == _CURR
    assert "total_real_revenue" in data["summary"]
    assert "mom_growth" in data["summary"]

    assert "rankings" in data
    assert len(data["rankings"]) == 3
    for r in data["rankings"]:
        assert "dimension" in r
        assert "metric" in r
        assert "rows" in r
        assert "current_month" in r
        assert "previous_month" in r

    assert "trend_summary" in data
    assert len(data["trend_summary"]) == 6

    assert "level1_options" in data
    assert "channel" in data["level1_options"]
    assert "publisher" in data["level1_options"]
