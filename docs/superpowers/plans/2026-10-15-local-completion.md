# Local workflow completion implementation plan

> For agentic workers: use subagent-driven-development with explicit file ownership and verification.

**Goal:** Complete the ten user-requested local finance, role, access, catalogue and acceptance workflows.

**Architecture:** Preserve the existing Django/PostgreSQL transaction boundaries and React role workspace. Add focused access/catalog handlers and schema fields; financial corrections remain immutable ledger operations. Use the existing checkout because the running project contains uncommitted files that would not be copied to a worktree.

**Tech stack:** Django, PostgreSQL, React, TypeScript, Vite, Vitest, Playwright.

**Spec:** User request of 2026-10-15; original requirements in docs/source-tz.txt; outstanding audit in docs/local-operations.md.

## Constraints

- Local version first; no deployment or real bank integration without actual merchant configuration.
- Five helpers, maximum three concurrent helpers: three implementers followed by independent QA and review.
- Preserve user data, existing sessions, immutable history, role/object permissions, idempotency, Russian/Kazakh/English and light/dark themes.
- Root owns models, migrations, integration, worker, API documentation and load acceptance. Finance owns existing financial backend files. Access owns new access/catalog modules. UI owns frontend. No commits or destructive checkout operations.

## Tasks and verification

- [ ] Schema: add reversal linkage/reason, payment reversal/proof metadata, refund source/order, account password-change flag, client archive, product image/shelf life, structured audit. Generate one migration and run migration consistency checks. Verify against a restored disposable DB before live application.
- [ ] Finance: use overdue_amount everywhere; POST payments/{id}/reverse with reason, immutable opposite entry, allocations/cash reconciliation and duplicate handling. Cancellation creates one refund obligation; actual refund remains a separate confirmation. Tests cover cash custody, allocations, prior refunds, duplicate cancellation and overdue equality.
- [ ] Access/catalog: normal admin reset and client member invitation with expiring one-use tokens; restricted mandatory password-change state; independent approval/credit; archive preserves history. Catalog includes image, description, shelf life, available dates. Kaspi uses actual configured seller instruction plus authorized order proof. Tests cover cross-client/token abuse, password restriction, archive and image/link validation.
- [ ] Role UI: expose courier returns/report, cashier report, accountant returns, admin Kaspi reason; complete order history/private photos; independent client controls; archive/member/reset actions; compact forms and translations. Tests cover state updates and field errors.
- [ ] Global notification/error behavior: all pages receive events; overdue worker creates deduplicated notifications; price conflict refreshes basket and requires reconfirmation; Refresh remounts/reloads all staff registries. Verify with real browser interactions.
- [ ] Pagination/audit: paginate large registry APIs without hidden cutoffs; expose actor/object/before/after/reason; history follows linked business objects without leaking other client data. Tests page past limits and check role scoping.
- [ ] API/operations: publish route/request/response/security contracts; benchmark read and order creation using an isolated dataset/server; capture exact environment, p95, sample sizes, errors and target results. Do not describe laptop results as a 2-vCPU/4-GB production acceptance.
- [ ] Independent QA agent: backend regression, real browser finance/access/roles and integration scenarios using disposable fixtures, no mutations to user records.
- [ ] Independent review agent: monetary invariants, permissions, idempotency, migrations, frontend contracts and regression risks. Fix meaningful findings and rerun affected checks.
- [ ] Root final acceptance: backup, apply migration, restart local API/worker, build, smoke-test five roles; document evidence and real unresolved external configuration.

## Integration contracts

Finance exposes ensure_cancellation_refund(actor, order, reason), overdue_amount(client), POST payments/{id}/reverse {reason}.
Access exposes handle_access(request, route, data), with explicit pre-auth invitation handling and authenticated mutation handling coordinated before integration.
Catalog exposes enrichment functions; API changes are communicated to UI before completion.

## Execution log

- Initial audit read; three implementation helpers dispatched. QA/review pending free concurrency slots.
