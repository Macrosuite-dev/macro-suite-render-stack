# Macro Suite Render Stack

This folder contains the permanent-host deployment stack for Macro Suite licensing:

- `services/license_api`: FastAPI license API backed by PostgreSQL and Alembic.
- `services/admin_dashboard`: separate admin dashboard service with login and searchable license inventory.
- `render.yaml`: Render blueprint for the API, dashboard, and Postgres.
- `.dockerignore`: keeps local logs, sqlite files, and smoke-test artifacts out of Docker builds.
- `.env.example`: production-oriented environment template for Render.
- `.env.local.example`: local-only environment template for smoke tests.
- `DEPLOY_RENDER.md`: exact production deployment steps.
- `RELEASE_CHECKLIST.md`: pre-ship checklist that prevents dead URLs and secret mismatches.
- `SECRET_ROTATION.md`: client-auth and secret-rotation guidance.
- `runtime_templates/macro_suite.runtime.production.json`: customer-safe runtime config for the packaged desktop app.

The desktop app should only talk to the packaged runtime `macro_suite.runtime.json` and the `app/licensing` client layer inside `C:\MacroSuite\dev`.

Use this folder as the repo root when creating the Render GitHub repo. The blueprint and Docker contexts assume `render.yaml` is at the repository root.
