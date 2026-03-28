# Deploy Macro Suite on Render

## Repo Layout

Publish the contents of `render_stack` as the root of the Render deployment repo.

- `render.yaml`
- `services/license_api`
- `services/admin_dashboard`

Do not point Render at the parent `macor tool` folder. The blueprint and Docker contexts assume this folder is the repo root.

## Intended Production Values

- API URL: `https://macro-suite-license-api.onrender.com`
- Dashboard URL: `https://macro-suite-license-admin.onrender.com`
- Database engine: Render PostgreSQL
- Migration mode: API container runs `alembic upgrade head` before `uvicorn`
- Customer runtime template: `runtime_templates/macro_suite.runtime.production.json`
- Signature mode for public shipping: unsigned client requests
- Timezone behavior: API timestamps, license expiries, and activation token expiries are stored and returned in UTC

## Required Render Env Vars

API service:

- `API_ENVIRONMENT=production`
- `DATABASE_URL=<Render Postgres connection string>`
- `PUBLIC_BASE_URL=https://macro-suite-license-api.onrender.com`
- `DASHBOARD_BASE_URL=https://macro-suite-license-admin.onrender.com`
- `ADMIN_API_TOKEN=<long random token>`
- `LICENSE_KEY_SECRET=<long random secret>`
- `ACTIVATION_TOKEN_SECRET=<long random secret>`

Dashboard service:

- `DASHBOARD_ENVIRONMENT=production`
- `DASHBOARD_PUBLIC_BASE_URL=https://macro-suite-license-admin.onrender.com`
- `LICENSE_API_BASE_URL=https://macro-suite-license-api.onrender.com`
- `ADMIN_API_TOKEN=<exact same value used on the API service>`
- `DASHBOARD_ADMIN_USERNAME=<your bootstrap admin username>`
- `DASHBOARD_ADMIN_PASSWORD=<your bootstrap admin password>`
- `DASHBOARD_SESSION_SECRET=<long random secret>`

Optional only if you intentionally re-enable signed client requests:

- API service: `REQUIRE_CLIENT_SIGNATURES=true`
- API service: `CLIENT_SHARED_SECRET=<brand-new long random secret>`

Leave the current production path unsigned so the customer build does not ship a shared client secret.

## Blueprint Deploy Order

1. Create a new GitHub repo whose root is the contents of `render_stack`.
2. Push the repo.
3. In Render, create a Blueprint from that repo.
4. Let Render provision the Postgres database first.
5. Save the required secrets on the API service and the dashboard service before trusting the first green deploy.
6. Confirm the dashboard service `ADMIN_API_TOKEN` exactly matches the API service `ADMIN_API_TOKEN`.
7. Trigger a fresh deploy on the API service.
8. Wait for the API logs to show `alembic upgrade head` completed and `uvicorn` started.
9. Trigger or confirm the dashboard deploy after the API URL and token values are correct.

## Bootstrap Admin Flow

1. Choose the dashboard username and password before the first live deploy.
2. Set those values in the dashboard service env vars.
3. Deploy the dashboard.
4. Open `https://macro-suite-license-admin.onrender.com`.
5. Sign in with the bootstrap credentials.
6. Generate one new test key before packaging any customer build.

## Runtime Packaging Contract

- The desktop app reads the packaged `macro_suite.runtime.json` next to `Macro Suite.exe`.
- The desktop app only talks to the API through the separated `app/licensing` client layer.
- The customer-safe runtime template is `runtime_templates/macro_suite.runtime.production.json`.
- Public shipping mode is:
  - `REQUIRE_CLIENT_SIGNATURES=false` on the API
  - `sign_requests=false` in the packaged runtime
  - `client_shared_secret=null` in the packaged runtime
  - `device_hmac_key=null` in the packaged runtime

Those null fields intentionally block stale local override files from reintroducing retired secrets.

## Post-Deploy Checks Before Shipping

1. Verify `https://macro-suite-license-api.onrender.com/health` returns `200`.
2. Verify `https://macro-suite-license-admin.onrender.com/health` returns `200`.
3. Sign in to the dashboard with the production bootstrap credentials.
4. Generate a fresh test key from the dashboard.
5. Activate that key on a clean machine or VM with the exact build you plan to ship.
6. Verify `validate` succeeds after activation.
7. Verify `heartbeat` succeeds after activation.
8. Verify dashboard actions work:
   - extend
   - disable
   - ban
   - restore
   - reset-device
9. Verify audit logs record every admin action.
10. Only after those checks pass, rebuild the customer zip using the exact deployed API URL.

## Notes for Free Render

- Free services can sleep after inactivity.
- The desktop client already retries transient failures before showing a user-facing wake-up message.
- The first activation attempt after a long idle period may take longer than a warm service.
