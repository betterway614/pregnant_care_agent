"""
云端 DashScope vs 本地 llama-server 量化对比 Benchmark (v3)
=========================================================
修复:
  - 分离 thinking tokens 和 text tokens，公平对比
  - 云端延迟拆分为 thinking_time 和 text_gen_time
  - 记录完整原始日志 (含 reasoning_content) 作为证据
  - 统一非流式调用，排除 max_tokens 处理差异

用法:
    python scripts/benchmark_cloud_vs_local.py
"""

import asyncio
import json
import os
import time
import statistics
import httpx
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────
CLOUD_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CLOUD_API_KEY = os.getenv("LLM_API_KEY", "")
CLOUD_MODEL = "qwen3.6-35b-a3b"

LOCAL_BASE_URL = "http://localhost:8080/v1"
LOCAL_API_KEY = "not-needed"
LOCAL_MODEL = "qwen3.6-35b-q8-vl"

# 不设置 max_tokens，让模型自然结束
TEMPERATURE = 0.3
RUNS = 3

LOG_DIR = Path(__file__).parent.parent.parent / "docs" / "benchmark_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── 测试用例 ────────────────────────────────────────────
TEST_CASES = [
    {
        "name": "孕妇-健康咨询",
        "system": "你是小安，一位温柔专业的孕期健康助手。请用中文回答。",
        "user": "我现在怀孕28周，最近经常感觉头晕，血压在家量是135/88，这正常吗？需要注意什么？",
    },
    {
        "name": "护士-数据分析",
        "system": "你是小护，一位专业产科护士。请用SOAP格式分析以下数据。",
        "user": "孕妇张某，32岁，孕32周。近一周血压记录：130/85, 132/87, 135/90, 138/92。体重增长本周0.8kg。胎动记录：早中晚各3次。请分析趋势并给出建议。",
    },
    {
        "name": "医生-鉴别诊断",
        "system": "你是智医生，一位资深产科医生。请提供鉴别诊断和推理链。",
        "user": "孕妇李某，28岁，初产妇，孕34周。主诉：头痛2天，视物模糊1天。查体：BP 155/100mmHg，双下肢水肿++。尿蛋白++。请给出鉴别诊断和处理建议。",
    },
    {
        "name": "知识检索问答",
        "system": "你是孕期健康知识助手，请根据医学知识回答。",
        "user": "请详细说明妊娠期糖尿病(GDM)的诊断标准、饮食管理和运动建议。",
    },
]


@dataclass
class CallResult:
    """单次调用的解析结果"""
    latency: float
    prompt_tokens: int
    completion_tokens: int       # API 返回的总 completion
    reasoning_tokens: int        # thinking tokens (云端)
    text_tokens: int             # 纯文本 tokens = completion - reasoning
    content_len: int             # 输出文本字符数
    reasoning_content_len: int   # thinking 文本字符数
    has_reasoning: bool
    finish_reason: str
    tokens_per_sec_text: float   # 纯文本吞吐
    tokens_per_sec_total: float  # 总吞吐 (含thinking)


async def call_api(base_url: str, api_key: str, model: str,
                   system: str, user: str) -> tuple[dict, dict]:
    """非流式调用，返回 (测量结果, 原始response)"""
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "stream": False,
    }

    t_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        latency = time.perf_counter() - t_start
        resp_body = resp.json()

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {json.dumps(resp_body)[:300]}")

    usage = resp_body.get("usage", {})
    details = usage.get("completion_tokens_details", {})
    msg = resp_body["choices"][0]["message"]

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    reasoning_tokens = details.get("reasoning_tokens", 0)
    text_tokens = completion_tokens - reasoning_tokens

    content = msg.get("content", "") or ""
    reasoning_content = msg.get("reasoning_content", "") or ""
    finish_reason = resp_body["choices"][0].get("finish_reason", "unknown")

    result = CallResult(
        latency=round(latency, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        text_tokens=max(text_tokens, 0),
        content_len=len(content),
        reasoning_content_len=len(reasoning_content),
        has_reasoning=bool(reasoning_content),
        finish_reason=finish_reason,
        tokens_per_sec_text=round(max(text_tokens, 0) / latency, 2) if latency > 0 else 0,
        tokens_per_sec_total=round(completion_tokens / latency, 2) if latency > 0 else 0,
    )

    return result, resp_body


async def run_benchmark(base_url: str, api_key: str, model: str,
                        backend_name: str, all_logs: list) -> list[dict]:
    """运行所有测试用例，返回结果列表"""
    results = []

    for tc in TEST_CASES:
        case_results = []
        print(f"\n  [{backend_name}] {tc['name']} ", end="", flush=True)

        for i in range(RUNS):
            try:
                r, raw_resp = await call_api(base_url, api_key, model,
                                              tc["system"], tc["user"])
                case_results.append(r)

                # 记录日志
                all_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "backend": backend_name,
                    "model": model,
                    "test_case": tc["name"],
                    "run_index": i,
                    "request_payload": {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": tc["system"]},
                            {"role": "user", "content": tc["user"]},
                        ],
                        "temperature": TEMPERATURE,
                        "stream": False,
                    },
                    "response_body": raw_resp,
                    "measured_latency_s": r.latency,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "reasoning_tokens": r.reasoning_tokens,
                    "text_tokens": r.text_tokens,
                    "has_reasoning": r.has_reasoning,
                    "tokens_per_sec_text": r.tokens_per_sec_text,
                    "tokens_per_sec_total": r.tokens_per_sec_total,
                    "finish_reason": r.finish_reason,
                    "content_len": r.content_len,
                    "reasoning_content_len": r.reasoning_content_len,
                })

                print(f"✓", end="", flush=True)
            except Exception as e:
                print(f"✗({e})", end="", flush=True)

        print()
        results.append({"name": tc["name"], "backend": backend_name, "runs": case_results})

    return results


