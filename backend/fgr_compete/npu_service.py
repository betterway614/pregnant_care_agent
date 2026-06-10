"""NPU 预测服务：通过 ryzen_ai_venv 子进程在 AMD NPU 上执行 ONNX 推理。

架构：
  FastAPI (Python 3.13)  →  子进程 (Python 3.12 + VitisAI)  →  AMD NPU
                          JSON over stdin/stdout

使用方式：
  from fgr_compete.npu_service import NPUPredictorService
  service = NPUPredictorService()
  service.initialize()
  result = service.predict_from_bytes(image_bytes, mask_bytes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

# 子进程入口：加载 ONNX 模型并在主循环中处理请求
_SUBPROCESS_ENTRY = """
import json
import os
import sys

# 设置 LD_LIBRARY_PATH 和 ryzen_ai_venv 的 site-packages
_RYZEN_VENV = "{ryzen_venv}"
_BACKEND_DIR = "{backend_dir}"
_DEPLOYMENT_LIB = os.path.join(_RYZEN_VENV, "deployment", "lib")
_SITE_PACKAGES = os.path.join(_RYZEN_VENV, "lib", "python3.12", "site-packages")

os.environ["LD_LIBRARY_PATH"] = (_DEPLOYMENT_LIB + ":" + os.environ.get("LD_LIBRARY_PATH", ""))

# 添加 Python 路径：backend 目录 + ryzen_ai_venv 的 site-packages
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _SITE_PACKAGES)
sys.path.insert(0, os.path.join(_SITE_PACKAGES, ".."))

import numpy as np
from fgr_compete.onnx_predictor import ONNXFGRPredictor, preprocess_roi_for_onnx
from fgr_compete.features import bytes_to_raw, bytes_to_mask, extract_features

# 全局预测器（每个子进程只加载一次）
_PREDICTOR = None

def _handle_request(req: dict) -> dict:
    global _PREDICTOR
    try:
        if req.get("type") == "init":
            backend = req.get("backend", "onnx_npu")
            _PREDICTOR = ONNXFGRPredictor(backend)
            _PREDICTOR.initialize()
            return {{"ok": True, "hardware": _PREDICTOR.hardware, "provider": _PREDICTOR.execution_provider}}

        elif req.get("type") == "predict":
            if _PREDICTOR is None:
                return {{"error": "predictor not initialized"}}
            raw = bytes_to_raw(bytes(req["raw_bytes"]))
            mask = bytes_to_mask(bytes(req["mask_bytes"]))
            result = _PREDICTOR._predict_arrays(raw, mask)
            return result

        elif req.get("type") == "health":
            return {{"ok": True, "loaded": _PREDICTOR is None}}

    except Exception as e:
        import traceback
        return {{"error": str(e), "traceback": traceback.format_exc()}}

if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({{"error": "invalid JSON"}}), flush=True)
            continue
        resp = _handle_request(req)
        print(json.dumps(resp), flush=True)
