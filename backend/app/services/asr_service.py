"""ASR (语音识别) 服务 - 支持 cloud/local/llm 三种模式"""
import asyncio
import base64
import json
from typing import Optional

import httpx
from loguru import logger

from ..config import settings, get_asr_mode


class ASRService:
    """统一 ASR 服务

    模式：
    - llm: 返回 None，由调用方使用多模态 LLM 路径（当前默认行为）
    - cloud: DashScope Paraformer ASR REST API
    - local: Whisper 本地推理
    """

    async def transcribe(
        self, audio_base64: str, audio_format: str, role: str = "pregnant"
    ) -> Optional[str]:
        """将 base64 音频转为文本。role 用于查询角色专属配置。

        Returns:
            转录文本，llm 模式返回 None（调用方应使用多模态 LLM 路径）
        """
        mode = get_asr_mode(role)
        logger.info("[ASR] role={}, mode={}", role, mode)

        if mode == "llm":
            return None

        if mode == "cloud":
            return await self._transcribe_cloud(audio_base64, audio_format)

        if mode == "local":
            return await self._transcribe_local(audio_base64, audio_format)

        logger.warning("[ASR] 未知模式 '{}', 降级为 llm", mode)
        return None

    # ---- cloud: DashScope Paraformer ----

    async def _transcribe_cloud(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        api_key = settings.asr_cloud_api_key or settings.llm_api_key
        if not api_key:
            logger.error("[ASR] cloud 模式缺少 API Key")
            return None

        url = f"{settings.asr_cloud_base_url}/services/audio/asr/transcription"
        # DashScope Paraformer 支持的格式映射
        fmt_map = {"ogg": "ogg", "webm": "wav", "wav": "wav", "mp3": "mp3", "mp4": "mp4"}
        fmt = fmt_map.get(audio_format, "wav")

        payload = {
            "model": settings.asr_cloud_model,
            "input": {
                "file_urls": [f"data:audio/{fmt};base64,{audio_base64}"],
            },
            "parameters": {
                "language_hints": ["zh"],
            },
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                # 解析 DashScope 响应
                results = data.get("output", {}).get("results", [])
                if results:
                    transcript_url = results[0].get("transcription_url", "")
                    if transcript_url:
                        # 需要二次请求获取转录结果
                        t_resp = await client.get(transcript_url)
                        t_data = t_resp.json()
                        transcripts = t_data.get("transcripts", [])
                        if transcripts:
                            text = transcripts[0].get("text", "")
                            logger.info("[ASR] cloud 转录成功: {}字", len(text))
                            return text

                logger.warning("[ASR] cloud 响应无转录结果: {}", data)
                return None
        except Exception as e:
            logger.error("[ASR] cloud 调用失败: {}", e)
            return None

    # ---- local: Whisper ----

    async def _transcribe_local(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        try:
            import whisper
        except ImportError:
            logger.error("[ASR] local 模式需要安装 openai-whisper: pip install openai-whisper")
            return None

        def _run_whisper() -> Optional[str]:
            try:
                audio_bytes = base64.b64decode(audio_base64)
                # 写入临时文件（Whisper 需要文件路径）
                import tempfile
                import os

                suffix = f".{audio_format}" if audio_format else ".webm"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(audio_bytes)
                    tmp_path = f.name

                try:
                    model = whisper.load_model(settings.asr_local_model)
                    result = model.transcribe(tmp_path, language="zh")
                    text = result.get("text", "").strip()
                    logger.info("[ASR] local 转录成功: {}字", len(text))
                    return text
                finally:
                    os.unlink(tmp_path)
            except Exception as e:
                logger.error("[ASR] local 转录失败: {}", e)
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_whisper)


asr_service = ASRService()
