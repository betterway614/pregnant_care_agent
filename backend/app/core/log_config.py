"""Loguru 日志配置

在 main.py 入口调用一次 setup_logging() 即可：
  - 按 DEBUG / INFO / WARNING / ERROR 分颜色输出到控制台
  - 全部日志写入 logs/app_YYYY-MM-DD.log（按天轮转，保留7天）
  - ERROR 及以上单独写入 logs/error_YYYY-MM-DD.log（保留30天）
  - 接管 uvicorn / fastapi 等标准 logging 到 loguru
  - 全局日志脱敏：自动替换手机号、健康指标等敏感数据
"""
import logging
import sys
from pathlib import Path
from loguru import logger


class InterceptHandler(logging.Handler):
    """将标准 logging 全部转发到 loguru，保留原始 logger 名称"""

    def emit(self, record: logging.LogRecord) -> None:
        # 在源头拦截 sqlalchemy 的 SQL 语句（INFO 级别），不转发到 loguru
        if record.name.startswith("sqlalchemy") and record.levelno < logging.WARNING:
            return
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        # 使用 original logger name 作为 module 标识，便于溯源
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, "[{}] {}", record.name, record.getMessage()
        )


def _log_message_patcher(record: dict) -> None:
    """全局日志脱敏 patcher — 在每条日志格式化前自动脱敏 message 字段。

    复用 audit_service._desensitize_health 的脱敏规则：
    - 手机号 → [手机号]
    - 血压/体重/血糖/心率/体温 → [血压值]/[体重值]/etc.

    注意：仅影响 message 字段，不影响结构化 extra 字段。
    延迟导入避免循环依赖。
    """
    from ..services.audit_service import _desensitize_health

    msg = record.get("message")
    if isinstance(msg, str):
        record["message"] = _desensitize_health(msg)


def setup_logging(log_dir: str = "logs") -> None:
    """应用启动时调用一次"""

    logger.remove()  # 清除 loguru 默认 handler

    # ── 全局消息脱敏 ──
    # 通过 patcher 在格式化前对所有日志消息做脱敏，覆盖所有 sink
    logger.configure(patcher=_log_message_patcher)

    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # ── DEBUG → 绿色 ──
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
        colorize=True,
        filter=lambda r: r["level"].no < 20,
    )

    # ── INFO / WARNING → 白色/黄色 ──
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:HH:mm:ss} | {level: <8} | {name} | {message}",
        colorize=True,
        filter=lambda r: 20 <= r["level"].no < 40,
    )

    # ── ERROR+ → 红色 ──
    logger.add(
        sys.stderr,
        level="ERROR",
        format="<red>{time:HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}</red>",
        colorize=True,
    )

    # ── 全部日志 → 文件（按天轮转） ──
    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        enqueue=True,
    )

    # ── ERROR 单独写文件 ──
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="30 days",
        enqueue=True,
    )

    # ── 接管第三方库的 logging ──
    for lib in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(lib).handlers = [InterceptHandler()]
        logging.getLogger(lib).propagate = False

    # sqlalchemy: 用 NullHandler 静默 SQL 语句（InterceptHandler 在 emit 中已拦截）
    for name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine",
                 "sqlalchemy.pool", "sqlalchemy.dialects", "sqlalchemy.orm"):
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False

    # root logger
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
