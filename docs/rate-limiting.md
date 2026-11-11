# API rate limiting

## Design

Collector uses one Redis-backed sliding-window limiter shared by FastAPI workers. A Lua script prunes expired sorted-set entries, checks the current count, adds an allowed request, and updates the TTL in one atomic operation. Keys are namespaced by deployment and contain hashes of identities rather than raw account identifiers or IP addresses.

Authenticated API routers use a shared per-user general counter (240 requests/60 seconds) and a shared write counter (120/60 seconds). `POST`, `PUT`, `PATCH`, and `DELETE` operations consume both. Planning generation, location confirmation, automatic assignment requests, and route-refresh retries also consume a distinct per-user planning counter (3/minute); saved route reads stay on the general policy. Existing database job state/deduplication remains authoritative for concurrent planning work.

Login requests consume a per-IP counter (30/15 minutes). Invalid credentials additionally consume a per-submitted-account HMAC counter (5/15 minutes). That account counter is checked only after credential verification fails, so a correct password is never denied because of previous failures. A successful login clears that account’s failure counter. The public auth error stays generic, and no permanent lockout is added. Refresh and logout use per-IP and, when present, per-session counters (30/minute).

Sensitive auth, session, and planning actions fail closed with HTTP 503 if Redis cannot enforce the policy. Routine authenticated reads fail open. Authenticated writes use a separate fail-closed 120/minute counter because they can mutate assignments, reports, schedules, or account state. Redis errors are logged by category with per-process cooldown; raw Redis keys and identity values are not logged. Rate-limit denial logs aggregate counts by policy category. Client IP uses `request.client.host`; forwarded headers are only usable in production when Uvicorn is explicitly configured with `FORWARDED_ALLOW_IPS` for the actual trusted proxy addresses. The production default trusts loopback only; operators behind a different proxy must set the exact proxy IP/CIDR list rather than `*`.

HTTP 429 responses use the existing FastAPI `detail` envelope and include `code`, `message`, `retry_after_seconds`, `Retry-After`, and `X-RateLimit-*` metadata. Redis enforcement failures use HTTP 503 and `RATE_LIMIT_UNAVAILABLE`. Frontend `ApiError` preserves Retry-After; `useResource` shows a wait message and suppresses automatic/manual repeat requests until the cooldown expires. The API client does not refresh tokens or sign out on 429.

## Defaults and isolated test profile

Normal/default policy values:

| Policy | Limit | Window |
|---|---:|---:|
| General authenticated API | 240 | 60 seconds |
| Authenticated writes | 120 | 60 seconds |
| Login requests per IP | 30 | 900 seconds |
| Invalid attempts per account identifier | 5 | 900 seconds |
| Refresh/logout per IP or session | 30 | 60 seconds |
| Planning enqueue/retry | 3 | 60 seconds |

`compose.ratelimit-test.yaml` sets an isolated namespace and Redis database 15, with a general API limit of 30/60 seconds. It also raises the test login IP cap to 200 so a six-request account-failure test exercises the account counter rather than the IP counter. Do not use this override in production. It does not change default values in `compose.yaml`.

## Windows PowerShell: local Docker test guide

Commands use the repository’s verified service names and ports: API `backend` at `localhost:8000`, Redis `redis` at `localhost:6379`, and Postgres `postgres` at `localhost:5432`. Run commands from `C:\Users\SPM\Projects\openci-web`. The backend container runs Python 3.14; `httpx` and `pytest` are installed from `backend/requirements.txt`. The root `scripts` folder is mounted read-only at `/workspace/scripts` in the development backend container.

### 1. Start the test configuration

From the repository root:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml up -d --build postgres redis backend
```

This starts the local API and data services with test-only 30/minute general policy and Redis DB 15. It requires the existing local `.env` values needed by Compose, including `JWT_SECRET_KEY`. It does not start the Celery worker or geospatial profile because these tests do not require them.

Check service status and recent logs:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml ps
docker compose -f compose.yaml -f compose.ratelimit-test.yaml logs --tail 100 postgres redis backend
```

Confirm the API is responding:

```powershell
Invoke-RestMethod http://localhost:8000/
```

