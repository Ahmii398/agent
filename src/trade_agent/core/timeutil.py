"""UTC-only time helpers. Naive datetimes are rejected."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)


def utcnow_iso() -> str:
    """ISO-8601 UTC timestamp with Z suffix."""
    return to_iso(utcnow())


def to_iso(dt: datetime) -> str:
    """Serialize a UTC datetime to ISO-8601 with Z."""
    ensure_utc(dt)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def from_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return ensure_utc(dt)


def ensure_utc(dt: datetime) -> datetime:
    """Require an aware datetime and normalize to UTC.

    Raises:
        ValueError: if ``dt`` is naive (look-ahead / TZ bugs hide in naive times).
    """
    if dt.tzinfo is None:
        raise ValueError("naive datetime rejected; all timestamps must be UTC-aware")
    return dt.astimezone(UTC)


def year_month(dt: datetime | None = None) -> str:
    """Return ``YYYY-MM`` for a UTC datetime (default: now)."""
    when = ensure_utc(dt) if dt is not None else utcnow()
    return when.strftime("%Y-%m")
