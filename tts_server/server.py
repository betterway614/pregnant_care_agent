"""
CosyVoice2 TTS FastAPI 服务
端口 9880，支持 SFT/Zero-shot 两种推理模式
"""
import io
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import config
from .model_loader import get_model

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Pydantic 请求 / 响应模型
# ---------------------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="合成文本")
    speaker: Optional[str] = Field(None, description="说话人名称，默认使用配置")
    format: str = Field("wav", description="输出格式: wav 或 mp3")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="语速 0.5~2.0")


class SpeakersResponse(BaseModel):
    speakers: list
    sample_rate: int


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifespan: 服务启动时尝试预加载模型
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TTS service starting, attempting to preload model...")
    model = get_model()
    loaded = model.load()
    if loaded:
        logger.info("Model preloaded successfully")
    else:
        logger.warning(f"Model preload failed: {model.load_error}")
        logger.warning("Service will start but return 503 until model is available")
    yield
    logger.info("TTS service shutting down")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CosyVoice2 TTS API",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def audio_to_wav_bytes(audio_np: np.ndarray, sample_rate: int) -> bytes:
    """将 numpy 音频数组转换为 WAV 字节"""
    try:
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, audio_np, sample_rate, format="WAV", subtype="PCM_16")
        buf.seek(0)
        return buf.read()
    except ImportError:
        pass

    # fallback: scipy
    try:
        from scipy.io import wavfile
        buf = io.BytesIO()
        # 转 int16
        audio_int16 = (audio_np * 32767).astype(np.int16)
        wavfile.write(buf, sample_rate, audio_int16)
        buf.seek(0)
        return buf.read()
    except Exception:
        pass

    # fallback: 手动构建 WAV
    import struct
    audio_int16 = (audio_np * 32767).astype(np.int16)
    data = audio_int16.tobytes()
    num_channels = 1
    sample_width = 2
    data_size = len(data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        num_channels,
        sample_rate,
        sample_rate * num_channels * sample_width,
        num_channels * sample_width,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + data


def audio_to_mp3_bytes(audio_np: np.ndarray, sample_rate: int) -> Optional[bytes]:
    """将 numpy 音频数组转换为 MP3 字节，失败返回 None"""
    # 方式1: pydub
    try:
        from pydub import AudioSegment
        audio_int16 = (audio_np * 32767).astype(np.int16)
        segment = AudioSegment(
            data=audio_int16.tobytes(),
            sample_width=2,
            frame_rate=sample_rate,
            channels=1,
        )
        buf = io.BytesIO()
        segment.export(buf, format="mp3", bitrate="192k")
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.debug(f"pydub mp3 export failed: {e}")

    # 方式2: lameenc
    try:
        import lameenc
        audio_int16 = (audio_np * 32767).astype(np.int16)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(192)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(1)
        encoder.set_quality(2)
        mp3_data = encoder.encode(audio_int16.tobytes())
        mp3_data += encoder.flush()
        return mp3_data
    except Exception as e:
        logger.debug(f"lameenc mp3 export failed: {e}")

    return None


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    model = get_model()
    return HealthResponse(
        status="ok" if model.is_loaded else "unavailable",
        model_loaded=model.is_loaded,
        error=model.load_error,
    )


@app.get("/v1/tts/speakers", response_model=SpeakersResponse)
async def list_speakers():
    """返回可用说话人列表"""
    model = get_model()
    if not model.is_loaded:
        raise HTTPException(status_code=503, detail="模型未加载，请稍后重试")
    return SpeakersResponse(
        speakers=model.get_speakers(),
        sample_rate=model.sample_rate,
    )


@app.post("/v1/tts/synthesize")
async def synthesize(req: SynthesizeRequest):
    """合成语音并返回音频流"""
    # 文本校验
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="合成文本不能为空")
    if len(text) > config.MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"文本过长（最大 {config.MAX_TEXT_LENGTH} 字符，当前 {len(text)} 字符）",
        )

    # 模型检查
    model = get_model()
    if not model.is_loaded:
        # 尝试懒加载
        if not model.load():
            raise HTTPException(
                status_code=503,
                detail=f"模型未加载: {model.load_error}",
            )

    # 合成（线程安全通过 model_loader 的 threading.Lock 保证）
    start = time.time()
    audio_np = model.synthesize(
        text=text,
        speaker=req.speaker or config.DEFAULT_SPEAKER,
        speed=req.speed,
    )
    elapsed = time.time() - start

    if audio_np is None:
        raise HTTPException(status_code=500, detail="语音合成失败，请检查模型配置和日志")

    logger.info(f"Synthesized {len(audio_np)/model.sample_rate:.2f}s audio in {elapsed:.2f}s")

    # 编码
    fmt = req.format.lower()
    if fmt == "mp3":
        mp3_bytes = audio_to_mp3_bytes(audio_np, model.sample_rate)
        if mp3_bytes is None:
            # fallback to wav
            logger.warning("MP3 encoding unavailable, falling back to WAV")
            wav_bytes = audio_to_wav_bytes(audio_np, model.sample_rate)
            return StreamingResponse(
                io.BytesIO(wav_bytes),
                media_type="audio/wav",
                headers={"Content-Disposition": "attachment; filename=tts_output.wav"},
            )
        return StreamingResponse(
            io.BytesIO(mp3_bytes),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=tts_output.mp3"},
        )
    else:
        # 默认 WAV
        wav_bytes = audio_to_wav_bytes(audio_np, model.sample_rate)
        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=tts_output.wav"},
        )


