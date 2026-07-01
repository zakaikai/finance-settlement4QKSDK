"""Shared date/month utilities used across services."""
from datetime import date, timedelta


def month_start(month: str) -> date:
    """Parse 'YYYY-MM' to first day of month."""
    y, m = int(month[:4]), int(month[5:7])
    return date(y, m, 1)


def month_end(month: str) -> date:
    """Get last day of a month from 'YYYY-MM' string."""
    first = month_start(month)
    if first.month == 12:
        return date(first.year + 1, 1, 1) - timedelta(days=1)
    return date(first.year, first.month + 1, 1) - timedelta(days=1)


def month_bounds(month: str) -> tuple[date, date]:
    """Return (first_day_of_month, first_day_of_next_month) for range queries."""
    first = month_start(month)
    if first.month == 12:
        nxt = date(first.year + 1, 1, 1)
    else:
        nxt = date(first.year, first.month + 1, 1)
    return (first, nxt)


def prev_month_end(month: str) -> date:
    """Get last day of previous month."""
    return month_start(month) - timedelta(days=1)
