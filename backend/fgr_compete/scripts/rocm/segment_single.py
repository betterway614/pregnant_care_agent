"""ROCm 环境下调用 nnU-Net 进行单张胎盘图像分割。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import settings
from app.services.segmentation_service import SegmentationService


def _resolve_model_dir(model_dir: str) -> str:
    path = Path(model_dir)
    if not path.is_absolute():
        path = _BACKEND_DIR / path
    return str(path.resolve())


def segment_single(image_path: str, output_dir: str, model_dir: str | None = None, folds: str | None = None) -> str:
    model_dir = _resolve_model_dir(model_dir or settings.nnunet_model_dir)
    service = SegmentationService(
        model_dir=model_dir,
        dataset_id=settings.nnunet_dataset_id,
        folds=folds or settings.nnunet_folds,
    )
    return service.segment(image_path, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="原始超声图像路径")
    parser.add_argument("--output-dir", required=True, help="分割 mask 输出目录")
    parser.add_argument("--model-dir", help="nnU-Net 模型目录，默认读取 .env 的 NNUNET_MODEL_DIR")
    parser.add_argument("--folds", help="nnU-Net folds，默认读取 .env 的 NNUNET_FOLDS")
    parser.add_argument("--rocr-visible-devices", default="0", help="ROCm 设备号，默认 0")
    args = parser.parse_args()

    os.environ.setdefault("ROCR_VISIBLE_DEVICES", args.rocr_visible_devices)
    os.environ.setdefault("HIP_VISIBLE_DEVICES", os.environ["ROCR_VISIBLE_DEVICES"])
    mask_path = segment_single(args.image, args.output_dir, args.model_dir, args.folds)
    print(mask_path)


if __name__ == "__main__":
    main()
