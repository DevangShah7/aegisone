"""Debug script — inspect session rows after a failed test.

Run from backend/: ``PYTHONPATH=. .venv/Scripts/python.exe scripts/inspect_sessions.py``
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models import Session, User


async def main() -> None:
    async with SessionLocal() as s:
        users = (await s.execute(select(User).order_by(User.created_at))).scalars().all()
        for u in users:
            print(f"user {u.id}: email={u.email} created={u.created_at}")
        rows = (await s.execute(select(Session).order_by(Session.created_at))).scalars().all()
        for r in rows:
            print(
                f"  sess {r.id}: user={r.user_id} revoked_at={r.revoked_at} "
                f"replaced_by={r.replaced_by} expires={r.expires_at}"
            )


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(engine.dispose())
