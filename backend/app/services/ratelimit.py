"""Postgres-backed sliding-window rate limiting (no Redis needed)."""

from __future__ import annotations

import datetime as dt
import random

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import RateHit


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def count(db: Session, bucket: str, window_s: int) -> int:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=window_s)
    return db.scalar(
        select(func.count()).select_from(RateHit).where(RateHit.bucket == bucket, RateHit.created_at > since)
    ) or 0


def record(db: Session, bucket: str) -> None:
    db.add(RateHit(bucket=bucket))
    if random.random() < 0.02:  # occasional cleanup of old rows
        db.execute(delete(RateHit).where(RateHit.created_at < dt.datetime.now(dt.UTC) - dt.timedelta(days=1)))
    db.flush()


def hit(db: Session, bucket: str, limit: int, window_s: int) -> None:
    """Record a hit, or raise 429 when the bucket is already full."""
    if count(db, bucket, window_s) >= limit:
        raise HTTPException(status_code=429, detail="محاولات كتير، جرّب كمان شوية")
    record(db, bucket)
