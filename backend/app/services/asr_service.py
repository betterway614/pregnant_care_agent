"""ASR (语音识别) 服务 - 支持 cloud/local 两种模式"""
import asyncio
import base64
import os
import tempfile
from typing import Optional

import httpx
from loguru import logger

from ..config import settings, get_asr_mode


class ASRService:
    """统一 ASR 服务

    模式：
    - cloud: DashScope 兼容 REST API，通过 asr_cloud_base_url 切换云端 / 本地部署
             - dashscope.aliyuncs.com → 异步提交 + 轮询（Transcription API 要求）
             - 其他地址 → multipart 同步上传（本地兼容框架）
    - local: Whisper 本地推理
    """

    async def transcribe(
        self, audio_base64: str, audio_format: str, role: str = "pregnant"
    ) -> Optional[str]:
        """将 base64 音频转为文本。role 用于查询角色专属配置。

        Returns:
            转录文本，失败时返回 None
        """
        mode = get_asr_mode(role)
        logger.info("[ASR] role={}, mode={}", role, mode)

        if mode == "cloud":
            return await self._transcribe_cloud(audio_base64, audio_format)

        if mode == "local":
            return await self._transcribe_local(audio_base64, audio_format)

        logger.warning("[ASR] 未知模式 '{}'", mode)
        return None

    # ---- cloud: DashScope 兼容 API ----

    def _is_dashscope_cloud(self) -> bool:
        return "dashscope" in settings.asr_cloud_base_url

    async def _transcribe_cloud(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        if self._is_dashscope_cloud():
            return await self._transcribe_dashscope_cloud(audio_base64, audio_format)
        return await self._transcribe_local_server(audio_base64, audio_format)

    async def _transcribe_dashscope_cloud(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        """DashScope 云端：异步提交任务 + 轮询结果。
        Transcription API 不支持同步调用，需先提交再轮询。"""
        api_key = settings.asr_cloud_api_key or settings.llm_api_key
        if not api_key:
            logger.error("[ASR] cloud 模式缺少 API Key")
            return None

        base_url = settings.asr_cloud_base_url
        submit_url = f"{base_url}/services/audio/asr/transcription"
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
                # 1. 提交异步任务
                resp = await client.post(submit_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                task_id = data.get("output", {}).get("task_id")
                if not task_id:
                    logger.error("[ASR] DashScope 未返回 task_id: {}", data)
                    return None

                logger.info("[ASR] DashScope 任务已提交: task_id={}", task_id)

                # 2. 轮询任务结果
                query_url = f"{base_url}/tasks/{task_id}"
                for _ in range(60):  # 最多轮询 60 次，约 120 秒
                    await asyncio.sleep(2)
                    q_resp = await client.get(query_url, headers=headers)
                    q_resp.raise_for_status()
                    q_data = q_resp.json()

                    status = q_data.get("output", {}).get("task_status", "")
                    if status == "SUCCEEDED":
                        return self._parse_asr_response(q_data)
                    if status == "FAILED":
                        logger.error("[ASR] DashScope 任务失败: {}", q_data)
                        return None

                    logger.debug("[ASR] DashScope 任务进行中: {}", status)

                logger.error("[ASR] DashScope 任务超时: task_id={}", task_id)
                return None
        except Exception as e:
            logger.error("[ASR] DashScope cloud 调用失败: {}", e)
            return None

    async def _transcribe_local_server(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        """本地 ASR 服务：multipart 文件上传。"""
        url = f"{settings.asr_cloud_base_url}/services/audio/asr/transcription"
        fmt_map = {"ogg": "ogg", "webm": "wav", "wav": "wav", "mp3": "mp3", "mp4": "mp4"}
        fmt = fmt_map.get(audio_format, "wav")

        headers = {
            "Authorization": f"Bearer {settings.asr_cloud_api_key or settings.llm_api_key or 'not-needed'}",
        }

        try:
            audio_bytes = base64.b64decode(audio_base64)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    files={"file": (f"audio.{fmt}", audio_bytes, f"audio/{fmt}")},
                    data={
                        "model": settings.asr_cloud_model,
                        "language_hints": '["zh"]',
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                return self._parse_asr_response(resp.json())
        except Exception as e:
            logger.error("[ASR] 本地 ASR 调用失败: {}", e)
            return None

    @staticmethod
    def _parse_asr_response(data: dict) -> Optional[str]:
        """解析 DashScope 兼容的 ASR 响应。"""
        results = data.get("output", {}).get("results", [])
        if not results:
            logger.warning("[ASR] 响应无转录结果: {}", data)
            return None

        # 直接返回文本
        text = results[0].get("text", "")
        if text:
            logger.info("[ASR] 转录成功: {}字", len(text))
            return text

        # 二次请求获取转录结果
        transcription_url = results[0].get("transcription_url", "")
        if transcription_url:
            try:
                t_resp = httpx.get(transcription_url, timeout=10.0)
                t_data = t_resp.json()
                transcripts = t_data.get("transcripts", [])
                if transcripts:
                    text = transcripts[0].get("text", "")
                    logger.info("[ASR] 转录成功: {}字", len(text))
                    return text
            except Exception as e:
                logger.error("[ASR] 获取转录结果失败: {}", e)

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
