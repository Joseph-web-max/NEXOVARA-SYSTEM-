# NEXOVARA production readiness register

This register describes what is implemented in this source package versus what still requires account setup, live testing or business decisions. **Code being present is not the same as a verified live service.**

| Area | Implemented in source | Still required before production sign-off |
|---|---|---|
| Render + Supabase PostgreSQL | SQLAlchemy `psycopg` URL normalization, TLS required, Supabase transaction-pooler handling, separate session-pooler migration URL, Alembic revisions | Enter real Supabase URLs in Render; run migration against a backup/staging database; verify connectivity from the Render region |
| Supabase Storage | Private-bucket upload/download/delete APIs, owner checks, size/extension/signature checks, ClamAV INSTREAM scanning, file metadata/hash and audit events | Create private bucket; add service-role key to Render only; deploy private ClamAV daemon; test infected/oversized/unauthorized files; define retention |
| Authentication | HttpOnly Secure SameSite=Lax session cookie, origin checks on cookie-authenticated writes, token-version revocation, one-time hashed password reset tokens | Configure SMTP; staging security review; email verification and recovery codes are not implemented |
| Staff MFA | TOTP setup, encrypted stored secret, MFA challenge at sign-in, required for staff by default, admin reset of other staff MFA | Enroll the first admin and every staff account; store `MFA_ENCRYPTION_KEY` safely; no self-service recovery codes |
| Staff RBAC | Fixed roles: admin, operations_manager, finance_manager, support_agent, content_manager, developer; route/method permission checks; staff management UI | Review the permission matrix against real job duties; security-test every route and role |
| Rate limiting | Shared Redis counters with fixed-window expiry; fails closed if configured Redis becomes unavailable; per-process fallback when no Redis URL is configured | Provision Redis/Render Key Value and set `REDIS_URL`; test limits through Render proxy; do not use in-memory fallback for multi-instance production |
| Stripe | Checkout session creation, signed webhook verification, event idempotency, invoice/client/amount/currency matching; client portal card button | Enter test keys; configure Stripe webhook URL and event; test success/failure/duplicate/amount mismatch; only then switch to live keys |
| M-PESA Daraja | STK Push initiation, Kenyan phone validation, secret callback path, checkout/merchant request/phone/receipt/amount matching, idempotency; invoice marked paid only on matching success | Enter sandbox credentials; register public callback URL; test sandbox; add Transaction Status API reconciliation and live merchant approval before production. Daraja callbacks are not HMAC-signed like Stripe |
| SMTP | STARTTLS authenticated sender, password reset emails, automation notifications, admin test-email endpoint | Enter provider credentials; verify sender domain SPF/DKIM/DMARC; test inbox/spam and delivery logs; configure bounce handling |
| AURORA AI | Server-to-server integration code; separate public product URL and backend API URL; token stays server-side; admin-only access | `AURORA_PUBLIC_URL` is prefilled with the owner's GitHub Pages URL. Enter deployed `AURORA_BASE_URL` and renewable `AURORA_API_TOKEN`; test real chat and knowledge retrieval; design tenant isolation before client access |
| Offsite backups | Daily Render Cron Blueprint, `pg_dump` custom-format backup, S3-compatible upload, server-side AES256, size check, restore helper with explicit confirmation | Deploy Cron separately; configure S3 bucket/credentials/region and session-mode DB URL; lifecycle/versioning; restore to a separate Supabase staging project and record RPO/RTO |
| Legal/privacy | Draft privacy and terms pages; readiness documentation | Identify legal entity, data controller/processor relationships, data regions, retention, cookie/marketing practices, tax/refunds and support contacts; obtain qualified legal review |
| Monitoring/operations | Health endpoint and application audit log | Configure error monitoring, central logs, uptime alerting, on-call contact, dependency scanning, incident response and secret rotation |

## Important architecture note

Render runs the FastAPI application. Supabase provides PostgreSQL and Storage. The current application authentication remains NEXOVARA's FastAPI-managed identity/session system; this release does **not** migrate users to Supabase Auth. Database authorization is enforced in FastAPI route dependencies and per-customer filters; this release does not claim a complete Supabase Row Level Security policy rollout.

## Current validation in the build environment

- Python compilation: passed.
- Frontend JavaScript syntax: passed.
- 11 unit tests: passed.
- Fresh SQLite Alembic upgrade: passed.
- Legacy SQLite schema upgrade: passed, including user token invalidation and product metadata additions.
- Render web and backup Blueprint YAML: parsed successfully.
- ZIP integrity: checked at packaging time.

A full FastAPI startup was not certified in the build environment because the environment did not have all newly required packages (`python-jose`, `passlib`, `pyotp`, `stripe`, `redis`, and `psycopg`) installed and outbound package installation was unavailable. No live Render, Supabase, Stripe, Safaricom, SMTP, Redis, ClamAV or S3 transaction was performed here.
