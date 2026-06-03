"""
ASR 后端实现 — 语音识别的具体提供商

遵循 OCP: 新增后端只需实现 ASRBackend 协议并注册到容器。
遵循 SRP: 每个后端类只负责一种 ASR 服务的对接。
"""
from __future__ import annotations

import asyncio
import base64
import tempfile
from typing import Any

import httpx
from loguru import logger


class DashScopeASRBackend:
    """阿里云 DashScope 语音识别"""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._base_url = "https://dashscope.aliyuncs.com/api/v1"

    async def transcribe(self, audio_base64: str, audio_format: str) -> str:
        audio_bytes = base64.b64decode(audio_base64)

        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            # 提交转录任务
            async with httpx.AsyncClient(timeout=60) as client:
                submit_resp = await client.post(
                    f"{self._base_url}/services/audio/asr/transcription",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "paraformer-v2",
                        "input": {"file_urls": [f"file://{temp_path}"]},
                    },
                )
                submit_data = submit_resp.json()
                task_id = submit_data.get("output", {}).get("task_id")
                if not task_id:
                    raise RuntimeError(f"提交转录任务失败: {submit_data}")

                # 轮询结果
                for _ in range(30):
                    await asyncio.sleep(2)
                    poll_resp = await client.get(
                        f"{self._base_url}/tasks/{task_id}",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                    )
                    poll_data = poll_resp.json()
                    status = poll_data.get("output", {}).get("task_status")
                    if status == "SUCCEEDED":
                        results = poll_data.get("output", {}).get("results", [])
                        if results:
                            return results[0].get("transcription_text", "")
                        return ""
                    elif status == "FAILED":
                        raise RuntimeError(f"转录失败: {poll_data}")

                raise RuntimeError("转录超时")
        finally:
            import os
            os.unlink(temp_path)


class FunASRBackend:
    """FunASR 本地服务"""

    def __init__(self, server_url: str = "http://localhost:10095") -> None:
        self._server_url = server_url

    async def transcribe(self, audio_base64: str, audio_format: str) -> str:
        audio_bytes = base64.b64decode(audio_base64)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._server_url}/",
                files={"audio": (f"audio.{audio_format}", audio_bytes)},
            )
            data = resp.json()
            if isinstance(data, dict):
                return data.get("text", data.get("result", ""))
            return str(data)


class WhisperBackend:
    """Whisper 本地推理"""

    def __init__(self, model_name: str = "base") -> None:
        self._model_name = model_name

    async def transcribe(self, audio_base64: str, audio_format: str) -> str:
        import whisper
        audio_bytes = base64.b64decode(audio_base64)

        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            model = whisper.load_model(self._model_name)
            result = await asyncio.to_thread(model.transcribe, temp_path)
            return result.get("text", "")
        finally:
            import os
            os.unlink(temp_path)


class MockASRBackend:
    """Mock ASR — 测试用"""

    async def transcribe(self, audio_base64: str, audio_format: str) -> str:
        return "[语音转录结果 - Mock模式]"
