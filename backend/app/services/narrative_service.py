"""叙事生成服务 - 策略模式（LLM 优先 + 模板兜底）

遵循 SOLID 原则：
- SRP: 仅负责叙事文本生成
- OCP: 通过策略模式扩展不同叙事源（LLM / 模板），无需修改已有代码
- DIP: 依赖抽象 LLMClient 接口，不绑定具体模型实现
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List

from loguru import logger

from ..config import settings
from ..core import get_llm_client
from ..core.json_parser import parse_llm_json


@dataclass
class NarrativeResult:
    """叙事生成结果"""
    narrative: str
    highlights: List[str] = field(default_factory=list)
    source: str = "template"


class NarrativeStrategy(ABC):
    """叙事生成策略抽象基类"""

    @abstractmethod
    async def generate(
        self,
        week: int,
        metrics: dict,
        has_abnormal: bool,
    ) -> Optional[NarrativeResult]:
        ...


class LLMNarrativeStrategy(NarrativeStrategy):
    """通过 LLM 生成个性化孕期叙事"""

    SYSTEM_PROMPT = (
        "你是一位资深产科医生，同时也是一位温暖的陪伴者。\n"
        "请根据孕妇本周的健康数据，用温馨、专业、鼓励的语气写一段 150-300 字的孕期日记叙事。\n"
        "要求：\n"
        "1. 用第二人称（\"你\"）称呼准妈妈，语气亲切自然\n"
        "2. 结合具体数据分析各项指标是否正常，给出专业解读\n"
        "3. 如果有异常指标，温和地提醒并给出建议\n"
        "4. 适当提及宝宝的发育情况（根据孕周推算）\n"
        "5. 结尾给一句鼓励的话\n"
        "\n"
        "请严格按 JSON 格式返回，不要包含 markdown 代码块标记：\n"
        '{"narrative": "叙事文本...", "highlights": ["亮点1", "亮点2"]}'
    )

    async def generate(
        self,
        week: int,
        metrics: dict,
        has_abnormal: bool,
    ) -> Optional[NarrativeResult]:
        try:
            client = get_llm_client()
            prompt = self._build_prompt(week, metrics, has_abnormal)
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            t0 = time.time()
            response = await client.chat(messages)
            elapsed = time.time() - t0
            logger.info("[NarrativeLLM] 生成完成 ({:.1f}s), week={}", elapsed, week)

            if not response or not response.strip():
                logger.warning("[NarrativeLLM] LLM 返回空内容, week={}", week)
                return None

            data = parse_llm_json(response)
            if not data or "narrative" not in data:
                logger.warning("[NarrativeLLM] JSON 解析失败或缺少 narrative, week={}", week)
                return None

            return NarrativeResult(
                narrative=data["narrative"],
                highlights=data.get("highlights", []),
                source="llm",
            )
        except Exception as e:
            logger.warning("[NarrativeLLM] 生成失败: {}, week={}", e, week)
            return None

    @staticmethod
    def _build_prompt(week: int, metrics: dict, has_abnormal: bool) -> str:
        """构建 user prompt，注入指标数据"""
        if week <= 12:
            stage = "孕早期（胚胎发育关键期）"
        elif week <= 27:
            stage = "孕中期（宝宝快速成长期）"
        elif week <= 36:
            stage = "孕晚期（宝宝成熟期）"
        else:
            stage = "足月待产期（随时可能分娩）"

        parts = [f"当前孕周：第 {week} 周（{stage}）\n"]
        parts.append("本周健康数据汇总：")

        if metrics.get("weight_delta") is not None:
            parts.append(f"- 体重变化：{metrics['weight_delta']:+.1f} kg")
        if metrics.get("avg_bp"):
            sys, dia = metrics["avg_bp"]
            parts.append(f"- 平均血压：{sys:.0f}/{dia:.0f} mmHg")
        if metrics.get("avg_fetal") is not None:
            parts.append(f"- 平均胎动：{metrics['avg_fetal']:.1f} 次/小时")
        if metrics.get("avg_blood_sugar_fasting") is not None:
            parts.append(f"- 空腹血糖：{metrics['avg_blood_sugar_fasting']:.1f} mmol/L")
        if metrics.get("avg_heart_rate") is not None:
            parts.append(f"- 平均心率：{metrics['avg_heart_rate']:.0f} bpm")
        if metrics.get("avg_sleep") is not None:
            parts.append(f"- 平均睡眠：{metrics['avg_sleep']:.1f} 小时")

        if has_abnormal:
            parts.append("\n⚠️ 本周存在健康预警，请适当提醒。")

        if len(parts) == 2:
            parts.append("（本周暂无健康数据记录）")

        return "\n".join(parts)


class TemplateNarrativeStrategy(NarrativeStrategy):
    """使用硬编码模板生成叙事（LLM 不可用时的兜底方案）"""

    async def generate(
        self,
        week: int,
        metrics: dict,
        has_abnormal: bool,
    ) -> Optional[NarrativeResult]:
        from .pregnancy_diary import PregnancyDiaryService
        svc = PregnancyDiaryService()
        narrative = svc._generate_narrative(
            week=week,
            weight_delta=metrics.get("weight_delta"),
            avg_bp=metrics.get("avg_bp"),
            avg_fetal=metrics.get("avg_fetal"),
            avg_blood_sugar_fasting=metrics.get("avg_blood_sugar_fasting"),
            avg_heart_rate=metrics.get("avg_heart_rate"),
            avg_sleep=metrics.get("avg_sleep"),
            has_abnormal=has_abnormal,
        )
        return NarrativeResult(
            narrative=narrative,
            highlights=[],
            source="template",
        )


class NarrativeService:
    """叙事生成门面：LLM 优先 → 模板兜底"""

    def __init__(self):
        self._llm_strategy = LLMNarrativeStrategy()
        self._template_strategy = TemplateNarrativeStrategy()

    async def generate_narrative(
        self,
        week: int,
        metrics: dict,
        has_abnormal: bool,
    ) -> NarrativeResult:
        """生成叙事：优先 LLM，失败自动回退模板。"""
        if not settings.diary_llm_enabled:
            logger.debug("[Narrative] LLM 已禁用，使用模板, week={}", week)
            result = await self._template_strategy.generate(week, metrics, has_abnormal)
            return result or NarrativeResult(narrative="", source="template")

        result = await self._llm_strategy.generate(week, metrics, has_abnormal)
        if result is not None:
            return result

        logger.info("[Narrative] LLM 失败，回退模板, week={}", week)
        fallback = await self._template_strategy.generate(week, metrics, has_abnormal)
        if fallback is not None:
            fallback.source = "template_fallback"
            return fallback

        return NarrativeResult(narrative="", source="template")


def generate_narrative_sync(
    week: int,
    metrics: dict,
    has_abnormal: bool,
) -> NarrativeResult:
    """同步版叙事生成（在 APScheduler daemon 线程中安全使用 asyncio.run）"""
    svc = NarrativeService()
    return asyncio.run(svc.generate_narrative(week, metrics, has_abnormal))


narrative_service = NarrativeService()