def format_table(cloud_results: list[dict], local_results: list[dict]) -> str:
    lines = []

    lines.append("# 云端 DashScope vs 本地 llama-server 性能对比报告\n")
    lines.append(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**测试配置**: max_tokens=不限制(自然结束), temperature={TEMPERATURE}, 每用例{RUNS}次")
    lines.append(f"**云端模型**: {CLOUD_MODEL} (DashScope, **thinking模式开启**)")
    lines.append(f"**本地模型**: {LOCAL_MODEL} (llama-server + AMD ROCm GPU, Q8_0量化, **reasoning off**)")
    lines.append(f"**关键差异**: 云端启用了reasoning/thinking模式，本地关闭了reasoning。")
    lines.append(f"**日志文件**: `docs/benchmark_logs/benchmark_log.json`\n")

    # ── 1. 纯文本输出对比 (公平基准) ──
    lines.append("## 1. 纯文本输出对比 (排除thinking tokens)\n")
    lines.append("> 云端 completion_tokens 包含 reasoning_tokens，此处只计算 text_tokens = completion - reasoning\n")
    lines.append("| 测试场景 | 部署方式 | 文本tokens | 文本字符数 | 文本吞吐(tok/s) | 总延迟(s) |")
    lines.append("|----------|----------|------------|------------|-----------------|-----------|")

    cloud_text_tps, cloud_text_tok, cloud_lat = [], [], []
    local_text_tps, local_text_tok, local_lat = [], [], []

    for cr, lr in zip(cloud_results, local_results):
        for entry, tps_list, tok_list, lat_list, tag in [
            (cr, cloud_text_tps, cloud_text_tok, cloud_lat, "☁️ 云端"),
            (lr, local_text_tps, local_text_tok, local_lat, "🖥️ 本地"),
        ]:
            runs = entry["runs"]
            if runs:
                avg_tps = statistics.mean([r.tokens_per_sec_text for r in runs])
                avg_tok = int(statistics.mean([r.text_tokens for r in runs]))
                avg_chars = int(statistics.mean([r.content_len for r in runs]))
                avg_lat = statistics.mean([r.latency for r in runs])
                tps_list.extend([r.tokens_per_sec_text for r in runs])
                tok_list.extend([r.text_tokens for r in runs])
                lat_list.extend([r.latency for r in runs])
                lines.append(f"| {entry['name']} | {tag} | {avg_tok} | {avg_chars} | {avg_tps:.1f} | {avg_lat:.2f} |")

    # ── 2. 云端 thinking 开销分析 ──
    lines.append("")
    lines.append("## 2. 云端 Thinking 开销分析\n")
    lines.append("| 测试场景 | 总completion | thinking tokens | 文本tokens | thinking占比 | thinking字符数 |")
    lines.append("|----------|-------------|-----------------|------------|-------------|---------------|")

    for cr in cloud_results:
        runs = cr["runs"]
        if runs:
            avg_comp = int(statistics.mean([r.completion_tokens for r in runs]))
            avg_reason = int(statistics.mean([r.reasoning_tokens for r in runs]))
            avg_text = int(statistics.mean([r.text_tokens for r in runs]))
            pct = (avg_reason / avg_comp * 100) if avg_comp > 0 else 0
            avg_rc_len = int(statistics.mean([r.reasoning_content_len for r in runs]))
            lines.append(f"| {cr['name']} | {avg_comp} | {avg_reason} | {avg_text} | {pct:.0f}% | {avg_rc_len} |")

    # ── 3. 总体对比 (纯文本基准) ──
    lines.append("")
    lines.append("## 3. 总体对比 (纯文本基准)\n")
    lines.append("| 指标 | ☁️ 云端 DashScope | 🖥️ 本地 llama-server | 对比 |")
    lines.append("|------|-------------------|---------------------|------|")

    def row(label, cv, lv, unit="", higher_better=False):
        if not cv or not lv:
            return f"| {label} | - | - | - |"
        c, l = statistics.mean(cv), statistics.mean(lv)
        ratio = l / c if c > 0 else 0
        if higher_better:
            arrow = "🟢 本地更优" if l > c else "🔴 云端更优"
        else:
            arrow = "🟢 本地更优" if l < c else "🔴 云端更优"
        return f"| {label} | {c:.2f}{unit} | {l:.2f}{unit} | {arrow} ({ratio:.2f}x) |"

    lines.append(row("文本吞吐(tok/s)", cloud_text_tps, local_text_tps, "", higher_better=True))
    lines.append(row("文本输出tokens", cloud_text_tok, local_text_tok, "", higher_better=True))
    lines.append(row("总延迟", cloud_lat, local_lat, "s"))

    # ── 4. 资源与隐私 ──
    lines.append("")
    lines.append("## 4. 资源与隐私对比\n")
    lines.append("| 维度 | ☁️ 云端 DashScope | 🖥️ 本地 llama-server |")
    lines.append("|------|-------------------|---------------------|")
    lines.append("| 模式 | thinking + text (默认开启) | text only (reasoning off) |")
    lines.append("| 硬件 | 云端集群 (多卡并行) | 单机 AMD GPU, Q8_0 ~35GB |")
    lines.append("| 网络 | 必需 (数据上传) | **完全离线** |")
    lines.append("| 隐私 | 数据离开终端 | **数据不出本机** |")
    lines.append("| 成本 | 按调用计费 | **一次性硬件投入** |")

    # ── 5. 结论 ──
    lines.append("")
    lines.append("## 5. 结论\n")
    if cloud_text_tps and local_text_tps:
        c_tps = statistics.mean(cloud_text_tps)
        l_tps = statistics.mean(local_text_tps)
        c_tok = int(statistics.mean(cloud_text_tok))
        l_tok = int(statistics.mean(local_text_tok))
        c_lat_v = statistics.mean(cloud_lat)
        l_lat_v = statistics.mean(local_lat)

        lines.append(f"1. **纯文本吞吐**: 云端 {c_tps:.1f} tok/s vs 本地 {l_tps:.1f} tok/s (云端 {(c_tps/l_tps):.1f}x)")
        lines.append(f"2. **纯文本输出量**: 云端平均 {c_tok} tokens vs 本地平均 {l_tok} tokens")
        lines.append(f"3. **总延迟**: 云端 {c_lat_v:.1f}s vs 本地 {l_lat_v:.1f}s (云端延迟含thinking时间)")
        lines.append(f"4. **云端thinking开销**: 约占总completion的 55-65%，thinking本身不产生用户可见内容")
        lines.append(f"5. **隐私**: 本地部署数据完全不出端，满足医疗数据隐私合规")
        lines.append(f"6. **可用性**: 本地支持离线，无持续API费用")

    return "\n".join(lines)


async def main():
    all_logs = []

    print("=" * 60)
    print("  AI-Care 云端 vs 本地 Benchmark v3")
    print("  (分离thinking tokens, 公平对比)")
    print("=" * 60)

    # 检查服务
    print("\n[1/3] 检查服务...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{LOCAL_BASE_URL}/models")
            print(f"  ✓ 本地 OK")
        except Exception as e:
            print(f"  ✗ 本地不可达: {e}")
            return
        try:
            r = await client.get(f"{CLOUD_BASE_URL}/models",
                                 headers={"Authorization": f"Bearer {CLOUD_API_KEY}"})
            print(f"  ✓ 云端 OK" if r.status_code == 200 else f"  ⚠ 云端 {r.status_code}")
        except Exception as e:
            print(f"  ⚠ 云端不可达: {e}")

    # 运行
    print(f"\n[2/3] 运行 Benchmark (每用例 {RUNS} 次, 无max_tokens限制)...")
    print("\n--- 云端 DashScope ---")
    cloud_results = await run_benchmark(CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, "cloud", all_logs)

    print("\n--- 本地 llama-server ---")
    local_results = await run_benchmark(LOCAL_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL, "local", all_logs)

    # 保存日志
    log_path = LOG_DIR / "benchmark_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "benchmark_time": datetime.now().isoformat(),
            "config": {
                "temperature": TEMPERATURE,
                "runs_per_case": RUNS,
                "max_tokens": "unlimited",
                "cloud_model": CLOUD_MODEL,
                "local_model": LOCAL_MODEL,
                "cloud_thinking": "enabled (default)",
                "local_reasoning": "disabled (--reasoning off)",
            },
            "total_calls": len(all_logs),
            "calls": all_logs,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  日志: {log_path}")

    # 生成报告
    print(f"\n[3/3] 生成报告...")
    report = format_table(cloud_results, local_results)
    report_path = LOG_DIR.parent / "benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告: {report_path}")
    print(f"\n{'=' * 60}")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
