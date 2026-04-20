# Decision: Test Suite and Quality Findings

**Author:** Kane (Tester)
**Date:** 2025-07-18
**Status:** Proposed

## Context

Created a 30-test suite for the web app and infrastructure validation script. All tests pass against the existing `web-app/app.py`.

## Quality Findings (for Ripley)

1. **XSS Risk:** `email_detail.html` uses `{{ email.body | safe }}` — malicious email HTML bodies render unescaped. Recommend sanitizing with `nh3` or `bleach` before passing to the template.
2. **Missing error handling:** The `/emails` route does not catch exceptions from `query_items()`. Cosmos failures propagate as raw 500 errors without a user-friendly error page. The `/emails/{id}` route has the same issue.
3. **azure-cosmos version:** Must be `>=4.0.0` — v3 has a completely different API.

## Test Architecture

- Tests patch `_get_cosmos_container()` and `_get_blob_service()` at module level on the `app` module
- Sync SDK mocks (not async) — matches the actual app
- Run with: `cd web-app && python -m pytest ../tests/ -v`
