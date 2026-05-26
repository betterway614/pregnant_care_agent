"""兼容入口：Ryzen AI/Quark ONNX 量化。

新脚本位置：fgr_compete.scripts.ryzen_ai.quantize_onnx。
"""

from .scripts.ryzen_ai.quantize_onnx import CalibrationDataReader, quantize_all


if __name__ == "__main__":
    quantize_all()
