"""Tests for raw_transactions import and overwrite behavior.

NOTE: RawTransaction model has been removed (deprecated). These tests are
skipped because the raw_transactions import flow no longer exists.
"""
import pytest


@pytest.mark.skip(reason="RawTransaction model deleted - raw_transactions import flow deprecated")
@pytest.mark.asyncio
async def test_import_raw_transactions_inserts_rows(db_session):
    pass


@pytest.mark.skip(reason="RawTransaction model deleted - raw_transactions import flow deprecated")
@pytest.mark.asyncio
async def test_overwrite_replaces_same_month(db_session):
    pass


@pytest.mark.skip(reason="RawTransaction model deleted - raw_transactions import flow deprecated")
@pytest.mark.asyncio
async def test_overwrite_does_not_affect_other_months(db_session):
    pass


@pytest.mark.skip(reason="RawTransaction model deleted - raw_transactions import flow deprecated")
@pytest.mark.asyncio
async def test_non_overwrite_duplicates_rows(db_session):
    pass
