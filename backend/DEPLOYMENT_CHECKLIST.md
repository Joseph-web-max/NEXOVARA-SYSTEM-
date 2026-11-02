# Deployment checklist — Render + Supabase

## Supabase
- [ ] Back up the current project before applying schema changes.
- [ ] In Supabase **Connect**, copy the shared transaction pooler URL (port 6543) into Render `DATABASE_URL`.
- [ ] Copy the shared session pooler URL (port 5432) into Render `MIGRATION_DATABASE_URL`.
- [ ] Create a Storage bucket named `nexovara-private` and set it to **Private**.
- [ ] Copy the project URL and service-role key into Render `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Never expose the service-role key to the browser.

## Render Web Service
- [ ] Connect the GitHub repository containing this release.
- [ ] Use `pip install -r requirements.txt` as build command.
- [ ] Use the start command from `render.yaml`.
- [ ] Set `ENVIRONMENT=production`.
- [ ] Generate `SECRET_KEY` and `MFA_ENCRYPTION_KEY` in Render.
- [ ] Set `ADMIN_EMAIL`, `ADMIN_PASSWORD` (12+ characters), `PUBLIC_APP_URL`, `CORS_ORIGINS`, `DATABASE_URL`, and `MIGRATION_DATABASE_URL`.
- [ ] Keep `COOKIE_SECURE=true`.
- [ ] Confirm `/api/health` reports the database connected.
- [ ] Confirm Render deployment logs show Alembic upgrade completed before Uvicorn starts.

## Security services
- [ ] Provision private Redis/Render Key Value and set `REDIS_URL`.
- [ ] Deploy a private ClamAV daemon and set `CLAMAV_HOST`/`CLAMAV_PORT`. Until configured, uploads are intentionally rejected.
- [ ] Sign in at `/admin`; complete authenticator-app MFA enrollment; sign in again with the code.
- [ ] Create staff accounts with least privilege; verify denied routes for each role.
- [ ] Test password reset email and logout/session revocation.

## External integrations
- [ ] Set AURORA backend origin and renewable service token. Do not use the GitHub Pages product URL as `AURORA_BASE_URL`.
- [ ] Set SMTP provider settings and verify SPF, DKIM and DMARC; use the SMTP test action.
- [ ] Set Stripe test keys and register `https://YOUR-RENDER-HOST/api/webhooks/stripe` for `checkout.session.completed`.
- [ ] Set Daraja sandbox credentials and callback URL; test STK push and callback. Keep `MPESA_ENV=sandbox` until merchant approval and reconciliation are complete.

## Backups and launch
- [ ] Configure an S3-compatible bucket and credentials.
- [ ] Deploy `render-backup.yaml` separately as a Render Cron Job. Note that the included Cron plan is paid; review Render pricing before deploying.
- [ ] Run a backup and restore it into a separate Supabase staging project.
- [ ] Test customer isolation, payments, webhooks, file scanning, email, Redis, logs and error alerts.
- [ ] Obtain legal/privacy review and complete support/contact details.
- [ ] Upgrade the web service from Render Free to an always-on paid plan before relying on it for production traffic.
