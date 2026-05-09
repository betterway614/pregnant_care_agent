# AI-Care AMD锐龙AI Max+ 平台硬件适配设计方案 V1.0

| 文档版本 | 修改日期 | 修改人 | 修改内容 |
|:---|:---|:---|:---|
| V1.0 | 2026-04-29 | [你的名字] | 初始版本创建 |
| V1.1 | 2026-04-29 | [你的名字] | 增加分阶段适配策略、开发阶段云端方案 |

## 0. 分阶段适配策略

```
阶段一：业务闭环验证（当前）              阶段二：端侧迁移（竞赛前）
────────────────────────────────────────────────────────────
大模型推理    → 云端API                  → GPU Ollama (ROCm)
FGR评估       → Mock服务                 → NPU ONNX Runtime
NLU解析       → 云端API + 正则           → NPU轻量BERT
规则引擎      → CPU（始终本地）           → CPU（不变）

环境          → 任意开发PC               → AMD锐龙AI Max+ 395
模型加载      → 无                       → 6模型按需加载至UMA
量化          → 无                       → INT4/INT8/FP16

关键原则：业务代码通过接口抽象与推理实现解耦，
         阶段一切换至阶段二仅需改环境变量，不改业务逻辑。
```

## 1. 硬件平台概述

### 1.1 目标平台
| 参数 | 规格 |
|:---|:---|
| 处理器 | AMD 锐龙 AI Max+ 395 |
| GPU | 集成 Radeon 8060S (RDNA 3.5架构) |
| NPU | 锐龙AI专用NPU (XDNA 2架构, 50 TOPS) |
| 内存 | 128GB LPDDR5x (统一内存架构) |
| GPU最大显存分配 | 96GB (UMA动态分配) |
| 存储 | 2TB NVMe SSD |
| 操作系统 | Windows 11 / Ubuntu 24.04 LTS |

### 1.2 统一内存架构（UMA）优势
```
传统架构 (分立显存):
  CPU内存 ←→ [PCIe总线] ←→ GPU显存
  数据拷贝延迟: ~10-50μs/GB
  模型加载需双份内存

AMD UMA架构:
  ┌─────────────────────────────┐
  │   128GB LPDDR5x 统一内存     │
  │   ┌─────┐ ┌─────┐ ┌─────┐  │
  │   │ CPU │ │ GPU │ │ NPU │  │
  │   └──┬──┘ └──┬──┘ └──┬──┘  │
  │      └───────┼───────┘      │
  │              │ 零拷贝访问     │
  │              ▼              │
  │       统一寻址空间            │
  └─────────────────────────────┘
  数据拷贝延迟: ~0 (同物理内存)
  模型仅需加载一份
```

对本项目的意义：7B医疗大模型(INT4约4GB) + Embedding模型(约0.6GB) + FGR模型(约0.5GB) + NLU模型(约0.2GB) 可同时加载在统一内存中，GPU/NPU/CPU直接共享，无需显存交换。

## 2. 异构计算任务分配

### 2.1 任务分工矩阵
```
                     GPU                NPU               CPU
                   (Radeon 8060S)   (锐龙AI 50TOPS)   (Zen5 x16核)
─────────────────────────────────────────────────────────────────
通用医疗大模型推理     ★ 主力              -                 -
  - 对话生成
  - 医嘱推荐
  - 文书撰写

向量检索与Embedding    ★ 主力              -                 -
  - BGE-M3 Embedding
  - ChromaDB ANN搜索
  - RAG知识召回

FGR评估算法             -               ★ 主力              -
  - B超图像推理
  - 风险等级评估
  - 置信区间计算

NLU轻量推理             -               ★ 主力              -
  - 意图识别
  - 实体抽取
  - 情绪分类

数据预处理              -               ★ 辅助              -
  - 图像归一化
  - 文本Tokenize

规则引擎                -                 -               ★ 主力
  - 高危规则匹配
  - 阈值判断

任务调度与编排           -                 -               ★ 主力
  - 智能体路由
  - 消息队列管理

API网关与前后端交互      -                 -               ★ 主力
  - REST API处理
  - WebSocket连接

报告与文档生成           -                 -               ★ 辅助
  - JSON→文本格式化

排期计算                -                 -               ★ 主力
  - 孕周计算
  - 日历冲突检测

数据加解密               -                 -               ★ 主力
  - 哈希脱敏
  - 文件加密
─────────────────────────────────────────────────────────────────
```

