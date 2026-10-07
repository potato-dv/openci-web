import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://openci:openci_password@localhost:5432/openci",
)