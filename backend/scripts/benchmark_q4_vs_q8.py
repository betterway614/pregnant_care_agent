"""
Q4 vs Q8 vs BF16 三模型对比 Benchmark
======================================
串行测试三种量化方案的智能体响应速率、工具使用率、输出质量。

用法:
    # 测试当前在线的后端 (自动检测)
    python scripts/benchmark_q4_vs_q8.py

    # 指定后端测试
    python scripts/benchmark_q4_vs_q8.py --backend q4
    python scripts/benchmark_q4_vs_q8.py --backend q8
    python scripts/benchmark_q4_vs_q8.py --backend bf16

    # 只运行某个模块
    python scripts/benchmark_q4_vs_q8.py --backend q4 --module basic
    python scripts/benchmark_q4_vs_q8.py --backend q4 --module agent
    python scripts/benchmark_q4_vs_q8.py --backend q4 --module streaming

    # 合并已有日志生成报告
    python scripts/benchmark_q4_vs_q8.py --report
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import httpx

# ─── 后端配置 ────────────────────────────────────────────

BACKENDS = {
    "q4": {
        "base_url": "http://localhost:8080/v1",
        "api_key": "not-needed",
        "model": "qwen3.6-35b-q4-vl",
        "engine": "llama.cpp",
        "quantization": "Q4_K_M",
        "model_size": "21GB",
    },
    "q8": {
        "base_url": "http://localhost:8080/v1",
        "api_key": "not-needed",
        "model": "qwen3.6-35b-q8-vl",
        "engine": "llama.cpp",
        "quantization": "Q8_0",
        "model_size": "35GB",
    },
    "bf16": {
        "base_url": "http://localhost:8000/v1",
        "api_key": "EMPTY",
        "model": "qwen3.6-35b-a3b",
        "engine": "vLLM ROCm",
        "quantization": "BF16",
        "model_size": "67GB",
    },
}

TEMPERATURE = 0.3
RUNS = 3
WARMUP_RUNS = 1

LOG_DIR = Path(__file__).parent.parent.parent / "docs" / "benchmark_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── 通用测试场景 (模块A) ─────────────────────────────────

GENERAL_CASES = [
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

# ─── Agent 测试场景 (模块B/C) ─────────────────────────────

NURSE_SYSTEM = """你是小护，一位专业产科护士AI助手。
你的职责：分析孕妇健康数据、SOAP格式记录、生成随访计划、异常上报。
可用工具：query_patient_data, analyze_health_trends, search_knowledge, create_followup_record, report_issue_to_doctor, check_emergency"""

DOCTOR_SYSTEM = """你是智医生，一位资深产科医生AI助手。
你的职责：综合评估、鉴别诊断、生成医嘱、处理异常。
可用工具：analyze_patient_comprehensive, query_patient_data, query_clinical_guideline, generate_medical_order, handle_issue"""

AGENT_CASES = [
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-血压异常分析",
        "user": "请分析孕妇张某（ID: P20240032）最近一周的血压数据，她孕32周，血压记录：130/85, 132/87, 135/90, 138/92。需要判断是否有子痫前期风险。",
        "expected_tools": ["query_patient_data", "analyze_health_trends", "search_knowledge"],
    },
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-随访计划生成",
        "user": "孕妇李某（ID: P20240045）孕28周，GDM确诊，空腹血糖5.8mmol/L，餐后2h血糖8.2mmol/L。请制定本周随访计划。",
        "expected_tools": ["query_patient_data", "search_knowledge", "create_followup_record"],
    },
    {
        "role": "nurse", "system": NURSE_SYSTEM,
        "name": "护士-紧急情况上报",
        "user": "孕妇王某（ID: P20240018）孕36周，胎动明显减少（过去2小时只有1次），之前每天约10次。请立即评估。",
        "expected_tools": ["query_patient_data", "check_emergency", "report_issue_to_doctor"],
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-鉴别诊断",
        "user": "孕妇李某，28岁，初产妇，孕34周。主诉：头痛2天，视物模糊1天。查体：BP 155/100mmHg，双下肢水肿++。尿蛋白++。请给出鉴别诊断。",
        "expected_tools": ["analyze_patient_comprehensive", "query_clinical_guideline"],
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-异常处理",
        "user": "护士报告：孕妇王某孕36周，胎动明显减少（2小时内仅1次），无腹痛无出血。既往产检正常。请评估并给出处理方案。",
        "expected_tools": ["query_patient_data", "handle_issue", "query_clinical_guideline"],
    },
    {
        "role": "doctor", "system": DOCTOR_SYSTEM,
        "name": "医生-医嘱生成",
        "user": "孕妇赵某孕30周，GDM，饮食控制血糖不达标（空腹5.9, 餐后2h 9.1）。请评估是否需要胰岛素治疗并生成医嘱。",
        "expected_tools": ["analyze_patient_comprehensive", "query_clinical_guideline", "generate_medical_order"],
    },
]

TOOL_KEYWORDS = [
    "query_patient_data", "analyze_health_trends", "search_knowledge",
    "create_followup_record", "report_issue_to_doctor", "check_emergency",
    "analyze_patient_comprehensive", "query_clinical_guideline",
    "generate_medical_order", "handle_issue",
]


# ─── 数据结构 ─────────────────────────────────────────────

@dataclass
class CallResult:
    latency: float = 0
    ttft: float = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    text_tokens: int = 0
    content_len: int = 0
    content_preview: str = ""
    mentioned_tools: list = field(default_factory=list)
    expected_tools: list = field(default_factory=list)
    tool_match: bool = False
    finish_reason: str = ""
    tokens_per_sec: float = 0


# ─── API 调用 ─────────────────────────────────────────────

async def call_non_stream(base_url: str, api_key: str, model: str,
                          system: str, user: str) -> tuple[CallResult, dict]:
    """非流式调用"""
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
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
    content = msg.get("content", "") or ""
    reasoning_content = msg.get("reasoning_content", "") or ""

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    reasoning_tokens = details.get("reasoning_tokens", 0)
    text_tokens = completion_tokens - reasoning_tokens

    mentioned = [t for t in TOOL_KEYWORDS if t in content]

    result = CallResult(
        latency=round(latency, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        text_tokens=max(text_tokens, 0),
        content_len=len(content),
        content_preview=content[:300],
        mentioned_tools=mentioned,
        finish_reason=resp_body["choices"][0].get("finish_reason", "unknown"),
        tokens_per_sec=round(max(text_tokens, 0) / latency, 2) if latency > 0 else 0,
    )

    return result, resp_body


async def call_stream(base_url: str, api_key: str, model: str,
                      system: str, user: str) -> tuple[CallResult, dict]:
    """流式调用，测量 TTFT"""
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "stream": True,
    }

    t_start = time.perf_counter()
    ttft = None
    text_content = ""

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
                    ct = delta.get("content")
                    if ct:
                        if ttft is None:
                            ttft = time.perf_counter() - t_start
                        text_content += ct
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    total_time = time.perf_counter() - t_start

    # 非流式获取真实 token 数
    usage = await _get_usage(base_url, api_key, model, system, user)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    details = usage.get("completion_tokens_details", {})
    reasoning_tokens = details.get("reasoning_tokens", 0)
    text_tokens = completion_tokens - reasoning_tokens

    mentioned = [t for t in TOOL_KEYWORDS if t in text_content]

    result = CallResult(
        latency=round(total_time, 4),
        ttft=round(ttft, 4) if ttft else round(total_time, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        text_tokens=max(text_tokens, 0),
        content_len=len(text_content),
        content_preview=text_content[:300],
        mentioned_tools=mentioned,
        tokens_per_sec=round(max(text_tokens, 0) / total_time, 2) if total_time > 0 else 0,
    )

    return result, {"text_preview": text_content[:500]}


async def _get_usage(base_url: str, api_key: str, model: str,
                     system: str, user: str) -> dict:
    """非流式调用获取 token usage"""
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": TEMPERATURE,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                return r.json().get("usage", {})
    except Exception:
        pass
    return {}


# ─── 模块A: 非流式基础性能 ────────────────────────────────

async def run_basic(backend_name: str, all_logs: list) -> list[dict]:
    """4个通用场景 x RUNS 次"""
    cfg = BACKENDS[backend_name]
    results = []

    for tc in GENERAL_CASES:
        case_runs = []
        print(f"  [{backend_name}] {tc['name']} ", end="", flush=True)

        for i in range(RUNS):
            try:
                r, raw = await call_non_stream(
                    cfg["base_url"], cfg["api_key"], cfg["model"],
                    tc["system"], tc["user"])
                case_runs.append(r)
                all_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "backend": backend_name,
                    "module": "basic",
                    "test_case": tc["name"],
                    "run_index": i,
                    "result": asdict(r),
                    "response_body": raw,
                })
                print("✓", end="", flush=True)
            except Exception as e:
                print(f"✗({e})", end="", flush=True)

        print()
        if case_runs:
            avg_tps = statistics.mean([r.tokens_per_sec for r in case_runs])
            avg_lat = statistics.mean([r.latency for r in case_runs])
            avg_tok = int(statistics.mean([r.text_tokens for r in case_runs]))
            results.append({
                "name": tc["name"],
                "backend": backend_name,
                "avg_latency": round(avg_lat, 2),
                "avg_text_tokens": avg_tok,
                "avg_tok_per_sec": round(avg_tps, 1),
                "runs": len(case_runs),
            })

    return results


# ─── 模块B: Agent工具调用能力 ──────────────────────────────

async def run_agent(backend_name: str, all_logs: list) -> list[dict]:
    """6个Agent场景 x RUNS 次"""
    cfg = BACKENDS[backend_name]
    results = []

    for tc in AGENT_CASES:
        case_runs = []
        print(f"  [{backend_name}] {tc['name']} ", end="", flush=True)

        for i in range(RUNS):
            try:
                r, raw = await call_non_stream(
                    cfg["base_url"], cfg["api_key"], cfg["model"],
                    tc["system"], tc["user"])
                r.expected_tools = tc.get("expected_tools", [])
                r.tool_match = all(t in r.mentioned_tools for t in r.expected_tools)
                case_runs.append(r)
                all_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "backend": backend_name,
                    "module": "agent",
                    "test_case": tc["name"],
                    "run_index": i,
                    "result": asdict(r),
                    "response_body": raw,
                })
                print("✓", end="", flush=True)
            except Exception as e:
                print(f"✗({e})", end="", flush=True)

        print()
        if case_runs:
            avg_lat = statistics.mean([r.latency for r in case_runs])
            avg_tps = statistics.mean([r.tokens_per_sec for r in case_runs])
            avg_tok = int(statistics.mean([r.text_tokens for r in case_runs]))
            tool_accuracy = sum(1 for r in case_runs if r.tool_match) / len(case_runs)
            all_mentioned = []
            for r in case_runs:
                all_mentioned.extend(r.mentioned_tools)
            tool_counts = {t: all_mentioned.count(t) for t in set(all_mentioned)}

            results.append({
                "name": tc["name"],
                "backend": backend_name,
                "role": tc["role"],
                "expected_tools": tc.get("expected_tools", []),
                "avg_latency": round(avg_lat, 2),
                "avg_text_tokens": avg_tok,
                "avg_tok_per_sec": round(avg_tps, 1),
                "tool_accuracy": round(tool_accuracy, 2),
                "tool_mentions": tool_counts,
                "runs": len(case_runs),
            })

    return results


# ─── 模块C: 流式响应 ──────────────────────────────────────

async def run_streaming(backend_name: str, all_logs: list) -> list[dict]:
    """6个Agent场景 x RUNS 次 + warmup"""
    cfg = BACKENDS[backend_name]
    results = []

    # Warmup
    print(f"  [{backend_name}] warmup ", end="", flush=True)
    for _ in range(WARMUP_RUNS):
        try:
            await call_stream(cfg["base_url"], cfg["api_key"], cfg["model"],
                              AGENT_CASES[0]["system"], AGENT_CASES[0]["user"])
            print("✓", end="", flush=True)
        except Exception as e:
            print(f"✗({e})", end="", flush=True)
    print()

    for tc in AGENT_CASES:
        case_runs = []
        print(f"  [{backend_name}] {tc['name']} ", end="", flush=True)

        for i in range(RUNS):
            try:
                r, extra = await call_stream(
                    cfg["base_url"], cfg["api_key"], cfg["model"],
                    tc["system"], tc["user"])
                r.expected_tools = tc.get("expected_tools", [])
                r.tool_match = all(t in r.mentioned_tools for t in r.expected_tools)
                case_runs.append(r)
                all_logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "backend": backend_name,
                    "module": "streaming",
                    "test_case": tc["name"],
                    "run_index": i,
                    "result": asdict(r),
                    **extra,
                })
                print("✓", end="", flush=True)
            except Exception as e:
                print(f"✗({e})", end="", flush=True)

        print()
        if case_runs:
            avg_lat = statistics.mean([r.latency for r in case_runs])
            avg_ttft = statistics.mean([r.ttft for r in case_runs])
            avg_tps = statistics.mean([r.tokens_per_sec for r in case_runs])
            avg_tok = int(statistics.mean([r.text_tokens for r in case_runs]))
            results.append({
                "name": tc["name"],
                "backend": backend_name,
                "avg_latency": round(avg_lat, 2),
                "avg_ttft": round(avg_ttft, 3),
                "avg_text_tokens": avg_tok,
                "avg_tok_per_sec": round(avg_tps, 1),
                "runs": len(case_runs),
            })

    return results


# ─── 报告生成 ─────────────────────────────────────────────

def load_all_logs() -> dict:
    """加载所有已有的日志文件"""
    logs = {}
    for key in ["q4", "q8", "bf16"]:
        log_path = LOG_DIR / f"{key}_benchmark_log.json"
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                logs[key] = json.load(f)
    return logs


def generate_report(logs: dict) -> str:
    """从日志生成对比报告"""
    lines = []
    lines.append("# Q4 vs Q8 vs BF16 满血 量化对比报告\n")
    lines.append(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**模型**: Qwen3.6-35B-A3B (MoE, 35B total / 3B active)")
    lines.append(f"**硬件**: AMD Strix Halo, 96GB VRAM")
    lines.append(f"**配置**: temperature={TEMPERATURE}, 每用例{RUNS}次, reasoning/thinking关闭\n")

    # 后端信息表
    lines.append("## 测试环境\n")
    lines.append("| 模型 | 精度 | 文件大小 | 引擎 | 端口 |")
    lines.append("|------|------|----------|------|------|")
    for key in ["q4", "q8", "bf16"]:
        if key in logs:
            cfg = BACKENDS[key]
            lines.append(f"| {cfg['model']} | {cfg['quantization']} | {cfg['model_size']} | {cfg['engine']} | {cfg['base_url'].split(':')[2].split('/')[0]} |")
    lines.append("")

    # 提取各模块数据
    basic_data = {}
    agent_data = {}
    stream_data = {}

    for key, log in logs.items():
        for call in log.get("calls", []):
            module = call.get("module", "unknown")
            tc_name = call.get("test_case", "")
            r = call.get("result", {})

            if module == "basic":
                basic_data.setdefault(key, {}).setdefault(tc_name, []).append(r)
            elif module == "agent":
                agent_data.setdefault(key, {}).setdefault(tc_name, []).append(r)
            elif module == "streaming":
                stream_data.setdefault(key, {}).setdefault(tc_name, []).append(r)

    # 模块A: 基础性能
    if basic_data:
        lines.append("## 1. 基础性能对比 (非流式)\n")
        lines.append("| 场景 | 指标 | " + " | ".join(BACKENDS[k]["quantization"] for k in basic_data) + " | 最优 |")
        lines.append("|------|------|" + "|".join("------" for _ in basic_data) + "|------|")

        all_cases = set()
        for d in basic_data.values():
            all_cases.update(d.keys())

        for case in sorted(all_cases):
            for metric, unit, higher_better in [
                ("latency", "s", False), ("text_tokens", "tok", True), ("tokens_per_sec", "tok/s", True)
            ]:
                vals = {}
                for key in basic_data:
                    runs = basic_data[key].get(case, [])
                    if runs:
                        vals[key] = statistics.mean([r.get(metric, 0) for r in runs])

                if vals:
                    best_key = max(vals, key=vals.get) if higher_better else min(vals, key=vals.get)
                    best_q = BACKENDS[best_key]["quantization"]
                    row = f"| {case} | {metric} |"
                    for key in basic_data:
                        v = vals.get(key, 0)
                        row += f" {v:.1f}{unit} |"
                    row += f" {best_q} |"
                    lines.append(row)
        lines.append("")

    # 模块B: Agent工具调用
    if agent_data:
        lines.append("## 2. Agent 工具调用对比\n")
        lines.append("| 场景 | 角色 | " + " | ".join(
            f"{BACKENDS[k]['quantization']}延迟 | {BACKENDS[k]['quantization']}工具准确率"
            for k in agent_data
        ) + " |")
        lines.append("|------|------|" + "|".join("------|------" for _ in agent_data) + "|")

        all_cases = set()
        for d in agent_data.values():
            all_cases.update(d.keys())

        for case in sorted(all_cases):
            row = f"| {case} |"
            role = ""
            for key in agent_data:
                runs = agent_data[key].get(case, [])
                if runs:
                    if not role:
                        role = runs[0].get("role", "")
            row += f" {role} |"

            for key in agent_data:
                runs = agent_data[key].get(case, [])
                if runs:
                    avg_lat = statistics.mean([r.get("latency", 0) for r in runs])
                    avg_acc = statistics.mean([r.get("tool_accuracy", 0) for r in runs])
                    row += f" {avg_lat:.1f}s | {avg_acc:.0%} |"
                else:
                    row += " - | - |"
            lines.append(row)

        # 工具调用详情
        lines.append("\n### 工具调用详情\n")
        for key in agent_data:
            q = BACKENDS[key]["quantization"]
            lines.append(f"**{q}**:")
            for case, runs in agent_data[key].items():
                if runs:
                    expected = runs[0].get("expected_tools", [])
                    mentioned = set()
                    for r in runs:
                        mentioned.update(r.get("mentioned_tools", []))
                    lines.append(f"- {case}: 期望={expected}, 实际提及={sorted(mentioned)}")
            lines.append("")

    # 模块C: 流式响应
    if stream_data:
        lines.append("## 3. 流式响应对比\n")
        lines.append("| 场景 | " + " | ".join(
            f"{BACKENDS[k]['quantization']} TTFT | {BACKENDS[k]['quantization']}延迟 | {BACKENDS[k]['quantization']}吞吐"
            for k in stream_data
        ) + " |")
        lines.append("|------|" + "|".join("------|------|------" for _ in stream_data) + "|")

        all_cases = set()
        for d in stream_data.values():
            all_cases.update(d.keys())

        for case in sorted(all_cases):
            row = f"| {case} |"
            for key in stream_data:
                runs = stream_data[key].get(case, [])
                if runs:
                    avg_ttft = statistics.mean([r.get("ttft", 0) for r in runs])
                    avg_lat = statistics.mean([r.get("latency", 0) for r in runs])
                    avg_tps = statistics.mean([r.get("tokens_per_sec", 0) for r in runs])
                    row += f" {avg_ttft:.2f}s | {avg_lat:.1f}s | {avg_tps:.1f}tok/s |"
                else:
                    row += " - | - | - |"
            lines.append(row)
        lines.append("")

    # 总体汇总
    lines.append("## 4. 综合汇总\n")
    for key in logs:
        q = BACKENDS[key]["quantization"]
        all_lats = []
        all_tps = []
        all_tkts = []

        for module_data in [basic_data.get(key, {}), agent_data.get(key, {}), stream_data.get(key, {})]:
            for case_runs in module_data.values():
                for r in case_runs:
                    if r.get("latency"):
                        all_lats.append(r["latency"])
                    if r.get("tokens_per_sec"):
                        all_tps.append(r["tokens_per_sec"])
                    if r.get("text_tokens"):
                        all_tkts.append(r["text_tokens"])

        if all_lats:
            lines.append(f"**{q}**:")
            lines.append(f"- 平均延迟: {statistics.mean(all_lats):.2f}s")
            if all_tps:
                lines.append(f"- 平均吞吐: {statistics.mean(all_tps):.1f} tok/s")
            if all_tkts:
                lines.append(f"- 平均输出: {statistics.mean(all_tkts):.0f} tokens")
            lines.append("")

    # 结论
    lines.append("## 5. 结论与建议\n")
    lines.append("根据以上测试数据，从以下维度给出部署建议:")
    lines.append("1. **响应速度**: 哪个量化方案 TTFT 最低、吞吐最高")
    lines.append("2. **工具准确性**: 哪个方案 Agent 工具调用准确率最高")
    lines.append("3. **输出质量**: 哪个方案输出最完整、最符合预期")
    lines.append("4. **资源成本**: VRAM 占用 vs 性能收益的权衡")
    lines.append("")

    return "\n".join(lines)


# ─── 主流程 ───────────────────────────────────────────────

async def check_backend(backend_name: str) -> bool:
    """检查后端是否可用"""
    cfg = BACKENDS[backend_name]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{cfg['base_url']}/models",
                headers={"Authorization": f"Bearer {cfg['api_key']}"})
            if r.status_code == 200:
                print(f"  ✓ {backend_name} ({cfg['quantization']}) 可用")
                return True
    except Exception:
        pass
    print(f"  ✗ {backend_name} ({cfg['quantization']}) 不可达")
    return False


async def run_backend(backend_name: str, modules: list[str]) -> dict:
    """运行指定后端的所有测试模块"""
    all_logs = []
    result = {"backend": backend_name, "config": BACKENDS[backend_name], "calls": []}

    print(f"\n{'='*60}")
    print(f"  测试后端: {backend_name} ({BACKENDS[backend_name]['quantization']})")
    print(f"{'='*60}")

    if "basic" in modules:
        print(f"\n--- 模块A: 非流式基础性能 ---")
        basic_results = await run_basic(backend_name, all_logs)
        result["basic_results"] = basic_results

    if "agent" in modules:
        print(f"\n--- 模块B: Agent工具调用能力 ---")
        agent_results = await run_agent(backend_name, all_logs)
        result["agent_results"] = agent_results

    if "streaming" in modules:
        print(f"\n--- 模块C: 流式响应 ---")
        stream_results = await run_streaming(backend_name, all_logs)
        result["stream_results"] = stream_results

    result["calls"] = all_logs

    # 保存日志
    log_path = LOG_DIR / f"{backend_name}_benchmark_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "benchmark_time": datetime.now().isoformat(),
            "backend": backend_name,
            "config": BACKENDS[backend_name],
            "temperature": TEMPERATURE,
            "runs_per_case": RUNS,
            "total_calls": len(all_logs),
            "calls": all_logs,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  日志已保存: {log_path}")

    return result


def main():
    global RUNS

    parser = argparse.ArgumentParser(description="Q4 vs Q8 vs BF16 三模型对比 Benchmark")
    parser.add_argument("--backend", choices=["q4", "q8", "bf16"],
                        help="指定测试后端 (默认自动检测在线后端)")
    parser.add_argument("--module", choices=["basic", "agent", "streaming"],
                        default=None, help="只运行指定模块 (默认全部)")
    parser.add_argument("--report", action="store_true",
                        help="从已有日志生成对比报告")
    parser.add_argument("--runs", type=int, default=RUNS,
                        help=f"每个场景重复次数 (默认{RUNS})")
    args = parser.parse_args()

    RUNS = args.runs

    if args.report:
        logs = load_all_logs()
        if not logs:
            print("未找到日志文件，请先运行测试")
            return
        report = generate_report(logs)
        report_path = Path(__file__).parent.parent.parent / "docs" / "benchmark_q4_vs_q8_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已生成: {report_path}")
        print(f"\n{'='*60}")
        print(report)
        return

    modules = [args.module] if args.module else ["basic", "agent", "streaming"]

    async def _main():
        print("=" * 60)
        print("  Q4 vs Q8 vs BF16 三模型对比 Benchmark")
        print("=" * 60)

        if args.backend:
            # 测试指定后端
            backends_to_test = [args.backend]
        else:
            # 自动检测在线后端
            print("\n[检测] 检查在线后端...")
            backends_to_test = []
            for name in ["q4", "q8", "bf16"]:
                if await check_backend(name):
                    backends_to_test.append(name)

            if not backends_to_test:
                print("没有可用的后端，请先启动模型服务")
                return

        for backend_name in backends_to_test:
            await run_backend(backend_name, modules)

        # 如果测试了多个后端，自动生成报告
        if len(backends_to_test) > 1:
            print(f"\n{'='*60}")
            print("  生成对比报告...")
            print(f"{'='*60}")
            logs = load_all_logs()
            report = generate_report(logs)
            report_path = Path(__file__).parent.parent.parent / "docs" / "benchmark_q4_vs_q8_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"报告已生成: {report_path}")

    asyncio.run(_main())


if __name__ == "__main__":
    main()
