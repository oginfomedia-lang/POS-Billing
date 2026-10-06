"""Business date and IST timezone helpers."""
from datetime import date, datetime, timedelta, timezone

# Fixed offset: IST has no DST, and Windows has no tz database without the tzdata package.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def business_date() -> date:
    return now_ist().date()
