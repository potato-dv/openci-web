from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

import httpx

from app.config.settings import OSRM_DATASET_VERSION, OSRM_URL, VROOM_URL
from app.workers.celery_app import celery_app


STATUS_CACHE_SECONDS = 10.0
PROBE_TIMEOUT_SECONDS = 2.0
OSRM_PROBE_COORDINATE = (121.0, 14.5)

_cache_lock = Lock()
_cache: tuple[float, dict] | None = None


def _dataset_ready() -> bool:
    version = OSRM_DATASET_VERSION.strip()
    return bool(
        version
        and version.lower() != "unconfigured"
        and "yyyy" not in version.lower()
    )


def _worker_ready() -> bool:
    try:
        return bool(celery_app.control.ping(timeout=PROBE_TIMEOUT_SECONDS))
    except Exception:
        return False


def _osrm_ready() -> bool:
    longitude, latitude = OSRM_PROBE_COORDINATE
    try:
        response = httpx.get(
            f"{OSRM_URL.rstrip('/')}/nearest/v1/driving/{longitude},{latitude}",
            params={"number": 1},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("code") == "Ok" and len(payload.get("waypoints", [])) == 1
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def _vroom_ready() -> bool:
    try:
        response = httpx.get(
            f"{VROOM_URL.rstrip('/')}/health",
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def clear_planning_status_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def get_planning_service_status(*, force: bool = False) -> dict:
    global _cache
    now = monotonic()
    with _cache_lock:
        if not force and _cache and now - _cache[0] < STATUS_CACHE_SECONDS:
            return _cache[1]

    with ThreadPoolExecutor(max_workers=3) as pool:
        worker_future = pool.submit(_worker_ready)
        osrm_future = pool.submit(_osrm_ready)
        vroom_future = pool.submit(_vroom_ready)
        worker_ready = worker_future.result()
        osrm_ready = osrm_future.result()
        vroom_ready = vroom_future.result()

    dataset_ready = _dataset_ready()
    blocking_reasons = []
    if not dataset_ready:
        blocking_reasons.append("dataset_unconfigured")
    if not worker_ready:
        blocking_reasons.append("worker_unavailable")
    if not osrm_ready:
        blocking_reasons.append("osrm_unavailable")
    if not vroom_ready:
        blocking_reasons.append("vroom_unavailable")

    result = {
        "ready": not blocking_reasons,
        "checked_at": datetime.now(timezone.utc),
        "dataset_version": OSRM_DATASET_VERSION if dataset_ready else None,
        "dependencies": {
            "dataset": "ready" if dataset_ready else "unconfigured",
            "worker": "ready" if worker_ready else "unavailable",
            "osrm": "ready" if osrm_ready else "unavailable",
            "vroom": "ready" if vroom_ready else "unavailable",
        },
        "blocking_reasons": blocking_reasons,
    }
    with _cache_lock:
        _cache = (monotonic(), result)
    return result
