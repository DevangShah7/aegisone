"""Pydantic DTOs for AegisOne.

Modules:

- ``auth``: request / response shapes for the auth endpoints.
- ``device``: request / response shapes for the device endpoints.
- ``user``: read-only user profile.
- ``common``: shared helpers and error envelopes.

Schemas use ``extra='forbid'`` so unknown fields in a request body
produce a 422 instead of being silently dropped — keeps the API
contract tight as it evolves.
"""
