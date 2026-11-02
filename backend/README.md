# NEXOVARA Technologies – Corporate Platform

A full-stack starter platform containing the public company website, FastAPI backend, SQLite/PostgreSQL data layer, administrator dashboard and client portal.

## Included
- Single-file `frontend/index.html` containing the public website, admin dashboard, client portal, legal pages, all CSS and all browser JavaScript. Backend serves it at `/`, `/admin`, `/portal`, `/privacy` and `/terms`.
- Responsive corporate website with sections for Home, About, Services, Products, Industry Solutions, AI & Innovation, Cybersecurity, Portfolio, Pricing, Resources, Careers, Partnerships and Contact.
- Original robot/AI hero illustration built as inline SVG (no external image dependency).
- Initial AURORA AI, Smart Cash Desk, Nexovara Business, Nexovara Secure and Nexovara Automate product records; administrators control publication status.
- Working enquiry and career application APIs.
- Client registration/login, project/invoice/ticket/subscription views and support ticket creation.
- Admin authentication, overview metrics, lead status management, customer listing, project creation, invoice creation/status updates, full product registry (create/edit/publish/draft/archive/feature/order) and career application listing.
- API health endpoint and OpenAPI docs at `/docs`.
- SQLite by default; PostgreSQL supported through `DATABASE_URL`.
- Optional SMTP notification configuration.

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux/Android terminal: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set a unique SECRET_KEY (32+ random characters), ADMIN_EMAIL and a strong ADMIN_PASSWORD
alembic upgrade head
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open:
- Website: http://localhost:8000
- Client portal: http://localhost:8000/portal
- Admin: http://localhost:8000/admin
- API documentation: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

The `.env.example` intentionally leaves required secrets and administrator credentials blank. Set them before first run. The first startup creates the administrator (only when both admin variables are set) and initial product catalogue. New seeded product records start as Draft so concepts are not advertised as live services until an administrator reviews and publishes them. If you change the admin password after the database has already been created, update the user through a secure password reset/admin process or remove the local development database and restart (only if you do not need its data).

## Deployment
### Render (simple low-cost start)
1. Push this folder to a private GitHub repository.
2. Create a new Web Service in Render and connect the repository.
3. Use the included `render.yaml` or configure build command `pip install -r requirements.txt` and start command `alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
4. Set `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and a persistent PostgreSQL `DATABASE_URL` in the service environment.
5. Add a persistent PostgreSQL database. Do not rely on an ephemeral filesystem for production SQLite data.
6. Add your real domain after testing.

### Important production settings
- Set `SECRET_KEY` to a cryptographically random secret (32+ random bytes).
- Use PostgreSQL, not ephemeral SQLite, in hosted production.
- Restrict CORS using `FRONTEND_ORIGIN` or comma-separated `CORS_ORIGINS`; wildcard origins are not enabled.
- Use HTTPS, backups, logging, monitoring and database migrations.
- The package includes security headers, optional shared Redis rate limiting, HttpOnly cookie sessions, origin checks for cookie-authenticated state changes, password reset, staff TOTP MFA and route-level staff permissions. These controls still require staging penetration testing and operational monitoring before sensitive production use.
- Replace the example company email and review legal pages.
- Set a real support contact, company address and social links.
- Add a production email provider's SMTP settings to enable enquiry notifications.

## Product catalogue management

Open `/admin`, sign in with the configured administrator, and choose **Products**. Create a product with a unique lowercase slug, description, semicolon-separated features/platforms, optional deployed/GitHub/documentation/demo URLs, optional image URL, display order and featured flag. New records default to **Draft**. Change status to **Published** to show the product on the public homepage; use **Draft** to hide it without archiving, or **Archive** to remove it from the public catalogue while retaining its record. Public endpoints are `GET /api/products`, `GET /api/products?search=...`, `GET /api/products?category=...`, `GET /api/products?featured=true`, and `GET /api/products/{slug}`. Admin create/list/edit/archive endpoints require an administrator token.

On startup, the app applies an additive compatibility migration for the new product metadata columns so an existing MVP database can be upgraded without dropping its product records. This is a small compatibility migration, not a replacement for a versioned Alembic migration system; formal migrations should be introduced before larger schema changes.