# ---------------------------------------------------------------------------
# 流式合成端点
# ---------------------------------------------------------------------------

def _pcm16_chunk(audio_float32: np.ndarray) -> bytes:
    """将 float32 音频数组转为 PCM_16 小端字节"""
    audio_int16 = (audio_float32 * 32767).astype(np.int16)
    return audio_int16.tobytes()


def _wav_header(sample_rate: int, bits_per_sample: int = 16, num_channels: int = 1) -> bytes:
    """生成 WAV 文件头（data 大小设为 0xFFFFFFFF 用于流式）"""
    import struct
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)
    # data size = 0xFFFFFFFF 表示流式（客户端应持续读取直到连接关闭）
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0xFFFFFFFF,           # 整体大小（流式设为最大）
        b"WAVE",
        b"fmt ",
        16,                   # fmt chunk 大小
        1,                    # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        0xFFFFFFFF,           # data 大小（流式设为最大）
    )


@app.post("/v1/tts/stream")
async def synthesize_stream(req: SynthesizeRequest):
    """流式合成语音 — 边生成边返回 PCM 音频块（WAV 格式）

    客户端可以通过 HTTP chunked transfer encoding 实时播放。
    首包延迟约 3-5s（取决于文本长度和 GPU 推理速度），
    后续片段每 1-3s 到达一个。

    返回 WAV 格式：先发 header，再逐 chunk 发送 PCM_16 数据。
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="合成文本不能为空")
    if len(text) > config.MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"文本过长（最大 {config.MAX_TEXT_LENGTH} 字符，当前 {len(text)} 字符）",
        )

    model = get_model()
    if not model.is_loaded:
        if not model.load():
            raise HTTPException(status_code=503, detail=f"模型未加载: {model.load_error}")

    sample_rate = model.sample_rate

    def audio_generator():
        """生成 WAV header + PCM_16 音频块"""
        # GPU 推理串行化（通过 model_loader 的 threading.Lock）
        # 注意：回退为 sync generator，运行在线程池中，不影响事件循环
        yield _wav_header(sample_rate)

        chunk_count = 0
        t_start = time.time()
        for audio_np in model.synthesize_stream(
            text=text,
            speaker=req.speaker or config.DEFAULT_SPEAKER,
            speed=req.speed,
        ):
            if chunk_count == 0:
                t_first = time.time() - t_start
                logger.info(f"Stream first chunk: {t_first:.2f}s, {len(audio_np)/sample_rate:.2f}s audio")
            yield _pcm16_chunk(audio_np)
            chunk_count += 1

        elapsed = time.time() - t_start
        logger.info(f"Stream complete: {chunk_count} chunks in {elapsed:.2f}s")

    return StreamingResponse(
        audio_generator(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline; filename=tts_stream.wav",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    import uvicorn
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        log_level=config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
