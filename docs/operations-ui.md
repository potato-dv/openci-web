# Collector Operations workspace

The React application uses protected URL routes, route-local requests, and page bundles loaded on demand. Supervisor planning is `/route-planning`; field agents use `/my-route`. Reports remains a separate supervisor review queue. The Route Planning screen shows persisted assignments and published routes; pending optimizer output is never presented as an official assignment.

## Development and migration

Install frontend dependencies with `cd frontend && npm ci`. Apply `cd backend && alembic upgrade head` before running the API and worker. Migration `0010_automatic_assignment_source` records whether an assignment came from VROOM or an authorized manual override and adds durable automatic replan tracking. Restart an already running Celery worker after code updates.

## Automatic assignment lifecycle

An investigation becomes eligible after an administrator or supervisor confirms its location. Address, priority, service-time, or visit-window changes invalidate queued results; confirming the changed location queues planning again. Creating or changing an agent shift also queues a plan for that region and date. Authorized manual assignment or reassignment saves immediately, then queues a route rebuild for affected agents.

The backend coalesces queued region/date triggers, serializes planner creation with a PostgreSQL advisory lock, and waits briefly before dispatching Celery work. H3 provides stable geographic ordering for bounded batches only. OSRM builds the road travel matrix; VROOM chooses feasible vehicles and visit order using active status, available dated shifts, road travel, service time, visit windows, max visits, open-case capacity, and locked existing assignments. VROOM priority favors which jobs are included when capacity is tight; a second route pass orders urgent, high, then normal work, and uses the earliest persisted assignment time within each priority. Same-day no-contact retries follow all primary stops and use the retry's contact window. The pass has a two-second search limit per attempt. Hard visit windows, shift hours, breaks, and retry feasibility can require an order exception; the affected stop and supervisor route details explain it. A feasible route is retained with an optimization warning if the bounded search cannot finish. Existing assignments remain locked to their agent. Agent skills and leave/time-off are not modeled and therefore are not optimizer constraints.

The latest applied route for an agent and work date supplies the mandatory sequence. The route response includes its revision and marks each stop current, upcoming, deferred, retry, or handled. `POST /investigations/{id}/start`, report draft saves, and report submission validate the assignment, current stop, and route revision in the backend. A stale revision or out-of-sequence action returns a conflict. A submitted report advances the queue while it remains `under_review` for supervisor review. An in-progress visit stays reportable through a route refresh and is replanned after its report is submitted.

`POST /investigations/{id}/unable-to-proceed` records a no-contact attempt in `investigation_route_events`, with its reason, agent, route run, time, notes, location, and optional contact window. It does not create a report or change the investigation to completed or cancelled. It releases the next primary stop; after primary work is handled, the planner offers at most one feasible same-day retry. `POST /investigations/{id}/no-contact-report` finalizes that same attempt for carry-over. At shift end, untouched work receives a separate `Shift End — Not Visited` event. Manual assignments remain with their agent and queue for that agent's next configured working day; automatic assignments return to the planning pool. These events preserve history across reassignment and do not create duplicate investigations. Historical applied planning runs and reports are not rewritten.

The worker rechecks the input digest before storing results and again while holding investigation and shift locks before applying them. It validates that every job appears once as assigned or unassigned, validates VROOM vehicle and schedule data including return-to-depot time, and requires valid OSRM geometry for every assigned agent. One database transaction creates any new official assignment records, updates investigation assignment pointers, records activity, updates dated route pointers, and marks the run applied. Duplicate application is idempotent. A failed or stale run does not change assignments or current route pointers.

Existing official assignments are included as locked work in optimization runs. The planner does not clear old published route pointers when queueing; the UI and agent endpoint withhold geometry when the stored stop set no longer matches current assignments. The prior route remains available until a complete replacement is committed. Agents receive only persisted official assignments; their route endpoint withholds stale routes during a manual override refresh.

Infeasible investigations are saved as unassigned planning items with reasons such as no available agents, capacity, road connectivity, or an impossible visit window. Routing dependency failures and invalid or incomplete VROOM output fail the run without publishing. Worker retries are bounded for transient routing failures; a redelivered task rechecks a persisted running run after its lease expires instead of acknowledging it as complete.

## Planning and assignment contracts

`GET /investigations/` returns paginated, role-scoped investigation data. Location confirmation and planning management endpoints require administrator or supervisor roles. `GET /planning/dashboard`, `/planning/map-data`, and `/planning/route-overview` provide the dashboard counts, planning states, mapped cases, current assignments, agent shifts, and validated routes. `GET /planning/my-route` is restricted to the signed-in field agent; managers can inspect a specific agent route. There is no manual planning-run creation or apply endpoint.

The Route Planning dashboard polls while runs are queued or running. It separates pending, optimizing, assigned, unassigned, and failed investigation states from route publication states. Assignment status comes from the persisted investigation pointer and assignment source; a queued VROOM result alone cannot make a case appear assigned. H3 is labeled as density information. Route geometry is solid only after validated OSRM geometry is published. No straight-line fallback is drawn.

The manager agent roster shows active/open workload counts and visit workload by the shift region. Manual overrides only list active agents with an available matching shift and remaining capacity; the backend repeats all eligibility and capacity checks under database locks. Assignment history distinguishes automatic assignments from manual overrides.

## Maps

`VITE_MAP_TILE_URL` and `VITE_MAP_TILE_ATTRIBUTION` override the default OSM raster provider. They are build-time Vite values; production Compose forwards them as build arguments. Blank values use the standard HTTPS tile URL and visible linked OSM attribution. Browser caching and referrers remain enabled. There is no offline tile download or prefetch. Starting markers represent configured shift points.

## Verification

- `cd frontend && npm run lint && npm run build && npm test`
- Start a local frontend and run `OPENCI_UI_URL=http://127.0.0.1:5174 npm run test:e2e`. Browser tests use deterministic API and tile fixtures; screenshots are written under `/tmp`.
- `cd backend && .venv/bin/python -m unittest discover -s tests -q`
- Set `OPENCI_TEST_POSTGRES_URL` for `tests.test_postgres_planning_integration`; it creates and removes a private test schema. SQLite unit/API tests cover planning and authorization. The PostgreSQL integration test covers concurrent automatic publication and the active-assignment invariant.

Live OSRM/VROOM routing requires the configured Philippines dataset and running geospatial services. Browser fixtures verify presentation and interaction; live route quality also depends on operationally maintained shifts and confirmed investigation locations.
