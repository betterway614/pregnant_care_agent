"""Loguru 日志配置

在 main.py 入口调用一次 setup_logging() 即可：
  - 按 DEBUG / INFO / WARNING / ERROR 分颜色输出到控制台
  - 全部日志写入 logs/app_YYYY-MM-DD.log（按天轮转，保留7天）
  - ERROR 及以上单独写入 logs/error_YYYY-MM-DD.log（保留30天）
  - 接管 uvicorn / fastapi 等标准 logging 到 loguru
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


def setup_logging(log_dir: str = "logs") -> None:
    """应用启动时调用一次"""

    logger.remove()  # 清除 loguru 默认 handler

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
