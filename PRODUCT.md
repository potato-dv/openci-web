# Collector Operations

Collector Operations manages investigations for administrators, supervisors, and field agents. Supervisors create investigations, confirm geocoded locations, and configure dated agent shifts and starting points. Once a confirmed investigation is eligible, the backend automatically plans it in the background.

H3 supplies geographic grouping and density information. OSRM supplies road travel times, distances, and route geometry. VROOM chooses among eligible agents and orders visits using configured shift hours, service durations, open-case and visit limits, priority, and investigation time windows. A valid result is committed and published automatically. Infeasible work stays unassigned with a reason. Administrators and supervisors monitor these states in Route Planning; no planning approval step is used.

Administrators and supervisors can still make a clearly labeled manual assignment override. The backend requires a confirmed location, active agent, available matching shift, and remaining workload limits, logs the override, and refreshes the affected routes. Agents see official assignments and published routes, then complete investigations and submit reports for supervisor review.

Leave, absence, agent skills, and qualifications are not modeled in the current system, so the optimizer cannot enforce them. Account activation and dated shift availability are separate. The application has no GPS, presence, live tracking, simulated movement, or fabricated routing result.

The application uses React 19 and TypeScript with Vite, FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, Leaflet, Nominatim, OSRM, and VROOM. Desktop is the primary planning environment; tablets use drawers and phones prioritize lists.
