"""兼容入口：CUDA/PyTorch 单张 FGR 分类推理。

新脚本位置：fgr_compete.scripts.cuda.predict_single。
"""

from .scripts.cuda.predict_single import main, predict_single


if __name__ == "__main__":
    main("cuda")