"""

class NPUPredictorService:
    """通过子进程调用 ryzen_ai_venv 中的 ONNX+VitisAI 预测器。

    接口与 ONNXFGRPredictor 保持一致，支持：
      - initialize(): 启动子进程，加载模型
      - predict(image_path, mask_path): 基于文件路径预测
      - predict_from_bytes(image_bytes, mask_bytes): 基于字节预测
      - hardware / execution_provider 属性
    """

    def __init__(self, backend: str = "onnx_npu", max_workers: int = 4):
        self.requested_backend = backend
        self.actual_backend: str | None = None
        self.execution_provider: str = "VitisAIExecutionProvider"
        self.hardware: str = "NPU/VitisAI"
        self._initialized = False
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        ryzen_venv = os.environ.get("RYZEN_AI_VENV") or "/media/amd-22oilkp/workspace/amdryzen_ai/ryzen_ai_venv"
        self._ryzen_venv = ryzen_venv
        self._backend_dir = str(Path(__file__).parent.parent)  # fgr_compete 的父目录
        self._env = os.environ.copy()
        deployment_lib = os.path.join(ryzen_venv, "deployment", "lib")
        self._env["LD_LIBRARY_PATH"] = deployment_lib + ":" + self._env.get("LD_LIBRARY_PATH", "")

    def _start_subprocess(self) -> subprocess.Popen:
        """启动子进程，运行 NPU 推理服务。"""
        entry = _SUBPROCESS_ENTRY.format(
            ryzen_venv=self._ryzen_venv.replace("\\", "\\\\"),
            backend_dir=self._backend_dir.replace("\\", "\\\\"),
        )
        python_path = os.path.join(self._ryzen_venv, "bin", "python")

        proc = subprocess.Popen(
            [python_path, "-c", entry],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
            cwd=self._backend_dir,  # 设置工作目录
            text=False,  # binary mode for image bytes
            bufsize=0,
        )
        return proc

    def _send_request(self, req: dict, timeout: float = 60.0) -> dict:
        """向子进程发送 JSON 请求并等待响应。"""
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError("NPU 子进程已退出，请先调用 initialize()")

        request_json = json.dumps(req, ensure_ascii=False) + "\n"
        try:
            self._process.stdin.write(request_json.encode("utf-8"))
            self._process.stdin.flush()
        except BrokenPipeError:
            raise RuntimeError("NPU 子进程 stdin 已关闭")

        # 读取响应（带超时）
        import select
        ready, _, _ = select.select([self._process.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"NPU 推理超时 ({timeout}s)")
        resp_line = self._process.stdout.readline()
        if not resp_line:
            raise RuntimeError("NPU 子进程 stdout 为空")
        resp = json.loads(resp_line.decode("utf-8"))
        if "error" in resp:
            raise RuntimeError(f"NPU 推理错误: {resp['error']}")
        return resp

    def initialize(self) -> None:
        """启动子进程并发送初始化请求。"""
        logger.info("[NPU-服务] 启动 NPU 推理子进程 (ryzen_ai_venv={})", self._ryzen_venv)
        self._process = self._start_subprocess()

        # 发送 init 请求
        resp = self._send_request({"type": "init", "backend": self.requested_backend}, timeout=120.0)
        self.hardware = resp.get("hardware", "NPU/VitisAI")
        self.execution_provider = resp.get("provider", "VitisAIExecutionProvider")
        self._initialized = True

        logger.info(
            "[NPU-服务] 初始化完成 backend={} hardware={} provider={}",
            self.requested_backend, self.hardware, self.execution_provider,
        )

    def predict(self, image_path: str, mask_path: str) -> dict:
        """基于文件路径的预测。"""
        with open(image_path, "rb") as f:
            raw_bytes = f.read()
        with open(mask_path, "rb") as f:
            mask_bytes = f.read()
        return self.predict_from_bytes(raw_bytes, mask_bytes)

    def predict_from_bytes(self, image_bytes: bytes, mask_bytes: bytes) -> dict:
        """基于字节数据的预测（用于 API 上传）。"""
        assert self._initialized, "NPUPredictorService.initialize() 必须先调用"

        req = {
            "type": "predict",
            "raw_bytes": list(image_bytes),
            "mask_bytes": list(mask_bytes),
        }
        return self._send_request(req, timeout=30.0)

    def close(self) -> None:
        """终止子进程。"""
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._thread_pool.shutdown(wait=False)
        self._initialized = False
        logger.info("[NPU-服务] 子进程已关闭")

    def __del__(self):
        self.close()


# ── 模块级单例管理 ───────────────────────────────────────────────
_service: NPUPredictorService | None = None
_service_lock = threading.Lock()


def get_npu_service() -> NPUPredictorService:
    """获取全局 NPU 预测服务单例。"""
    global _service
    with _service_lock:
        if _service is None:
            _service = NPUPredictorService()
        return _service


def initialize_npu_service(backend: str = "onnx_npu") -> NPUPredictorService:
    """按指定后端初始化全局 NPU 预测服务。"""
    global _service
    with _service_lock:
        if _service is not None:
            _service.close()
        _service = NPUPredictorService(backend)
        _service.initialize()
        return _service


def shutdown_npu_service() -> None:
    """关闭全局 NPU 预测服务。"""
    global _service
    with _service_lock:
        if _service is not None:
            _service.close()
            _service = None