Expected body includes `OpenCI Operations API`; `postgres` and `redis` should be healthy and `backend` running.

Confirm effective non-secret policy values inside the test backend:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T backend python -c "from app.config.settings import RATE_LIMIT_GENERAL_LIMIT, RATE_LIMIT_GENERAL_WINDOW_SECONDS, RATE_LIMIT_NAMESPACE, RATE_LIMIT_REDIS_URL; print(RATE_LIMIT_GENERAL_LIMIT, RATE_LIMIT_GENERAL_WINDOW_SECONDS, RATE_LIMIT_NAMESPACE, RATE_LIMIT_REDIS_URL)"
```

Expected output begins with `30 60 collector:ratelimit:test redis://redis:6379/15`.

### 2. Run automated tests

The tests use Redis DB 15 and a unique per-test namespace. They only delete keys under the namespace they created; they never flush a Redis database.

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T -e RATE_LIMIT_TEST_REDIS_URL=redis://redis:6379/15 backend python -m pytest tests/test_rate_limit.py tests/test_auth_rate_limit.py -q
```

Expected: passing boundary, expiry, identity, concurrency, shared-counter, outage, and login-failure tests. They skip only if their isolated Redis URL cannot be reached. To run all existing backend tests too:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T backend python -m pytest tests -q
```

### 3. Obtain a local test token without printing it

Use a dedicated local test account. The login route is `POST /users/login` and requires an allowed `Origin` plus `X-CSRF-Token: 1`.

```powershell
$testEmail = Read-Host "Local test account email"
$securePassword = Read-Host "Local test account password" -AsSecureString
$plainPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password
$loginBody = @{ email = $testEmail; password = $plainPassword } | ConvertTo-Json
$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/users/login" -Method Post -ContentType "application/json" -Headers @{ Origin = "http://localhost:5173"; "X-CSRF-Token" = "1" } -Body $loginBody
$env:RATE_LIMIT_TEST_TOKEN = $loginResult.access_token
Remove-Variable plainPassword, securePassword, loginBody, loginResult
```

The access token remains in the current PowerShell process and is not printed. The example endpoint `GET /locations/regions` is authenticated and does not require query parameters.

### 4. Scenario B: controlled 90-request test

This sends 90 requests paced across 40 seconds under the explicit 30/60 test policy. With a fresh identity and no concurrent requests using its counter, expect 30 successful responses, 60 HTTP 429 responses, and a positive `Retry-After` value on every 429.

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T -e "RATE_LIMIT_TEST_TOKEN=$env:RATE_LIMIT_TEST_TOKEN" backend python /workspace/scripts/test_rate_limits.py --base-url http://localhost:8000 --endpoint /locations/regions --method GET --count 90 --duration 40 --concurrency 10 --mode general --expected-allowed 30 --expected-429 60
```

The output reports successful, authentication-failure, 429, and other responses separately. `401`, `403`, `404`, `500`, network errors, unexpected response counts, or a missing/invalid `Retry-After` make the result FAIL.

### 5. Scenario A: below production/default limit

First restore base configuration (step 9 below), then verify the effective policy is `240 60`. Obtain a fresh token and run:

```powershell
docker compose exec -T -e "RATE_LIMIT_TEST_TOKEN=$env:RATE_LIMIT_TEST_TOKEN" backend python /workspace/scripts/test_rate_limits.py --base-url http://localhost:8000 --endpoint /locations/regions --method GET --count 90 --duration 40 --concurrency 10 --mode general --expected-allowed 90 --expected-429 0
```

With a fresh counter and no other restriction, expected output is 90 successful responses and 0 HTTP 429. This verifies the production/default policy does not incorrectly reject the 90-request workload.

### 6. Login failure scenario

Use a dedicated test account and intentionally incorrect password. In PowerShell, set only non-secret test data; the bad password must not be the actual test-account password:

```powershell
$env:RATE_LIMIT_TEST_EMAIL = Read-Host "Dedicated local test account email"
$env:RATE_LIMIT_TEST_BAD_PASSWORD = "IntentionallyWrong-RateLimit-Test-2026!"
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T -e "RATE_LIMIT_TEST_EMAIL=$env:RATE_LIMIT_TEST_EMAIL" -e "RATE_LIMIT_TEST_BAD_PASSWORD=$env:RATE_LIMIT_TEST_BAD_PASSWORD" backend python /workspace/scripts/test_rate_limits.py --base-url http://localhost:8000 --endpoint /users/login --method POST --count 6 --duration 3 --concurrency 1 --mode login --expected-allowed 0 --expected-auth-failures 5 --expected-429 1
```

Expected: five generic `401` authentication failures, followed by one account-throttled `429`. The test IP ceiling is 200/15 minutes, so it does not mask the account counter. A valid login is tested separately in pytest after accumulated failures and must succeed and clear that account counter. Remove the temporary values afterward:

```powershell
Remove-Item Env:RATE_LIMIT_TEST_EMAIL, Env:RATE_LIMIT_TEST_BAD_PASSWORD -ErrorAction SilentlyContinue
```

### 7. Check Retry-After and inspect isolated Redis keys

The standalone script validates that each 429 has a positive integer `Retry-After`. To inspect only keys under the rate-limit test namespace:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T redis redis-cli -n 15 --scan --pattern "collector:ratelimit:test:*"
```

