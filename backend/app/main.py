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
from .routers import websocket, tts, admin, knowledge, resource
from .models import AgentAuditLog, ToolCallDetail, Feedback
from .models.models import ResourceAlert, ResourceMetric, GeneratedReport

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


def _ensure_alert_columns():
    """为已有 SQLite 数据库添加 Alert 新列（幂等）"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("alerts")]
        new_cols = [
            ("domain", "VARCHAR(32)"),
        ]
        with engine.connect() as conn:
            for col_name, col_type in new_cols:
                if col_name not in columns:
                    conn.execute(sa.text(
                        f"ALTER TABLE alerts ADD COLUMN {col_name} {col_type}"
                    ))
                    logger.info("alerts.{} 列已添加", col_name)
            conn.commit()
    except Exception as e:
        logger.warning("Alert 列迁移跳过: {}", e)


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


def _ensure_pregnant_columns():
    """为已有 SQLite 数据库添加 Pregnant 基线数据新列（幂等）

    新增身高、孕前体重两个静态基线字段。
    """
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("pregnant")]
        new_cols = [
            ("height_cm", "FLOAT", None),
            ("pre_pregnancy_weight_kg", "FLOAT", None),
        ]
        added = 0
        with engine.connect() as conn:
            for col_name, col_type, default_val in new_cols:
                if col_name not in columns:
                    sql = f"ALTER TABLE pregnant ADD COLUMN {col_name} {col_type}"
                    if default_val:
                        sql += f" DEFAULT {default_val}"
                    conn.execute(sa.text(sql))
                    added += 1
            conn.commit()
        if added:
            logger.info("Pregnant 基线列迁移完成: 新增 {} 列", added)
    except Exception as e:
        logger.warning("Pregnant 列迁移跳过: {}", e)


def _ensure_audit_log_table():
    """为已有数据库添加 agent_audit_logs 表 + tool_call_details 表（幂等）"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        existing = inspector.get_table_names()
        tables_to_create = []
        if "agent_audit_logs" not in existing:
            tables_to_create.append(AgentAuditLog.__table__)
        if "tool_call_details" not in existing:
            tables_to_create.append(ToolCallDetail.__table__)
        if tables_to_create:
            Base.metadata.create_all(bind=engine, tables=tables_to_create)
            logger.info("审计表创建完成: {}", [t.name for t in tables_to_create])
        else:
            logger.info("审计表已存在，跳过创建")

        # 为已有 agent_audit_logs 表添加新列（tool_call_count, tool_error_count, feedback_*）
        if "agent_audit_logs" in existing:
            audit_cols = {c["name"] for c in inspector.get_columns("agent_audit_logs")}
            with engine.begin() as conn:
                if "tool_call_count" not in audit_cols:
                    conn.execute(sa.text("ALTER TABLE agent_audit_logs ADD COLUMN tool_call_count INTEGER DEFAULT 0"))
                    logger.info("agent_audit_logs 添加 tool_call_count 列")
                if "tool_error_count" not in audit_cols:
                    conn.execute(sa.text("ALTER TABLE agent_audit_logs ADD COLUMN tool_error_count INTEGER DEFAULT 0"))
                    logger.info("agent_audit_logs 添加 tool_error_count 列")
                if "feedback_rating" not in audit_cols:
                    conn.execute(sa.text("ALTER TABLE agent_audit_logs ADD COLUMN feedback_rating VARCHAR(16)"))
                    logger.info("agent_audit_logs 添加 feedback_rating 列")
                if "feedback_comment" not in audit_cols:
                    conn.execute(sa.text("ALTER TABLE agent_audit_logs ADD COLUMN feedback_comment TEXT"))
                    logger.info("agent_audit_logs 添加 feedback_comment 列")
    except Exception as e:
        logger.warning("审计表迁移跳过: {}", e)


