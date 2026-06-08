"""
TTS 后端实现 — 语音合成的具体提供商

遵循 OCP: 新增后端只需实现 TTSBackend 协议并注册到容器。
遵循 SRP: 每个后端类只负责一种 TTS 服务的对接。
"""
from __future__ import annotations

import asyncio
import io
from typing import Any, AsyncGenerator

import httpx
from loguru import logger


class DashScopeTTSBackend:
    """阿里云 DashScope CosyVoice 语音合成"""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._base_url = "https://dashscope.aliyuncs.com/api/v1"

    async def synthesize(self, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            # 提交合成任务
            submit_resp = await client.post(
                f"{self._base_url}/services/aigc/text2audio/generation",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "cosyvoice-v2",
                    "input": {"text": text},
                    "parameters": {"format": "mp3"},
                },
            )
            submit_data = submit_resp.json()
            task_id = submit_data.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"提交合成任务失败: {submit_data}")

            # 轮询结果
            for _ in range(30):
                await asyncio.sleep(1)
                poll_resp = await client.get(
                    f"{self._base_url}/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                poll_data = poll_resp.json()
                status = poll_data.get("output", {}).get("task_status")
                if status == "SUCCEEDED":
                    audio_url = poll_data.get("output", {}).get("audio", {}).get("url", "")
                    if audio_url:
                        audio_resp = await client.get(audio_url)
                        return audio_resp.content
                    raise RuntimeError("合成成功但无音频URL")
                elif status == "FAILED":
                    raise RuntimeError(f"合成失败: {poll_data}")

            raise RuntimeError("合成超时")


class EdgeTTSBackend:
    """Edge-TTS 本地语音合成"""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        import edge_tts

        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, self._voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()


class MockTTSBackend:
    """Mock TTS — 测试用"""

    async def synthesize(self, text: str) -> bytes:
        # 返回空 MP3 帧
        return b"\xff\xfb\x90\x00" + b"\x00" * 100


class CosyVoiceLocalBackend:
    """CosyVoice2 本地 TTS 服务后端（通过 HTTP 调用独立部署的 CosyVoice2 服务）

    支持两种合成方式：
    - synthesize(): 非流式，等待完整音频生成后返回 bytes
    - synthesize_stream(): 流式，边生成边 yield WAV 音频块（首包延迟约 3-5s）
    """

    def __init__(
        self,
        base_url: str,
        speaker: str,
        timeout: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._speaker = speaker
        self._timeout = timeout

    async def synthesize(self, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/tts/synthesize",
                json={
                    "text": text,
                    "speaker": self._speaker,
                    "format": "mp3",
                    "speed": 1.0,
                },
            )
            if resp.status_code != 200:
                error_detail = resp.text
                raise RuntimeError(f"CosyVoice 合成失败 [{resp.status_code}]: {error_detail}")
            return resp.content

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """流式合成 — 边生成边 yield WAV 音频块

        首个 yield 是 WAV header，后续 yield 是 PCM_16 音频数据。
        客户端可实时写入音频播放器实现流式播放。
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/tts/stream",
                json={
                    "text": text,
                    "speaker": self._speaker,
                    "format": "wav",
                    "speed": 1.0,
                },
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"CosyVoice 流式合成失败 [{resp.status_code}]: {body.decode()}"
                    )
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    if chunk:
                        yield chunk

    async def get_speakers(self) -> list[str]:
        """获取可用说话人列表"""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{self._base_url}/v1/tts/speakers")
                if resp.status_code == 200:
                    return resp.json().get("speakers", [])
            except Exception:
                pass
            return []
