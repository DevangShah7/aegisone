"""Database primitives for AegisOne.

This package owns:

- ``base``: the SQLAlchemy 2.x declarative ``Base`` that every model inherits.
- ``session``: the async engine + session factory wired to ``settings.database_url``.
- ``models``: concrete ORM tables (users, sessions, audit_logs, consents).

The Alembic environment imports ``Base`` and the model modules so its
``target_metadata`` reflects the live schema.
"""
