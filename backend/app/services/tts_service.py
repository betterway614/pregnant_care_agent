"""TTS (语音合成) 服务 - 支持 cloud/local 两种后端模式"""
import asyncio
import io
from typing import AsyncGenerator, Optional

import httpx
from loguru import logger

from ..config import settings, get_tts_mode


class TTSService:
    """统一 TTS 服务"""

    def __init__(self, backend=None) -> None:
        self._backend = backend

    async def synthesize(
        self, text: str, role: str = "pregnant", speed: float = 1.0
    ) -> Optional[bytes]:
        """将文本转为音频 bytes"""
        if self._backend is not None:
            try:
                return await self._backend.synthesize(text)
            except Exception as e:
                logger.error("[TTS] 后端合成失败: {}", e)
                return None

        mode = get_tts_mode(role)
        logger.info("[TTS] role={}, mode={}, text_len={}", role, mode, len(text))

        if mode == "browser":
            return None
        if mode == "cloud":
            return await self._synthesize_cloud(text)
        if mode == "local":
            return await self._synthesize_local(text, role, speed)
        logger.warning("[TTS] 未知模式 '{}', 降级为 browser", mode)
        return None

    async def synthesize_stream(
        self, text: str, role: str = "pregnant", speed: float = 1.0
    ) -> AsyncGenerator[bytes, None]:
        """流式合成 — 边生成边 yield WAV 音频块"""
        mode = get_tts_mode(role)
        if mode != "local" or settings.tts_local_backend != "cosyvoice":
            raise RuntimeError(f"流式 TTS 仅支持 local/cosyvoice 模式，当前: {mode}")

        from .tts_backends import CosyVoiceLocalBackend

        speaker_map = {
            "pregnant": getattr(settings, "tts_local_cosyvoice_speaker_pregnant", None) or settings.tts_local_cosyvoice_speaker,
            "nurse": getattr(settings, "tts_local_cosyvoice_speaker_nurse", None) or settings.tts_local_cosyvoice_speaker,
            "doctor": getattr(settings, "tts_local_cosyvoice_speaker_doctor", None) or settings.tts_local_cosyvoice_speaker,
        }
        speaker = speaker_map.get(role, settings.tts_local_cosyvoice_speaker)

        backend = CosyVoiceLocalBackend(
            base_url=settings.tts_local_cosyvoice_url,
            speaker=speaker,
            timeout=settings.tts_local_cosyvoice_timeout,
        )
        try:
            async for chunk in backend.synthesize_stream(text, speed):
                yield chunk
        except Exception as e:
            logger.error("[TTS] CosyVoice 流式合成失败: {}", e)
            raise

    async def _synthesize_cloud(self, text: str) -> Optional[bytes]:
        api_key = settings.tts_cloud_api_key or settings.llm_api_key
        if not api_key:
            logger.error("[TTS] cloud 模式缺少 API Key")
            return None

        url = f"{settings.tts_cloud_base_url}/services/aigc/text2audio/generation"
        payload = {
            "model": settings.tts_cloud_model,
            "input": {"text": text[:500]},
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
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                task_data = resp.json()
                task_id = task_data.get("output", {}).get("task_id")
                if not task_id:
                    logger.error("[TTS] cloud 未返回 task_id: {}", task_data)
                    return None

                check_url = f"{settings.tts_cloud_base_url}/tasks/{task_id}"
                for _ in range(30):
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

    async def _synthesize_local(
        self, text: str, role: str = "pregnant", speed: float = 1.0
    ) -> Optional[bytes]:
        if settings.tts_local_backend == "cosyvoice":
            return await self._synthesize_cosyvoice(text, role, speed)
        else:
            return await self._synthesize_edge_tts(text)

    async def _synthesize_cosyvoice(
        self, text: str, role: str = "pregnant", speed: float = 1.0
    ) -> Optional[bytes]:
        from .tts_backends import CosyVoiceLocalBackend

        speaker_map = {
            "pregnant": getattr(settings, "tts_local_cosyvoice_speaker_pregnant", None) or settings.tts_local_cosyvoice_speaker,
            "nurse": getattr(settings, "tts_local_cosyvoice_speaker_nurse", None) or settings.tts_local_cosyvoice_speaker,
            "doctor": getattr(settings, "tts_local_cosyvoice_speaker_doctor", None) or settings.tts_local_cosyvoice_speaker,
        }
        speaker = speaker_map.get(role, settings.tts_local_cosyvoice_speaker)

        backend = CosyVoiceLocalBackend(
            base_url=settings.tts_local_cosyvoice_url,
            speaker=speaker,
            timeout=settings.tts_local_cosyvoice_timeout,
        )
        try:
            result = await backend.synthesize(text, speed)
            if result:
                logger.info("[TTS] CosyVoice 合成成功: {}bytes, role={}, speaker={}", len(result), role, speaker)
            return result
        except Exception as e:
            logger.error("[TTS] CosyVoice 合成失败: {}", e)
            return None

    async def _synthesize_edge_tts(self, text: str) -> Optional[bytes]:
        try:
            import edge_tts
        except ImportError:
            logger.error("[TTS] local/edge 模式需要安装 edge-tts: pip install edge-tts")
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
                logger.info("[TTS] edge-tts 合成成功: {}bytes", len(result))
                return result
            logger.warning("[TTS] edge-tts 合成结果为空")
            return None
        except Exception as e:
            logger.error("[TTS] edge-tts 合成失败: {}", e)
            return None


tts_service = TTSService()
