"""
护士/医生 Agent 流式 Benchmark (云端无thinking vs 本地)
======================================================
- 云端禁用 thinking (enable_thinking=false)
- 统一流式调用，测量 TTFT / 总延迟 / 文本吞吐
- 记录原始日志

用法: python scripts/benchmark_agent_streaming.py
"""

import asyncio
import json
import os
import time
import httpx
from datetime import datetime
from pathlib import Path

CLOUD_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CLOUD_API_KEY = os.getenv("LLM_API_KEY", "")
CLOUD_MODEL = "qwen3.6-35b-a3b"

LOCAL_BASE_URL = "http://localhost:8080/v1"
LOCAL_API_KEY = "not-needed"
LOCAL_MODEL = "qwen3.6-35b-q8-vl"

TEMPERATURE = 0.3
LOG_DIR = Path(__file__).parent.parent.parent / "docs" / "benchmark_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── 测试用例 ────────────────────────────────────────────

NURSE_SYSTEM = """你是小护，一位专业产科护士AI助手。
你的职责：分析孕妇健康数据、SOAP格式记录、生成随访计划、异常上报。
可用工具：query_patient_data, analyze_health_trends, search_knowledge, create_followup_record, report_issue_to_doctor, check_emergency"""

DOCTOR_SYSTEM = """你是智医生，一位资深产科医生AI助手。
你的职责：综合评估、鉴别诊断、生成医嘱、处理异常。
可用工具：analyze_patient_comprehensive, query_patient_data, query_clinical_guideline, generate_medical_order, handle_issue"""

TEST_CASES = [
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-血压异常分析",
        "user": "请分析孕妇张某（ID: P20240032）最近一周的血压数据，她孕32周，血压记录：130/85, 132/87, 135/90, 138/92。需要判断是否有子痫前期风险。",
    },
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-随访计划生成",
        "user": "孕妇李某（ID: P20240045）孕28周，GDM确诊，空腹血糖5.8mmol/L，餐后2h血糖8.2mmol/L。请制定本周随访计划。",
    },
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-紧急情况上报",
        "user": "孕妇王某（ID: P20240018）孕36周，胎动明显减少（过去2小时只有1次），之前每天约10次。请立即评估。",
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-鉴别诊断",
        "user": "孕妇李某，28岁，初产妇，孕34周。主诉：头痛2天，视物模糊1天。查体：BP 155/100mmHg，双下肢水肿++。尿蛋白++。请给出鉴别诊断。",
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-异常处理",
        "user": "护士报告：孕妇王某孕36周，胎动明显减少（2小时内仅1次），无腹痛无出血。既往产检正常。请评估并给出处理方案。",
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-医嘱生成",
        "user": "孕妇赵某孕30周，GDM，饮食控制血糖不达标（空腹5.9, 餐后2h 9.1）。请评估是否需要胰岛素治疗并生成医嘱。",
    },
]

REPEATS = 3
WARMUP_RUNS = 1


async def stream_call(base_url: str, api_key: str, model: str,
                      system: str, user: str, backend: str,
                      disable_thinking: bool, all_logs: list) -> dict:
    """流式调用，测量 TTFT / 总延迟 / 文本吞吐"""
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "stream": True,
    }
    if disable_thinking:
        payload["enable_thinking"] = False

    t_start = time.perf_counter()
    ttft = None
    text_content = ""
    thinking_content = ""
    text_chunk_count = 0
    thinking_chunk_count = 0
    in_thinking = False
    current_field = None  # track which field we're receiving

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"HTTP {resp.status_code}: {body[:500]}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})

                    # 检测 thinking 和 content
                    rc = delta.get("reasoning_content")
                    ct = delta.get("content")

                    if rc:
                        if not in_thinking:
                            in_thinking = True
                        thinking_content += rc
                        thinking_chunk_count += 1
                        if ttft is None:
                            ttft = time.perf_counter() - t_start

                    if ct:
                        if in_thinking:
                            in_thinking = False
                        if ttft is None:
                            ttft = time.perf_counter() - t_start
                        text_content += ct
                        text_chunk_count += 1

                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    t_end = time.perf_counter()
    total_time = t_end - t_start

    # 用非流式获取真实 token 数
    usage = await get_usage(base_url, api_key, model, system, user, disable_thinking)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    details = usage.get("completion_tokens_details", {})
    reasoning_tokens = details.get("reasoning_tokens", 0)
    text_tokens = completion_tokens - reasoning_tokens

    result = {
        "backend": backend,
        "latency": round(total_time, 4),
        "ttft": round(ttft, 4) if ttft else round(total_time, 4),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "text_tokens": max(text_tokens, 0),
        "text_content_len": len(text_content),
        "thinking_content_len": len(thinking_content),
        "has_thinking": bool(thinking_content),
        "text_chunk_count": text_chunk_count,
        "thinking_chunk_count": thinking_chunk_count,
        "text_tok_per_sec": round(max(text_tokens, 0) / total_time, 2) if total_time > 0 else 0,
    }

    # 检测工具调用
    tool_keywords = ["query_patient_data", "analyze_health_trends", "search_knowledge",
                     "create_followup_record", "report_issue_to_doctor", "check_emergency",
                     "analyze_patient_comprehensive", "query_clinical_guideline",
                     "generate_medical_order", "handle_issue"]
    result["mentioned_tools"] = [t for t in tool_keywords if t in text_content]

    all_logs.append({
        "timestamp": datetime.now().isoformat(),
        "backend": backend,
        "request_payload": payload,
        "response_headers": dict(resp.headers) if hasattr(resp, 'headers') else {},
        "result": result,
        "text_preview": text_content[:500],
        "thinking_preview": thinking_content[:500],
    })

    return result


