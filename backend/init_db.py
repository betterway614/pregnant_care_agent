"""
数据库初始化脚本 - 可独立运行
用法:
    python init_db.py                  # 创建表 + 列迁移 + 注入Mock数据
    python init_db.py --force          # 删除旧库全部重建
    python init_db.py --ingest         # 同时执行知识库文档入库
    python init_db.py --force --ingest # 全部重建 + 知识库入库
功能: 创建所有表、执行列迁移、注入Mock演示数据、（可选）知识库入库
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base
from app.models import *  # noqa: 确保所有模型已导入
from app.scripts.seed_data import seed_all

force = "--force" in sys.argv
do_ingest = "--ingest" in sys.argv

print("=" * 50)
print("  AI-Care 数据库初始化")
print("=" * 50)

# 0. 强制重建
if force:
    db_path = "ai_care.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"\n[0] 已删除旧数据库: {db_path}")

# 1. 创建所有表
print("\n[1/4] 创建数据库表...")
Base.metadata.create_all(bind=engine)
print("  表创建完成")

# 2. 执行列迁移（幂等）
print("\n[2/4] 执行列迁移...")
from app.main import (
    _ensure_schedule_columns,
    _ensure_pregnant_columns,
    _ensure_fgr_columns,
    _ensure_followup_columns,
    _ensure_order_columns,
    _ensure_alert_columns,
    _ensure_audit_log_table,
    _ensure_feedback_audit_link,
    _ensure_resource_tables,
    _ensure_diary_table,
)
_ensure_schedule_columns()
_ensure_pregnant_columns()
_ensure_fgr_columns()
_ensure_followup_columns()
_ensure_order_columns()
_ensure_alert_columns()
_ensure_audit_log_table()
_ensure_feedback_audit_link()
_ensure_resource_tables()
_ensure_diary_table()
print("  列迁移完成")

# 3. 注入Mock数据
print("\n[3/4] 注入Mock演示数据...")
seed_all()

# 4. 知识库入库（可选）
if do_ingest:
    print("\n[4/4] 知识库文档入库...")
    from app.config import settings
    if settings.rag_enabled:
        try:
            from scripts.ingest_knowledge import ingest
            ingest(force=force)
        except Exception as e:
            print(f"  知识库入库失败（可稍后重试）: {e}")
    else:
        print("  RAG 未启用，跳过入库")
else:
    print("\n[4/4] 知识库入库（跳过，使用 --ingest 启用）")

print("\n" + "=" * 50)
print("  初始化完成！可以启动服务了")
print("  python -m uvicorn app.main:app --port 8000")
print("=" * 50)
