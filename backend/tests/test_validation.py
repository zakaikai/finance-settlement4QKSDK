"""Tests for import validation (validate_values)."""
import pytest
from decimal import Decimal
from backend.services.template_import import validate_values


@pytest.mark.asyncio
async def test_invalid_month_format():
    """Deductions with invalid month format should be flagged."""
    rows = [
        {"channel_name": "商店", "game_id": "G001", "month": "2024-13",
         "vouchers": Decimal("0"), "test": Decimal("0"), "welfare": Decimal("0"), "bad_debt": Decimal("0")},
    ]
    result = await validate_values("deductions", rows)
    month_errors = [e for e in result["errors"] if "month" in e["error"].lower()]
    assert len(month_errors) == 1


@pytest.mark.asyncio
async def test_valid_month_format():
    """Deductions with valid month format should pass."""
    rows = [
        {"channel_name": "商店", "game_id": "G001", "month": "2024-01",
         "vouchers": Decimal("0"), "test": Decimal("0"), "welfare": Decimal("0"), "bad_debt": Decimal("0")},
    ]
    result = await validate_values("deductions", rows)
    month_errors = [e for e in result["errors"] if "month" in e["error"].lower()]
    assert len(month_errors) == 0


@pytest.mark.asyncio
async def test_invalid_record_date_format():
    """raw_transactions with invalid record_date format should be flagged."""
    rows = [
        {"sub_channel_name": "华为-游戏", "game_id": "G001", "amount": Decimal("100"), "record_date": "2024/01/01"},
    ]
    result = await validate_values("raw_transactions", rows)
    date_errors = [e for e in result["errors"] if "record_date" in e["error"].lower()]
    assert len(date_errors) == 1


@pytest.mark.asyncio
async def test_valid_record_date_format():
    """raw_transactions with valid record_date should pass."""
    rows = [
        {"sub_channel_name": "华为-游戏", "game_id": "G001", "amount": Decimal("100"), "record_date": "2024-01-01"},
    ]
    result = await validate_values("raw_transactions", rows)
    date_errors = [e for e in result["errors"] if "record_date" in e["error"].lower()]
    assert len(date_errors) == 0


@pytest.mark.asyncio
async def test_decimal_precision_too_many_places():
    """discount_rate with more than 4 decimal places should be flagged."""
    rows = [
        {"game_id": "G001", "game_name": "Game A", "discount_rate": Decimal("0.12345")},
    ]
    result = await validate_values("games", rows)
    prec_errors = [e for e in result["errors"] if "decimal" in e["error"].lower() or "precision" in e["error"].lower()]
    assert len(prec_errors) == 1


@pytest.mark.asyncio
async def test_decimal_precision_valid():
    """discount_rate with at most 4 decimal places should pass."""
    rows = [
        {"game_id": "G001", "game_name": "Game A", "discount_rate": Decimal("0.1234")},
    ]
    result = await validate_values("games", rows)
    prec_errors = [e for e in result["errors"] if "decimal" in e["error"].lower() or "precision" in e["error"].lower()]
    assert len(prec_errors) == 0


@pytest.mark.asyncio
async def test_duplicate_game_id_in_games():
    """Same game_id in two rows should be flagged as duplicate."""
    rows = [
        {"game_id": "G001", "game_name": "Game A", "discount_rate": Decimal("0.7")},
        {"game_id": "G001", "game_name": "Game B", "discount_rate": Decimal("0.8")},
    ]
    result = await validate_values("games", rows)
    dup_errors = [e for e in result["errors"] if "duplicate" in e["error"].lower()]
    assert len(dup_errors) == 1
    assert "G001" in dup_errors[0]["error"]


@pytest.mark.asyncio
async def test_duplicate_income_split():
    """Same channel_name + game_id in income_split should be flagged."""
    rows = [
        {"channel_name": "商店", "game_id": "G001",
         "split_rate": Decimal("0.5"), "channel_fee_rate": Decimal("0.1"), "tax_rate": Decimal("0.05")},
        {"channel_name": "商店", "game_id": "G001",
         "split_rate": Decimal("0.6"), "channel_fee_rate": Decimal("0.1"), "tax_rate": Decimal("0.05")},
    ]
    result = await validate_values("income_split", rows)
    dup_errors = [e for e in result["errors"] if "duplicate" in e["error"].lower()]
    assert len(dup_errors) == 1
    assert "商店" in dup_errors[0]["error"]


@pytest.mark.asyncio
async def test_no_false_positive_different_values():
    """Different values should not trigger duplicate errors."""
    rows = [
        {"game_id": "G001", "game_name": "Game A", "discount_rate": Decimal("0.7")},
        {"game_id": "G002", "game_name": "Game B", "discount_rate": Decimal("0.8")},
    ]
    result = await validate_values("games", rows)
    dup_errors = [e for e in result["errors"] if "duplicate" in e["error"].lower()]
    assert len(dup_errors) == 0


@pytest.mark.asyncio
async def test_duplicate_channel_row():
    """Same channel_name + backend_channel_name + sub_channel_name should be flagged."""
    rows = [
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏"},
        {"channel_name": "应用商店", "backend_channel_name": "华为", "sub_channel_name": "华为-游戏"},
    ]
    result = await validate_values("channels", rows)
    dup_errors = [e for e in result["errors"] if "duplicate" in e["error"].lower()]
    assert len(dup_errors) == 1


@pytest.mark.asyncio
async def test_no_duplicate_check_for_raw_transactions():
    """Templates without unique_fields should skip duplicate check."""
    rows = [
        {"sub_channel_name": "华为-游戏", "game_id": "G001", "amount": Decimal("100"), "record_date": "2024-01-01"},
        {"sub_channel_name": "华为-游戏", "game_id": "G001", "amount": Decimal("200"), "record_date": "2024-01-02"},
    ]
    result = await validate_values("raw_transactions", rows)
    dup_errors = [e for e in result["errors"] if "duplicate" in e["error"].lower()]
    assert len(dup_errors) == 0
