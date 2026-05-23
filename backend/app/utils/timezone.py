"""东八区（北京时间）工具函数

全局替换 datetime.utcnow()，统一使用北京时间。
SQLite DateTime 列存储 timezone-naive 的北京时间。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    """返回东八区当前时间（timezone-naive，适合存入 SQLite）"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def beijing_today():
    """返回东八区当前日期"""
    return datetime.now(BEIJING_TZ).date()
