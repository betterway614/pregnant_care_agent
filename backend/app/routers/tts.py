"""TTS 语音合成 API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal

from ..config import settings, get_tts_mode
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/tts", tags=["语音合成"])


class TTSRequest(BaseModel):
    text: str
    role: Literal["pregnant", "nurse", "doctor"] = "pregnant"


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
    return {
        "mode": mode,
        "available": mode != "browser",  # browser 模式由前端处理
        "backend_modes": ["cloud", "local"],
    }
