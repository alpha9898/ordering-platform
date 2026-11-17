"""Working hours and business-day logic in the restaurant's timezone."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .settings import WEEKDAYS

# Python weekday(): Mon=0 .. Sun=6  ->  our keys
_PY_TO_KEY = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def local_now(tz: str, now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.UTC)
    return now.astimezone(ZoneInfo(tz))


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _intervals_for(day: dt.date, hours: dict) -> list[tuple[dt.datetime, dt.datetime]]:
    """Naive local datetimes for the ranges that START on `day`."""
    key = _PY_TO_KEY[day.weekday()]
    out = []
    base = dt.datetime.combine(day, dt.time())
    for start, end in hours.get(key, []):
        s, e = _minutes(start), _minutes(end)
        if e <= s:  # crosses midnight (or 00:00-00:00 = all day)
            e += 24 * 60
        out.append((base + dt.timedelta(minutes=s), base + dt.timedelta(minutes=e)))
    return out


def is_open(hours: dict, tz: str, now: dt.datetime | None = None) -> bool:
    local = local_now(tz, now).replace(tzinfo=None)
    for day in (local.date() - dt.timedelta(days=1), local.date()):
        for s, e in _intervals_for(day, hours):
            if s <= local < e:
                return True
    return False


def next_opening(hours: dict, tz: str, now: dt.datetime | None = None) -> dt.datetime | None:
    """Next local opening time within a week, or None if never open."""
    local = local_now(tz, now).replace(tzinfo=None)
    best = None
    for i in range(0, 8):
        for s, _e in _intervals_for(local.date() + dt.timedelta(days=i), hours):
            if s > local and (best is None or s < best):
                best = s
    return best


def business_day(tz: str, starts: str = "05:00", now: dt.datetime | None = None) -> dt.date:
    """Orders after midnight but before `starts` belong to the previous day."""
    local = local_now(tz, now)
    return (local - dt.timedelta(minutes=_minutes(starts))).date()


AR_DAYS = {"sat": "السبت", "sun": "الأحد", "mon": "الاتنين", "tue": "التلات", "wed": "الأربع", "thu": "الخميس", "fri": "الجمعة"}


def fmt_time_ar(t: dt.datetime | dt.time) -> str:
    h, m = t.hour, t.minute
    suffix = "ص" if h < 12 else "م"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def describe_next_opening(hours: dict, tz: str, now: dt.datetime | None = None) -> str | None:
    nxt = next_opening(hours, tz, now)
    if nxt is None:
        return None
    today = local_now(tz, now).date()
    if nxt.date() == today:
        day = "النهارده"
    elif nxt.date() == today + dt.timedelta(days=1):
        day = "بكرة"
    else:
        day = "يوم " + AR_DAYS[_PY_TO_KEY[nxt.weekday()]]
    return f"{day} الساعة {fmt_time_ar(nxt)}"


__all__ = ["WEEKDAYS", "is_open", "next_opening", "business_day", "describe_next_opening", "local_now"]
