# nnU-Net 胎盘分割模型使用说明

> 本模型用于NT期（孕11-13周）胎盘超声图像的自动分割，是FGR检测三阶段框架的第一阶段。

---

## 模型概览

| 项目 | 内容 |
|------|------|
| 任务 | NT期胎盘二值分割 |
| 框架 | nnU-Net v2，2D配置 |
| 训练数据 | 40张手工标注的NT期胎盘超声图 |
| 性能 | 5折交叉验证 Dice = **0.722** |
| 后处理 | 保留最大前景连通区域（Dice后处理后约0.7224） |

---

## 文件结构

```
nnUNet_segmentation_model/
├── README.md                         ← 本文档
├── inference_instructions.txt        ← 原始推理说明（自动生成）
├── inference_information.json        ← 推理信息
└── nnUNetTrainer__nnUNetPlans__2d/
    ├── dataset.json                  ← 数据集配置（必须）
    ├── plans.json                    ← 训练计划配置（必须）
    ├── dataset_fingerprint.json      ← 数据指纹（必须）
    ├── fold_0/checkpoint_final.pth   ← 第1折模型
    ├── fold_1/checkpoint_final.pth   ← 第2折模型
    ├── fold_2/checkpoint_final.pth   ← 第3折模型
    ├── fold_3/checkpoint_final.pth   ← 第4折模型
    ├── fold_4/checkpoint_final.pth   ← 第5折模型
    └── crossval_results_folds_0_1_2_3_4/
        ├── postprocessing.pkl        ← 后处理参数
        ├── postprocessing.json
        ├── plans.json
        └── summary.json              ← 性能指标
```

---

## 环境安装

```bash
# 推荐使用 conda 创建独立环境
conda create -n nnunet python=3.9 -y
conda activate nnunet

# 安装PyTorch（根据自己的CUDA版本选择）
pip install torch torchvision

# 安装nnU-Net v2
pip install nnunetv2
```

---

## 部署步骤

### Step 1：放置模型文件

把整个 `Dataset001_PlacentaNT` 文件夹放到一个目录下，假设路径为：

```
/your/path/nnUNet_results/Dataset001_PlacentaNT/
```

### Step 2：设置环境变量

```bash
# 推理只需要设置这一个变量
export nnUNet_results="/your/path/nnUNet_results"

# 训练时还需要这两个（推理可不设）
# export nnUNet_raw="/your/path/nnUNet_raw"
# export nnUNet_preprocessed="/your/path/nnUNet_preprocessed"
```

建议把上面的 `export` 加到 `~/.bashrc` 里，这样每次开终端自动生效。

### Step 3：准备输入图片

把要分割的图片放在一个文件夹里，**文件名必须以 `_0000.png` 结尾**（nnU-Net的命名规范）：

```
input_images/
├── case001_0000.png
├── case002_0000.png
└── case003_0000.png
```

如果原图不是这个命名，需要批量重命名。例如：

```bash
# 把所有.png加上_0000后缀
cd your_input_dir
for f in *.png; do
    mv "$f" "${f%.png}_0000.png"
done
```

---

## 运行推理

### 方法1：5折集成推理（推荐，精度最高）

```bash
nnUNetv2_predict \
    -d Dataset001_PlacentaNT \
    -i /path/to/input_images \
    -o /path/to/output_masks \
    -f 0 1 2 3 4 \
    -tr nnUNetTrainer \
    -c 2d \
    -p nnUNetPlans
```

参数说明：
- `-d Dataset001_PlacentaNT`：数据集名（固定）
- `-i`：输入图片文件夹
- `-o`：输出mask文件夹（会自动创建）
- `-f 0 1 2 3 4`：使用5折集成（最稳）；如果嫌慢可以只用一折，比如 `-f 0`
- `-tr nnUNetTrainer -c 2d -p nnUNetPlans`：训练器/配置/计划（固定）

### 方法2：后处理（推荐用，提升精度）

推理完成后，应用后处理（保留最大连通区域）：

