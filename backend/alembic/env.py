"""Alembic 环境配置 — 使用项目数据库配置和模型元数据"""
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 确保项目包可导入
sys.path.insert(0, ".")

# 从项目配置获取数据库 URL 和模型元数据
from app.config import settings
from app.database import Base

# 导入所有模型以确保 autogenerate 能发现它们
import app.models.models  # noqa: F401

# Alembic Config object
config = context.config

# 动态设置数据库 URL（来自项目配置，而非 alembic.ini 硬编码）
config.set_main_option("sqlalchemy.url", settings.database_url)

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 的目标元数据
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式迁移（仅生成 SQL，不连接数据库）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 兼容：ALTER TABLE 用 batch 模式
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式迁移（连接数据库执行）"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 兼容
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
