from fastapi import FastAPI

from app.routes.investigation import router as investigation_router
from app.routes.user import router as user_router

app = FastAPI()

app.include_router(investigation_router)
app.include_router(user_router)

@app.get("/")
def root():
    return {"message": "OpenCI Operations API"}