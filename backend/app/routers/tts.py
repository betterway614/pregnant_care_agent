"""TTS 语音合成 API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional

from ..config import settings, get_tts_mode
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/tts", tags=["语音合成"])


class TTSRequest(BaseModel):
    text: str
    role: Literal["pregnant", "nurse", "doctor"] = "pregnant"
    speaker: Optional[str] = None  # 说话人（CosyVoice模式可用）
    speed: float = 1.0  # 语速 0.5-2.0


@router.post("/synthesize")
async def tts_synthesize(req: TTSRequest, user: TokenPayload = Depends(get_current_user)):
    """TTS 合成接口 - 接收文本，返回 MP3 音频流"""
    if not req.text or not req.text.strip():
        raise HTTPException(400, "text 不能为空")

    text = req.text.strip()
    if len(text) > 500:
        text = text[:500]

    mode = get_tts_mode(req.role)
    if mode == "browser":
        raise HTTPException(
            400,
            detail="当前 TTS 模式为 browser，请使用前端 SpeechSynthesis",
        )

    from ..services.tts_service import tts_service

    audio_bytes = await tts_service.synthesize(text, req.role)
    if not audio_bytes:
        raise HTTPException(500, "TTS 合成失败")

    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=tts.mp3"},
    )


@router.get("/config")
async def tts_config(role: str = "pregnant", user: TokenPayload = Depends(get_current_user)):
    """返回 TTS 配置信息（前端用于决定用浏览器 TTS 还是后端 TTS）"""
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
    """获取可用说话人列表（仅CosyVoice本地模式可用）"""
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
