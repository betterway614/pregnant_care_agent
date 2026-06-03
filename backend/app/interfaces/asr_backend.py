"""
ASR 后端接口 — 替代 ASRService 中的 if/elif 分发链

遵循 OCP: 新增 ASR 后端只需实现此协议并注册，无需修改 ASRService。
"""
from __future__ import annotations

from typing import Protocol


class ASRBackend(Protocol):
    """语音识别后端协议"""

    async def transcribe(self, audio_base64: str, audio_format: str) -> str:
        """将音频转录为文本

        Args:
            audio_base64: Base64 编码的音频数据
            audio_format: 音频格式 (webm, wav, mp3 等)

        Returns:
            转录文本

        Raises:
            RuntimeError: 转录失败时抛出
        """
        ...
