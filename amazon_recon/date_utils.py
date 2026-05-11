from __future__ import annotations

from datetime import date, datetime
import re


DATE_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m/%d/%y",
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.strip())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    return None


def date_distance_days(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left - right).days)
