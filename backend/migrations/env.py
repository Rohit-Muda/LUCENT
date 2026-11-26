
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from backend.app.config import get_settings
from backend.app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured_url = get_settings().database_url
    if configured_url is None:
        raise RuntimeError("DATABASE_URL must be configured before running migrations.")

    url = configured_url.get_secret_value()

    try:
        parsed_url = make_url(url)
    except ArgumentError as exc:
        raise RuntimeError("DATABASE_URL is invalid.") from exc

    if parsed_url.drivername != "mysql+pymysql":
        raise RuntimeError("DATABASE_URL must use mysql+pymysql.")

    return url


def _set_configured_url() -> str:
    url = _database_url()
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return url


def run_migrations_offline() -> None:
    url = _set_configured_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    _set_configured_url()

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"ssl": {}},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
