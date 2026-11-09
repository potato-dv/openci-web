import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://openci:openci_password@localhost:5432/openci",
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if JWT_SECRET_KEY and len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
if not 1 <= ACCESS_TOKEN_EXPIRE_MINUTES <= 15:
    raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 15")
AUTH_SESSION_ABSOLUTE_HOURS = 8
AUTH_SESSION_IDLE_MINUTES = 30
AUTH_REFRESH_TOKEN_GRACE_SECONDS = 10
AUTH_REFRESH_TOKEN_RETENTION_DAYS = 30
AUTH_REFRESH_COOKIE_SECURE = (
    os.getenv("AUTH_REFRESH_COOKIE_SECURE", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
AUTH_REFRESH_COOKIE_SAMESITE = os.getenv("AUTH_REFRESH_COOKIE_SAMESITE", "lax").strip().lower()
if AUTH_REFRESH_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise ValueError("AUTH_REFRESH_COOKIE_SAMESITE must be lax, strict, or none")
if AUTH_REFRESH_COOKIE_SAMESITE == "none" and not AUTH_REFRESH_COOKIE_SECURE:
    raise ValueError("SameSite=None refresh cookies require Secure")
AUTH_REFRESH_COOKIE_ISOLATE_BY_ORIGIN = (
    os.getenv("AUTH_REFRESH_COOKIE_ISOLATE_BY_ORIGIN", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://nominatim:8080")
OSRM_URL = os.getenv("OSRM_URL", "http://osrm:5000")
VROOM_URL = os.getenv("VROOM_URL", "http://vroom:3000")
OSRM_DATASET_VERSION = os.getenv("OSRM_DATASET_VERSION", "unconfigured")
GEOSPATIAL_HTTP_TIMEOUT_SECONDS = float(os.getenv("GEOSPATIAL_HTTP_TIMEOUT_SECONDS", "15"))
PLANNING_MAX_LOCATIONS = int(os.getenv("PLANNING_MAX_LOCATIONS", "80"))
REALTIME_REDIS_CHANNEL = os.getenv("REALTIME_REDIS_CHANNEL", "openci:realtime:v1")
REALTIME_REDIS_URL = os.getenv("REALTIME_REDIS_URL") or os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
REALTIME_AUTH_TIMEOUT_SECONDS = float(os.getenv("REALTIME_AUTH_TIMEOUT_SECONDS", "5"))
REALTIME_IDLE_TIMEOUT_SECONDS = int(os.getenv("REALTIME_IDLE_TIMEOUT_SECONDS", "90"))
REALTIME_OUTBOX_POLL_SECONDS = float(os.getenv("REALTIME_OUTBOX_POLL_SECONDS", "0.5"))
REALTIME_OUTBOX_RETENTION_DAYS = int(os.getenv("REALTIME_OUTBOX_RETENTION_DAYS", "14"))
REALTIME_MAX_CONNECTIONS_PER_USER = int(os.getenv("REALTIME_MAX_CONNECTIONS_PER_USER", "4"))
REALTIME_MAX_CONNECTIONS_PER_WORKER = int(os.getenv("REALTIME_MAX_CONNECTIONS_PER_WORKER", "2000"))
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
PLANNING_ENABLED = os.getenv("PLANNING_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
