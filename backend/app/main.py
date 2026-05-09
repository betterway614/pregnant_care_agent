"""AI-Care 孕期智能管理平台 - FastAPI 主入口"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .config import settings
from .database import engine, Base
from .routers import chat, schedule, followup, alerts, fgr, orders, dashboard, monitor
from .routers import pregnant, recommend, nurse_ai, doctor_ai, auth, fetal_movement


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动：创建表
    Base.metadata.create_all(bind=engine)
    print(f"[OK] {settings.app_name} v{settings.app_version} 启动成功")
    print(f"  LLM模式: {settings.llm_mode}")
    print(f"  FGR模式: {settings.fgr_mode}")
    print(f"  数据库: {settings.db_host}:{settings.db_port}/{settings.db_name}")

    # 启动后自动填充Mock数据
    if settings.seed_data:
        try:
            from .scripts.seed_data import seed_all
            seed_all()
        except Exception as e:
            print(f"   Mock数据注入: {e}")

    yield
    # 关闭：清理资源
    print("应用关闭")


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
app.include_router(monitor.router)
app.include_router(pregnant.router)
app.include_router(recommend.router)
app.include_router(nurse_ai.router)
app.include_router(doctor_ai.router)
app.include_router(auth.router)
app.include_router(fetal_movement.router)


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
