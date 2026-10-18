# Production operations: Railway + existing Supabase

Audit date: 2026-10-18. Target application: Railway project `ravishing-emotion`; persistent data remain in Supabase schema `bakery` and private bucket `bakery-private-media`. This document records a source audit and a proposed runbook. No cloud backup, restore drill, account activation, monitoring setup, or payment verification was performed by this audit.

## What the existing scripts actually cover

| Script | Verified from source | Cloud gap |
| --- | --- | --- |
| `scripts/backup.py` | Custom PostgreSQL dump, local media archive, SHA-256 manifest, refuses an existing destination | Reads `DB_*`, ignores application `DATABASE_URL`; defaults to localhost port 54329. Dumps all accessible schemas without `--schema=bakery` or `--no-privileges`. Reads `backend/media`, never the remote bucket. Does not explicitly require TLS. ZIP is unencrypted and local only. |
| `scripts/verify_restore.py` | Creates isolated `verify_*` DB, checks dump/file hashes and balance reconciliation | Requires `createdb` on source host. Queries unqualified tables rather than `bakery.*`. Restores media only to disk, not Storage. Does not compare source snapshot counts/totals to restored counts/totals. Not suitable to point at Supabase production. |
| `scripts/daily_backup.py` | Date-based filename and skip when already present | No cloud scheduler, off-site upload, freshness alert, or integrity check of an existing archive. |

