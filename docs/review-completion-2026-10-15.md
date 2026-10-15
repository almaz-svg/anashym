# Independent completion review — 15 October 2026

Reviewer: fourth delegated agent. This is an initial review of actively changing code, not a release approval. No application files or live demo data were changed by this reviewer. The review artifact is the only saved file.

## Environment and evidence

All dynamic reproductions used Django `DiscoverRunner.setup_databases()` with `DB_NAME=review_completion`, `DB_HOST=127.0.0.1`, `DB_PORT=54329`, `DB_USER=confectionery`, and an empty password. Django created `test_review_completion`; every reproduction called `teardown_databases()` afterward. The shared demo database and services were not stopped or mutated.

Source line numbers below identify the reviewed version and can move as fixes land.

## Findings

### P1 — Later delivery spent money reserved for an existing refund

Original locations: `backend/shop/services.py`, `allocate_advance` (original line 230); `backend/shop/routes.py`, refund confirmation (original line 483).

Reproduction using real services and the API:

1. Confirm a Kaspi payment of 100 for submitted order A.
2. Cancel A through `transition`; a pending cancellation refund for 100 is created.
3. Post a delivery charge of 100 for deferred order B and call `allocate_advance`.
4. Confirm A's refund through `POST /api/v1/refunds/{id}/confirm`.

Initial observed result: the payment for A was allocated to B for 100, client net balance became zero, and refund confirmation returned HTTP 409 `ADVANCE_UNAVAILABLE`. The promised refund lost its reservation.

Finance implementation was notified immediately. After its fix, this exact scenario was independently repeated: allocation to B was absent, refund confirmation returned HTTP 200, and client balance after refund was 100. **This specific reproduction is fixed.** Broader concurrency and end-to-end tests remain the main agent's responsibility.

### P1 — Financial lock ordering produced a PostgreSQL deadlock

Original locations: `backend/shop/routes.py`, payment reverse/confirm handlers; `backend/shop/services.py`, `reverse_payment` and `allocate_advance`.

The payment handlers acquired Payment then Client, while delivery/return acquired Client then confirmed Payments during advance allocation.

Deterministic two-thread reproduction, synchronized after the first locks:

- Thread A: atomic transaction, `Client.objects.select_for_update().get(...)`, then `allocate_advance(client)`.
- Thread B: atomic transaction, `Payment.objects.select_for_update().get(...)`, then `reverse_payment(admin, payment, reason)`.

Observed output: `[('reverse', 'OperationalError', 'deadlock detected'), ('allocate', 'ok')]`. Both threads terminated and the test database was removed. The API does not catch that `OperationalError`, so a production collision would produce a server error.

Finance reports a consistent custody User → Client → Payment route lock order, Client → Refund order, and removal of unnecessary Payment locks during allocation. **The revised concurrency path was not independently rerun by this reviewer.** Main agent should verify simultaneous delivery/reversal and cancellation/refund confirmation.

### P2 — Report pagination did not bound database work

Locations: `backend/shop/routes.py`, `report` and the `reports` route's final `listing` call (around lines 87 and 505 in the latest read).

`report()` serialized every ledger row before the route sliced the response. Each serialization loaded actor and client independently. `CaptureQueriesContext` measured:

| Ledger entries in selected period | Requested limit | Returned rows | SQL queries |
| --- | --- | --- | --- |
| 10 | 2 | 2 | 23 |
| 50 | 2 | 2 | 103 |

This is an unbounded 2N+3 query path despite pagination. Totals should be aggregated, then only the requested rows serialized with needed relations selected; full CSV export should be explicit and efficient. The main agent owns the report rewrite. **Open at reviewer handoff.**

### P2 — Courier return creation cannot select normal completed orders

Locations: `backend/shop/routes.py:187` and `:198`; `frontend/src/staff.tsx:138` and `:141`; `frontend/src/order-workspace.tsx:33`.

The new courier return selector requests `/orders?limit=20`, then retains only delivered orders. The backend courier list excludes delivered orders unless `cash_collection_assigned` is true, and the detail route also rejects normal delivered orders. Consequently a completed courier delivery disappears before the new return/exchange action can be used. The photo permission helper now allows assigned couriers to attach return/exchange evidence after delivery, but list/detail access prevents reaching that flow.

Recommended contract: add an explicit completed-history mode scoped to the assigned courier, and use it for the return selector; permit the corresponding read-only detail. Keep other couriers' orders inaccessible. Main agent and UI implementation were notified. **Open at reviewer handoff.**

### P2 — Audit redaction was only top level

Original location: `backend/shop/services.py`, original `audit` line 29.

The original implementation stripped exact sensitive names only from the outer `details` dictionary. Nested payloads such as `{'meta': {'password': 'secret', 'invitation_token': 'secret'}}` passed through. Numerous handlers pass request data to audit. Snapshots also need recursive sanitization, and the username field contains a phone number in this application's account contract.

Finance was assigned recursive sanitization and reports it implemented. **No independent persistence test of the final sanitizer was run by this reviewer.** Verify nested lists/dictionaries, before/after snapshots, token aliases, and that needed object names/reasons survive.

## Additional observations

- Reviewed new invitation/reset handling: password-derived one-time stamps, expiry, row locking, session revocation, forced password change gate, and cross-organization membership rejection are present. Existing tests exercise these paths; this reviewer did not rerun that full suite.
- Kaspi proof lookup checks order, uploader and `payment` purpose. Courier photo reads/writes remain assignment scoped in the new helper.
- The main agent identified mutable-role cash custody before this review's final pass. The latest source stores `Payment.cash_holder_kind`; legacy unknown custody returns a conflict requiring reconciliation. This reviewer did not retest that change.
- UI was still under active implementation. No whole-application visual or browser acceptance claim is made here.

## Handoff

Only the pending-refund reproduction has an independent successful post-fix retest in this document. Report scalability, completed courier history, final redaction, and final financial concurrency should be checked before marking the requested work complete.
