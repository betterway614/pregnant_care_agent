"""FastAPI 请求/响应日志中间件（纯 ASGI 实现）

使用原生 ASGI 接口替代 BaseHTTPMiddleware，
兼容 Starlette 1.x / FastAPI 最新版。
在请求处理前就输出一条入口日志，方便定位卡死位置。

安全策略：不记录 request/response body 内容，
避免医疗隐私数据（PHI）泄露到日志文件。
"""
import time
from loguru import logger


class RequestLogMiddleware:
    """纯 ASGI 中间件：记录请求入口和响应状态（不含 body 内容）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # 跳过静态资源/上传文件的请求日志
        if path.startswith("/static") or path.startswith("/uploads"):
            await self.app(scope, receive, send)
            return

        start = time.time()

        # ── 读取请求体（用于回放给下游，但不记录内容） ──
        body_bytes = b""
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] == "http.request":
                body_bytes += msg.get("body", b"")
                more_body = msg.get("more_body", False)
            else:
                more_body = False

        # ── 请求入口日志（仅记录方法+路径，不记录 body 以保护隐私） ──
        body_size = len(body_bytes)
        logger.info("[REQ] {} {} (body_size={}B)", method, path, body_size)

        # ── 将已读取的 body 回放给下游处理器 ──
        body_replayed = False

        async def replay_receive():
            nonlocal body_replayed
            if not body_replayed:
                body_replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        # ── 收集响应状态（不收集响应 body 内容） ──
        resp_status = 200
        resp_body_size = 0

        async def send_wrapper(msg):
            nonlocal resp_status, resp_body_size
            if msg["type"] == "http.response.start":
                resp_status = msg.get("status", 200)
            elif msg["type"] == "http.response.body":
                resp_body_size += len(msg.get("body", b""))
            await send(msg)

        # ── 执行后续中间件 ──
        try:
            await self.app(scope, replay_receive, send_wrapper)
        except Exception:
            elapsed = time.time() - start
            logger.error("[REQ] {} {} 异常 ({:.0f}ms)", method, path, elapsed * 1000)
            raise

        elapsed = time.time() - start

        logger.info(
            "[RES] {} {} [{}] ({:.0f}ms) resp_size={}B",
            method, path, resp_status,
            elapsed * 1000,
            resp_body_size,
        )
