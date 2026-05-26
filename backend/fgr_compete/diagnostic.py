"""兼容入口：CUDA/PyTorch FGR 诊断脚本。

新脚本位置：fgr_compete.scripts.cuda.diagnostic。
"""

from .scripts.cuda.diagnostic import run_diagnostic


if __name__ == "__main__":
    run_diagnostic()
