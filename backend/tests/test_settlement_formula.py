from decimal import Decimal
from backend.services.settlement_formula import compute


def test_income_basic():
    real, settlement = compute(
        raw_revenue=Decimal("1000"),
        discount_rate=Decimal("0.9"),
        total_deductions=Decimal("100"),
        split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"),
        tax_rate=Decimal("0.05"),
        direction="income",
    )
    assert real == Decimal("900.00")  # 1000 * 0.9
    # net = 900 - 100 = 800; ratio = 0.5 * 0.9 * 0.95 = 0.4275
    assert settlement == Decimal("342.00")


def test_payment_basic():
    real, settlement = compute(
        raw_revenue=Decimal("1000"),
        discount_rate=Decimal("0.9"),
        total_deductions=Decimal("100"),
        split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"),
        tax_rate=Decimal("0.05"),
        fixed_fee=Decimal("10"),
        direction="payment",
    )
    # net = 900 - 100 = 800; ratio = 0.5 * 0.9 * 0.95 = 0.4275
    # settlement = 800 * 0.4275 + 10 = 352.00
    assert settlement == Decimal("352.00")


def test_locked_real_revenue():
    real, settlement = compute(
        raw_revenue=Decimal("1000"),
        discount_rate=Decimal("0.9"),
        total_deductions=Decimal("100"),
        split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"),
        tax_rate=Decimal("0.05"),
        locked_real_revenue=Decimal("850"),
        direction="income",
    )
    assert real == Decimal("850")  # locked overrides formula
    assert settlement == Decimal("320.62")


def test_locked_settlement_amount():
    real, settlement = compute(
        raw_revenue=Decimal("1000"),
        discount_rate=Decimal("0.9"),
        total_deductions=Decimal("100"),
        split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"),
        tax_rate=Decimal("0.05"),
        locked_settlement_amount=Decimal("500"),
        direction="income",
    )
    assert settlement == Decimal("500")  # locked overrides formula


def test_locked_both():
    real, settlement = compute(
        raw_revenue=Decimal("1000"),
        discount_rate=Decimal("0.9"),
        total_deductions=Decimal("100"),
        split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"),
        tax_rate=Decimal("0.05"),
        locked_real_revenue=Decimal("999"),
        locked_settlement_amount=Decimal("888"),
        direction="income",
    )
    assert real == Decimal("999")
    assert settlement == Decimal("888")


def test_income_vs_payment_formula_difference():
    """Payment adds fixed_fee; income does not."""
    real_i, settlement_i = compute(
        raw_revenue=Decimal("1000"), discount_rate=Decimal("1"),
        total_deductions=Decimal("0"), split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"), tax_rate=Decimal("0.05"),
        direction="income",
    )
    real_p, settlement_p = compute(
        raw_revenue=Decimal("1000"), discount_rate=Decimal("1"),
        total_deductions=Decimal("0"), split_rate=Decimal("0.5"),
        channel_fee_rate=Decimal("0.1"), tax_rate=Decimal("0.05"),
        fixed_fee=Decimal("10"),
        direction="payment",
    )
    # income: 0.5 * 0.9 * 0.95 = 0.4275 → settlement = 427.50
    # payment: 0.5 * 0.9 * 0.95 = 0.4275 → settlement = 427.50 + 10 = 437.50
    assert settlement_i != settlement_p
    assert settlement_p == settlement_i + Decimal("10")
