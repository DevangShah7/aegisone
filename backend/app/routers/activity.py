"""Cross-device activity feed.

A single ``GET /activity`` endpoint that returns the activity events
across **every** device owned by the caller, paginated and ordered by
``occurred_at DESC``. The dashboard's main timeline reads this so the
``Activity`` tab on the home page doesn't have to fan out per-device.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models import Device, DeviceActivityEvent
from app.schemas.device import DeviceActivityEventOut

router = APIRouter()


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


@router.get(
    "",
    summary="Cross-device activity feed for the caller",
    response_model=list[DeviceActivityEventOut],
)
async def list_activity(
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> list[DeviceActivityEventOut]:
    owner_id = claims["sub"]
    # Subquery to find the caller's device ids. We use a correlated WHERE
    # so the activity query is a single SELECT — simpler and faster than
    # a join + GROUP BY for this cardinality.
    owned_ids_subq = select(Device.id).where(Device.owner_id == owner_id).scalar_subquery()
    stmt = (
        select(DeviceActivityEvent)
        .where(DeviceActivityEvent.device_id.in_(owned_ids_subq))
        .order_by(DeviceActivityEvent.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(DeviceActivityEvent.id < before_id)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        DeviceActivityEventOut(
            id=r.id,
            device_id=r.device_id,
            event_type=r.event_type,
            occurred_at=_iso(r.occurred_at),
            payload=r.payload,
        )
        for r in rows
    ]


# Squelches an unused-import warning for ``or_`` if the schema grows to
# include owner-side filtering by event_type.
_ = or_
