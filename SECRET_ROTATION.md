# Macro Suite Secret Rotation

## Server-Only Secrets

These must stay only on the API or dashboard service:

- `ADMIN_API_TOKEN`
- `LICENSE_KEY_SECRET`
- `ACTIVATION_TOKEN_SECRET`
- `DASHBOARD_SESSION_SECRET`
- `DASHBOARD_ADMIN_PASSWORD`

Do not ship any of those in the customer package.

## Client Authentication Strategy

Current recommended production mode:

- API: `REQUIRE_CLIENT_SIGNATURES=false`
- Customer runtime: `sign_requests=false`
- Customer runtime: `client_shared_secret=null`
- Customer runtime: `device_hmac_key=null`

That removes the shared client secret from the customer package while keeping the same API contract for activation, validation, and heartbeat.

The null runtime fields are intentional. They keep old local override files from silently injecting a retired shared secret back into a newer unsigned build.

## If An Older Build Already Shipped A Client Secret

1. Leave the API in `REQUIRE_CLIENT_SIGNATURES=false`.
2. Replace the next packaged runtime with `client_shared_secret=null` and `device_hmac_key=null`.
3. Rebuild the customer package.
4. Treat the old shared client secret as retired.

Because the API no longer enforces client signatures, the leaked client secret is no longer trusted for production access control.

## If You Intentionally Re-Enable Signatures Later

1. Generate a brand-new `CLIENT_SHARED_SECRET`.
2. Set `REQUIRE_CLIENT_SIGNATURES=true` on the API.
3. Set the new `CLIENT_SHARED_SECRET` on the API.
4. Put the matching `client_shared_secret` and `sign_requests=true` into the packaged runtime.
5. Rebuild the customer zip.
6. Do not mix old signed builds and new signed builds unless they share the same secret by design.

## Rotation Trigger Events

Rotate and rebuild if any of these happen:

- a signed customer package leaks
- a tester receives the wrong runtime config
- the API is deployed with the wrong signature mode
- you move from unsigned mode back to signed mode
