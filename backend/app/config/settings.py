import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://openci:openci_password@localhost:5432/openci",
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://nominatim:8080")
OSRM_URL = os.getenv("OSRM_URL", "http://osrm:5000")
VROOM_URL = os.getenv("VROOM_URL", "http://vroom:3000")
OSRM_DATASET_VERSION = os.getenv("OSRM_DATASET_VERSION", "unconfigured")
GEOSPATIAL_HTTP_TIMEOUT_SECONDS = float(os.getenv("GEOSPATIAL_HTTP_TIMEOUT_SECONDS", "15"))
PLANNING_MAX_LOCATIONS = int(os.getenv("PLANNING_MAX_LOCATIONS", "80"))
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
PLANNING_ENABLED = os.getenv("PLANNING_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
