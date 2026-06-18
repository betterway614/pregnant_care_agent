#!/bin/bash
# ============================================================================
# CosyVoice2 TTS 服务启动脚本 (ROCm 适配版)
# 用法: bash start_tts.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo "  CosyVoice2 TTS 服务启动 (ROCm)"
echo "=========================================="

# ---------------------------------------------------------------------------
# 0. 激活虚拟环境
# ---------------------------------------------------------------------------
VENV_DIR="${VENV_DIR:-$REPO_ROOT/cosyvoice_env}"
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "[0/4] 激活虚拟环境: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
else
    echo "[警告] 虚拟环境不存在: $VENV_DIR"
    echo "  请确认已运行安装步骤"
fi

# ---------------------------------------------------------------------------
# 1. ROCm 设备检查
# ---------------------------------------------------------------------------
echo ""
echo "[1/4] 检查 ROCm GPU 设备..."
if command -v rocm-smi &> /dev/null; then
    rocm-smi --showproductname 2>/dev/null || echo "  (rocm-smi 信息获取失败，继续启动)"
    echo "  ROCm GPU 设备检测通过"
else
    echo "  [警告] rocm-smi 未找到，无法确认 AMD GPU 状态"
    echo "  请确认已安装 ROCm: https://rocm.docs.amd.com/"
fi

# ---------------------------------------------------------------------------
# 2. 环境变量设置（可通过外部 export 覆盖）
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] 配置环境变量..."

# gfx1151 (RDNA 3.5, Strix Halo) 需要伪装为 gfx1100 (RDNA 3) 以兼容 PyTorch ROCm
if [ -z "$HSA_OVERRIDE_GFX_VERSION" ]; then
    export HSA_OVERRIDE_GFX_VERSION=11.0.0
    echo "  自动设置 HSA_OVERRIDE_GFX_VERSION=11.0.0 (gfx1151 -> gfx1100 兼容模式)"
else
    echo "  HSA_OVERRIDE_GFX_VERSION=$HSA_OVERRIDE_GFX_VERSION (已手动设置)"
fi

# ROCm 推理加速优化
if [ -z "$TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL" ]; then
    export TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1
    echo "  启用 AOTriton 加速 attention (TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1)"
fi
if [ -z "$MIOPEN_FIND_MODE" ]; then
    # 3 = FAST（使用已知的高效算法，避免 Tuning 模式下的 workspace 分配崩溃）
    export MIOPEN_FIND_MODE=3
    echo "  MIOpen 快速搜索模式 (MIOPEN_FIND_MODE=3)"
fi
# MIOpen 工作空间（2GB，足够 fp32 卷积使用）
export PYTORCH_MIOPEN_WORKSPACE_SIZE_LIMIT="${PYTORCH_MIOPEN_WORKSPACE_SIZE_LIMIT:-2147483648}"
echo "  MIOpen workspace: ${PYTORCH_MIOPEN_WORKSPACE_SIZE_LIMIT} bytes"

# PyTorch 缓存分配器：预分配大块显存，减少碎片
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

# 默认环境变量
export TTS_HOST="${TTS_HOST:-0.0.0.0}"
export TTS_PORT="${TTS_PORT:-9880}"
export COSYVOICE_MODEL_DIR="${COSYVOICE_MODEL_DIR:-$PROJECT_DIR/pretrained_models/CosyVoice2-0.5B}"
export TTS_DEVICE="${TTS_DEVICE:-cuda}"
export TTS_LOG_LEVEL="${TTS_LOG_LEVEL:-INFO}"

# CosyVoice 仓库路径
COSYVOICE_REPO_DEFAULT="$REPO_ROOT/CosyVoice"
export COSYVOICE_REPO="${COSYVOICE_REPO:-$COSYVOICE_REPO_DEFAULT}"

echo "  TTS_HOST=$TTS_HOST"
echo "  TTS_PORT=$TTS_PORT"
echo "  COSYVOICE_MODEL_DIR=$COSYVOICE_MODEL_DIR"
echo "  COSYVOICE_REPO=$COSYVOICE_REPO"
echo "  TTS_DEVICE=$TTS_DEVICE"
echo "  TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=$TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL"

# ---------------------------------------------------------------------------
# 3. 模型检查
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] 检查模型文件..."

MODEL_DIR="$COSYVOICE_MODEL_DIR"
if [ ! -d "$MODEL_DIR" ]; then
    echo "  [错误] 模型目录不存在: $MODEL_DIR"
    echo ""
    echo "  请先下载模型:"
    echo "    python -c \"from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='$MODEL_DIR')\""
    echo ""
    echo "  或设置环境变量指向已有模型目录:"
    echo "    export COSYVOICE_MODEL_DIR=/path/to/CosyVoice2-0.5B"
    exit 1
fi

# 检查关键模型文件
if [ ! -f "$MODEL_DIR/cosyvoice.yaml" ] && [ ! -f "$MODEL_DIR/configuration.json" ]; then
    echo "  [警告] 模型目录中未找到 cosyvoice.yaml 或 configuration.json，可能模型不完整"
    echo "  请确认模型下载完整"
else
    echo "  模型目录检查通过: $MODEL_DIR"
fi

# CosyVoice 推理库检查
if [ -n "$COSYVOICE_REPO" ]; then
    echo "  COSYVOICE_REPO=$COSYVOICE_REPO"
    if [ ! -d "$COSYVOICE_REPO/cosyvoice" ]; then
        echo "  [警告] COSYVOICE_REPO 中未找到 cosyvoice 子目录"
    else
        echo "  CosyVoice 推理库检查通过"
    fi
else
    echo "  COSYVOICE_REPO 未设置，将尝试直接从 Python 环境导入 cosyvoice"
    echo "  如导入失败，请设置: export COSYVOICE_REPO=/path/to/CosyVoice"
fi

# ---------------------------------------------------------------------------
# 4. 启动服务
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] 启动 TTS 服务..."
echo "  服务地址: http://$TTS_HOST:$TTS_PORT"
echo "  API 文档: http://localhost:$TTS_PORT/docs"
echo "=========================================="
echo ""

cd "$PROJECT_DIR"
python -m uvicorn tts_server.server:app \
    --host "$TTS_HOST" \
    --port "$TTS_PORT" \
    --log-level "${TTS_LOG_LEVEL,,}"