async def get_usage(base_url: str, api_key: str, model: str,
                    system: str, user: str, disable_thinking: bool) -> dict:
    """非流式调用获取真实 token usage"""
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
    if disable_thinking:
        payload["enable_thinking"] = False

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                return r.json().get("usage", {})
    except Exception:
        pass
    return {}


async def run_all(all_logs: list) -> dict:
    """运行所有测试用例，返回 {case_name: {cloud: result, local: result}}"""
    import numpy as np
    results = {}

    for tc in TEST_CASES:
        name = tc["name"]
        results[name] = {}
        print(f"\n  {name}")

        backends = [
            ("cloud", CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, True),
            ("local", LOCAL_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL, False),
        ]

        for backend, base_url, api_key, model, disable_thinking in backends:
            tag = "☁️ 云端" if backend == "cloud" else "🖥️ 本地"
            print(f"    {tag} ", end="", flush=True)

            # Warmup
            for _ in range(WARMUP_RUNS):
                try:
                    await stream_call(base_url, api_key, model,
                                      tc["system"], tc["user"], backend,
                                      disable_thinking, all_logs)
                except:
                    pass

            # Repeated runs
            runs = []
            for _ in range(REPEATS):
                try:
                    r = await stream_call(base_url, api_key, model,
                                          tc["system"], tc["user"], backend,
                                          disable_thinking, all_logs)
                    runs.append(r)
                except Exception as e:
                    print(f"    {tag} ERROR: {e}")

            if runs:
                agg = runs[0].copy()
                agg["latency"] = round(np.mean([r["latency"] for r in runs]), 4)
                agg["ttft"] = round(np.mean([r["ttft"] for r in runs]), 4)
                agg["text_tok_per_sec"] = round(np.mean([r["text_tok_per_sec"] for r in runs]), 2)
                agg["latency_range"] = f"{min(r['latency'] for r in runs):.2f}-{max(r['latency'] for r in runs):.2f}"
                agg["runs"] = len(runs)
                results[name][backend] = agg
                print(f"    {tag} avg:{agg['latency']:.1f}s range:{agg['latency_range']}s ({agg['runs']}runs)")
            else:
                results[name][backend] = {"error": "all runs failed"}

    return results


