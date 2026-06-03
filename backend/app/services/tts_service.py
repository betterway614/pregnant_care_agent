"""TTS (语音合成) 服务 - 支持 cloud/local 两种后端模式"""
import asyncio
import io
from typing import Optional

import httpx
from loguru import logger

from ..config import settings, get_tts_mode


class TTSService:
    """统一 TTS 服务

    支持两种使用方式:
    1. 注入模式: 通过 __init__ 传入 TTSBackend 实现（OCP 合规）
    2. 旧模式: 保留原有 if/elif 分发逻辑（向后兼容）

    模式（后端处理的两种模式）：
    - cloud: DashScope CosyVoice API
    - local: edge-tts（微软 Edge TTS，免费高质量中文）

    注意: browser 模式由前端 SpeechSynthesis 处理，不经过此服务。
    """

    def __init__(self, backend=None) -> None:
        """Args:
            backend: 可选的 TTSBackend 实现。传入时优先使用。
        """
        self._backend = backend

    async def synthesize(self, text: str, role: str = "pregnant") -> Optional[bytes]:
        """将文本转为音频 bytes（MP3 格式）。

        Returns:
            MP3 音频字节，失败返回 None
        """
        # 优先使用注入的后端（OCP 合规路径）
        if self._backend is not None:
            try:
                return await self._backend.synthesize(text)
            except Exception as e:
                logger.error("[TTS] 后端合成失败: {}", e)
                return None

        # 回退到旧的 if/elif 分发逻辑（向后兼容）
        mode = get_tts_mode(role)
        logger.info("[TTS] role={}, mode={}, text_len={}", role, mode, len(text))

        if mode == "browser":
            logger.info("[TTS] browser 模式，无需后端处理")
            return None

        if mode == "cloud":
            return await self._synthesize_cloud(text)

        if mode == "local":
            return await self._synthesize_local(text)

        logger.warning("[TTS] 未知模式 '{}', 降级为 browser", mode)
        return None

    # ---- cloud: DashScope CosyVoice ----

    async def _synthesize_cloud(self, text: str) -> Optional[bytes]:
        api_key = settings.tts_cloud_api_key or settings.llm_api_key
        if not api_key:
            logger.error("[TTS] cloud 模式缺少 API Key")
            return None

        url = f"{settings.tts_cloud_base_url}/services/aigc/text2audio/generation"

        payload = {
            "model": settings.tts_cloud_model,
            "input": {
                "text": text[:500],  # CosyVoice 文本长度限制
            },
            "parameters": {
                "voice": settings.tts_cloud_voice,
                "format": "mp3",
                "sample_rate": 22050,
            },
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 提交异步任务
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                task_data = resp.json()

                task_id = task_data.get("output", {}).get("task_id")
                if not task_id:
                    logger.error("[TTS] cloud 未返回 task_id: {}", task_data)
                    return None

                # 轮询任务结果
                check_url = f"{settings.tts_cloud_base_url}/tasks/{task_id}"
                for _ in range(30):  # 最多等待 30 秒
                    await asyncio.sleep(1)
                    check_resp = await client.get(check_url, headers=headers)
                    check_data = check_resp.json()
                    status = check_data.get("output", {}).get("task_status")

                    if status == "SUCCEEDED":
                        audio_url = check_data["output"]["results"][0]["url"]
                        audio_resp = await client.get(audio_url)
                        logger.info("[TTS] cloud 合成成功: {}bytes", len(audio_resp.content))
                        return audio_resp.content
                    elif status == "FAILED":
                        logger.error("[TTS] cloud 任务失败: {}", check_data)
                        return None

                logger.error("[TTS] cloud 任务超时")
                return None
        except Exception as e:
            logger.error("[TTS] cloud 调用失败: {}", e)
            return None

    # ---- local: edge-tts ----

    async def _synthesize_local(self, text: str) -> Optional[bytes]:
        try:
            import edge_tts
        except ImportError:
            logger.error("[TTS] local 模式需要安装 edge-tts: pip install edge-tts")
            return None

        try:
            voice = settings.tts_local_voice
            communicate = edge_tts.Communicate(text[:500], voice)

            audio_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])

            result = audio_data.getvalue()
            if result:
                logger.info("[TTS] local 合成成功: {}bytes", len(result))
                return result

            logger.warning("[TTS] local 合成结果为空")
            return None
        except Exception as e:
            logger.error("[TTS] local 合成失败: {}", e)
            return None


tts_service = TTSService()
