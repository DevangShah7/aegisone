"""AegisOne service layer.

Modules:

- ``audit``: helpers for writing ``audit_logs`` rows.
- ``auth``: register / login / refresh / logout business logic.

Services are pure functions over an ``AsyncSession`` — they never
import FastAPI primitives. That keeps them easy to unit-test against
an in-memory or test-Postgres database.
"""
