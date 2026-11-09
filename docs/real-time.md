# Collector real-time updates

Collector uses one native browser WebSocket connection per authenticated React application instance. FastAPI authenticates that connection, authorizes its subscriptions, and sends small invalidation notifications. PostgreSQL REST APIs remain authoritative for all reads and writes; WebSocket frames contain no report or investigation contents.

## Event and resource contract

The backend records events from SQLAlchemy model changes in the same transaction as the business mutation. The frontend mapping in `frontend/src/realtime/resourceMap.ts` converts an event into resource keys. Only currently mounted resources matching those keys refetch. `useResource` keeps filters and pagination in their existing URL state, and coalesces concurrent event refreshes.

| Event names | Source mutation | Recipients and authorized subscription | Frontend resource keys | REST reads after invalidation |
| --- | --- | --- | --- | --- |
| `investigation.created`, `investigation.updated`, `investigation.location_updated`, `investigation.assigned`, `investigation.unassigned`, `investigation.status_changed`, `investigation.priority_changed`, `investigation.deleted`, `investigation.restored` | `Investigation` ORM insert/update/delete, including assignment, detail edits, trash/restore, and worker changes | Admin/supervisor audience; assigned agent IDs where applicable. Agents also require current assignment for investigation-specific delivery. Scopes: `investigations`, `route.planning`, `route.own`, dashboard, or `investigation:<id>` | `investigations.list`, `investigations.trash`, `dashboard.investigations`, `dashboard.reports`, `route.planning`, `route.own`, plus investigation detail/activity/location keys when an ID is present | `GET /investigations/`, `/investigations/{id}`, `/investigations/trash`, `/investigations/{id}/activity-history`, `/investigations/{id}/location`, and relevant `/planning/*` reads |
| `report.submitted`, `report.updated`, `report.reviewed`, `report.returned_for_correction`, `report.completed` | `InvestigationReport` insert or report status/content update | Report author and admin/supervisor roles. Scopes: `reports.queue`, `investigations`, `dashboard`, `me`, or authorized `investigation:<id>` | `reports.queue`, `dashboard.reports`, investigation list/dashboard keys, `route.own`, `investigation.report:<id>`, case detail/activity keys | `GET /reports/review-queue`, `/investigations/awaiting-no-contact-review`, `/investigations/{id}/report`, `/investigations/{id}/reports`, `/investigations/{id}/activity-history`, `/planning/my-route` |
| `investigation.revisit_updated` | `AgentRevisitRequest` insert/update/delete | Affected agent and admin/supervisor roles; investigation-specific access is rechecked. Scopes: `investigation:<id>`, `route.own`, or `route.planning` | `investigations.list`, dashboard investigation counts, `route.planning`, `route.own`, `investigation.revisit:<id>`, activity | `GET /investigations/{id}/revisit-request`, `/investigations/`, `/planning/my-route`, `/planning/route-overview` |
| `route.published`, `route.replanned`, `route.updated` | `PlanningRun` creation or status/application changes | The run's listed agents plus admin/supervisor roles. Scopes: `route.own`, `route.planning`, or dashboard | `route.planning`, `route.readiness`, `route.own`, `dashboard.route`, `investigations.list` | `GET /planning/my-route`, `/planning/map-data`, `/planning/route-overview`, `/planning/dashboard`, `/planning/readiness`, `/investigations/` |
| `route.cancelled`, `route.agent_updated` | Investigation cancellation/deletion, assignment changes, `InvestigationRouteEvent` changes, and a safe per-agent route invalidation when assignment access is lost | Admin/supervisor roles and affected agent IDs. Agent invalidation frames omit investigation IDs when the case is no longer accessible. Scopes: `route.own`, `route.planning`, or an authorized `investigation:<id>` | `route.planning`, `route.own`, `dashboard.route`, `investigations.list`, and the no-contact review queue through the route-planning key | `GET /planning/my-route`, `/planning/map-data`, `/planning/route-overview`, `/investigations/`, `/investigations/awaiting-no-contact-review` |
| `schedule.updated` | `AgentWorkProfile` or `AgentWeeklySchedule` insert/update/delete | Affected agent plus admin/supervisor roles. Scope: `schedules` (or a related route scope) | `schedules.list`, `schedules.<agent-id>`, `route.planning`, `route.own` | `GET /planning/agent-shifts`, `/planning/agents/{id}/work-profile`, `/weekly-schedule`, `/availability` |
| `shift.updated`, `shift.activated`, `shift.expired` | `AgentShift` insert/update/delete, including the shift-expiry worker | Affected agent plus admin/supervisor roles. Scope: `schedules`, `route.planning`, `route.own`, or dashboard | `schedules.list`, `schedules.<agent-id>`, `route.planning`, `route.own`, `dashboard.route` | `GET /planning/agent-shifts`, `/planning/agents/{id}/shifts/{date}`, `/planning/my-route`, and planning dashboard reads |
| `activity.created` | `ActivityLog` insert | Admin only, and only while subscribed to `activity.logs` | `activity.logs` | `GET /activity-logs/query` and `/activity-logs/filter-options` |
| `user.created`, `user.role_changed`, `user.activated`, `user.deactivated`, `user.permissions_changed` | `User` or `UserPermissionOverride` insert/update | Admins for user administration; permission-change notification also targets the affected identity. Scopes: `users`, `me`, or `role:<current-role>` | `users.list`, `agent.permissions` | `GET /users/`, `/users/me/agent-permissions`, `/users/{id}/agent-permissions` |

