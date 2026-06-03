"""ASR (语音识别) 服务 - 支持 cloud/local 两种模式"""
import asyncio
import base64
import os
import tempfile
from typing import Any, Optional

import httpx
from loguru import logger

from ..config import settings, get_asr_mode


class ASRService:
    """统一 ASR 服务

    支持两种使用方式:
    1. 注入模式: 通过 __init__ 传入 ASRBackend 实现（OCP 合规）
    2. 旧模式: 保留原有 if/elif 分发逻辑（向后兼容）

    模式：
    - cloud: DashScope 兼容 REST API。
    - local: 默认调用本地 FunASR HTTP API；也可通过 ASR_LOCAL_BACKEND=whisper
             切回 openai-whisper 本地推理。
    """

    def __init__(self, backend=None) -> None:
        """Args:
            backend: 可选的 ASRBackend 实现。传入时优先使用。
        """
        self._backend = backend

    async def transcribe(
        self, audio_base64: str, audio_format: str, role: str = "pregnant"
    ) -> Optional[str]:
        """将 base64 音频转为文本。role 用于查询角色专属配置。

        Returns:
            转录文本，失败时返回 None
        """
        # 优先使用注入的后端（OCP 合规路径）
        if self._backend is not None:
            try:
                return await self._backend.transcribe(audio_base64, audio_format)
            except Exception as e:
                logger.error("[ASR] 后端转录失败: {}", e)
                return None

        # 回退到旧的 if/elif 分发逻辑（向后兼容）
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
                    parsed = self._parse_asr_response(data)
                    if parsed:
                        return parsed
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
        """本地 DashScope 兼容 ASR 服务：multipart 文件上传。"""
        url = f"{settings.asr_cloud_base_url}/services/audio/asr/transcription"
        fmt_map = {"ogg": "ogg", "webm": "wav", "wav": "wav", "mp3": "mp3", "mp4": "mp4"}
        fmt = fmt_map.get(audio_format, "wav")

        headers = {
            "Authorization": f"Bearer {settings.asr_cloud_api_key or settings.llm_api_key or 'not-needed'}",
        }

        try:
            audio_bytes = self._decode_audio(audio_base64)

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

    # ---- local: FunASR HTTP API / Whisper ----

    async def _transcribe_local(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        backend = getattr(settings, "asr_local_backend", "funasr")
        if backend == "funasr":
            return await self._transcribe_funasr(audio_base64, audio_format)
        if backend == "whisper":
            return await self._transcribe_whisper(audio_base64, audio_format)

        logger.warning("[ASR] 未知 local backend '{}'", backend)
        return None

    async def _transcribe_funasr(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        """本地 FunASR API：支持 /recognition 与 OpenAI 风格 /v1/audio/transcriptions。"""
        base_url = settings.asr_local_base_url.rstrip("/")
        endpoint = settings.asr_local_endpoint or "/v1/audio/transcriptions"
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        url = f"{base_url}{endpoint}"

        try:
            audio_bytes = self._decode_audio(audio_base64)
            fmt = self._normalize_audio_format(audio_format)
            field_name = "audio" if endpoint.rstrip("/").endswith("/recognition") else "file"
            data: dict[str, str] = {}
            if field_name == "file":
                data["model"] = settings.asr_local_funasr_model or "local-funasr"
                data["response_format"] = "json"
                if settings.asr_local_hotword:
                    data["prompt"] = settings.asr_local_hotword
            elif settings.asr_local_hotword:
                data["hotword"] = settings.asr_local_hotword

            headers = {}
            if settings.asr_local_api_key:
                headers["Authorization"] = f"Bearer {settings.asr_local_api_key}"

            async with httpx.AsyncClient(timeout=settings.asr_local_timeout) as client:
                resp = await client.post(
                    url,
                    files={
                        field_name: (
                            f"audio.{fmt}",
                            audio_bytes,
                            self._audio_mime_type(fmt),
                        )
                    },
                    data=data,
                    headers=headers,
                )
                resp.raise_for_status()
                text = self._parse_funasr_response(self._response_payload(resp))
                if text:
                    logger.info("[ASR] FunASR 转录成功: {}字", len(text))
                else:
                    logger.warning("[ASR] FunASR 响应无转录文本: {}", getattr(resp, "text", ""))
                return text
        except Exception as e:
            logger.error("[ASR] FunASR 本地 API 调用失败: {}", e)
            return None

    async def _transcribe_whisper(
        self, audio_base64: str, audio_format: str
    ) -> Optional[str]:
        try:
            import whisper
        except ImportError:
            logger.error("[ASR] whisper backend 需要安装 openai-whisper: pip install openai-whisper")
            return None

        def _run_whisper() -> Optional[str]:
            try:
                audio_bytes = self._decode_audio(audio_base64)
                suffix = f".{audio_format}" if audio_format else ".webm"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(audio_bytes)
                    tmp_path = f.name

                try:
                    model = whisper.load_model(settings.asr_local_model)
                    result = model.transcribe(tmp_path, language="zh")
                    text = result.get("text", "").strip()
                    logger.info("[ASR] whisper 转录成功: {}字", len(text))
                    return text
                finally:
                    os.unlink(tmp_path)
            except Exception as e:
                logger.error("[ASR] whisper 转录失败: {}", e)
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_whisper)

    @staticmethod
    def _decode_audio(audio_base64: str) -> bytes:
        payload = audio_base64.strip()
        if payload.startswith("data:") and "," in payload:
            payload = payload.split(",", 1)[1]
        return base64.b64decode(payload)

    @staticmethod
    def _normalize_audio_format(audio_format: str) -> str:
        fmt = (audio_format or "webm").lower().strip().lstrip(".")
        if ";" in fmt:
            fmt = fmt.split(";", 1)[0]
        if "/" in fmt:
            fmt = fmt.rsplit("/", 1)[-1]
        aliases = {
            "x-wav": "wav",
            "mpeg": "mp3",
            "quicktime": "mp4",
            "m4a": "mp4",
        }
        return aliases.get(fmt, fmt or "webm")

    @staticmethod
    def _audio_mime_type(fmt: str) -> str:
        mime_map = {
            "mp3": "audio/mpeg",
            "mp4": "audio/mp4",
            "wav": "audio/wav",
            "webm": "audio/webm",
            "ogg": "audio/ogg",
        }
        return mime_map.get(fmt, f"audio/{fmt}")

    @staticmethod
    def _response_payload(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return getattr(resp, "text", "")

    @classmethod
    def _parse_funasr_response(cls, data: Any) -> Optional[str]:
        if isinstance(data, str):
            text = data.strip()
            return text or None

        if isinstance(data, list):
            texts = [cls._parse_funasr_response(item) for item in data]
            joined = "".join(text for text in texts if text)
            return joined or None

        if not isinstance(data, dict):
            return None

        for key in ("text", "transcript", "transcription", "result"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ("data", "output"):
            value = data.get(key)
            text = cls._parse_funasr_response(value)
            if text:
                return text

        for key in ("results", "transcripts"):
            value = data.get(key)
            text = cls._parse_funasr_response(value)
            if text:
                return text

        return None


asr_service = ASRService()
