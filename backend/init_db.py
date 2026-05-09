"""
数据库初始化脚本 - 可独立运行
用法: python init_db.py
功能: 创建所有表 + 注入Mock演示数据
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base
from app.models import *  # noqa: 确保所有模型已导入
from app.scripts.seed_data import seed_all

print("=" * 50)
print("  AI-Care 数据库初始化")
print("=" * 50)

# 1. 创建所有表
print("\n[1/2] 创建数据库表...")
Base.metadata.create_all(bind=engine)
print("  表创建完成")

# 2. 注入Mock数据
print("\n[2/2] 注入Mock演示数据...")
seed_all()

print("\n" + "=" * 50)
print("  初始化完成！可以启动服务了")
print("  python -m uvicorn app.main:app --port 8000")
print("=" * 50)
