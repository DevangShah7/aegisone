"""SQLAlchemy declarative base.

All ORM models inherit from ``Base``. The metadata on ``Base`` is what
Alembic reads for autogenerate.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Single naming convention keeps Alembic autogenerate stable across all
# migration revisions: drop/create of indexes and constraints produces
# predictable names, which is essential for `alembic downgrade` correctness.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base.

    The shared ``MetaData`` carries the naming convention above so every
    constraint/index Alembic creates follows the same template.
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


def utcnow() -> datetime:
    """UTC ``datetime`` for default factories on ``DateTime`` columns."""
    return datetime.now(tz=UTC)
