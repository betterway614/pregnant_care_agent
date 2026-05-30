"""Ryzen AI NPU runtime 诊断脚本。

用于区分三类问题：
1. Python 是否能看到 VitisAIExecutionProvider；
2. XRT 是否能识别并验证 NPU；
3. amdxdna 是否加载了 AMD Ryzen AI 包提供的 DKMS 驱动。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return 124, output + f"\n[TIMEOUT] command timed out after {timeout}s"


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def _check_onnx_provider() -> bool:
    _section("1. ONNX Runtime Provider")
    try:
        import onnxruntime as ort
    except Exception as exc:
        print(f"[FAIL] onnxruntime import 失败: {exc}")
        return False
    providers = list(ort.get_available_providers())
    print(f"onnxruntime: {ort.__version__}")
    print(f"providers: {providers}")
    ok = "VitisAIExecutionProvider" in providers
    print("[OK] VitisAIExecutionProvider 可用" if ok else "[FAIL] 未发现 VitisAIExecutionProvider")
    return ok


def _check_xrt() -> bool:
    _section("2. XRT / NPU")
    xrt_smi = shutil.which("xrt-smi")
    if not xrt_smi:
        print("[FAIL] xrt-smi 不在 PATH。请先 source /opt/xilinx/xrt/setup.sh")
        return False
    print(f"xrt-smi: {xrt_smi}")
    code, output = _run([xrt_smi, "examine"], timeout=30)
    print(output.strip())
    ok = code == 0 and ("RyzenAI" in output or "NPU" in output)
    print("[OK] XRT 能识别 NPU" if ok else "[FAIL] XRT 未能识别 NPU")
    return ok


def _check_amdxdna() -> bool:
    _section("3. amdxdna 内核驱动")
    code, output = _run(["modinfo", "amdxdna"], timeout=30)
    if code != 0:
        print(output.strip())
        print("[FAIL] modinfo amdxdna 失败")
        return False
    fields = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    filename = fields.get("filename", "")
    intree = fields.get("intree", "")
    print(f"filename: {filename}")
    print(f"intree: {intree or '(unknown)'}")
    if intree == "Y" or "/kernel/drivers/accel/amdxdna/" in filename:
        print("[WARN] 当前加载的是内核自带 amdxdna；Ryzen AI 1.7.1 包内还提供了 DKMS 驱动。")
        return False
    print("[OK] 当前 amdxdna 看起来不是内核内置模块")
    return True


def _check_dkms_tools() -> bool:
    _section("4. DKMS 工具")
    dkms = shutil.which("dkms")
    if not dkms:
        print("[FAIL] 未安装 dkms 命令")
        return False
    print(f"dkms: {dkms}")
    code, output = _run([dkms, "status"], timeout=30)
    print(output.strip() or "(dkms status 无输出)")
    ok = "xrt-amdxdna" in output or "amdxdna" in output
    print("[OK] DKMS 中发现 amdxdna/xrt-amdxdna" if ok else "[WARN] DKMS 中未发现 xrt-amdxdna")
    return ok


def _run_validate() -> bool:
    _section("5. xrt-smi validate")
    xrt_smi = shutil.which("xrt-smi")
    if not xrt_smi:
        print("[SKIP] xrt-smi 不可用")
        return False
    code, output = _run([xrt_smi, "validate", "--verbose"], timeout=120)
    print(output.strip())
    ok = code == 0 and "Validation failed" not in output
    print("[OK] xrt-smi validate 通过" if ok else "[FAIL] xrt-smi validate 未通过")
    return ok


def _run_quicktest(timeout: int) -> bool:
    _section("6. Ryzen AI quicktest")
    install_path = os.environ.get("RYZEN_AI_INSTALLATION_PATH") or os.environ.get("VIRTUAL_ENV")
    if not install_path:
        print("[SKIP] 未设置 RYZEN_AI_INSTALLATION_PATH/VIRTUAL_ENV")
        return False
    quicktest = Path(install_path) / "quicktest" / "quicktest.py"
    if not quicktest.exists():
        print(f"[SKIP] quicktest.py 不存在: {quicktest}")
        return False
    code, output = _run([sys.executable, str(quicktest)], timeout=timeout)
    tail = "\n".join(output.splitlines()[-80:])
    print(tail)
    ok = code == 0 and "Test Finished" in output
    print("[OK] quicktest 通过" if ok else "[FAIL] quicktest 未通过")
    return ok


def _run_fgr(image: str | None, mask: str | None) -> bool:
    if not image or not mask:
        return False
    _section("7. FGR onnx_npu benchmark")
    try:
        from fgr_compete.scripts.common.benchmark import benchmark_backend
        result = benchmark_backend("onnx_npu", image, mask)
        print(result)
        ok = result.get("hardware") == "NPU/VitisAI"
        print("[OK] FGR onnx_npu 通过" if ok else "[FAIL] FGR 未使用 NPU/VitisAI")
        return ok
    except Exception as exc:
        print(f"[FAIL] FGR onnx_npu 异常: {exc}")
        return False


def _print_next_steps(provider_ok: bool, xrt_ok: bool, dkms_loaded: bool, dkms_tool_ok: bool, quicktest_ok: bool) -> None:
    _section("建议下一步")
    if provider_ok and xrt_ok and not quicktest_ok:
        print("VitisAI EP 和 XRT 设备识别都已就绪，但 NPU kernel 执行失败。")
    if not dkms_loaded:
        print("当前最大嫌疑：系统仍在使用内核自带 amdxdna，而不是 Ryzen AI 1.7.1 驱动包提供的 xrt-amdxdna DKMS 模块。")
    if not dkms_tool_ok:
        print("请先安装 DKMS 工具和当前内核头文件：")
        print("  sudo apt update")
        print("  sudo apt install -y dkms build-essential linux-headers-$(uname -r)")
    print("然后安装 AMD 包内的 amdxdna DKMS 驱动并重启：")
    print("  sudo /opt/xilinx/xrt/share/amdxdna/dkms_driver.sh --install")
    print("  sudo reboot")
    print("重启后期望看到：")
    print("  dkms status | grep xrt-amdxdna")
    print("  modinfo amdxdna | grep -E 'filename|intree'")
    print("  xrt-smi validate --verbose")
    print("  python /media/amd-22oilkp/workspace/amdryzen_ai/ryzen_ai_venv/quicktest/quicktest.py")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="可选：FGR 原始图片路径")
    parser.add_argument("--mask", help="可选：FGR mask 路径")
    parser.add_argument("--skip-validate", action="store_true", help="跳过 xrt-smi validate")
    parser.add_argument("--skip-quicktest", action="store_true", help="跳过 Ryzen AI quicktest")
    parser.add_argument("--quicktest-timeout", type=int, default=120)
    args = parser.parse_args()

    provider_ok = _check_onnx_provider()
    xrt_ok = _check_xrt()
    dkms_loaded = _check_amdxdna()
    dkms_tool_ok = _check_dkms_tools()
    if not args.skip_validate:
        _run_validate()
    quicktest_ok = False if args.skip_quicktest else _run_quicktest(args.quicktest_timeout)
    _run_fgr(args.image, args.mask)
    _print_next_steps(provider_ok, xrt_ok, dkms_loaded, dkms_tool_ok, quicktest_ok)


if __name__ == "__main__":
    main()
