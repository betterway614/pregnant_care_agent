"""FastAPI 请求/响应日志中间件（纯 ASGI 实现）

使用原生 ASGI 接口替代 BaseHTTPMiddleware，
兼容 Starlette 1.x / FastAPI 最新版。
在请求处理前就输出一条入口日志，方便定位卡死位置。
"""
import json
import time
from loguru import logger


class RequestLogMiddleware:
    """纯 ASGI 中间件：记录请求入口和响应状态"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        import sys as _sys
        print(f"[ASGI_CALL] type={scope.get('type')} path={scope.get('path')}", file=_sys.stderr, flush=True)

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # 只记录非静态资源请求
        if path.startswith("/static") or path.startswith("/uploads"):
            await self.app(scope, receive, send)
            return

        start = time.time()

        # ── 读取请求体 ──
        body_bytes = b""
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] == "http.request":
                body_bytes += msg.get("body", b"")
                more_body = msg.get("more_body", False)
            else:
                more_body = False

        body_str = self._format_body(body_bytes)

        # ── 请求入口日志（在业务处理之前输出，即使后续卡死也能看到） ──
        logger.info("[REQ] {} {} body={}", method, path, body_str[:500])

        # ── 将已读取的 body 回放给下游处理器 ──
        # 否则下游中间件/路由会收到空 body，导致 POST/PUT 请求丢失数据
        body_replayed = False

        async def replay_receive():
            nonlocal body_replayed
            if not body_replayed:
                body_replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        # ── 收集响应体 ──
        resp_body = b""
        resp_status = 200

        async def send_wrapper(msg):
            nonlocal resp_body, resp_status
            if msg["type"] == "http.response.start":
                resp_status = msg.get("status", 200)
            elif msg["type"] == "http.response.body":
                resp_body += msg.get("body", b"")
            await send(msg)

        # ── 执行后续中间件（使用 replay_receive 替代原始 receive） ──
        try:
            await self.app(scope, replay_receive, send_wrapper)
        except Exception:
            elapsed = time.time() - start
            logger.error("[REQ] {} {} 异常 ({:.0f}ms)", method, path, elapsed * 1000)
            raise

        elapsed = time.time() - start
        resp_str = self._format_body(resp_body)

        logger.info(
            "[RES] {} {} [{}] ({:.0f}ms) resp={}",
            method, path, resp_status,
            elapsed * 1000,
            resp_str[:300],
        )

    @staticmethod
    def _format_body(body: bytes) -> str:
        if not body:
            return "(empty)"
        try:
            obj = json.loads(body)
            return json.dumps(obj, ensure_ascii=False, indent=2)[:2000]
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body.decode("utf-8", errors="replace")[:2000]