```bash
nnUNetv2_apply_postprocessing \
    -i /path/to/output_masks \
    -o /path/to/output_masks_pp \
    -pp_pkl_file /your/path/nnUNet_results/Dataset001_PlacentaNT/nnUNetTrainer__nnUNetPlans__2d/crossval_results_folds_0_1_2_3_4/postprocessing.pkl \
    -np 8 \
    -plans_json /your/path/nnUNet_results/Dataset001_PlacentaNT/nnUNetTrainer__nnUNetPlans__2d/crossval_results_folds_0_1_2_3_4/plans.json
```

参数说明：
- `-i`：上一步的输出文件夹
- `-o`：后处理后的输出文件夹
- `-pp_pkl_file`：后处理参数（在 `crossval_results_folds_0_1_2_3_4/` 下）
- `-np 8`：使用8个进程并行处理
- `-plans_json`：训练计划配置

---

## ⚠️ 重要：mask读取的坑

nnU-Net生成的mask像素值为 **0和1**（背景=0，胎盘=1），不是常见的 0和255。

**直接用PIL读取会发现图片全黑（其实数据是对的，只是肉眼看不见）。**

正确的读取方式：

```python
import numpy as np
from PIL import Image

mask = np.array(Image.open("mask.png").convert("L"))

# 如果最大值<=1，说明是nnU-Net格式，需要乘以255才能正常显示/使用
if mask.max() <= 1.0:
    mask = mask * 255

# 转为二值布尔mask
mask_bool = (mask > 127).astype(bool)
```

---

## 完整使用示例

假设你要分割10张图片：

```bash
# 1. 准备
mkdir -p input_images output_masks output_masks_pp

# 2. 把图片放到input_images/，文件名带_0000.png后缀

# 3. 设置环境变量
export nnUNet_results=/home/user/nnUNet_results

# 4. 推理（5折集成）
nnUNetv2_predict \
    -d Dataset001_PlacentaNT \
    -i ./input_images \
    -o ./output_masks \
    -f 0 1 2 3 4 \
    -tr nnUNetTrainer \
    -c 2d \
    -p nnUNetPlans

# 5. 后处理
nnUNetv2_apply_postprocessing \
    -i ./output_masks \
    -o ./output_masks_pp \
    -pp_pkl_file $nnUNet_results/Dataset001_PlacentaNT/nnUNetTrainer__nnUNetPlans__2d/crossval_results_folds_0_1_2_3_4/postprocessing.pkl \
    -np 8 \
    -plans_json $nnUNet_results/Dataset001_PlacentaNT/nnUNetTrainer__nnUNetPlans__2d/crossval_results_folds_0_1_2_3_4/plans.json
```

完成后 `output_masks_pp/` 里就是最终的胎盘mask，可以传给FGR分类阶段使用。

---

## 常见问题

**Q: 推理报错 "Dataset001_PlacentaNT not found"**
A: 检查环境变量 `nnUNet_results` 是否指向正确的目录。运行 `echo $nnUNet_results` 确认。

**Q: 推理很慢/没GPU能跑吗？**
A: 5折大约几分钟（GPU）/几十分钟（CPU）。如果没GPU或想加快速度，只用1折：`-f 0`，精度会略低。

**Q: mask看起来全黑**
A: 见上面"mask读取的坑"部分，需要乘以255。

**Q: 输入图片不是PNG怎么办？**
A: nnU-Net需要PNG格式，先用 PIL 转一下：
```python
from PIL import Image
Image.open("input.jpg").save("input_0000.png")
```

**Q: 能用于其他孕期的胎盘超声吗？**
A: 模型只在NT期（11-13周）数据上训练，用在其他孕期效果不保证。

---

## 模型性能（来自训练时的5折交叉验证）

| 指标 | 数值 |
|------|------|
| 平均Dice | 0.722 |
| 后处理后Dice | 约0.7224 |
| 训练数据量 | 40张 |
| 训练设备 | NVIDIA GPU |

详细的5折分数可以查看：
`crossval_results_folds_0_1_2_3_4/summary.json`

---

如有问题请联系师姐。祝比赛顺利！
