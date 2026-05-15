"""AI-Care 孕期智能管理平台 - FastAPI 主入口"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .config import settings
from .database import engine, Base
from .routers import chat, schedule, followup, alerts, fgr, orders, dashboard
from .routers import pregnant, recommend, nurse_ai, doctor_ai, auth, fetal_movement, feedback, mental_health, health_trends
from .routers import websocket

# 日志配置（在 app 创建前初始化，确保接管 uvicorn 的 logging）
from .core.log_config import setup_logging
from loguru import logger
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import logging as _logging
    _logging.getLogger("sqlalchemy.engine").setLevel(_logging.WARNING)

    Base.metadata.create_all(bind=engine)
    logger.info("数据库表同步完成（仅创建缺失表）")

    logger.info("{} v{} 启动成功", settings.app_name, settings.app_version)
    logger.info("  LLM模式: {}", settings.llm_mode)
    logger.info("  FGR模式: {}", settings.fgr_mode)
    logger.info("  数据库: {}:{}/{}", settings.db_host, settings.db_port, settings.db_name)

    if settings.seed_data:
        try:
            from .scripts.seed_data import seed_all
            seed_all()
        except Exception as e:
            logger.error("Mock数据注入失败: {}", e)

    yield
    logger.info("应用关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Care 孕期智能管理平台 API",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router)
app.include_router(schedule.router)
app.include_router(followup.router)
app.include_router(alerts.router)
app.include_router(fgr.router)
app.include_router(orders.router)
app.include_router(dashboard.router)
app.include_router(pregnant.router)
app.include_router(recommend.router)
app.include_router(nurse_ai.router)
app.include_router(doctor_ai.router)
app.include_router(auth.router)
app.include_router(fetal_movement.router)
app.include_router(feedback.router)
app.include_router(mental_health.router)
app.include_router(health_trends.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
