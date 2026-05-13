"""请求超时中间件（纯 ASGI 实现）

防止请求无限挂起。SSE 流式端点跳过超时检查。
"""
import asyncio
from loguru import logger


class TimeoutMiddleware:
    """纯 ASGI 中间件：全局请求超时保护"""

    def __init__(self, app, timeout: int = 300):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # SSE 端点跳过中间件超时（流式连接可能长期保持）
        if "/stream" in path or path == "/api/v1/chat/send/stream":
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            method = scope.get("method", "")
            logger.warning("请求超时: {} {} ({}s)", method, path, self.timeout)
            # 发送 504 响应
            body = '{"error":"请求超时","detail":"服务器处理时间过长，请重试"}'.encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 504,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
