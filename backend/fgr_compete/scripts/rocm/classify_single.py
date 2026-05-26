"""ROCm/MIGraphX 单张 FGR 分类推理。"""

from fgr_compete.scripts.common.classify_single import main, predict_single


if __name__ == "__main__":
    main("rocm")
