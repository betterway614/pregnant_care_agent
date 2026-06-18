"""
CosyVoice2 模型加载器 - 线程安全单例
支持 CosyVoice2-0.5B (zero-shot) 和 CosyVoice-300M-SFT (sft) 两种模式
"""
import sys
import os
import threading
import logging
import numpy as np
from typing import Optional, List, Generator

from . import config

logger = logging.getLogger(__name__)


class CosyVoiceModel:
    """CosyVoice2 模型封装，线程安全单例"""

    _instance: Optional["CosyVoiceModel"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        # 防止重复初始化
        if CosyVoiceModel._initialized:
            return
        with CosyVoiceModel._lock:
            if CosyVoiceModel._initialized:
                return
            self._model = None
            self._sample_rate: int = config.DEFAULT_SAMPLE_RATE
            self._available_spks: List[str] = []
            self._has_sft: bool = False
            self._load_error: Optional[str] = None
            self._cached_prompt_input = None
            CosyVoiceModel._initialized = True

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def load(self) -> bool:
        """加载模型，返回是否成功"""
        if self._model is not None:
            return True

        with self._lock:
            if self._model is not None:
                return True

            try:
                # 将 CosyVoice 仓库路径加入 sys.path
                if config.COSYVOICE_REPO and config.COSYVOICE_REPO not in sys.path:
                    sys.path.insert(0, config.COSYVOICE_REPO)
                    # Matcha-TTS 是 CosyVoice 的子模块依赖
                    matcha_path = os.path.join(config.COSYVOICE_REPO, "third_party", "Matcha-TTS")
                    if os.path.exists(matcha_path) and matcha_path not in sys.path:
                        sys.path.insert(0, matcha_path)
                    logger.info(f"Added CosyVoice repo to sys.path: {config.COSYVOICE_REPO}")

                try:
                    from cosyvoice.cli.cosyvoice import AutoModel
                except ImportError as e:
                    error_msg = (
                        f"无法导入 CosyVoice 推理库: {e}\n"
                        "请按以下步骤安装:\n"
                        "1. git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git\n"
                        "2. cd CosyVoice && git submodule update --init --recursive\n"
                        "3. pip install -r requirements.txt\n"
                        "4. 设置环境变量 COSYVOICE_REPO=/path/to/CosyVoice\n"
                        "或将 CosyVoice 安装到 Python 环境中"
                    )
                    logger.error(error_msg)
                    self._load_error = error_msg
                    return False

                model_dir = config.MODEL_DIR
                logger.info(f"Loading CosyVoice model from: {model_dir}, quantize={config.QUANTIZE}")

                if not os.path.exists(model_dir):
                    error_msg = (
                        f"模型目录不存在: {model_dir}\n"
                        "请先下载模型:\n"
                        "from modelscope import snapshot_download\n"
                        "snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')"
                    )
                    logger.error(error_msg)
                    self._load_error = error_msg
                    return False

                self._model = AutoModel(model_dir=model_dir, fp16=config.QUANTIZE)
                self._sample_rate = self._model.sample_rate
                self._available_spks = list(self._model.list_available_spks())
                self._has_sft = len(self._available_spks) > 0

                logger.info(
                    f"Model loaded successfully. sample_rate={self._sample_rate}, "
                    f"available_spks={self._available_spks}, has_sft={self._has_sft}"
                )

                # ── 预计算 prompt 特征 + GPU 预热 ──
                self._cached_prompt_input = None
                self._warmup()

                return True

            except Exception as e:
                error_msg = f"模型加载失败: {e}"
                logger.exception(error_msg)
                self._load_error = error_msg
                return False

    def get_speakers(self) -> List[str]:
        """返回可用说话人列表"""
        if not self.is_loaded:
            return []
        return self._available_spks

    def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        """
        合成语音（非流式），返回完整 numpy float32 数组（单声道）

        Args:
            text: 合成文本
            speaker: 说话人名称（SFT模式下使用）
            speed: 语速（0.5~2.0）

        Returns:
            numpy 数组，或 None（失败时）
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return None

        try:
            import torch

            speaker = speaker or config.DEFAULT_SPEAKER
            result_gen = self._get_inference_generator(text, speaker, speed, stream=False)
            if result_gen is None:
                return None

            # 拼接所有音频 chunk
            audio_chunks = []
            for chunk in result_gen:
                if chunk is not None and "tts_speech" in chunk:
                    tensor = chunk["tts_speech"]
                    if tensor.dim() > 1:
                        tensor = tensor.squeeze(0)
                    audio_chunks.append(tensor)

            if not audio_chunks:
                logger.warning("Synthesis produced no audio")
                return None

            audio_tensor = torch.cat(audio_chunks, dim=-1)

            if abs(speed - 1.0) > 0.01:
                audio_tensor = self._adjust_speed(audio_tensor, speed)

            audio_np = audio_tensor.cpu().numpy().astype(np.float32)
            max_val = np.abs(audio_np).max()
            if max_val > 0:
                audio_np = audio_np / max_val
            return audio_np

        except Exception as e:
            logger.exception(f"Synthesis failed: {e}")
            return None

    def synthesize_stream(
        self,
        text: str,
        speaker: Optional[str] = None,
        speed: float = 1.0,
    ) -> Generator[np.ndarray, None, None]:
        """流式合成语音，逐句 yield numpy float32 数组"""
        if not self.is_loaded:
            logger.error("Model not loaded")
            return

        try:
            import torch

            speaker = speaker or config.DEFAULT_SPEAKER
            result_gen = self._get_inference_generator(text, speaker, speed, stream=True)
            if result_gen is None:
                return

            chunk_idx = 0
            for chunk in result_gen:
                if chunk is None or "tts_speech" not in chunk:
                    continue
                tensor = chunk["tts_speech"]
                if tensor.dim() > 1:
                    tensor = tensor.squeeze(0)

                audio_np = tensor.cpu().numpy().astype(np.float32)
                # 固定幅度裁剪替代逐段 /max_val，保留段间自然幅度关系
                np.clip(audio_np, -0.99, 0.99, out=audio_np)

                chunk_len = len(audio_np) / self._sample_rate
                logger.info(f"Stream chunk #{chunk_idx}: {chunk_len:.2f}s audio")
                chunk_idx += 1
                yield audio_np

        except Exception as e:
            logger.exception(f"Stream synthesis failed: {e}")

    def _get_inference_generator(self, text, speaker, speed, stream):
        """根据配置创建推理生成器（SFT 或 zero-shot），使用缓存的 prompt 特征"""
        if self._has_sft and speaker in self._available_spks:
            logger.info(f"Using SFT inference: speaker={speaker}, stream={stream}")
            return self._model.inference_sft(text, speaker, stream=stream, speed=speed)
        elif self._cached_prompt_input is not None:
            # ── 快速路径：使用缓存的 prompt 特征，跳过 ONNX 重复计算 ──
            logger.info(f"Using cached zero-shot inference: stream={stream}")
            return self._inference_zero_shot_cached(text, stream=stream, speed=speed)
        elif config.ZERO_SHOT_PROMPT_WAV and os.path.exists(config.ZERO_SHOT_PROMPT_WAV):
            prompt_text = config.ZERO_SHOT_PROMPT_TEXT or ""
            logger.info(f"Using zero-shot inference: stream={stream}")
            return self._model.inference_zero_shot(
                text, prompt_text, config.ZERO_SHOT_PROMPT_WAV,
                stream=stream, speed=speed,
            )
        else:
            logger.error(
                "无法进行语音合成：无 SFT 说话人且未配置 zero-shot 提示音频"
            )
            return None

    def _warmup(self):
        """预计算 prompt 特征 + GPU 预热推理"""
        import time as _time

        prompt_wav = config.ZERO_SHOT_PROMPT_WAV
        if not prompt_wav or not os.path.exists(prompt_wav):
            logger.info("No prompt WAV configured, skipping warmup")
            return

        prompt_text = config.ZERO_SHOT_PROMPT_TEXT or ""

        # ── Step 1: 预计算 prompt 特征 ──
        logger.info("Pre-computing prompt features (speech_token, spk_embedding, speech_feat)...")
        t0 = _time.time()
        try:
            frontend = self._model.frontend
            prompt_text_norm = frontend.text_normalize(prompt_text, split=False, text_frontend=True)
            prompt_text_token, prompt_text_len = frontend._extract_text_token(prompt_text_norm)
            speech_feat, speech_feat_len = frontend._extract_speech_feat(prompt_wav)
            speech_token, speech_token_len = frontend._extract_speech_token(prompt_wav)

            # CosyVoice2: 对齐 speech_feat 和 speech_token 长度
            if self._sample_rate == 24000:
                token_len = min(int(speech_feat.shape[1] / 2), speech_token.shape[1])
                speech_feat = speech_feat[:, :2 * token_len]
                speech_feat_len[:] = 2 * token_len
                speech_token = speech_token[:, :token_len]
                speech_token_len[:] = token_len

            embedding = frontend._extract_spk_embedding(prompt_wav)

            self._cached_prompt_input = {
                'prompt_text': prompt_text_token,
                'prompt_text_len': prompt_text_len,
                'llm_prompt_speech_token': speech_token,
                'llm_prompt_speech_token_len': speech_token_len,
                'flow_prompt_speech_token': speech_token,
                'flow_prompt_speech_token_len': speech_token_len,
                'prompt_speech_feat': speech_feat,
                'prompt_speech_feat_len': speech_feat_len,
                'llm_embedding': embedding,
                'flow_embedding': embedding,
            }
            elapsed = _time.time() - t0
            logger.info(f"Prompt features cached in {elapsed:.2f}s")
        except Exception as e:
            logger.warning(f"Failed to cache prompt features: {e}, will use original path")
            self._cached_prompt_input = None
            return

        # ── Step 2: GPU 预热 — 跑一次短推理，让 GPU kernel 编译和缓存 ──
        logger.info("Running GPU warmup inference...")
        t0 = _time.time()
        try:
            warmup_gen = self._inference_zero_shot_cached("你好", stream=False, speed=1.0)
            if warmup_gen is not None:
                for chunk in warmup_gen:
                    pass  # 消费完
            elapsed = _time.time() - t0
            logger.info(f"GPU warmup complete in {elapsed:.2f}s")
        except Exception as e:
            logger.warning(f"GPU warmup failed (non-fatal): {e}")

    def _inference_zero_shot_cached(self, tts_text, stream=False, speed=1.0):
        """使用缓存 prompt 特征的 zero-shot 推理，支持 instruct 模式"""
        import time as _time
        from tqdm import tqdm
        from types import GeneratorType

        frontend = self._model.frontend
        instruct_text = config.INSTRUCT_TEXT

        for i in tqdm(frontend.text_normalize(tts_text, split=True, text_frontend=True)):
            # 只计算新文本的 text token（很快）
            tts_text_token, tts_text_token_len = frontend._extract_text_token(i)

            # 合并缓存的 prompt 特征 + 新文本 token
            model_input = {**self._cached_prompt_input}
            model_input['text'] = tts_text_token
            model_input['text_len'] = tts_text_token_len

            # Instruct 模式：用 instruct_text 替换 llm_prompt_speech_token
            if instruct_text:
                instruct_token, instruct_token_len = frontend._extract_text_token(instruct_text)
                model_input['prompt_text'] = instruct_token
                model_input['prompt_text_len'] = instruct_token_len
                # 移除 llm_prompt_speech_token（instruct2 模式不需要）
                model_input.pop('llm_prompt_speech_token', None)
                model_input.pop('llm_prompt_speech_token_len', None)

            start_time = _time.time()
            import logging as _logging
            _logging.getLogger(__name__).info(f'synthesis text {i}')
            for model_output in self._model.model.tts(**model_input, stream=stream, speed=speed):
                speech_len = model_output['tts_speech'].shape[1] / self._sample_rate
                _logging.getLogger(__name__).info(
                    f'yield speech len {speech_len:.2f}, rtf {(_time.time() - start_time) / speech_len:.2f}'
                )
                yield model_output
                start_time = _time.time()

    def _adjust_speed(self, audio_tensor, speed: float):
        """通过重采样实现简单变速"""
        try:
            import torchaudio
            import torch

            # 简单变速：改变采样率
            orig_sr = self._sample_rate
            target_sr = int(orig_sr * speed)
            # 先重采样到 target_sr（相当于变速），再重采样回 orig_sr
            if audio_tensor.dim() == 1:
                audio_tensor = audio_tensor.unsqueeze(0)
            resampled = torchaudio.functional.resample(audio_tensor, orig_sr, target_sr)
            result = torchaudio.functional.resample(resampled, target_sr, orig_sr)
            return result.squeeze(0)
        except Exception as e:
            logger.warning(f"Speed adjustment failed, returning original: {e}")
            return audio_tensor.squeeze(0) if audio_tensor.dim() > 1 else audio_tensor


def get_model() -> CosyVoiceModel:
    """获取模型单例"""
    return CosyVoiceModel()