### 2.2 推理流水线时间预算
以一次完整的孕妇对话交互为例：
```
时间线 (目标总延迟 < 3s)：

t=0ms    用户发送消息
t=10ms   CPU接收 → 任务路由 → 分发至NLU引擎
t=15ms   NPU开始意图/实体/情绪识别 (ONNX Runtime)
t=50ms   NPU返回NLU结果 (推理耗时 ~35ms)
t=55ms   CPU判断：是否需要知识检索
t=60ms   GPU Embedding用户问题 (BGE-M3) ~10ms
t=70ms   GPU ChromaDB向量检索 ~10ms
t=80ms   CPU拼装Prompt (System + Context + User)
t=85ms   GPU大模型推理开始 (INT4 7B模型)
t=2800ms GPU推理完成，返回token流 (首个token ~300ms, 总计~2.7s)
t=2820ms CPU后处理：安全过滤、来源标注、记忆更新
t=2850ms 响应返回前端
────────────────────────────────
总延迟: ~2.85s ✓ (目标 < 3s)
```

## 3. 模型量化与优化方案

### 3.1 量化策略总览
| 模型 | 原始大小 | 量化方案 | 量化后大小 | 部署位置 | 精度损失 |
|:---|:---|:---|:---|:---|:---|
| 医疗大模型 (Qwen2.5-7B-Med) | ~14GB (FP16) | GPTQ INT4 | ~4GB | GPU | <5% |
| 对话模型 (ChatGLM-6B) | ~12GB (FP16) | GPTQ INT4 | ~3.5GB | GPU | <5% |
| Embedding (BGE-M3) | ~1.2GB (FP16) | 保持FP16 | ~1.2GB | GPU | 0% (检索精度要求) |
| NLU-意图 (BERT-base) | ~0.4GB (FP32) | ONNX INT8 | ~0.1GB | NPU | <2% |
| NLU-情绪 (BERT-tiny) | ~0.1GB (FP32) | ONNX INT8 | ~0.03GB | NPU | <2% |
| FGR评估 (自研) | ~1GB (FP32) | ONNX FP16 | ~0.5GB | NPU | <1% (医学图像敏感) |

### 3.2 GPU模型量化流程（GPTQ INT4）
```
原始模型 (FP16) → 校准数据集准备 (1000条医疗对话)
                → GPTQ量化 (group_size=128, sym=True)
                → GGUF格式导出 (llama.cpp兼容)
                → 精度验证 (Perplexity + 医疗QA准确率对比)
                → Ollama Modelfile 注册
                → 部署

关键参数:
  - bits: 4
  - group_size: 128
  - desc_act: False (提升推理速度)
  - sym: True (对称量化，NPU友好)
```

### 3.3 NPU模型部署流程（ONNX Runtime + Ryzen AI SDK）
```
PyTorch/TF 训练模型
    │
    ▼
导出ONNX (opset_version=17, 包含NPU支持的算子)
    │
    ▼
ONNX Runtime + Vitis AI EP (Execution Provider)
    │
    ▼
AMD Vitis AI 编译器 → 生成NPU指令流
    │
    ▼
量化 (INT8/FP16) → 校准 → 精度验证
    │
    ▼
Ryzen AI SDK 运行时加载 → NPU推理服务
```

### 3.4 统一内存分配计划 (128GB UMA)
```
内存分配布局 (总计 ~100GB / 128GB，余量28GB用于系统与其他服务)：

┌────────────────────────────────────────────┐
│ 系统预留 (OS + 驱动)           ~8GB         │
├────────────────────────────────────────────┤
│ GPU 推理区                     ~45GB        │
│   Ollama服务                   2GB         │
│   医疗大模型 (INT4)             4GB         │
│   对话模型 (INT4)              3.5GB        │
│   Embedding模型 (FP16)         1.2GB        │
│   KV Cache预留                 30GB         │
│   向量索引 (ChromaDB)          4GB          │
├────────────────────────────────────────────┤
│ NPU 推理区                     ~2GB         │
│   FGR模型 (FP16)               0.5GB        │
│   NLU模型 (INT8)               0.15GB       │
│   预处理缓冲区                  1.35GB       │
├────────────────────────────────────────────┤
│ CPU 工作区                     ~45GB        │
│   FastAPI后端                  2GB         │
│   PostgreSQL                   8GB         │
│   Redis                        4GB         │
│   规则引擎+排期                 1GB         │
│   文件缓存/Buffer               10GB        │
│   剩余系统弹性                  20GB        │
└────────────────────────────────────────────┘
```

