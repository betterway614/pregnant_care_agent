"""TTS 语音合成 API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional
from loguru import logger

from ..config import settings, get_tts_mode
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/tts", tags=["语音合成"])


class TTSRequest(BaseModel):
    text: str
    role: Literal["pregnant", "nurse", "doctor"] = "pregnant"
    speaker: Optional[str] = None
    speed: float = 1.0


@router.post("/synthesize")
async def tts_synthesize(req: TTSRequest, user: TokenPayload = Depends(get_current_user)):
    """TTS 合成接口 - 接收文本，返回 WAV/MP3 音频流"""
    if not req.text or not req.text.strip():
        raise HTTPException(400, "text 不能为空")

    text = req.text.strip()
    if len(text) > 500:
        text = text[:500]

    mode = get_tts_mode(req.role)
    if mode == "browser":
        raise HTTPException(400, detail="当前 TTS 模式为 browser，请使用前端 SpeechSynthesis")

    from ..services.tts_service import tts_service

    try:
        audio_bytes = await tts_service.synthesize(text, req.role, req.speed)
    except Exception as e:
        logger.error("[TTS] synthesize() 异常: {}", e)
        raise HTTPException(500, f"TTS 合成异常: {e}")

    if not audio_bytes:
        raise HTTPException(502, f"TTS 合成失败：请检查 TTS 服务 ({settings.tts_local_cosyvoice_url})")

    if mode == "local" and settings.tts_local_backend == "cosyvoice":
        media_type = "audio/wav"
        filename = "tts.wav"
    else:
        media_type = "audio/mpeg"
        filename = "tts.mp3"

    return StreamingResponse(
        iter([audio_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@router.post("/stream")
async def tts_stream(req: TTSRequest, user: TokenPayload = Depends(get_current_user)):
    """TTS 流式合成 — 边生成边返回 WAV 音频块"""
    if not req.text or not req.text.strip():
        raise HTTPException(400, "text 不能为空")

    text = req.text.strip()
    if len(text) > 500:
        text = text[:500]

    mode = get_tts_mode(req.role)
    if mode == "browser":
        raise HTTPException(400, detail="browser 模式不支持流式合成")
    if mode != "local" or settings.tts_local_backend != "cosyvoice":
        raise HTTPException(400, detail=f"流式 TTS 仅支持 local/cosyvoice 模式，当前 mode={mode}")

    from ..services.tts_service import tts_service

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            health_resp = await client.get(f"{settings.tts_local_cosyvoice_url}/health")
            if health_resp.status_code != 200:
                raise HTTPException(502, f"TTS 服务健康检查失败 [{health_resp.status_code}]")
            health_data = health_resp.json()
            if not health_data.get("model_loaded"):
                raise HTTPException(503, f"TTS 模型未加载: {health_data.get('error', 'unknown')}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"无法连接 TTS 服务 ({settings.tts_local_cosyvoice_url}): {e}")

    async def wav_chunk_generator():
        try:
            async for chunk in tts_service.synthesize_stream(text, req.role, req.speed):
                yield chunk
        except Exception as exc:
            logger.error("[TTS] 流式生成中断: {}", exc)

    return StreamingResponse(
        wav_chunk_generator(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=tts_stream.wav",
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@router.get("/config")
async def tts_config(role: str = "pregnant", user: TokenPayload = Depends(get_current_user)):
    """返回 TTS 配置信息"""
    mode = get_tts_mode(role)
    local_backend = settings.tts_local_backend if mode == "local" else None
    return {
        "mode": mode,
        "available": mode != "browser",
        "backend_modes": ["cloud", "local"],
        "local_backend": local_backend,
    }


@router.get("/speakers")
async def tts_speakers(user: TokenPayload = Depends(get_current_user)):
    """获取可用说话人列表"""
    if settings.tts_mode != "local" or settings.tts_local_backend != "cosyvoice":
        return {"speakers": [], "message": "说话人列表仅在 CosyVoice 本地模式可用"}
    from ..services.tts_backends import CosyVoiceLocalBackend
    backend = CosyVoiceLocalBackend(
        base_url=settings.tts_local_cosyvoice_url,
        speaker=settings.tts_local_cosyvoice_speaker,
        timeout=10,
    )
    try:
        speakers = await backend.get_speakers()
        return {"speakers": speakers}
    except Exception:
        raise HTTPException(503, "无法连接 CosyVoice 服务")
