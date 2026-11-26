from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.auth import require_auth
from backend.app.config import get_settings
from backend.app.database import DatabaseConfigurationError, check_database_connection, get_engine
from backend.app.errors import ApiError
from backend.app.routes.lectures import router as lectures_router
from backend.app.routes.pdf import router as pdf_router
from backend.app.routes.processing import router as processing_router
from backend.app.routes.study_materials import router as study_materials_router
from backend.app.routes.transcripts import router as transcripts_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_application: FastAPI):
    try:
        yield
    finally:
        if get_engine.cache_info().currsize > 0:
            try:
                get_engine().dispose()
            except Exception:  # pragma: no cover - defensive shutdown guard
                logger.warning("Database engine disposal encountered an error during shutdown.")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")

    is_production = settings.environment == "production"
    application = FastAPI(
        title="Code-Mixed Lecture Notes Generator API",
        debug=False,
        lifespan=_lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
            expose_headers=["Content-Disposition"],
        )

    protected = [Depends(require_auth)]
    application.include_router(lectures_router, dependencies=protected)
    application.include_router(pdf_router, dependencies=protected)
    application.include_router(processing_router, dependencies=protected)
    application.include_router(transcripts_router, dependencies=protected)
    application.include_router(study_materials_router, dependencies=protected)

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        details = [
            {"location": error["loc"], "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": details,
                }
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        del request
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={"error": {"code": "http_error", "message": message}},
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del request
        logger.exception("Unhandled application error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected internal error occurred.",
                }
            },
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/database")
    def database_health() -> dict[str, str]:
        try:
            check_database_connection()
        except DatabaseConfigurationError as exc:
            raise ApiError(503, "database_unavailable", "Database configuration is missing or invalid.") from exc
        except SQLAlchemyError as exc:
            logger.exception("Database health check failed")
            raise ApiError(503, "database_unavailable", "Database is unavailable.") from exc
        return {"status": "ok", "database": "ok"}

    return application


app = create_app()