## Integrations and honest readiness status
**Working in this starter:** database persistence, registration/login, JWT-protected endpoints, enquiry submission, career applications, client support tickets, admin lead/project/invoice/product workflows and portal data views.

**Requires provider credentials and additional production configuration:** AURORA backend API, M-PESA Daraja merchant account, Stripe account, SMTP provider, Supabase private Storage bucket, ClamAV scanner, Redis and offsite backup bucket. Stripe Checkout with signed webhook validation and M-PESA STK/callback processing are implemented, but no live merchant transaction has been verified. Payment state changes only after provider callback checks; M-PESA still needs Transaction Status API reconciliation before production sign-off.

## Security note
This is a functional MVP foundation, not a fully audited enterprise production system. Have the authentication, authorization, privacy, payment and deployment configuration reviewed before using it with sensitive customer or financial data. Do not commit `.env`, database files, credentials or API keys to GitHub.

## Project structure
```text
backend/       FastAPI API, database models, schemas and security
frontend/      Single combined index.html
requirements.txt
.env.example
Dockerfile
render.yaml
```

## Stage 3 business-operations API additions

The operations layer now includes a public quote-request endpoint and protected admin review endpoints:

- `POST /api/quotes` — accept a quote request; new requests begin in `new` status.
- `GET /api/admin/quotes` — list quote requests (authenticated staff session with the required permission).
- `PATCH /api/admin/quotes/{quote_id}` — update status (`new`, `reviewing`, `quoted`, `accepted`, `declined`, `closed`) and internal notes.
- `GET /api/admin/audit-logs?limit=100` — view recent recorded administrative changes (authenticated staff session with the required permission; limit is capped at 500).

The audit log currently records lead status changes, project and invoice creation, invoice status changes, ticket updates, product creation/updates/archiving, and quote updates. It deliberately does not record passwords, access tokens, or payment credentials. Quote email notifications are attempted only when SMTP is configured; a successful HTTP response does not mean an email was delivered.

The new `quotes` and `audit_logs` tables are additive and are created by SQLAlchemy metadata initialization. Existing product-column compatibility migration remains in place. A formal Alembic revision history is still recommended before further complex schema evolution; this Stage 3 package does not claim to provide a complete migration framework.

Run the Stage 3 model smoke tests from the project root with:

```bash
python -m unittest discover -s tests -v
```


## Stage 4 — AURORA AI and Automation Studio

