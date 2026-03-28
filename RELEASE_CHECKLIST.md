# Macro Suite Release Checklist

## Deploy First

1. Confirm the API health check returns `200` at `https://macro-suite-license-api.onrender.com/health`.
2. Confirm the dashboard health check returns `200` at `https://macro-suite-license-admin.onrender.com/health`.
3. Confirm the dashboard login works with the production admin credentials.
4. Confirm the dashboard service `ADMIN_API_TOKEN` exactly matches the API service `ADMIN_API_TOKEN`.
5. Generate one new test key from the dashboard.

## Contract Check

6. Activate that key on a clean test machine or VM.
7. Verify `validate` succeeds after activation.
8. Verify `heartbeat` succeeds after activation.
9. Verify dashboard actions work:
   - extend
   - disable
   - ban
   - restore
   - reset-device
10. Verify audit logs record every admin action.

## Device/Test Hygiene

11. If you switch test machines, either use `reset-device` in the dashboard or issue a fresh key.
12. If a tester gets stale offline-cache behavior, delete:
    - `%APPDATA%\Jay\Macro Suite\Licensing\license_state.dat`

## Packaging Gate

13. Build the packaged runtime from `runtime_templates/macro_suite.runtime.production.json`.
14. Update only the packaged `macro_suite.runtime.json` next to `Macro Suite.exe`.
15. Verify `license_server_url` points to the real deployed Render API URL.
16. Verify the packaged runtime uses `sign_requests=false`.
17. Verify the packaged runtime sets `client_shared_secret=null` and `device_hmac_key=null`.
18. Verify no `localhost`, `127.0.0.1`, or tunnel URL remains anywhere in the customer release folder.
19. Verify the customer release folder contains only one runtime config file.
20. Verify the packaged bytecode includes the separated `app/licensing` client layer.
21. If you intentionally re-enable signatures, verify the packaged `client_shared_secret` matches the deployed API and document why signatures are enabled.
22. Rebuild the customer package only after steps 1-21 pass.
23. Do not send any zip that was built before the current API deployment was verified.
