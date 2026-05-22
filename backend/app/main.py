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
from .routers import websocket, tts

# 日志配置（在 app 创建前初始化，确保接管 uvicorn 的 logging）
from .core.log_config import setup_logging
from loguru import logger
setup_logging()


def _ensure_fgr_columns():
    """为已有 SQLite 数据库添加 FGR 新列（幂等）"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("fgr_assessments")]
        new_cols = [
            ("fgr_probability", "FLOAT"),
            ("predicted_label", "VARCHAR(8)"),
            ("model_confidence", "VARCHAR(8)"),
        ]
        with engine.connect() as conn:
            for col_name, col_type in new_cols:
                if col_name not in columns:
                    conn.execute(sa.text(
                        f"ALTER TABLE fgr_assessments ADD COLUMN {col_name} {col_type}"
                    ))
            conn.commit()
    except Exception as e:
        logger.warning("FGR 列迁移跳过: {}", e)


def _ensure_followup_columns():
    """为已有 SQLite 数据库添加 FollowUpRecord 归档新列（幂等）

    参照国家基本公共卫生服务规范(2024版) + SOAP格式新增字段。
    SQLite ALTER TABLE 限制: JSON/DATE/TIMESTAMP 列不加 DEFAULT，
    由模型的 default=dict/list 或应用层保证默认值。
    """
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("follow_up_records")]
        # (column_name, type, default_value) — default 仅在支持时使用
        new_cols = [
            # O: 客观数据
            ("obstetric_exam", "JSON", None),
            ("lab_results", "JSON", None),
            # A: 评估
            ("classification", "VARCHAR(32)", "'normal'"),
            # P: 计划
            ("guidance_tags", "JSON", None),
            ("referral", "JSON", None),
            ("next_followup_date", "DATE", None),
            # 审核追溯
            ("reviewed_by", "VARCHAR(64)", None),
            ("reviewed_at", "TIMESTAMP", None),
            ("review_comment", "TEXT", None),
            ("ai_snapshot", "JSON", None),
            # 归档文档
            ("record_snapshot", "JSON", None),
            ("record_text", "TEXT", None),
            ("signature_data", "JSON", None),
        ]
        added = 0
        with engine.connect() as conn:
            for col_name, col_type, default_val in new_cols:
                if col_name not in columns:
                    sql = f"ALTER TABLE follow_up_records ADD COLUMN {col_name} {col_type}"
                    if default_val:
                        sql += f" DEFAULT {default_val}"
                    conn.execute(sa.text(sql))
                    added += 1
            conn.commit()
        if added:
            logger.info("FollowUpRecord 归档列迁移完成: 新增 {} 列", added)
        else:
            logger.info("FollowUpRecord 归档列已存在，跳过迁移")
    except Exception as e:
        logger.warning("FollowUpRecord 列迁移跳过: {}", e)


def _ensure_order_columns():
    """为已有 SQLite 数据库添加 MedicalOrder 签署增强新列（幂等）

    新增手写签名、归档文档、医生修改追踪等字段。
    """
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("medical_orders")]
        new_cols = [
            ("signature_data", "JSON", None),
            ("order_snapshot", "JSON", None),
            ("order_text", "TEXT", None),
            ("modified_by_doctor", "BOOLEAN", "0"),
            ("doctor_notes", "TEXT", None),
        ]
        added = 0
        with engine.connect() as conn:
            for col_name, col_type, default_val in new_cols:
                if col_name not in columns:
                    sql = f"ALTER TABLE medical_orders ADD COLUMN {col_name} {col_type}"
                    if default_val:
                        sql += f" DEFAULT {default_val}"
                    conn.execute(sa.text(sql))
                    added += 1
            conn.commit()
        if added:
            logger.info("MedicalOrder 签署增强列迁移完成: 新增 {} 列", added)
    except Exception as e:
        logger.warning("MedicalOrder 列迁移跳过: {}", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import logging as _logging
    _logging.getLogger("sqlalchemy.engine").setLevel(_logging.WARNING)

    if settings.db_type == "sqlite":
        db_path = settings.database_url.replace("sqlite:///", "")
        db_exists = os.path.exists(db_path)
    else:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        db_exists = len(inspector.get_table_names()) > 0

    if not db_exists:
        Base.metadata.create_all(bind=engine)
        logger.info("数据库初始化完成")
    else:
        logger.info("数据库已存在，跳过初始化")

    # 对已有 SQLite 数据库添加 FGR 新列
    _ensure_fgr_columns()
    # 对已有 SQLite 数据库添加 FollowUpRecord 归档新列
    _ensure_followup_columns()
    # 对已有 SQLite 数据库添加 MedicalOrder 签署增强新列
    _ensure_order_columns()

    # FGR 模式：加载真实预测模型
    if settings.fgr_mode:
        try:
            from fgr_compete import initialize_predictor
            initialize_predictor()
            logger.info("FGR 预测模型加载完成")
        except Exception as e:
            logger.error("FGR 模型初始化失败，回退到 mock 模式: {}", e)

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
    # 应用关闭
    if settings.fgr_mode:
        from fgr_compete.predictor import _PREDICTOR as fgr_predictor
        if fgr_predictor is not None:
            logger.info("FGR 预测模型已释放")
    logger.info("应用关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-Care 孕期智能管理平台 API",
    lifespan=lifespan,
)

# 请求超时中间件（300s，跳过流式端点）
from .core.timeout_middleware import TimeoutMiddleware
app.add_middleware(TimeoutMiddleware, timeout=300)

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
app.include_router(tts.router)


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
