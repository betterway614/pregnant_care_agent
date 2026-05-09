"""数据库连接与会话管理"""
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
        cursor.close()
else:
    engine = create_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