Do not run these scripts with production credentials as a cloud backup solution. Existing local restore reports do not prove cloud recoverability. Supabase database backups exclude actual Storage objects; those need a separate copy. [Supabase backup coverage](https://supabase.com/docs/guides/platform/backups).

## Cloud backup procedure to implement and execute

1. Use an isolated cloud backup job with PostgreSQL client tools matching or newer than the source server. Read credentials from its secret store; never print URLs, passwords, environment dumps, or signed object URLs. Use a direct database connection or session pooler, with TLS required; do not use transaction-pooler port 6543 for the dump. [Connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres), [backup/restore guidance](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore).
2. Identify the exact source project and record schema/bucket names and application revision without credentials. Pause application writes, uploads/deletions and scheduled jobs for a coordinated snapshot, recording the start/end time. If maintenance is unavailable, implement a shared exported PostgreSQL snapshot for dump and reference metrics plus object-version coordination before claiming a consistent backup.
3. With `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGPASSWORD` injected securely and `PGSSLMODE=require`, run in the backup job:

   ```sh
   pg_dump --format=custom --schema=bakery --no-owner --no-privileges --file=bakery.dump
   pg_restore --list bakery.dump
   ```

   This intentionally covers application tables including Django users, sessions and migrations in `bakery`. Confirm no dependencies outside that schema before relying on this dump. It does not back up platform configuration or Storage object bytes.
4. Export a baseline using schema-qualified SQL while writes remain paused: row count of each application table, order count, ledger count and sum, per-client balance reconciliation, and the complete `bakery.shop_photo.file` reference list. Store raw data only inside the encrypted backup; operational logs should contain counts, hashes and timestamps.
5. Enumerate **all pages and nested prefixes** of `bakery-private-media` using the authenticated Storage API or supported storage tooling. Download each object with its full key preserved, recording key, byte length, content type and SHA-256 in the encrypted manifest. Fail if any DB photo reference is absent or a download fails. Also preserve objects currently unreferenced by photos. Record bucket privacy and required policies/configuration separately. Do not substitute a dump of `storage.objects` for object bytes. [Supabase object download guidance](https://supabase.com/docs/guides/storage/management/download-objects).
6. Hash the dump and manifest, encrypt the completed archive, then upload it to a separately controlled durable backup destination. Verify the uploaded archive checksum and record a non-sensitive completion receipt. Only a complete, verified DB-plus-objects pair counts as success. Resume writers and jobs in a guaranteed cleanup step even after failure.
7. Configure a daily cloud schedule and alert on failure or last verified backup older than 24 hours. Proposed retention is 7 daily plus 4 weekly copies; the owner must choose retention and confirm the existing proposed RPO ≤24h / RTO ≤4h. Do not use the application's ephemeral filesystem as the sole copy.

## Restore validation without touching production

Provision a separate disposable **cloud** database/project and a separate private bucket; do not run a local DB/server/worker. Its database and Storage credentials must be distinct from production. Independently compare target host/project identity with source before any restore. Keep the restored app private, disable outbound notifications and all scheduled jobs, and block restored customer access: the dump contains real accounts and sessions.

Verify archive checksums before extraction. Restore only into a fresh target with no `bakery` schema, using target-only `PG*` secrets:

```sh
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$PGDATABASE" bakery.dump
```

No `--clean`, `DROP`, or production target is part of this drill. Restore the object bytes through the Storage API into the isolated bucket, recreate its private configuration, and use only that target's storage key in the drill app. The application currently expects the bucket name `bakery-private-media`, so a separate Supabase project with that bucket name avoids changing shared settings. Platform project cloning alone does not copy Storage files/settings. [Supabase clone limitations](https://supabase.com/docs/guides/platform/clone-project).

Run and compare the same baseline queries on the target. In particular:

```sql
SELECT count(*) AS orders FROM bakery.shop_order;
SELECT count(*) AS ledger_count, coalesce(sum(amount), 0) AS ledger_total
FROM bakery.shop_ledgerentry;
SELECT count(*) AS balance_mismatches FROM (
  SELECT c.id FROM bakery.shop_client c
  LEFT JOIN bakery.shop_ledgerentry l ON l.client_id = c.id
  GROUP BY c.id HAVING c.balance <> coalesce(sum(l.amount), 0)
) AS mismatches;
SELECT file FROM bakery.shop_photo;
```

Require exact baseline counts/totals, zero reconciliation mismatches, all photo references resolvable in the restored bucket and matching object SHA-256 hashes. Run `python manage.py migrate --check` against the isolated target. Then verify `/live`, `/ready`, authenticated access to one restored photo and rejection of anonymous photo access in the private cloud deployment. Do not generate real orders or payments for this drill.

Record backup ID, application revision, snapshot age, restore duration, object counts, hash checks and pass/fail results. Measure RTO through the completed application checks, not only `pg_restore`. Preserve failures for diagnosis. Remove disposable resources only after recording evidence and confirming their identity. **Current status: this drill has not been executed.**

## Monitoring that exists and what remains

`/live` checks process response. `/ready` runs a database query and checks for pending migrations; it returns 503 on failure. It does not check Storage, background-job freshness or backups. `shop.logging_filters.SensitiveQueryFilter` is attached to `django.server`; this is not evidence that every production logger/error reporter redacts secrets. No external error-alert delivery was verified.

Configure external HTTPS checks for both endpoints every minute and alert after two consecutive failures. Separately alert on elevated HTTP 5xx rate and worker/job failure or lateness. Configure the chosen error-monitoring service to exclude request bodies, cookies, authorization headers, payment evidence and signed query parameters. Validate alerts with a synthetic event in a private staging deployment and record receipt by the responsible operator; do not deliberately crash production. A cloud schedule, actual recipients and successful alert delivery remain unconfirmed.

## Accounts and payment setup

The owner supplied display names and usernames for admin, cashier and courier through the private task. They are not passwords and are not repeated in this public runbook.

These accounts were not created by this audit. Activate through the controlled invitation/activation flow; obtain user-chosen passwords privately. Never infer a password from an account name. Disable known demo accounts only after confirming real administrative access; do not delete their ledger/audit relationships. The known seed usernames are `+77010000001` through `+77010000005`; other demo accounts may exist and require separate review.

The audit found an E.164-only login field. This revision corrects login to a text field with `autocomplete=username`, while registration remains phone-based. Staff invitations now accept Django-validated Unicode usernames. Invitation, activation and login have regression coverage. This document does not assert that the UI correction has been deployed.

`KASPI_MERCHANT_URL` controls the existing payment-instructions response. The owner has not supplied or verified real payment recipient details/link. Do not substitute a guessed merchant URL or call payment setup complete. Once received, verify recipient identity in the payment provider and then check the displayed instructions with an authorized account.

## Read-only readiness command

From the deployed backend's cloud shell, with its existing environment:

```sh
python manage.py production_readiness --strict
```

The command reads only username/role/active columns and reports counts and configuration booleans, never raw credentials or account names. It checks active admin/cashier/courier roles, active known demo usernames, HTTPS-cookie settings, PostgreSQL TLS/schema configuration, private storage configuration and basic secret/host configuration. `--strict` exits nonzero on a failed scoped check. A connection failure is reported without raw connection details.

Passing means only these scoped checks passed. It does **not** prove activation/password quality, that a real user's intended account is present, storage availability/privacy, restore success, payment ownership, job scheduling or alert delivery; these limitations are included in its JSON. Tests use `SimpleTestCase` and mocked database reads, and do not start a DB, server or worker. No live production-readiness result was collected by this audit.
