"""Date and time helpers."""

from datetime import date, datetime, timedelta, timezone


def utcnow() -> datetime:
    """
    Current UTC time as a naive datetime.

    Columns are declared as DateTime without timezone, so tzinfo is stripped to
    keep comparisons consistent. datetime.utcnow() is deprecated in Python 3.12.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def days_between(start: date, end: date) -> int:
    return (end - start).days


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def add_days(value: datetime, days: int) -> datetime:
    return value + timedelta(days=days)


def start_of_day(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time())


def end_of_day(value: date) -> datetime:
    return datetime.combine(value, datetime.max.time())