## 4. 开发环境搭建

### 4.1 AMD云端开发环境（赛题官方提供）
```bash
# 确认硬件信息
lscpu | grep "AMD Ryzen"
rocminfo | grep "Name"
# 预期输出: AMD Radeon 8060S

# 确认NPU可用
ls /dev/ipu*  # AMD NPU设备节点
ryzen-ai-smi  # Ryzen AI系统管理工具

# 确认UMA
cat /proc/meminfo | grep MemTotal
# 预期: ~131000 MB (128GB)
```

### 4.2 驱动与SDK安装
```bash
# 1. ROCm GPU驱动 (Ubuntu 24.04)
wget https://repo.radeon.com/amdgpu-install/latest/ubuntu/jammy/amdgpu-install.deb
sudo apt install ./amdgpu-install.deb
sudo amdgpu-install --usecase=rocm,graphics

# 2. Ryzen AI SDK (NPU)
pip install ryzen-ai-sdk
ryzen-ai-smi --version

# 3. ONNX Runtime with Vitis AI EP
pip install onnxruntime-vitisai

# 4. Ollama (ROCm版本)
curl -fsSL https://ollama.com/install.sh | sh
ollama --version

# 验证GPU可用
ollama run qwen2.5:7b --device rocm
rocminfo | grep "Device"
```

### 4.3 Python环境配置
```bash
# 核心依赖
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.0
pip install transformers accelerate
pip install onnx onnxruntime
pip install ryzen-ai-sdk
pip install ollama chromadb
pip install fastapi uvicorn[standard]
pip install redis psycopg2-binary
pip install pydicom numpy Pillow

# 验证PyTorch + ROCm
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
# 预期: True / AMD Radeon 8060S

# 验证NPU
python -c "import ryzen_ai; print(ryzen_ai.list_devices())"
```

## 5. 性能基准与优化目标

### 5.1 性能KPI
| 指标 | 目标值 | 测量方法 |
|:---|:---|:---|
| 大模型首Token延迟 (TTFT) | < 500ms | GPU推理计时 |
| 大模型Token生成速率 | > 20 tokens/s | Ollama metrics |
| FGR评估延迟 | < 5s (含图像预处理) | NPU推理计时 |
| NLU推理延迟 | < 50ms | NPU推理计时 |
| Embedding+检索延迟 | < 50ms | GPU计时 |
| 端到端对话延迟 (P99) | < 3s | 前端→后端→前端计时 |
| GPU利用率 (推理时) | ≥ 60% | rocm-smi监控 |
| NPU利用率 (推理时) | ≥ 50% | ryzen-ai-smi监控 |
| 整机功耗 (满载) | ≤ 120W | IPMI/ACPI读取 |
| 并发支持 | 3-5路并发对话 | JMeter压测 |

### 5.2 硬件监控命令
```bash
# GPU状态监控
rocm-smi --showuse --showmemuse --showtemp --csv -l 1

# NPU状态监控
ryzen-ai-smi --monitor

# 整机功耗
cat /sys/class/power_supply/*/power_now  # 笔记本
ipmitool sensor list | grep Power        # 台式机

# 统一内存占用
cat /proc/meminfo | grep -E "MemTotal|MemAvailable|MemFree"
```

### 5.3 优化策略
```
延迟优化:
  1. KV Cache预分配 → 避免首次对话时的内存分配抖动
  2. 模型预热 → 启动时先跑一次空推理，确保模型已加载到UMA
  3. Prompt Caching → 系统提示缓存在GPU侧，减少重复Prefill
  4. 流水线并行 → NLU(NPU)与大模型推理(GPU)流水线重叠

吞吐优化:
  1. Continuous Batching → 多用户请求动态合并
  2. 请求排队 → Redis队列缓冲，削峰填谷

内存优化:
  1. 模型按需加载 → 非高峰时段卸载对话模型，释放UMA
  2. 向量索引分段 → ChromaDB索引按科室分段加载
```