Dashboard updates are invalidations of the dashboard's existing resource keys, not a separate copy of dashboard data. Schedule and shift notifications include only the authorized affected agent ID so open per-agent schedule editors can refresh precisely. Activity Log payloads, report bodies, coordinates, user permission values, and other business fields are never sent over WebSocket.

## Authentication and authorization

1. The browser opens `/ws` with no credentials in the URL. The WebSocket `Origin` must exactly match an origin in `CORS_ALLOWED_ORIGINS`.
2. Within five seconds it sends `{"type":"auth","token":"<access JWT>","subscriptions":[...]}`. The token is sent in a WebSocket message, never in a query parameter or log entry.
3. FastAPI applies the same JWT claims, active `AuthSession`, active-user, idle-timeout, absolute-expiry, and role checks as the REST authentication path. Access tokens are reauthenticated over the open socket as the existing refresh flow issues new tokens.
4. Subscriptions are checked against the database on initial auth, subscribe, heartbeat, and before protected event delivery. `me` is identity-specific and matches only outbox events that name that user. Fixed module scopes reflect the current API roles. `role:admin`, `role:supervisor`, and `role:agent` are checked against the authenticated database role and the event's recipient roles. `investigation:<id>` checks current assignment and the existing completed-history permission.
5. Outbox audience metadata is server-only. Event delivery checks both that audience and the live subscription. It rechecks an agent's assignment before delivering an investigation-linked event. A role, account, permission, or session change closes or narrows the connection before a later protected event can be delivered.

The current REST APIs grant admin/supervisor operational views globally and agents access to assigned records; WebSocket authorization mirrors those rules. There is no separate region-level visibility rule in the current API. If that changes, the same access service must be added to `scope_is_authorized` and event delivery.

The client sends a heartbeat every 25 seconds; the server drops idle sockets after 90 seconds. Heartbeats do not extend the existing interactive-session timeout. Existing HTTP activity recording and REST authentication remain in place.

## Cross-worker delivery and recovery

Every API worker starts a Redis subscriber and an outbox relay. ORM flush hooks create content-free `realtime_outbox_events` rows inside the business transaction for API and Celery sessions alike. The relay claims pending rows with `FOR UPDATE SKIP LOCKED`, publishes to `REALTIME_REDIS_CHANNEL`, then records the published timestamp. Failed Redis publishes receive a bounded exponential retry delay. A publish/commit interruption can result in duplicate delivery; each worker and browser deduplicates recent event IDs.

Each API process owns only its local WebSocket connections. Redis Pub/Sub sends the committed event envelope to all API workers; each worker filters its own connections by current audience and scope. When a Redis listener reconnects, it sends a `resync` frame so connected clients refetch their active REST resources. A browser reconnect also refetches active resources. Pub/Sub is not replay storage, and REST remains the recovery source of truth.

Published outbox rows are pruned after `REALTIME_OUTBOX_RETENTION_DAYS` in batches. Failed unpublished rows are retained for retry and should be monitored if Redis remains unavailable.

## Files and migration

- Backend socket, auth, connection limits, Redis listener, and outbox relay: `backend/app/realtime/websocket.py`
- Event capture for API and Celery SQLAlchemy sessions: `backend/app/realtime/orm_events.py`
- Outbox model and migration: `backend/app/models/realtime_outbox.py`, `backend/alembic/versions/0021_realtime_outbox.py`
- Browser connection and invalidation map: `frontend/src/realtime/RealtimeProvider.tsx`, `frontend/src/realtime/resourceMap.ts`
- Vite `/ws` upgrade proxy: `frontend/vite.config.ts`

