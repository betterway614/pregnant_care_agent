"""CosyVoice2 TTS 服务配置"""
import os

# 服务配置
HOST = os.getenv("TTS_HOST", "0.0.0.0")
PORT = int(os.getenv("TTS_PORT", "9880"))

# 模型配置
MODEL_DIR = os.getenv("COSYVOICE_MODEL_DIR", "./pretrained_models/CosyVoice2-0.5B")
DEVICE = os.getenv("TTS_DEVICE", "cuda")  # cuda for ROCm via PyTorch
QUANTIZE = os.getenv("TTS_QUANTIZE", "true").lower() in ("true", "1", "yes")

# CosyVoice 源码路径（需 clone CosyVoice 仓库后设置）
COSYVOICE_REPO = os.getenv("COSYVOICE_REPO", "")

# 合成配置
DEFAULT_SPEAKER = os.getenv("TTS_DEFAULT_SPEAKER", "中文女")
MAX_TEXT_LENGTH = int(os.getenv("TTS_MAX_TEXT_LENGTH", "500"))
DEFAULT_SAMPLE_RATE = 22050

# Zero-shot 默认提示音频（用于 CosyVoice2-0.5B 零样本推理）
# 默认使用 CosyVoice 仓库自带的 zero_shot_prompt.wav
_COSYVOICE_REPO = os.getenv("COSYVOICE_REPO", "")
_DEFAULT_PROMPT_WAV = ""
if _COSYVOICE_REPO:
    _candidate = os.path.join(_COSYVOICE_REPO, "asset", "zero_shot_prompt.wav")
    if os.path.exists(_candidate):
        _DEFAULT_PROMPT_WAV = _candidate
# 也检查模型目录下的 zero_shot_prompt.wav
_MODEL_DIR = os.getenv("COSYVOICE_MODEL_DIR", "./pretrained_models/CosyVoice2-0.5B")
_model_prompt = os.path.join(_MODEL_DIR, "zero_shot_prompt.wav")
if os.path.exists(_model_prompt):
    _DEFAULT_PROMPT_WAV = _model_prompt

ZERO_SHOT_PROMPT_WAV = os.getenv("TTS_ZERO_SHOT_PROMPT_WAV", _DEFAULT_PROMPT_WAV)

# CosyVoice 官方示例 zero_shot_prompt.wav 的逐字文本。zero-shot 必须同时提供
# prompt 音频和对应文本，否则模型容易把参考音频语义混入输出，导致“读的不是输入文本”。
DEFAULT_ZERO_SHOT_PROMPT_TEXT = "希望你以后能够做的比我还好呦。"
_prompt_text_default = (
    DEFAULT_ZERO_SHOT_PROMPT_TEXT
    if ZERO_SHOT_PROMPT_WAV and ZERO_SHOT_PROMPT_WAV == _DEFAULT_PROMPT_WAV
    else ""
)
ZERO_SHOT_PROMPT_TEXT = os.getenv("TTS_ZERO_SHOT_PROMPT_TEXT", _prompt_text_default)

# Instruct 模式配置（用文字描述想要的音色风格）
INSTRUCT_TEXT = os.getenv("TTS_INSTRUCT_TEXT", "")

# 日志
LOG_LEVEL = os.getenv("TTS_LOG_LEVEL", "INFO")
