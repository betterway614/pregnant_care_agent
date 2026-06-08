"""
CosyVoice2 TTS 服务 API 测试脚本
用法: python test_api.py [--base-url http://localhost:9880]
"""
import argparse
import time
import os
import sys


def run_tests(base_url: str):
    try:
        import requests
    except ImportError:
        print("请先安装 requests: pip install requests")
        sys.exit(1)

    passed = 0
    failed = 0
    total = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}  {detail}")

    # -----------------------------------------------------------------------
    print("\n=== 1. 健康检查 ===")
    try:
        r = requests.get(f"{base_url}/health", timeout=10)
        check("GET /health 状态码", r.status_code == 200, f"got {r.status_code}")
        data = r.json()
        check("返回 model_loaded 字段", "model_loaded" in data)
        print(f"  模型状态: {'已加载' if data.get('model_loaded') else '未加载'}")
        if data.get("error"):
            print(f"  错误信息: {data['error']}")
    except Exception as e:
        check("健康检查请求", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 2. 获取说话人列表 ===")
    try:
        r = requests.get(f"{base_url}/v1/tts/speakers", timeout=10)
        if r.status_code == 503:
            print("  [SKIP] 模型未加载，跳过后续合成测试")
            print(f"\n结果: {passed}/{total} 通过 (模型未加载，合成测试跳过)")
            return
        check("GET /v1/tts/speakers 状态码", r.status_code == 200, f"got {r.status_code}")
        data = r.json()
        check("返回 speakers 列表", "speakers" in data)
        print(f"  可用说话人: {data.get('speakers', [])}")
        print(f"  采样率: {data.get('sample_rate')}")
    except Exception as e:
        check("获取说话人列表", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 3. 基础合成测试（中文短文本，WAV）===")
    try:
        text = "你好，我是智能语音助手，很高兴为您服务。"
        start = time.time()
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": text, "format": "wav"},
            timeout=120,
        )
        elapsed = time.time() - start
        check("合成请求成功", r.status_code == 200, f"got {r.status_code}")
        check("返回 Content-Type 含 audio", "audio" in r.headers.get("content-type", ""), 
              f"content-type={r.headers.get('content-type')}")
        check("返回数据非空", len(r.content) > 1000, f"size={len(r.content)}")
        print(f"  音频大小: {len(r.content) / 1024:.1f} KB")
        print(f"  耗时: {elapsed:.2f}s")

        # 保存测试文件
        output_dir = os.path.dirname(os.path.abspath(__file__))
        wav_path = os.path.join(output_dir, "test_output.wav")
        with open(wav_path, "wb") as f:
            f.write(r.content)
        print(f"  已保存到: {wav_path}")
    except Exception as e:
        check("基础合成测试", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 4. MP3 格式测试 ===")
    try:
        text = "这是一段MP3格式的语音测试。"
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": text, "format": "mp3"},
            timeout=120,
        )
        check("MP3 合成请求成功", r.status_code == 200, f"got {r.status_code}")
        ct = r.headers.get("content-type", "")
        check("返回音频数据", len(r.content) > 1000, f"size={len(r.content)}")
        print(f"  Content-Type: {ct}")
        print(f"  音频大小: {len(r.content) / 1024:.1f} KB")
    except Exception as e:
        check("MP3 格式测试", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 5. 长文本测试 ===")
    try:
        text = "人工智能技术的快速发展正在深刻改变我们的生活方式。" * 5
        start = time.time()
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": text, "format": "wav"},
            timeout=180,
        )
        elapsed = time.time() - start
        check("长文本合成成功", r.status_code == 200, f"got {r.status_code}")
        print(f"  文本长度: {len(text)} 字符")
        print(f"  音频大小: {len(r.content) / 1024:.1f} KB")
        print(f"  耗时: {elapsed:.2f}s")
    except Exception as e:
        check("长文本测试", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 6. 语速测试 ===")
    try:
        text = "语速测试，这段话将以一点五倍速播放。"
        start = time.time()
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": text, "speed": 1.5, "format": "wav"},
            timeout=120,
        )
        elapsed = time.time() - start
        check("语速合成成功", r.status_code == 200, f"got {r.status_code}")
        print(f"  音频大小: {len(r.content) / 1024:.1f} KB")
        print(f"  耗时: {elapsed:.2f}s")
    except Exception as e:
        check("语速测试", False, str(e))

    # -----------------------------------------------------------------------
    print("\n=== 7. 错误情况测试 ===")

    # 空文本
    try:
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": ""},
            timeout=10,
        )
        check("空文本返回 400", r.status_code == 400, f"got {r.status_code}")
    except Exception as e:
        check("空文本测试", False, str(e))

    # 超长文本
    try:
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": "测" * 1000},
            timeout=10,
        )
        check("超长文本返回 400", r.status_code == 400, f"got {r.status_code}")
    except Exception as e:
        check("超长文本测试", False, str(e))

    # 非法语速
    try:
        r = requests.post(
            f"{base_url}/v1/tts/synthesize",
            json={"text": "测试", "speed": 5.0},
            timeout=10,
        )
        check("非法语速返回 422", r.status_code == 422, f"got {r.status_code}")
    except Exception as e:
        check("非法语速测试", False, str(e))

    # -----------------------------------------------------------------------
    print(f"\n{'='*40}")
    print(f"测试完成: {passed}/{total} 通过, {failed} 失败")
    print(f"{'='*40}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS API 测试脚本")
    parser.add_argument(
        "--base-url",
        default="http://localhost:9880",
        help="TTS 服务地址 (默认 http://localhost:9880)",
    )
    args = parser.parse_args()
    print(f"测试目标: {args.base_url}")
    run_tests(args.base_url)
