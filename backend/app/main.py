import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis as SyncRedis
from redis.asyncio import Redis

from app.config.settings import (
    CORS_ALLOWED_ORIGINS,
    RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
    RATE_LIMIT_REDIS_URL,
    REALTIME_REDIS_URL,
)
from app.routes.investigation import router as investigation_router
from app.routes.user import router as user_router
from app.routes.location import router as location_router
from app.routes.activity import router as activity_router
from app.routes.planning import router as planning_router

from app.routes.report import router as report_router
from app.routes.agent_permissions import router as agent_permissions_router
from app.realtime.websocket import manager, router as realtime_router, run_outbox_relay, run_redis_listener


@asynccontextmanager
async def lifespan(_app: FastAPI):
    rate_limit_redis = SyncRedis.from_url(
        RATE_LIMIT_REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        socket_timeout=RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        health_check_interval=30,
    )
    _app.state.rate_limit_redis = rate_limit_redis
    redis = Redis.from_url(
        REALTIME_REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
        health_check_interval=30,
    )
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(run_redis_listener(redis, stop), name="realtime-redis-listener"),
        asyncio.create_task(run_outbox_relay(redis, stop), name="realtime-outbox-relay"),
    ]
    try:
        yield
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await manager.close_all(1001)
        await redis.aclose()
        rate_limit_redis.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=[
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)

app.include_router(investigation_router)
app.include_router(user_router)
app.include_router(location_router)
app.include_router(activity_router)
app.include_router(planning_router)
app.include_router(report_router)
app.include_router(agent_permissions_router)
app.include_router(realtime_router)

@app.get("/")
def root():
    return {"message": "OpenCI Operations API"}
