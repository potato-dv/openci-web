from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.investigation import router as investigation_router
from app.routes.user import router as user_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation_router)
app.include_router(user_router)

@app.get("/")
def root():
    return {"message": "OpenCI Operations API"}