import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://openci:openci_password@localhost:5432/openci",
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30