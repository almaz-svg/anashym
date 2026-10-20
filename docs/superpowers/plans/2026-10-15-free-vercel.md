# Free Vercel + Supabase deployment

**Goal:** Publish the existing application with working authentication, orders, private photos and scheduled accounting, using free plans only.

**Architecture:** Vercel serves Vite and Django from one deployment and origin. Supabase provides PostgreSQL in a private `bakery` schema, a private media bucket, and pg_cron/pg_net scheduling. Django continues to authorize every photo request. Local Windows services remain usable.

**Constraints:** No paid subscription, no local customer-data upload, no credentials in Git or browser bundles. Keep all existing session/CSRF and financial controls. Seed only the documented demo records into the new database.

- [ ] Test cloud database configuration, private storage failures and cron authentication.
- [ ] Add conditional cloud settings, private storage, bootstrap and authenticated scheduled-job endpoint.
- [ ] Add Vercel service configuration; build and run backend checks and relevant tests.
- [ ] Review, publish source, change Vercel root directory, redeploy and verify public API/login, storage and cron status.

Files: `vercel.json`, `backend/vercel.json`, `backend/config/settings.py`, `backend/config/cloud.py`, `backend/config/urls.py`, `backend/shop/cloud_storage.py`, `backend/shop/cloud_jobs.py`, `backend/shop/management/commands/bootstrap_cloud.py`, `backend/shop/test_cloud.py`, `docs/cloud-deployment.md`.