def format_report(results: dict) -> str:
    lines = []
    lines.append("# 护士/医生 Agent 流式对比报告\n")
    lines.append(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**云端**: {CLOUD_MODEL} (DashScope, **thinking 已禁用**, 流式)")
    lines.append(f"**本地**: {LOCAL_MODEL} (llama-server, reasoning off, 流式)")
    lines.append(f"**配置**: temperature={TEMPERATURE}, 无max_tokens限制\n")
    lines.append(f"**日志**: `docs/benchmark_logs/agent_stream_benchmark_log.json`\n")

    lines.append("## 逐场景对比\n")
    lines.append("| 场景 | 部署 | TTFT(s) | 总延迟(s) | 文本tokens | 文本吞吐(tok/s) | thinking |")
    lines.append("|------|------|---------|-----------|------------|-----------------|----------|")

    cloud_lat, cloud_tps, cloud_ttft, cloud_tok = [], [], [], []
    local_lat, local_tps, local_ttft, local_tok = [], [], [], []

    for name, pair in results.items():
        for backend, tag, lat_l, tps_l, ttft_l, tok_l in [
            ("cloud", "☁️", cloud_lat, cloud_tps, cloud_ttft, cloud_tok),
            ("local", "🖥️", local_lat, local_tps, local_ttft, local_tok),
        ]:
            r = pair.get(backend, {})
            if "error" in r:
                lines.append(f"| {name} | {tag} | ERROR | ERROR | ERROR | ERROR | - |")
                continue
            lat_l.append(r["latency"])
            tps_l.append(r["text_tok_per_sec"])
            ttft_l.append(r["ttft"])
            tok_l.append(r["text_tokens"])
            think = f"{r['reasoning_tokens']}tok" if r.get("has_thinking") else "-"
            lines.append(f"| {name} | {tag} | {r['ttft']:.2f} | {r['latency']:.1f} | {r['text_tokens']} | {r['text_tok_per_sec']:.1f} | {think} |")

    # 总体
    lines.append("")
    lines.append("## 总体对比\n")
    lines.append("| 指标 | ☁️ 云端 (无thinking) | 🖥️ 本地 | 对比 |")
    lines.append("|------|---------------------|---------|------|")

    def row(label, cv, lv, unit="", higher_better=False):
        if not cv or not lv:
            return f"| {label} | - | - | - |"
        c, l = sum(cv)/len(cv), sum(lv)/len(lv)
        ratio = l / c if c > 0 else 0
        if higher_better:
            arrow = "🟢 本地更优" if l > c else "🔴 云端更优"
        else:
            arrow = "🟢 本地更优" if l < c else "🔴 云端更优"
        return f"| {label} | {c:.2f}{unit} | {l:.2f}{unit} | {arrow} ({ratio:.2f}x) |"

    lines.append(row("TTFT", cloud_ttft, local_ttft, "s"))
    lines.append(row("总延迟", cloud_lat, local_lat, "s"))
    lines.append(row("文本吞吐", cloud_tps, local_tps, " tok/s", higher_better=True))
    lines.append(row("文本输出", cloud_tok, local_tok, " tok", higher_better=True))

    lines.append("")
    lines.append("## 结论\n")
    if cloud_lat and local_lat:
        c_lat = sum(cloud_lat)/len(cloud_lat)
        l_lat = sum(local_lat)/len(local_lat)
        c_tps = sum(cloud_tps)/len(cloud_tps)
        l_tps = sum(local_tps)/len(local_tps)
        c_ttft = sum(cloud_ttft)/len(cloud_ttft)
        l_ttft = sum(local_ttft)/len(local_ttft)
        c_tok = sum(cloud_tok)/len(cloud_tok)
        l_tok = sum(local_tok)/len(local_tok)

        lines.append(f"1. **TTFT**: 云端 {c_ttft:.2f}s vs 本地 {l_ttft:.2f}s")
        lines.append(f"2. **总延迟**: 云端 {c_lat:.1f}s vs 本地 {l_lat:.1f}s")
        lines.append(f"3. **文本吞吐**: 云端 {c_tps:.1f} tok/s vs 本地 {l_tps:.1f} tok/s")
        lines.append(f"4. **文本输出**: 云端平均 {c_tok:.0f} tok vs 本地平均 {l_tok:.0f} tok")
        lines.append(f"5. **隐私**: 本地数据不出端，满足医疗合规")

    return "\n".join(lines)


async def main():
    all_logs = []

    print("=" * 60)
    print("  Agent 流式 Benchmark (云端无thinking vs 本地)")
    print("=" * 60)

    print("\n[1/2] 检查服务...")
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

    print(f"\n[2/2] 运行测试...")
    results = await run_all(all_logs)

    # 保存日志
    log_path = LOG_DIR / "agent_stream_benchmark_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "benchmark_time": datetime.now().isoformat(),
            "config": {"cloud_model": CLOUD_MODEL, "local_model": LOCAL_MODEL,
                       "cloud_thinking": "disabled", "local_reasoning": "off",
                       "stream": True, "temperature": TEMPERATURE},
            "total_calls": len(all_logs),
            "calls": all_logs,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  日志: {log_path}")

    report = format_report(results)
    report_path = LOG_DIR.parent / "agent_benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告: {report_path}")
    print(f"\n{'=' * 60}")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