def _ensure_feedback_audit_link():
    """为已有 feedback 表添加新列（幂等）：audit_log_id, feedback_role, user_id"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        if "feedback" in inspector.get_table_names():
            fb_cols = {c["name"] for c in inspector.get_columns("feedback")}
            with engine.begin() as conn:
                if "audit_log_id" not in fb_cols:
                    conn.execute(sa.text("ALTER TABLE feedback ADD COLUMN audit_log_id INTEGER"))
                    logger.info("feedback 表添加 audit_log_id 列")
                if "feedback_role" not in fb_cols:
                    conn.execute(sa.text("ALTER TABLE feedback ADD COLUMN feedback_role VARCHAR(16) NOT NULL DEFAULT 'pregnant'"))
                    logger.info("feedback 表添加 feedback_role 列")
                if "user_id" not in fb_cols:
                    conn.execute(sa.text("ALTER TABLE feedback ADD COLUMN user_id VARCHAR(64)"))
                    logger.info("feedback 表添加 user_id 列")
            # 放宽 pregnant_id 约束（护士/医生反馈可能不关联孕妇）
            # SQLite 不支持 ALTER COLUMN，仅对 PostgreSQL 生效
            if settings.db_type == "postgres":
                try:
                    with engine.begin() as conn:
                        conn.execute(sa.text("ALTER TABLE feedback ALTER COLUMN pregnant_id DROP NOT NULL"))
                    logger.info("feedback.pregnant_id 放宽为可空")
                except Exception:
                    pass  # 已经是可空的
    except Exception as e:
        logger.warning("feedback 迁移跳过: {}", e)


def _ensure_resource_tables():
    """为已有数据库添加资源管理相关表（幂等）"""
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        existing = inspector.get_table_names()
        tables_to_create = []
        if "resource_alerts" not in existing:
            tables_to_create.append(ResourceAlert.__table__)
        if "resource_metrics" not in existing:
            tables_to_create.append(ResourceMetric.__table__)
        if "generated_reports" not in existing:
            tables_to_create.append(GeneratedReport.__table__)
        if tables_to_create:
            Base.metadata.create_all(bind=engine, tables=tables_to_create)
            logger.info("资源管理表创建完成: {}", [t.name for t in tables_to_create])
        else:
            logger.info("资源管理表已存在，跳过创建")
    except Exception as e:
        logger.warning("资源管理表迁移跳过: {}", e)


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

    # 对已有 SQLite 数据库添加 Pregnant 基线数据新列
    _ensure_pregnant_columns()
    # 对已有 SQLite 数据库添加 FGR 新列
    _ensure_fgr_columns()
    # 对已有 SQLite 数据库添加 FollowUpRecord 归档新列
    _ensure_followup_columns()
    # 对已有 SQLite 数据库添加 MedicalOrder 签署增强新列
    _ensure_order_columns()
    # 对已有 SQLite 数据库添加 Alert 新列
    _ensure_alert_columns()
    _ensure_audit_log_table()
    _ensure_feedback_audit_link()
    _ensure_resource_tables()

    # FGR 模式：按 .env 的 FGR_BACKEND 加载真实预测模型
    if settings.fgr_mode:
        try:
            from fgr_compete.predictor import initialize_predictor_for_backend
            predictor = initialize_predictor_for_backend(settings.fgr_backend)
            if predictor is not None:
                logger.info(
                    "FGR 预测模型加载完成 backend={} hardware={}",
                    settings.fgr_backend, getattr(predictor, "hardware", "unknown"),
                )
        except Exception as e:
            logger.error("FGR 模型初始化失败，回退到 mock 模式: {}", e)

    # 初始化依赖注入容器
    try:
        from .container import setup_container
        setup_container()
    except Exception as e:
        logger.warning("DI 容器初始化失败，使用旧模式: {}", e)

    logger.info("{} v{} 启动成功", settings.app_name, settings.app_version)
    logger.info("  LLM模式: {}", settings.llm_mode)
    logger.info("  FGR模式: {}", settings.fgr_mode)
    logger.info("  FGR后端: {}", settings.fgr_backend)
    logger.info("  数据库: {}:{}/{}", settings.db_host, settings.db_port, settings.db_name)

    if settings.seed_data:
        try:
            from .scripts.seed_data import seed_all
            seed_all()
        except Exception as e:
            logger.error("Mock数据注入失败: {}", e)

    # 修复可能存在 rule_id 与 message 不匹配的预警数据
    try:
        from .services.alert_service import alert_service
        from .database import SessionLocal
        db = SessionLocal()
        repaired = alert_service.repair_mismatched_alerts(db)
        if repaired:
            logger.info(f"预警数据修复: 已修正 {repaired} 条不匹配记录")
        db.close()
    except Exception as e:
        logger.warning(f"预警数据修复检查跳过: {e}")

    yield
    # 应用关闭
    if settings.fgr_mode:
        from fgr_compete.predictor import _PREDICTOR as fgr_predictor
        if fgr_predictor is not None:
            # 关闭 NPU 子进程（如有）
            if hasattr(fgr_predictor, "close"):
                fgr_predictor.close()
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
# 开发环境（debug=True）：允许所有来源，支持 SSH 远程开发 / 局域网访问 / IP 变化
# 生产环境：通过 settings.cors_origins 或环境变量 CORS_ORIGINS 配置域名白名单
if settings.debug:
    _cors_origins = ["*"]
    logger.info("CORS: 开发模式，允许所有来源")
else:
    _cors_origins = getattr(settings, "cors_origins", None) or [
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
    ]
    logger.info(f"CORS: 生产模式，白名单: {_cors_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── JWT 认证中间件 ──
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from .core.auth import decode_token

_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/api/v1/auth/login"}
_PUBLIC_PREFIXES = ("/api/v1/fgr/image/", "/ws/")


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT认证中间件：跳过公开路径和OPTIONS请求"""

    async def dispatch(self, request: Request, call_next):
        # 跳过 OPTIONS 预检请求
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        # 跳过公开路径
        if path in _PUBLIC_PATHS:
            return await call_next(request)

        # 跳过公开路径前缀（如 FGR 图片端点，供 <img src> 无 auth 访问）
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # 跳过静态资源
        if path.startswith("/assets") or path.rsplit(".", 1)[-1] in ("js", "css", "ico", "png", "jpg", "svg", "woff", "woff2", "ttf"):
            return await call_next(request)

        # 跳过 Swagger UI 相关资源
        if path.startswith("/swagger") or path.startswith("/favicon"):
            return await call_next(request)

        # 检查 Authorization 头
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "未提供认证凭据"})

        token = auth_header[7:]  # 去掉 "Bearer " 前缀
        payload = decode_token(token)
        if payload is None:
            return JSONResponse(status_code=401, content={"detail": "认证凭据无效或已过期"})

        return await call_next(request)


app.add_middleware(AuthMiddleware)

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
app.include_router(admin.router)
app.include_router(knowledge.router)
app.include_router(resource.router)


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
