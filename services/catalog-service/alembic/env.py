from logging.config import fileConfig

import sqlmodel
from alembic import context
from app import models  # noqa: F401  (registra as tabelas no metadata)
from app.core.config import settings
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)

target_metadata = SQLModel.metadata


def render_item(type_: str, obj: object, autogen_context) -> object:
    if type_ == "type" and isinstance(obj, sqlmodel.sql.sqltypes.AutoString):
        length = getattr(obj, "length", None)
        if length:
            return f"sa.String(length={length})"
        return "sa.String()"
    return False


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
