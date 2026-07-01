"""Test company_name project-based fallback in settlement queries."""

import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import select

from backend import models
from backend.services.settlement_service import query_income_settlement


async def _seed_basic(db_session):
    """Seed minimal data: channel, game, company, project association."""
    # Channel
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    # Games
    db_session.add(models.Game(game_id="G001", game_name="Game1", discount_rate=Decimal("0.8")))
    db_session.add(models.Game(game_id="G002", game_name="Game2", discount_rate=Decimal("0.8")))
    # Publisher + project mapping (same project for both games)
    db_session.add(models.Publisher(publisher_id=1, publisher_name="PubA"))
    db_session.add(models.PublisherGameMapping(
        publisher_id=1, game_id="G001",
        project_code="P001", project_name="Project One"))
    db_session.add(models.PublisherGameMapping(
        publisher_id=1, game_id="G002",
        project_code="P001", project_name="Project One"))
    # Company + direct mapping only for G001
    db_session.add(models.Company(company_id=1, company_name="MyCompany"))
    db_session.add(models.CompanyGameMapping(company_id=1, game_id="G001"))
    # RawSettlement rows for both games
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G001", game_name="Game1",
        month="2026-04", raw_revenue=Decimal("10000"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G002", game_name="Game2",
        month="2026-04", raw_revenue=Decimal("5000"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_direct_match_returns_company_name(db_session):
    """G001 has direct CompanyGameMapping → company_name is resolved."""
    await _seed_basic(db_session)

    results = await query_income_settlement(db_session, "2026-04", "2026-04")

    g1 = [r for r in results if r["game_id"] == "G001"]
    assert len(g1) == 1
    assert g1[0]["company_name"] == "MyCompany"


@pytest.mark.asyncio
async def test_project_fallback_resolves_company_name(db_session):
    """G002 has no direct mapping but shares project P001 with G001 → fallback resolves company_name."""
    await _seed_basic(db_session)

    results = await query_income_settlement(db_session, "2026-04", "2026-04")

    g2 = [r for r in results if r["game_id"] == "G002"]
    assert len(g2) == 1
    assert g2[0]["company_name"] == "MyCompany", \
        f"Expected 'MyCompany' via project fallback, got '{g2[0]['company_name']}'"


@pytest.mark.asyncio
async def test_no_project_no_company_returns_empty(db_session):
    """G003 has no mapping and no project → company_name is empty."""
    db_session.add(models.ChannelCategory(channel_id=1, channel_name="ChA"))
    db_session.add(models.Game(game_id="G003", game_name="Game3", discount_rate=Decimal("0.8")))
    db_session.add(models.RawSettlement(
        channel_id=1, channel_name="ChA", game_id="G003", game_name="Game3",
        month="2026-04", raw_revenue=Decimal("3000"),
        created_at="2026-01-01", updated_at="2026-01-01"))
    await db_session.commit()

    results = await query_income_settlement(db_session, "2026-04", "2026-04")

    g3 = [r for r in results if r["game_id"] == "G003"]
    assert len(g3) == 1
    assert g3[0]["company_name"] == "" or g3[0]["company_name"] is None
