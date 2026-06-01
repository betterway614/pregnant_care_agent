"""
护士/医生 Agent 能力 Benchmark
==============================
测试本地 llama-server 在 Agent 工具调用场景下的表现。
模拟真实的 Agent 对话链：系统提示 + 工具定义 + 用户输入 → 工具调用 → 结果整合。

用法: python scripts/benchmark_agent.py
"""

import asyncio
import json
import os
import time
import httpx
from datetime import datetime
from pathlib import Path

# 云端配置
CLOUD_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CLOUD_API_KEY = os.getenv("LLM_API_KEY", "")
CLOUD_MODEL = "qwen3.6-35b-a3b"

# 本地配置
LOCAL_BASE_URL = "http://localhost:8080/v1"
LOCAL_API_KEY = "not-needed"
LOCAL_MODEL = "qwen3.6-35b-q8-vl"

LOG_DIR = Path(__file__).parent.parent.parent / "docs" / "benchmark_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── 护士 Agent 场景 ─────────────────────────────────────

NURSE_SYSTEM = """你是小护，一位专业产科护士AI助手。
你的职责：
1. 分析孕妇健康数据，识别异常趋势
2. 使用SOAP格式记录护理评估
3. 生成个性化随访计划
4. 发现异常时向医生报告

你有以下工具可用：
- query_patient_data(patient_id): 查询孕妇档案和最近健康数据
- analyze_health_trends(patient_id, metric, period): 分析健康指标趋势
- search_knowledge(query): 检索医学知识库
- create_followup_record(patient_id, content): 创建随访记录
- report_issue_to_doctor(patient_id, issue): 向医生报告异常

请根据用户请求，选择合适的工具调用并给出专业分析。输出时使用结构化的SOAP格式。"""

NURSE_CASES = [
    {
        "name": "护士-血压异常分析",
        "user": "请分析孕妇张某（ID: P20240032）最近一周的血压数据，她孕32周，血压记录：130/85, 132/87, 135/90, 138/92。需要判断是否有子痫前期风险。",
        "expected_tools": ["query_patient_data", "analyze_health_trends", "search_knowledge"],
    },
    {
        "name": "护士-随访计划生成",
        "user": "孕妇李某（ID: P20240045）孕28周，GDM（妊娠期糖尿病）确诊，空腹血糖5.8mmol/L，餐后2h血糖8.2mmol/L。请制定本周随访计划，包括血糖监测方案和饮食建议。",
        "expected_tools": ["query_patient_data", "search_knowledge", "create_followup_record"],
    },
    {
        "name": "护士-紧急情况上报",
        "user": "孕妇王某（ID: P20240018）孕36周，刚才报告胎动明显减少（过去2小时只有1次），之前每天胎动约10次。请立即评估并处理。",
        "expected_tools": ["query_patient_data", "check_emergency", "report_issue_to_doctor"],
    },
]

# ─── 医生 Agent 场景 ─────────────────────────────────────

DOCTOR_SYSTEM = """你是智医生，一位资深产科医生AI助手。
你的职责：
1. 对孕妇健康状况进行综合评估
2. 提供鉴别诊断和推理链
3. 生成医疗建议（注意：不能确诊，只能提供建议）
4. 处理护士上报的异常情况

你有以下工具可用：
- analyze_patient_comprehensive(patient_id): 综合分析孕妇数据
- query_patient_data(patient_id): 查询孕妇档案
- query_clinical_guideline(condition): 查询临床指南
- generate_medical_order(patient_id, content): 生成医嘱
- handle_issue(patient_id, issue): 处理上报的异常

请根据用户请求，选择合适的工具调用，给出鉴别诊断和推理链。"""

DOCTOR_CASES = [
    {
        "name": "医生-鉴别诊断",
        "user": "孕妇李某，28岁，初产妇，孕34周。主诉：头痛2天，视物模糊1天。查体：BP 155/100mmHg，双下肢水肿++。尿蛋白++。既往体健，否认高血压病史。请给出鉴别诊断和处理建议。",
        "expected_tools": ["analyze_patient_comprehensive", "query_clinical_guideline"],
    },
    {
        "name": "医生-异常处理",
        "user": "护士报告：孕妇王某（ID: P20240018）孕36周，胎动明显减少（2小时内仅1次），无腹痛无出血。既往产检正常，NT、唐筛、四维均未见异常。请评估并给出处理方案。",
        "expected_tools": ["query_patient_data", "handle_issue", "query_clinical_guideline"],
    },
    {
        "name": "医生-医嘱生成",
        "user": "孕妇赵某（ID: P20240056）孕30周，诊断为GDM，目前饮食控制血糖不达标（空腹5.9, 餐后2h 9.1）。请评估是否需要胰岛素治疗，并生成相应医嘱。",
        "expected_tools": ["analyze_patient_comprehensive", "query_clinical_guideline", "generate_medical_order"],
    },
]