### AURORA AI connection
The NEXOVARA admin dashboard now includes an AURORA AI panel. It uses the existing AURORA backend routes found in the separate AURORA source: `GET /ai/native/models` (connection/authentication check), `POST /ai/native/chat/completions` (chat with AURORA's existing retrieval hook), and `POST /foundry/knowledge/ask` (direct knowledge-index question). The NEXOVARA server calls AURORA; the browser never receives the AURORA service token.

Configure these server environment variables:

- `AURORA_BASE_URL` — the deployed AURORA backend origin, for example `https://your-aurora-service.example` (no route suffix).
- `AURORA_API_TOKEN` — a valid AURORA bearer JWT for the service account whose knowledge base should be queried.

The AURORA source currently issues JWTs with a seven-day expiry. When it expires, the admin panel reports an authentication error; refresh the token using AURORA's own login flow and update the Render environment variable. Do not paste the token into the website or commit it to GitHub. The first release is administrator-only because the AURORA knowledge routes scope data to the authenticated AURORA user; sharing one service account across all NEXOVARA customers would risk mixing customer knowledge. A future customer-facing integration needs a tenant/user mapping design.

### Automation Studio
The admin dashboard supports real email-notification workflows for `lead.created`, `quote.created` and `ticket.created`. Each enabled workflow executes when that record is created and writes a success/failure record to the execution history. This release intentionally supports only the email-notification action, sent to the configured `ADMIN_EMAIL`; it does not claim arbitrary workflow execution, scheduled jobs, webhooks or document automation.

To enable a workflow, configure `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `ADMIN_EMAIL` on the server. SMTP delivery is recorded as successful only when the configured SMTP server accepts the message; this is not proof that a recipient read it or that final inbox delivery occurred. If SMTP is not configured, workflows can be created disabled but cannot be enabled.

Admin API routes: `GET /api/admin/integrations/aurora/status`, `POST /api/admin/integrations/aurora/chat`, `POST /api/admin/integrations/aurora/knowledge/ask`, `GET/POST /api/admin/automations`, `PATCH /api/admin/automations/{id}`, and `GET /api/admin/automations/runs`. These routes require a staff session with the relevant permission; AURORA and integration settings require `integrations.manage`.


## Consolidated platform release — Stage 5/6/7 foundations

This package consolidates the previously delivered Stage 1–4 work and adds the next available platform foundations in one source bundle. It is a consolidated implementation, not a claim that external merchant accounts, deployed AURORA services, legal approvals or production operations have been completed.

### New capabilities in this release

- **Partner relationship workflow:** public partnership application form/API, administrator review/status/notes, and audit entries.
- **Customer notifications:** administrator-created notifications, customer-only listing, and per-customer read acknowledgements.
- **Product licensing foundation:** administrator can issue a unique licence key to a customer and optionally link a product, set seats and expiry; customers can see only their own licences. This is an entitlement register, not a payment processor or cryptographic activation server.
- **Global defaults:** API exposes supported currency and locale choices plus default timezone. Amounts continue to be stored in their invoice currency; this release does not perform FX conversion or translate every static page.
- **Integration readiness panel/API:** reports whether server credentials are present for AURORA, SMTP, M-PESA and card payments. Credential presence is not a live integration test.
- **Security baseline:** security response headers, HttpOnly session cookies, origin checks, role permissions and Redis-backed shared throttling when `REDIS_URL` is configured. The per-process fallback is development-only.
- **Versioned migration foundation:** Alembic configuration and a non-destructive baseline revision. Revision `0002_production_services` also upgrades older product tables and invalidates legacy sessions.
- **Admin interface:** partner review, licence issuing and integration readiness tabs; customer portal includes licences and notifications.

### Migration and upgrade

For a fresh or existing database, install requirements and run:

```bash
alembic upgrade head
```

The baseline revision creates missing tables without dropping existing data. Revision `0002_production_services` adds the security/payment/file columns and product metadata columns to older schemas. The app no longer relies on `create_all()` at startup; Render runs Alembic before launching the web process. Back up production before upgrades. Future schema changes must be added as new Alembic revisions; do not edit an already-applied revision.

### New environment settings

- `DEFAULT_CURRENCY=KES`
- `DEFAULT_LOCALE=en`
- `DEFAULT_TIMEZONE=Africa/Nairobi`
- `STRIPE_WEBHOOK_SECRET` (used to verify Stripe webhook signatures)
- M-PESA variables: `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`

### Important external work still required before calling the system production-complete

1. **AURORA AI:** deploy AURORA, supply its real base URL and a renewable service token, test expired-token renewal, and design per-customer tenant isolation before exposing AURORA to client accounts. Current connection is administrator-only.
2. **M-PESA and cards:** Stripe Checkout plus signature-verified, idempotent webhook handling is implemented. Daraja STK push and callback reference/amount checks are implemented; Safaricom callback messages are not HMAC-signed, so configure Transaction Status API reconciliation and verify sandbox/merchant/live low-value transactions. Refunds, disputes, tax and full payout reconciliation remain outstanding.
3. **Email/domain:** configure verified SMTP sender/domain, SPF, DKIM and DMARC; test delivery and bounce handling.
4. **Identity hardening:** password reset, staff TOTP MFA, token-version session revocation, HttpOnly session cookies and a fixed role/permission map are implemented. Email verification, recovery codes, account lockout beyond rate limits and independent penetration testing remain outstanding.
5. **Files and documents:** private Supabase Storage uploads, per-user ownership checks, size/type validation, ClamAV fail-closed scanning and authenticated downloads are implemented. You must create the private bucket and deploy a reachable ClamAV scanner; automated retention policy and a security review remain outstanding.
6. **Operational resilience:** configure managed PostgreSQL backups and restore drills, central logs, error monitoring, uptime alerts, secret rotation, dependency scanning and a staging deployment.
7. **Compliance and content:** replace company placeholders, verify all published product claims, set support contacts, and have privacy/terms reviewed for the actual legal entity and operating regions.
8. **Localization:** locale/currency metadata is present, but page translation, locale-aware number formatting and foreign-exchange pricing are not yet implemented.

### Validation

Run all included persistence/schema tests with:

```bash
python -m unittest discover -s tests -v
```

Validate the frontend script with `node --check` after extracting the inline script if Node.js is available. Run the API with installed dependencies and test `/api/health`, registration/login, admin workflows and client isolation in a staging environment before production. The development environment used to assemble this ZIP did not have network access to install missing dependencies, so a full live backend start and provider integration test could not be certified here.

### API additions

- `GET /api/platform/config`
- `GET /api/admin/integrations/readiness`
- `POST /api/partners/apply`, `GET /api/admin/partners`, `PATCH /api/admin/partners/{id}`
- `GET /api/client/notifications`, `PATCH /api/client/notifications/{id}/read`, `POST /api/admin/notifications`
- `GET /api/client/licenses`, `GET /api/admin/licenses`, `POST /api/admin/licenses`
- `PATCH /api/admin/customers/{id}` to update account activation/company fields

Admin endpoints require an authenticated staff session (HttpOnly cookie or bearer token) and route-level permission checks; sensitive staff-management operations require the administrator role and MFA. Client endpoints derive the customer identity from the authenticated session and filter records by that identity.


# Render + Supabase production deployment profile

This project is configured for **Render Web Service + Supabase PostgreSQL**. Render hosts FastAPI; Supabase hosts PostgreSQL and private object storage. Browser authentication uses HttpOnly, Secure (in production), SameSite=Lax cookies rather than persistent JavaScript-readable localStorage tokens. The frontend is served by the same Render origin so the session cookie remains same-site. Do not place the Supabase service-role key, database password, Stripe secret, Daraja credentials, AURORA token or SMTP password in frontend code or GitHub.

## 1. Supabase PostgreSQL connection strings

In Supabase Dashboard, open **Connect** and copy the connection URLs; do not construct the host or username manually. Render deployments commonly need IPv4 connectivity, so use Supabase's shared pooler:

- `DATABASE_URL`: shared **transaction** pooler URL (port `6543`) for the web request workload. The SQLAlchemy driver disables prepared statements and uses `NullPool` for this mode.
- `MIGRATION_DATABASE_URL`: shared **session** pooler URL (port `5432`) for Alembic migrations and `pg_dump`/restore. This URL is used by the Render start command's `alembic upgrade head`.

Both URLs should be copied exactly from Supabase's Connect panel with the database password URL-encoded. TLS is required by the application. If you prefer to use one URL only, use the session pooler URL on port 5432 for both settings; this is simpler but has different connection-pooling characteristics. Do not use the direct `db.<project>.supabase.co:5432` address from an IPv4-only Render environment unless your Supabase project has IPv4 connectivity enabled.

References: Supabase connection modes and SQLAlchemy guidance; Render's Supabase connectivity guide. https://supabase.com/docs/guides/database/connecting-to-postgres and https://render.com/articles/how-to-connect-a-render-service-to-supabase-postgres

## 2. Render Web Service environment

Create or update the Render Web Service from this repository. Use the included `render.yaml` or set:

- Build: `pip install -r requirements.txt`
- Start: `alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`

Set the environment values from `.env.example` in Render Dashboard > Environment. Render should generate `SECRET_KEY` and `MFA_ENCRYPTION_KEY`; set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `PUBLIC_APP_URL`, `DATABASE_URL`, and `MIGRATION_DATABASE_URL`. The administrator password must be at least 12 characters. Keep the Render service private to the expected domain using `CORS_ORIGINS` if you later separate the frontend.

The included Blueprint currently leaves the web service plan at `free` to avoid silently selecting a paid plan. For an always-on production service, select an appropriate paid Render plan and check Render's current limits and pricing before launch.

## 3. Supabase Storage setup

In Supabase Storage, create a bucket named `nexovara-private` and set it to **Private**. Do not enable public access. Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to Render; the service-role key is server-only and bypasses Storage RLS, so the FastAPI endpoints enforce per-user ownership before downloads. Restrict dashboard access to trusted operators and rotate the key if exposed.

Uploads are limited by `MAX_UPLOAD_BYTES`, extension and basic content-signature checks. They are rejected unless a reachable ClamAV daemon is configured with `CLAMAV_HOST` and `CLAMAV_PORT`. Run the scanner as a private service on a private network; do not expose its TCP port publicly. Allowed file types: PDF, PNG, JPEG, TXT, CSV and DOCX. The current implementation streams through the API and stores only metadata/path/hash in PostgreSQL.

## 4. Redis rate limiting

Provision a Render Key Value/Redis instance (or another private Redis service) and set `REDIS_URL` on the web service. When configured, auth and public form throttling uses shared Redis counters. If Redis is not configured, the app falls back to per-process in-memory throttling; that fallback is not sufficient for multi-instance production. If Redis is configured but unreachable, protected submission requests fail closed with HTTP 503.

## 5. Staff MFA and RBAC

Staff roles are `admin`, `operations_manager`, `finance_manager`, `support_agent`, `content_manager`, and `developer`. The admin role has full permissions; other roles have a fixed least-privilege permission map in `backend/security.py`. Existing admin routes enforce permissions based on route and HTTP method. Create staff accounts through `/api/admin/staff` while signed in as an MFA-enabled admin.

`MFA_REQUIRED_FOR_STAFF=true` is the default. The first administrator can sign in using the bootstrap credentials only to enroll MFA; staff administration routes are blocked until MFA is enabled. After the first administrator sign-in, the `/admin` page guides the administrator through enrollment. The API endpoints are `POST /api/auth/mfa/setup`, then `POST /api/auth/mfa/confirm` with the current six-digit code. Confirmation revokes the setup session; sign in again and complete the challenge at `/api/auth/mfa/verify`. Client accounts are not forced to enroll by this setting. Back up authenticator recovery material securely; no MFA bypass endpoint is provided.

Password reset is a one-time, hashed, 30-minute token delivered through SMTP. Session tokens carry a token version; password reset, logout and revoke-all increment it, invalidating older sessions. Browser sessions are stored in HttpOnly cookies, not localStorage. Keep `MFA_ENCRYPTION_KEY` backed up securely; rotating it requires staff MFA re-enrollment. Use HTTPS only.

## 6. Payments

### Stripe

The code creates Stripe Checkout sessions for the authenticated customer's own unpaid invoice. Configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PUBLIC_APP_URL`, and a webhook in Stripe Dashboard pointing to `https://YOUR-RENDER-HOST/api/webhooks/stripe`. Subscribe to `checkout.session.completed`. The webhook validates Stripe's signature, checks payment metadata, amount and currency, and is idempotent by Stripe event ID before marking the invoice paid. Test with Stripe test keys and test cards before enabling live keys. Refunds, disputes, tax, reconciliation and a complete accounting ledger are not included.

### M-PESA Daraja

Configure Daraja app credentials and shortcode/passkey in Render. Keep `MPESA_ENV=sandbox` first. Set `PUBLIC_APP_URL`; Render generates `MPESA_CALLBACK_TOKEN`, which creates an unguessable callback path. The customer endpoint `POST /api/payments/mpesa/stk-push` accepts an invoice ID and Kenyan mobile number. The callback validates the secret path, checkout reference, receipt, amount and invoice currency and is idempotent. It marks the invoice paid only after a successful callback with matching values. Daraja callbacks are not a cryptographically signed webhook in the same way as Stripe; the path token and transaction/reference checks reduce spoofing risk, but production reconciliation against Safaricom's Transaction Status API and live sandbox/merchant certification are still required. Do not switch `MPESA_ENV=live` until Safaricom approves the shortcode and callback URL and a real low-value transaction has been reconciled.

## 7. SMTP verification

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `ADMIN_EMAIL`. The app uses STARTTLS and authenticates. As an administrator with MFA, call `POST /api/admin/integrations/smtp/test`; a successful response means the SMTP server accepted the message, not that it reached the inbox. Verify SPF, DKIM and DMARC at your sender domain and check inbox, spam and provider delivery logs.

## 8. Automated backups

The separate `render-backup.yaml` defines a daily Render Cron Job. Deploy it separately after configuring `BACKUP_BUCKET`, `BACKUP_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `BACKUP_ENDPOINT_URL`, and `MIGRATION_DATABASE_URL` using Supabase session pooler port 5432. It runs `pg_dump` and uploads a custom-format dump with S3 server-side AES256 encryption. Configure a bucket lifecycle policy for retention and enable bucket versioning/object lock if your backup provider supports it. A successful upload is not a tested restore.

A manual restore helper is provided at `scripts/restore_postgres.py`. It refuses to run unless `CONFIRM_RESTORE=YES` is set. Restore into a separate staging Supabase project first, verify row counts, key workflows and application login, then document the recovery time. Do not run restore against production without a maintenance window and a verified backup.

## 9. AURORA settings

`AURORA_PUBLIC_URL` is prefilled with the GitHub Pages product link supplied by the owner: `https://joseph-web-max.github.io/AURORA-AI-v2/`. This is the public product page, not the API host. Set `AURORA_BASE_URL` to the deployed AURORA FastAPI backend origin and `AURORA_API_TOKEN` to a valid renewable server token. The NEXOVARA integration remains admin-only until per-customer data/knowledge isolation is designed and tested.

## 10. Important production boundaries

- M-PESA callback processing has shared-secret URL validation and transaction-field matching, not provider-signed HMAC. Implement periodic Transaction Status API reconciliation before accepting it as a final financial control.
- Secure file upload requires a private Supabase bucket and reachable ClamAV scanner; uploads deliberately fail closed if scanning is absent.
- Redis must be configured for distributed throttling. In-memory fallback is only a development fallback.
- Supabase database backups depend on your Supabase plan and retention settings; the optional S3 Cron backup is a second copy, not a substitute for point-in-time recovery where required.
- Legal pages remain templates. A qualified reviewer must adapt privacy, terms, retention, cookies, cross-border processing, tax and consumer terms to the legal entity and regions where NEXOVARA operates.
- The payment flow does not include refunds, disputes, tax/VAT, payout reconciliation or a formal double-entry accounting subledger.
- The full live system cannot be certified from source checks alone. Complete staging tests, merchant sandbox/live tests, restore drill, security assessment and monitoring before launch.

## 11. Staging validation

Install dependencies and run:

```bash
pip install -r requirements.txt
alembic upgrade head
python -m unittest discover -s tests -v
uvicorn backend.main:app --reload
```

Verify `/api/health`, staff MFA enrollment/login, role-denied routes, password reset mail, private file upload/download with ClamAV, Stripe test Checkout/webhook, Daraja sandbox STK/callback, SMTP test, Redis throttling and a backup restore into a separate Supabase staging project. Do not mark a provider live based solely on configured environment variables.

---

# Stage 8 — correction pass

**Fixed**
- `requirements.txt`: pinned `bcrypt==4.0.1`. `passlib 1.7.4` crashes on first password hash with bcrypt 5.x, which would have broken registration and login on a fresh Render build.
- `backend/main.py`: `DATABASE_URL` was used in `/api/health` but never imported, so health returned HTTP 500 for any non-Supabase database URL.
- Payments: an abandoned Stripe or M-PESA attempt left a `pending` row that blocked the invoice forever. Stale attempts now expire (Stripe sessions are created with a 31-minute expiry; M-PESA after 10 minutes), `checkout.session.expired` is handled, and a late successful M-PESA callback still reconciles.
- Origin check no longer rejects requests from the site's own host when it differs from `PUBLIC_APP_URL` (e.g. custom domain vs `onrender.com`).
- Password-reset expiry comparison handles timezone-aware and naive timestamps.
- Paid invoices can no longer be reopened through the admin API.
- Role gaps: `finance_manager` could not load the Licences tab (needed `products.view`); `operations_manager` lacked `careers.view`.
- Frontend: downloaded documents lost their filename/extension; validation errors showed `[object Object]`; error styling persisted after a successful submit; first admin tab was not highlighted.
- SMTP: port 465 (implicit TLS) supported; failures are logged instead of silently ignored; notification emails no longer block form submissions.
- `.env.example` duplicate key and inline comment removed; `.dockerignore` added; `PYTHON_VERSION` pinned in `render.yaml`.

**Completed so every page uses its backend**
- Public site: quote-request form (`POST /api/quotes`) with per-product "Request a quote"; expandable resource articles.
- Client portal: live payment status (`GET /api/payments/{id}`), Stripe return handling, licence product names.
- Admin: customer enable/disable, project status/progress editing (`PATCH /api/admin/projects/{id}`), invoice status control, ticket replies (notify the customer in-portal and by email), article management (`/api/admin/articles`), customer notifications, customer dropdowns instead of numeric IDs.
- Validation: careers applications, project progress/status, invoice currency, article slugs.

**Not verifiable from code alone** (needs your credentials/services): Stripe and Daraja sandbox transactions, SMTP delivery, ClamAV, Supabase Storage, Redis, and the AURORA service.