## 6. 模型管理

### 6.1 Ollama Modelfile 示例
```dockerfile
# Modelfile: ai-care-medical-v1
FROM qwen2.5:7b-instruct

# 设置量化参数 (GGUF格式)
PARAMETER num_ctx 4096
PARAMETER num_gpu 99
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1

# 系统提示词
SYSTEM """你是AI-Care平台的医疗助手智能体。你的角色设定：
1. 仅提供孕期基础生理知识、常见不适缓解方法、生活建议
2. 绝不输出诊断结论、用药建议或替代医生判断
3. 所有答案标注知识来源，并兜底建议咨询医生
4. 遇到紧急关键词（剧烈腹痛、大出血等）立即建议就医
5. 仅用于科研/教学辅助，不用于临床诊断与治疗决策"""
```

### 6.2 模型版本管理
```
模型仓库目录结构:
/models
├── llm/
│   ├── medical-qwen2.5-7b-int4.gguf       (4.2GB)
│   ├── chat-chatglm-6b-int4.gguf          (3.7GB)
│   └── modelfiles/
│       ├── ai-care-medical-v1.Modelfile
│       └── ai-care-chat-v1.Modelfile
├── embedding/
│   └── bge-m3-fp16/                        (1.2GB)
├── nlu-npu/
│   ├── intent-bert-int8.onnx               (110MB)
│   ├── emotion-bert-int8.onnx              (35MB)
│   └── entity-extract-int8.onnx            (85MB)
└── fgr-npu/
    ├── fgr-assessment-fp16.onnx            (520MB)
    └── preprocess-config.json
```

## 7. 故障处理与降级策略

### 7.1 硬件故障降级
| 故障场景 | 降级方案 | 影响 |
|:---|:---|:---|
| GPU不可用 | 大模型推理切换至CPU (llama.cpp CPU后端) | 延迟增加至10-15s，提示用户等待 |
| NPU不可用 | FGR/NLU切换至CPU ONNX Runtime | FGR延迟增至20-30s |
| UMA不足 | 卸载对话模型，仅保留医疗模型 | 情绪安抚功能暂时降级 |
| 全部不可用 | 返回兜底话术 + 建议联系护士 | 服务降级但不断线 |

### 7.2 模型推理异常处理
```python
# 推理超时与重试策略
INFERENCE_CONFIG = {
    "llm": {
        "timeout_ms": 5000,
        "retry": 2,
        "fallback": "rule_based_response"  # 降级为规则话术
    },
    "fgr": {
        "timeout_ms": 8000,
        "retry": 1,
        "fallback": "return_previous_result"  # 返回最近一次结果
    },
    "nlu": {
        "timeout_ms": 500,
        "retry": 2,
        "fallback": "default_intent"  # 默认意图=普通对话
    }
}
```

## 8. 竞赛演示方案要点

### 8.1 演示场景设计
```
场景1：日常随访自动化 (展示GPU推理 + CPU编排)
  - 护士创建排期 → 定时触发 → 自动对话 → 记录生成

场景2：FGR高危预警闭环 (展示NPU推理 + 三端协同)
  - 上传B超图片 → NPU实时评估 → 预警触发 → 医生审核 → 医嘱生成

场景3：高情商对话与安全兜底 (展示GPU情商模型 + 安全边界)
  - 孕妇表达焦虑 → 情绪识别(NPU) → CBT疏导(GPU) → 安全兜底

场景4：硬件资源实时监控 (展示异构协同效率)
  - GPU利用率曲线 / NPU利用率曲线 / UMA占用 / 功耗实时面板
```

### 8.2 演示环境检查清单
- [ ] ROCm驱动正常，`rocm-smi`可见GPU
- [ ] NPU驱动正常，`ryzen-ai-smi`可见NPU设备
- [ ] Ollama加载医疗模型，推理延迟达标
- [ ] ONNX Runtime NPU后端正常，FGR推理延迟达标
- [ ] ChromaDB索引就绪，检索结果相关
- [ ] 三端Web界面正常访问
- [ ] 硬件监控面板数据刷新正常
- [ ] 离线模式验证（断开外网后核心功能正常）
