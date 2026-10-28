# Automatic assignment implementation status

OpenCI planning now follows an automatic workflow: location confirmation, dated shifts, and planning-relevant investigation changes enqueue region/date planning. Redis and Celery run OSRM and VROOM in the background. H3 orders bounded geographic batches; it does not select agents. The worker verifies complete solver results, schedule and capacity constraints, current input digests, and OSRM geometry before a single transaction saves assignment history, investigation pointers, and published route pointers.

Admins and supervisors monitor persisted assignment and route states in the Route Planning dashboard. The normal flow has no generate, approve, or reject action. Authorized manual assignment remains a separate override and is validated and logged. Agents receive only official assignments and a route whose stop set matches current assignments; stale geometry is withheld during route refreshes.

## Relevant code

- Backend optimization and publication: `backend/app/services/planning.py`
- Planning and field-agent endpoints: `backend/app/routes/planning.py`
- Location-confirmation trigger: `backend/app/routes/investigation.py`
- Manual assignment validation and history: `backend/app/services/investigation.py`
- Celery task dispatch and recovery: `backend/app/workers/tasks.py`
- Assignment provenance and replan persistence: `backend/app/models/assignment.py`, `backend/app/models/planning.py`, `backend/alembic/versions/0010_automatic_assignment_source.py`
- Supervisor dashboard: `frontend/src/features/route-planning/pages/RoutePlanningPage.tsx`
- Investigation/agent roster and route details: `frontend/src/features/route-planning/components/RouteRosterPanel.tsx`, `PublishedRoutePanel.tsx`
- Agent route view: `frontend/src/features/route-planning/pages/MyRoutePage.tsx`

## Current limits

The system has no leave/time-off or agent qualification data, so those constraints cannot be applied. Planning is bounded to 80 investigations/locations per run; oversized scopes are surfaced as failures and split into follow-up batches only when locked work leaves batch capacity. Live route quality requires an available Philippines OSRM graph, VROOM, Redis, Celery, confirmed investigation locations, and dated agent shifts.

## Verification

Run `cd frontend && npm run lint && npm run build && npm test` and `cd backend && .venv/bin/python -m unittest discover -s tests -q`. PostgreSQL concurrency coverage is skipped unless `OPENCI_TEST_POSTGRES_URL` points to a disposable PostgreSQL database. Live OSRM/VROOM service integration is separate from deterministic unit tests.
