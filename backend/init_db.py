"""
数据库初始化脚本 - 可独立运行
用法:
    python init_db.py            # 创建表 + 注入Mock数据（保留已有数据）
    python init_db.py --force    # 删除旧库全部重建
功能: 创建所有表、执行列迁移、注入Mock演示数据
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base
from app.models import *  # noqa: 确保所有模型已导入
from app.scripts.seed_data import seed_all

force = "--force" in sys.argv

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
print("\n[1/3] 创建数据库表...")
Base.metadata.create_all(bind=engine)
print("  表创建完成")

# 2. 执行列迁移（幂等）
print("\n[2/3] 执行列迁移...")
from app.main import _ensure_fgr_columns, _ensure_followup_columns
_ensure_fgr_columns()
_ensure_followup_columns()
print("  列迁移完成")

# 3. 注入Mock数据
print("\n[3/3] 注入Mock演示数据...")
seed_all()

print("\n" + "=" * 50)
print("  初始化完成！可以启动服务了")
print("  python -m uvicorn app.main:app --port 8000")
print("=" * 50)
