import asyncio
from typing import Annotated

from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import Engine, create_engine

from backend.app import database, main
from backend.app.config import Settings
from backend.app.database import get_engine


def test_health_endpoint_reports_application_status() -> None:
    response = _get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_missing_configuration(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: Settings(_env_file=None, database_url=None),
    )
    get_engine.cache_clear()

    try:
        response = _get("/health/database")
    finally:
        get_engine.cache_clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "DATABASE_URL" not in response.text


def test_database_health_reports_connection_success(monkeypatch: MonkeyPatch) -> None:
    test_engine = create_engine("sqlite://")
    monkeypatch.setattr(main, "check_database_connection", lambda: _check_engine(test_engine))

    try:
        response = _get("/health/database")
    finally:
        test_engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_http_error_response_uses_standard_shape() -> None:
    response = _get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "http_error", "message": "Not Found"}
    }


def test_validation_error_response_uses_standard_shape() -> None:
    test_app = main.create_app()

    @test_app.get("/validation-test")
    def validation_test(value: Annotated[int, Query(ge=1)]) -> dict[str, int]:
        return {"value": value}

    response = _get("/validation-test?value=0", app=test_app)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "input" not in response.json()["error"]["details"][0]


def _get(path: str, app: FastAPI = main.app):
    async def request():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _check_engine(engine: Engine) -> None:
    from sqlalchemy import text

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
