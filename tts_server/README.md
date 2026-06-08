# CosyVoice2 TTS API 服务

基于阿里通义 CosyVoice2-0.5B 大模型的本地语音合成（Text-to-Speech）API 服务，支持 AMD ROCm GPU 加速。

## 项目概述

本服务封装 CosyVoice2 语音合成模型为 RESTful API，提供：
- 中文/英文多语言语音合成
- SFT 预置说话人模式 & Zero-shot 零样本克隆模式
- WAV / MP3 双格式输出
- 语速调节（0.5x ~ 2.0x）
- 健康检查、说话人列表查询等运维端点

## 硬件要求

| 项目 | 最低要求 |
|------|---------|
| GPU | AMD RDNA2/RDNA3（如 RX 7900 XTX） |
| 显存 | ≥ 8GB（CosyVoice2-0.5B） |
| ROCm | 6.x |
| CPU | 4 核以上 |
| 内存 | ≥ 16GB |
| 磁盘 | ≥ 10GB（模型文件约 3GB） |

## 环境准备

### 1. 安装 ROCm

参考 [ROCm 官方文档](https://rocm.docs.amd.com/) 安装 ROCm 6.x。

验证安装：
```bash
rocm-smi
```

### 2. Python 环境（3.10+）

```bash
conda create -n tts python=3.10 -y
conda activate tts
```

### 3. PyTorch ROCm 版本

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/rocm6.2
```

验证 PyTorch ROCm：
```bash
python -c "import torch; print(torch.cuda.is_available(), torch.version.hip)"
```

### 4. 安装 CosyVoice 推理库

```bash
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
git submodule update --init --recursive
pip install -r requirements.txt
cd ..
```

### 5. 安装本服务依赖

```bash
cd tts_server
pip install -r requirements.txt
```

## 模型下载

使用 ModelScope SDK 下载 CosyVoice2-0.5B：

```python
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')
```

或使用 HuggingFace（海外用户）：

```python
from huggingface_hub import snapshot_download
snapshot_download('FunAudioLLM/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')
```

> 如需使用 SFT 预置说话人（如"中文女"），下载 `CosyVoice-300M-SFT`：
> ```python
> snapshot_download('iic/CosyVoice-300M-SFT', local_dir='pretrained_models/CosyVoice-300M-SFT')
> ```

## 配置说明

所有配置通过环境变量控制：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `TTS_HOST` | `0.0.0.0` | 监听地址 |
| `TTS_PORT` | `9880` | 服务端口 |
| `COSYVOICE_MODEL_DIR` | `./pretrained_models/CosyVoice2-0.5B` | 模型目录 |
| `COSYVOICE_REPO` | （空） | CosyVoice 源码路径 |
| `TTS_DEVICE` | `cuda` | 推理设备 |
| `TTS_DEFAULT_SPEAKER` | `中文女` | 默认说话人 |
| `TTS_MAX_TEXT_LENGTH` | `500` | 最大文本长度 |
| `TTS_ZERO_SHOT_PROMPT_WAV` | （空） | Zero-shot 提示音频路径 |
| `TTS_ZERO_SHOT_PROMPT_TEXT` | （空） | Zero-shot 提示文本 |
| `TTS_LOG_LEVEL` | `INFO` | 日志级别 |
| `HSA_OVERRIDE_GFX_VERSION` | （空） | AMD GPU 兼容设置 |

### HSA_OVERRIDE_GFX_VERSION 参考

| GPU 系列 | 设置值 |
|----------|--------|
| RX 6000 (RDNA2) | `10.3.0` |
| RX 7000 (RDNA3) | `11.0.0` |
| Vega 20 | `9.0.6` |

## 启动方式

### 方式一：启动脚本（推荐）

```bash
export COSYVOICE_REPO=/path/to/CosyVoice
export COSYVOICE_MODEL_DIR=/path/to/CosyVoice2-0.5B
bash start_tts.sh
```

### 方式二：直接启动

```bash
export COSYVOICE_REPO=/path/to/CosyVoice
export COSYVOICE_MODEL_DIR=/path/to/CosyVoice2-0.5B
python -m uvicorn tts_server.server:app --host 0.0.0.0 --port 9880
```

### 方式三：Python 入口

```bash
python -m tts_server.server
```

启动后访问 API 文档：http://localhost:9880/docs

## API 使用示例

### 健康检查
```bash
curl http://localhost:9880/health
```

### 获取说话人列表
```bash
curl http://localhost:9880/v1/tts/speakers
```

### 语音合成（WAV）
```bash
curl -X POST http://localhost:9880/v1/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是智能语音助手", "format": "wav"}' \
  --output output.wav
```

### 语音合成（MP3）
```bash
curl -X POST http://localhost:9880/v1/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "欢迎使用语音合成服务", "format": "mp3", "speed": 1.2}' \
  --output output.mp3
```

### 指定说话人
```bash
curl -X POST http://localhost:9880/v1/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "测试文本", "speaker": "中文女", "format": "wav"}' \
  --output output.wav
```

## 与主项目集成

在孕产护理 Agent 后端中调用 TTS 服务：

```python
import requests

TTS_URL = "http://localhost:9880"

def text_to_speech(text: str, format: str = "wav") -> bytes:
    """调用 TTS 服务合成语音"""
    resp = requests.post(
        f"{TTS_URL}/v1/tts/synthesize",
        json={"text": text, "format": format},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.content
```

在 `docker-compose.yml` 中添加 TTS 服务：

```yaml
services:
  tts:
    build: ./tts_server
    ports:
      - "9880:9880"
    environment:
      - COSYVOICE_MODEL_DIR=/models/CosyVoice2-0.5B
      - COSYVOICE_REPO=/opt/CosyVoice
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
```

## 常见问题

### Q: 启动时报 `无法导入 CosyVoice 推理库`
**A:** 需要 clone CosyVoice 仓库并安装其依赖：
```bash
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice && pip install -r requirements.txt
export COSYVOICE_REPO=/absolute/path/to/CosyVoice
```

### Q: 合成时报 `模型目录不存在`
**A:** 下载模型：
```bash
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')"
```

### Q: CUDA/ROCm 相关错误
**A:** 确认 PyTorch ROCm 版本已正确安装，并根据 GPU 型号设置：
```bash
export HSA_OVERRIDE_GFX_VERSION=11.0.0  # RX 7000 系列
```

### Q: MP3 输出失败，自动回退到 WAV
**A:** 需要安装 ffmpeg（pydub 依赖）：
```bash
sudo apt install ffmpeg
```
或安装 lameenc：`pip install lameenc`

### Q: CosyVoice2-0.5B 没有 SFT 说话人（如"中文女"）
**A:** CosyVoice2-0.5B 是 zero-shot 模型，不支持 SFT 说话人。如需使用预置说话人，请下载 `CosyVoice-300M-SFT` 并设置：
```bash
export COSYVOICE_MODEL_DIR=/path/to/CosyVoice-300M-SFT
```
或为 CosyVoice2-0.5B 配置 zero-shot 提示音频：
```bash
export TTS_ZERO_SHOT_PROMPT_WAV=/path/to/prompt.wav
export TTS_ZERO_SHOT_PROMPT_TEXT="提示音频对应的文本"
```

## 文件结构

```
tts_server/
├── __init__.py          # 包标识
├── config.py            # 服务配置
├── model_loader.py      # 模型加载器（单例）
├── server.py            # FastAPI 服务入口
├── requirements.txt     # Python 依赖
├── start_tts.sh         # 启动脚本
├── test_api.py          # API 测试脚本
└── README.md            # 本文档
```
