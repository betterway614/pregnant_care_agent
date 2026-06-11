"""数据库连接与会话管理"""
import asyncio
from typing import TypeVar, Callable
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# 检查是否需要支持UUID的SQLite
if settings.db_type == "sqlite":
    from sqlalchemy import event
    import uuid

    def _uuid_sqlite():
        """SQLite UUID支持"""
        return str(uuid.uuid4())

    engine = create_engine(
        settings.database_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        # 并发写入时等待最多 5 秒，避免立即报 "database is locked"
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
else:
    engine = create_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,       # 连接池基础大小
        max_overflow=20,    # 突发负载时额外连接数
        pool_timeout=30,    # 等待连接的最大秒数
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


T = TypeVar("T")


async def db_call(func: Callable[..., T], *args, **kwargs) -> T:
    """在默认线程池中执行同步 DB 操作，避免阻塞 async 事件循环

    用法:
        result = await db_call(some_sync_function, arg1, arg2)
    """
    return await asyncio.to_thread(lambda: func(*args, **kwargs))