Keys contain policy names and hashes, not raw account identifiers. To inspect expiry for one listed key, copy that key into:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T redis redis-cli -n 15 TTL "PASTE_ONE_TEST_NAMESPACE_KEY"
```

Do not run `FLUSHDB` or delete keys outside the test namespace.

### 8. Verify window recovery and counter sharing

After the 90-request run, wait longer than the full 60-second sliding window after its final request:

```powershell
Start-Sleep -Seconds 61
```

After the wait, send one request with the same token to confirm that the counter recovered:

```powershell
docker compose -f compose.yaml -f compose.ratelimit-test.yaml exec -T -e "RATE_LIMIT_TEST_TOKEN=$env:RATE_LIMIT_TEST_TOKEN" backend python /workspace/scripts/test_rate_limits.py --base-url http://localhost:8000 --endpoint /locations/regions --method GET --count 1 --duration 1 --concurrency 1 --mode general --expected-allowed 1 --expected-429 0
```

Expected: 1 successful response and 0 HTTP 429. Sending another 90-request burst would again produce 30 allowed and 60 limited responses. Automated tests verify that two separate API paths share the same general user counter and that a different user gets a separate counter. Planning retries use an additional distinct policy at `POST /planning/investigations/{investigation_id}/retry`; saved route reads use only the general policy.

### 9. Restore ordinary local configuration

Remove the test overlay from the Compose command and recreate the backend using only the base file:

```powershell
docker compose up -d --force-recreate backend
docker compose ps
docker compose exec -T backend python -c "from app.config.settings import RATE_LIMIT_GENERAL_LIMIT, RATE_LIMIT_GENERAL_WINDOW_SECONDS, RATE_LIMIT_NAMESPACE, RATE_LIMIT_REDIS_URL; print(RATE_LIMIT_GENERAL_LIMIT, RATE_LIMIT_GENERAL_WINDOW_SECONDS, RATE_LIMIT_NAMESPACE, RATE_LIMIT_REDIS_URL)"
Remove-Item Env:RATE_LIMIT_TEST_TOKEN, Env:RATE_LIMIT_TEST_EMAIL, Env:RATE_LIMIT_TEST_BAD_PASSWORD -ErrorAction SilentlyContinue
```

Expected general policy is `240 60` and the normal local namespace. No production environment is involved in this guide.

## Test result rules

- **Below threshold:** exact expected successful count and zero 429s; all other statuses are failures.
- **Above threshold:** exact expected successful and 429 counts; every 429 must include a positive `Retry-After`; all other statuses are failures.
- **Login test:** invalid attempts must remain generic 401 until the account threshold, then 429; valid credentials after failures must succeed.
- **Concurrency test:** the atomic Redis operation must allow no more than the configured threshold across simultaneous requests.
- **Redis outage:** sensitive policies return structured 503, routine GETs fail open, and successful Redis recovery resumes normal enforcement.
