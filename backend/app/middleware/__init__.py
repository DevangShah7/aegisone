"""AegisOne middleware package.

- request_id:        correlation id on every request.
- security_headers:  hardened response headers on every response.
- rate_limit:        Redis sliding window for sensitive endpoints.
"""
