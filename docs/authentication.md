# Browser authentication sessions

OpenCI keeps bearer access tokens short lived and in browser memory. The API returns an access token from `POST /users/login` and sets a host-only, `HttpOnly` refresh cookie scoped to `/users`. The browser restores a session after reload by calling `POST /users/refresh`; the refresh token is never exposed to JavaScript or stored in web storage.

## Session policy

- Access tokens expire after 15 minutes by default. `ACCESS_TOKEN_EXPIRE_MINUTES` may lower this value, and the API rejects values above 15.
- A login session has a fixed eight-hour maximum lifetime and a 30-minute idle timeout.
- Only visible user interaction extends the idle timeout. The frontend sends a throttled activity request after clicks, key presses, or touch input; API polling and background refresh do not count as activity.
- Every refresh rotates the opaque random token. Only its SHA-256 hash and generation are stored. Reuse of a consumed token outside the short concurrent-request grace window revokes the session.
- User deactivation and role changes revoke all of that user’s sessions. Celery Beat removes expired session history after its retention period.

## Browser and deployment settings

`CORS_ALLOWED_ORIGINS` must list the exact browser origin. Login, refresh, and logout also require the `X-CSRF-Token` request header and a matching `Origin` (or `Referer`) value. The frontend sends credentials only to those authentication endpoints.

The refresh cookie uses `HttpOnly`, `SameSite=Lax`, no `Domain`, and `Path=/users`. Production Compose enables `Secure` and uses the `__Secure-` cookie name. Local Compose defaults Secure off so HTTP development also works; never use that setting in production. Configure `AUTH_REFRESH_COOKIE_SAMESITE=None` only when the frontend and API are genuinely cross-site, and keep Secure enabled in that case.

Deploy the additive migration `0013_jwt_refresh_sessions` before serving the new backend and frontend. Existing access tokens do not contain a server session ID, so users sign in once after rollout. Keep exactly one Celery Beat instance active so session cleanup is not duplicated.

When a session ends, the frontend blocks the current page and asks the user to sign in again. This keeps an in-progress report form mounted while reauthentication occurs. Signing in as a different user remounts the authenticated workspace and discards the previous account’s in-memory view state.