async def call_llm(base_url: str, api_key: str, model: str,
                   system: str, user: str, test_name: str,
                   backend_name: str, all_logs: list) -> dict:
    """单次 LLM 调用，模拟 Agent 的一轮对话"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "stream": False,
    }

    t_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{base_url}/chat/completions",
                                 headers={"Authorization": f"Bearer {api_key}"},
                                 json=payload)
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

    # 检测工具调用意图
    tool_keywords = ["query_patient_data", "analyze_health_trends", "search_knowledge",
                     "create_followup_record", "report_issue_to_doctor", "check_emergency",
                     "analyze_patient_comprehensive", "query_clinical_guideline",
                     "generate_medical_order", "handle_issue"]
    mentioned_tools = [t for t in tool_keywords if t in content]

    result = {
        "backend": backend_name,
        "latency": round(latency, 4),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "text_tokens": max(text_tokens, 0),
        "content_len": len(content),
        "reasoning_content_len": len(reasoning_content),
        "has_reasoning": bool(reasoning_content),
        "content_preview": content[:300],
        "mentioned_tools": mentioned_tools,
        "finish_reason": resp_body["choices"][0].get("finish_reason", "unknown"),
    }

    all_logs.append({
        "timestamp": datetime.now().isoformat(),
        "backend": backend_name,
        "test_case": test_name,
        "request_payload": payload,
        "response_body": resp_body,
        "benchmark_result": result,
    })

    return result


async def run_cases(cases: list, system: str, role: str,
                    base_url: str, api_key: str, model: str,
                    backend_name: str, all_logs: list) -> list:
    results = []
    for tc in cases:
        print(f"  [{backend_name}-{role}] {tc['name']} ", end="", flush=True)
        try:
            r = await call_llm(base_url, api_key, model,
                               system, tc["user"], tc["name"], backend_name, all_logs)
            r["name"] = tc["name"]
            r["expected_tools"] = tc.get("expected_tools", [])
            r["tool_match"] = all(t in r["mentioned_tools"] for t in tc.get("expected_tools", []))
            results.append(r)
            tps = r["text_tokens"] / r["latency"] if r["latency"] > 0 else 0
            think_tag = f" [think:{r['reasoning_tokens']}tok]" if r["has_reasoning"] else ""
            print(f"✓ {r['latency']:.1f}s | text:{r['text_tokens']}tok | {tps:.1f}tok/s{think_tag} | tools:{r['mentioned_tools']}")
        except Exception as e:
            print(f"✗ {e}")
            results.append({"name": tc["name"], "backend": backend_name, "error": str(e)})
    return results


def format_report(cloud_nurse: list, local_nurse: list,
                  cloud_doctor: list, local_doctor: list) -> str:
    lines = []
    lines.append("# 护士/医生 Agent 能力对比报告\n")
    lines.append(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**云端**: {CLOUD_MODEL} (DashScope, thinking模式开启)")
    lines.append(f"**本地**: {LOCAL_MODEL} (llama-server, Q8_0, -np 1, reasoning off)")
    lines.append(f"**配置**: temperature=0.3, 无max_tokens限制\n")
    lines.append(f"**日志**: `docs/benchmark_logs/agent_benchmark_log.json`\n")

    for role, c_results, l_results in [
        ("护士Agent", cloud_nurse, local_nurse),
        ("医生Agent", cloud_doctor, local_doctor),
    ]:
        lines.append(f"## {role}\n")
        lines.append("| 场景 | 部署 | 文本tokens | 延迟(s) | 文本吞吐(tok/s) | thinking | 工具调用 |")
        lines.append("|------|------|------------|---------|-----------------|----------|----------|")

        for cr, lr in zip(c_results, l_results):
            for r, tag in [(cr, "☁️云端"), (lr, "🖥️本地")]:
                if "error" in r:
                    lines.append(f"| {r['name']} | {tag} | ERROR | ERROR | ERROR | - | - |")
                    continue
                tps = r["text_tokens"] / r["latency"] if r["latency"] > 0 else 0
                think = f"{r['reasoning_tokens']}tok" if r["has_reasoning"] else "-"
                tools_str = ", ".join(r["mentioned_tools"]) if r["mentioned_tools"] else "无"
                lines.append(f"| {r['name']} | {tag} | {r['text_tokens']} | {r['latency']:.1f} | {tps:.1f} | {think} | {tools_str} |")

        lines.append("")

    # 总体对比
    lines.append("## 总体对比 (纯文本tokens)\n")
    all_cloud = [r for r in cloud_nurse + cloud_doctor if "error" not in r]
    all_local = [r for r in local_nurse + local_doctor if "error" not in r]

    if all_cloud and all_local:
        c_lat = sum(r["latency"] for r in all_cloud) / len(all_cloud)
        l_lat = sum(r["latency"] for r in all_local) / len(all_local)
        c_tps = sum(r["text_tokens"] / r["latency"] for r in all_cloud if r["latency"] > 0) / len(all_cloud)
        l_tps = sum(r["text_tokens"] / r["latency"] for r in all_local if r["latency"] > 0) / len(all_local)
        c_tok = sum(r["text_tokens"] for r in all_cloud) / len(all_cloud)
        l_tok = sum(r["text_tokens"] for r in all_local) / len(all_local)
        c_reason = sum(r["reasoning_tokens"] for r in all_cloud) / len(all_cloud)

        lines.append("| 指标 | ☁️ 云端 DashScope | 🖥️ 本地 llama-server | 对比 |")
        lines.append("|------|-------------------|---------------------|------|")
        lines.append(f"| 平均延迟 | {c_lat:.1f}s | {l_lat:.1f}s | {'🟢 本地更优' if l_lat < c_lat else '🔴 云端更优'} ({l_lat/c_lat:.2f}x) |")
        lines.append(f"| 文本吞吐 | {c_tps:.1f} tok/s | {l_tps:.1f} tok/s | {'🟢 本地更优' if l_tps > c_tps else '🔴 云端更优'} ({l_tps/c_tps:.2f}x) |")
        lines.append(f"| 平均文本输出 | {c_tok:.0f} tokens | {l_tok:.0f} tokens | - |")
        lines.append(f"| 平均thinking | {c_reason:.0f} tokens | 0 tokens | 云端额外开销 |")
        lines.append(f"| 数据隐私 | 上传云端 | **不出本机** | 🟢 本地更优 |")

    # 结论
    lines.append("")
    lines.append("## 结论\n")
    if all_cloud and all_local:
        lines.append(f"1. **文本吞吐**: 本地 {l_tps:.1f} tok/s vs 云端 {c_tps:.1f} tok/s (不含thinking)")
        lines.append(f"2. **延迟**: 本地 {l_lat:.1f}s vs 云端 {c_lat:.1f}s (云端含thinking时间)")
        lines.append(f"3. **输出量**: 本地平均 {l_tok:.0f} text tokens vs 云端 {c_tok:.0f} text tokens")
        lines.append(f"4. **云端thinking开销**: 平均 {c_reason:.0f} tokens/次，约占总completion的 {c_reason/(c_reason+c_tok)*100:.0f}%")
        lines.append(f"5. **隐私**: 本地部署数据完全不出端，满足医疗数据隐私合规")

    return "\n".join(lines)


async def main():
    all_logs = []

    print("=" * 60)
    print("  护士/医生 Agent 能力对比 Benchmark")
    print("=" * 60)

    # 检查服务
    print("\n[1/3] 检查服务...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{LOCAL_BASE_URL}/models")
            print(f"  ✓ 本地服务正常")
        except Exception as e:
            print(f"  ✗ 本地不可达: {e}")
            return
        try:
            r = await client.get(f"{CLOUD_BASE_URL}/models",
                                 headers={"Authorization": f"Bearer {CLOUD_API_KEY}"})
            print(f"  ✓ 云端服务正常" if r.status_code == 200 else f"  ⚠ 云端 {r.status_code}")
        except Exception as e:
            print(f"  ⚠ 云端不可达: {e}")

    # 云端测试
    print(f"\n[2/3] 云端 DashScope 测试...\n")
    print("--- 护士 Agent (云端) ---")
    cloud_nurse = await run_cases(NURSE_CASES, NURSE_SYSTEM, "nurse",
                                  CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, "cloud", all_logs)
    print("\n--- 医生 Agent (云端) ---")
    cloud_doctor = await run_cases(DOCTOR_CASES, DOCTOR_SYSTEM, "doctor",
                                   CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, "cloud", all_logs)

    # 本地测试
    print(f"\n[3/3] 本地 llama-server 测试...\n")
    print("--- 护士 Agent (本地) ---")
    local_nurse = await run_cases(NURSE_CASES, NURSE_SYSTEM, "nurse",
                                  LOCAL_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL, "local", all_logs)
    print("\n--- 医生 Agent (本地) ---")
    local_doctor = await run_cases(DOCTOR_CASES, DOCTOR_SYSTEM, "doctor",
                                   LOCAL_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL, "local", all_logs)

    # 保存日志
    log_path = LOG_DIR / "agent_benchmark_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "benchmark_time": datetime.now().isoformat(),
            "cloud_model": CLOUD_MODEL,
            "local_model": LOCAL_MODEL,
            "total_calls": len(all_logs),
            "calls": all_logs,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  日志: {log_path}")

    # 生成报告
    report = format_report(cloud_nurse, local_nurse, cloud_doctor, local_doctor)
    report_path = LOG_DIR.parent / "agent_benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告: {report_path}")
    print(f"\n{'=' * 60}")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
