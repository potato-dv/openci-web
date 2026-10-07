from fastapi import FastAPI

from app.routes.investigation import router as investigation_router

app = FastAPI()

app.include_router(investigation_router)


@app.get("/")
def root():
    return {"message": "OpenCI Operations API"}