Apply migration `0021_realtime_outbox` with `alembic upgrade head`. Existing Compose startup already applies migrations: the development backend runs Alembic before Uvicorn, and production's migration service runs it before API workers start.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `REALTIME_REDIS_URL` | `CELERY_BROKER_URL` | Redis connection for Pub/Sub; set only if real-time Redis differs from Celery Redis |
| `REALTIME_REDIS_CHANNEL` | `openci:realtime:v1` | Pub/Sub channel name |
| `REALTIME_AUTH_TIMEOUT_SECONDS` | `5` | Initial auth-message timeout |
| `REALTIME_IDLE_TIMEOUT_SECONDS` | `90` | Maximum interval without a client message |
| `REALTIME_OUTBOX_POLL_SECONDS` | `0.5` | Pending outbox poll interval |
| `REALTIME_OUTBOX_RETENTION_DAYS` | `14` | Retention for published outbox records |
| `REALTIME_MAX_CONNECTIONS_PER_USER` | `4` | Per-user limit on each API worker |
| `REALTIME_MAX_CONNECTIONS_PER_WORKER` | `2000` | Local connection cap per API worker |
| `VITE_REALTIME_URL` | derived from `VITE_API_URL` plus `/ws` | Optional full browser WebSocket URL; production Compose exposes this as `PUBLIC_REALTIME_URL` |

The existing `CORS_ALLOWED_ORIGINS` is also the strict WebSocket Origin allowlist. Development Compose already includes `http://localhost:5173` and `http://localhost:5174`; the existing port-isolated refresh-cookie setting remains enabled so the two test origins retain separate login sessions. Production should set the public web origin there.

## Local verification

Start PostgreSQL, Redis, the API, and the Celery worker/beat with `docker compose up -d postgres redis backend celery_worker celery_beat`. Then run Vite on 5173 and, when testing a second role, on 5174. Both browser apps connect through Vite's `/ws` proxy to the same API and Redis event stream.

```powershell
Set-Location backend
python -m unittest discover -s tests -p "test_*.py"
```

```powershell
Set-Location frontend
npm test
npm run build
```

For the first vertical slice, sign in as an agent on one dev origin and submit a report through its existing form; sign in as a supervisor on the other origin and keep the report queue open. The supervisor's queue should refetch from `GET /reports/review-queue` without a page reload. To exercise cross-worker delivery, run the API with multiple workers and connect clients through the deployment ingress. REST mutation endpoints continue to work if Redis or WebSocket delivery is unavailable.

## Production deployment

- Keep `API_WORKERS` enabled; Redis Pub/Sub distributes events between the workers.
- The public ingress in front of the API must route `/ws` to FastAPI, forward WebSocket `Upgrade` and `Connection` headers, use a WebSocket-capable HTTP version, and set an idle timeout longer than the 25-second heartbeat. The repo's production Nginx serves static frontend files only; the existing external ingress owns public API and WebSocket routing.
- Set `PUBLIC_REALTIME_URL` when WebSocket routing uses a different public host or path from `PUBLIC_API_URL`; use `wss://` in production. When unset, the frontend derives the socket URL by appending `/ws` to `VITE_API_URL`.
- Allow the configured web origin in `CORS_ALLOWED_ORIGINS`; do not use wildcard origins with credentials.
- The outbox table adds one small row per event and should be included in normal PostgreSQL backup/monitoring. Track unpublished row count and oldest pending age; a long Redis outage increases pending storage but does not fail REST transactions.
- Set `REALTIME_MAX_CONNECTIONS_PER_USER` and `REALTIME_MAX_CONNECTIONS_PER_WORKER` for expected browser-tab and worker capacity. Limits are local to each API worker.

## Current verification scope

The backend suite covers transactional outbox writes/rollback, report audience metadata, assigned-agent access and history checks, content-free frames, role scopes, assignment-loss invalidation, session/permission closures, authorization filtering, Redis listener recovery, and delivery through separate worker managers. The frontend suite covers one shared socket, reconnect/cleanup, event coalescing, resource mapping, and scoped refreshes. Verification used SQLite and mocked Redis; a live end-to-end run still requires PostgreSQL, Redis, and browser clients behind multiple Uvicorn workers.
