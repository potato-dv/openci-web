# Geospatial services

## Development startup

1. Copy `.env.example` to `.env` and replace the JWT, PostgreSQL, and Nominatim passwords. Use a URL-safe PostgreSQL password because the backend DSN is assembled in Compose. The development Compose defaults preserve compatibility with an existing local PostgreSQL volume; production must inject a strong password through its deployment secret manager and rotate the database credential to match. PostgreSQL and Redis host ports bind to loopback for local tools only.
2. Prepare the OSRM graph once with `bash scripts/prepare-osrm-data.sh`. The script resumes interrupted Geofabrik Philippines downloads, runs the pinned CH preprocessing tools, checks the required `.osrm.*` graph artifacts, and validates real Metro Manila Nearest and Route requests. The extract and graph are ignored by Git. For refreshes, set `OSRM_DATA_DIR` to a new versioned directory before running the script.
3. Copy the exact `OSRM_DATASET_VERSION=...` value printed by the script into `.env`. The API records that value on each automatic planning run and treats a missing or placeholder version as a planning blocker.
4. Start the services with `docker compose --profile geospatial up --build -d`. Nominatim performs a first import into its own persistent PostgreSQL/PostGIS volume; allow the import to finish before using address suggestions. The service uses the Philippines extract and its Geofabrik replication feed.
5. Verify `docker compose --profile geospatial ps`, then open Route Planning. The page reports the dataset, Celery worker, OSRM, and VROOM independently. Confirm investigation locations and configure available shifts; those changes queue planning in the background.

The application only calls geospatial services from its backend and Celery worker. OSRM, VROOM, and Nominatim have no host port published. PostgreSQL and Redis are available on loopback only. The optimizer sends coordinates and numeric investigation IDs, not subject names or address text.

## Production deployment

Use the standalone `compose.production.yaml` with `.env.production`; it does not inherit the development mounts or ports from `compose.yaml`.

1. Copy `.env.production.example` to `.env.production`, then replace every `CHANGE_ME` value using the deployment secret manager. Use URL-safe database and Redis passwords because Compose builds service URLs from them. The migration job and API container reject the placeholder secret prefix.
2. Replace mutable base-image tags in `.env.production` with reviewed immutable digests. Keep the OSRM, VROOM, and Nominatim versions pinned in `compose.production.yaml` and update them only through a reviewed release.
3. Set `PUBLIC_WEB_ORIGIN` and `PUBLIC_API_URL` to the production HTTPS origins. The frontend is built as static assets and served by Nginx; API CORS allows only the configured web origin.
   `PLANNING_ENABLED` defaults to `false` in the production example. Keep it disabled during deployment checks, then set it to `true` and rebuild/redeploy both frontend and backend before enabling automatic planning. The backend rejects location confirmation and planning operations while the flag is off. Manual overrides still require a confirmed location, an active agent, an available matching shift, and capacity; they do not bypass route validation.
4. Prepare and validate a versioned OSRM graph. The production API and frontend bind to `127.0.0.1:8000` and `127.0.0.1:8080` for a host ingress or reverse proxy. PostgreSQL, Redis, Nominatim, OSRM, and VROOM have no published host ports. Forward only the frontend and API through the ingress, and terminate TLS there.
5. Check configuration with `docker compose --env-file .env.production -f compose.production.yaml config --quiet`, then deploy the core application with `docker compose --env-file .env.production -f compose.production.yaml up --build -d`. The one-shot migration service must finish before the API and worker start. While `PLANNING_ENABLED=false`, the geospatial profile stays stopped. For an enabled pilot, set the flag to `true` and deploy with `--profile planning` so Nominatim, OSRM, and VROOM start alongside the app.

Compose rotates JSON logs and provides health checks for data services and web processes. Keep database backups and restore tests in the host's operational policy; Compose volumes alone are not backups. Store `.env.production` outside source control and use the secret manager for production values. Apply resource caps using staging measurements before enabling planning for supervisors.

Planning lifecycle messages include a JSON `planning_event` payload for queued, started, ready, stale, failed, and applied runs. They report queue age, run duration, assignment totals, unassigned reason counts, snap-warning counts, and the OSRM dataset version. They deliberately omit case references, addresses, and coordinates. Forward these container logs to the organization's existing log collector and alert on growing queue age, repeated routing errors, stale runs, and rising unassigned counts. Geocoder confirmations and automatic or manual assignment changes are recorded in the activity log; review them with aggregate dashboard counts without exporting case locations.

## Refresh and rollback

Nominatim follows the Philippines replication feed. For OSRM, set `OSRM_DATA_DIR` to a new versioned directory, run the preparation script against it, and validate a known road pair plus ferry exclusion before changing the mounted graph. Keep the previous graph until the new one passes staging checks. Update `OSRM_DATASET_VERSION` with the activated extract date, then redeploy the API and worker so new planning runs record the activated version. Roll back by restoring the previous `OSRM_DATA_DIR` and dataset version, then redeploying. The first release uses the OSRM CH algorithm and car profile. Do not replace the graph in place while a planning run is using it.

## Resource and data notes

The Philippines import needs dedicated disk and memory. Nominatim's PostgreSQL/PostGIS data is isolated from OpenCI's operational database. Compose provides configurable memory and CPU caps (`NOMINATIM_*`, `OSRM_*`, `VROOM_*`, and `CELERY_WORKER_*` in `.env.example`); benchmark the Philippine extract on staging and adjust them for the target host before production. Size Nominatim import threads, shared memory, and persistent storage alongside those limits. Do not expose these internal services directly to the internet or send investigation addresses to public geocoding and routing demos.

OpenStreetMap data is licensed under ODbL. Preserve attribution when displaying derived map or route information and review database distribution obligations before publishing data externally: https://www.openstreetmap.org/copyright.
