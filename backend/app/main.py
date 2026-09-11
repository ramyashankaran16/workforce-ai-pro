"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.handlers import register_exception_handlers
from app.schemas.common import HealthResponse
from app.websockets.chat_ws import router as websocket_router

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
for _noisy in ("python_multipart", "multipart", "watchfiles", "httpx", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK (%s)", settings.DB_NAME)
    except Exception as exc:
        logger.error("Database connection FAILED: %s", exc)
    if settings.APP_ENV == "production":
        # Single instance only -- see app/tasks/scheduler.py for why.
        try:
            from app.tasks.scheduler import start as start_scheduler

            start_scheduler()
        except Exception:
            logger.exception("Scheduler failed to start; continuing without it")

    logger.info("%s started in %s mode", settings.APP_NAME, settings.APP_ENV)
    yield

    try:
        from app.tasks.scheduler import shutdown as stop_scheduler

        stop_scheduler()
    except Exception:
        # the scheduler is optional; never let shutdown fail because of it
        logger.debug("Scheduler shutdown skipped", exc_info=True)

    logger.info("%s shutting down", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "HR Attrition Prediction & Workforce Intelligence Platform.\n\n"
        "Sign in at `/api/v1/auth/login`, then paste the access token into "
        "the **Authorize** button."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket_router)


@app.get("/", tags=["Health"], summary="Service banner")
def root():
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"], summary="Health check")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        app=settings.APP_NAME,
        version="1.0.0",
        database=db_status,
    )
