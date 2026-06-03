"""
TTS 后端接口 — 替代 TTSService 中的 if/elif 分发链

遵循 OCP: 新增 TTS 后端只需实现此协议并注册，无需修改 TTSService。
"""
from __future__ import annotations

from typing import Protocol


class TTSBackend(Protocol):
    """语音合成后端协议"""

    async def synthesize(self, text: str) -> bytes:
        """将文本合成为音频

        Args:
            text: 待合成文本

        Returns:
            MP3 格式的音频字节

        Raises:
            RuntimeError: 合成失败时抛出
        """
        ...
