from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import CORS_ALLOWED_ORIGINS
from app.routes.investigation import router as investigation_router
from app.routes.user import router as user_router
from app.routes.location import router as location_router
from app.routes.activity import router as activity_router
from app.routes.planning import router as planning_router

from app.routes.report import router as report_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

app.include_router(investigation_router)
app.include_router(user_router)
app.include_router(location_router)
app.include_router(activity_router)
app.include_router(planning_router)
app.include_router(report_router)

@app.get("/")
def root():
    return {"message": "OpenCI Operations API"}
