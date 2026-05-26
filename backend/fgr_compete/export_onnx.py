"""兼容入口：导出 FGR ONNX 模型。

新脚本位置：fgr_compete.scripts.rocm.export_onnx。
"""

from .scripts.rocm.export_onnx import ONNXExportWrapper, export_all


if __name__ == "__main__":
    export_all()
