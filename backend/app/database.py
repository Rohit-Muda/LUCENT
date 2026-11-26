
from functools import lru_cache
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings


class DatabaseConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if database_url is None:
        raise DatabaseConfigurationError("DATABASE_URL must be configured.")

    try:
        url = make_url(database_url.get_secret_value())
    except ArgumentError as exc:
        raise DatabaseConfigurationError("DATABASE_URL is invalid.") from exc

    if url.drivername != "mysql+pymysql":
        raise DatabaseConfigurationError("DATABASE_URL must use mysql+pymysql.")

    try:
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"ssl": {}},
        )
    except SQLAlchemyError as exc:
        raise DatabaseConfigurationError(
            "The configured database engine is invalid."
        ) from exc


def check_database_connection() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
