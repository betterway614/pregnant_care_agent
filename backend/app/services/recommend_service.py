"""AI 推荐服务 - 遵循 SOLID 原则

- SRP: 仅负责推荐内容生成逻辑
- OCP: 通过策略模式扩展不同推荐源（LLM / 模板），无需修改已有代码
- LSP: 所有策略实现相同接口，可自由替换
- ISP: 策略接口最小化，仅一个 recommend 方法
- DIP: 依赖抽象接口和已有服务层，不直接依赖具体实现
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..core import get_llm_client
from ..core.json_parser import parse_llm_json
from ..models import Pregnant
from ..schemas import RecommendResponse
from .patient_context_service import get_patient_basic, get_recent_health_data, get_active_alerts


# ── 策略接口 (OCP / ISP) ──────────────────────────────────────────

class RecommendStrategy(ABC):
    """推荐生成策略抽象基类"""

    @abstractmethod
    async def recommend(
        self,
        db: Session,
        pregnant: Pregnant,
        gest_week: int,
        gest_day: int,
        risk_tags: list[str],
    ) -> Optional[RecommendResponse]:
        ...


# ── 简单 TTL 缓存 ─────────────────────────────────────────────────

class _TTLCache:
    """轻量级进程内 TTL 缓存"""

    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, RecommendResponse]] = {}

    def get(self, key: str) -> Optional[RecommendResponse]:
        entry = self._store.get(key)
        if entry and (time.time() - entry[0]) < self._ttl:
            return entry[1]
        return None

    def set(self, key: str, value: RecommendResponse) -> None:
        self._store[key] = (time.time(), value)

    def invalidate(self, key_prefix: str) -> None:
        """清除指定前缀的缓存条目"""
        keys_to_remove = [k for k in self._store if k.startswith(key_prefix)]
        for k in keys_to_remove:
            del self._store[k]


# ── LLM 推荐策略 ──────────────────────────────────────────────────

class LLMRecommendStrategy(RecommendStrategy):
    """通过 LLM 生成个性化推荐"""

    SYSTEM_PROMPT = (
        "你是一位资深的产科医生和孕期营养专家，请为孕妇提供专业、个性化的孕期建议。"
        "请严格按JSON格式返回，不要包含markdown代码块标记。"
        "返回字段：weekly_tips, diet_advice, exercise_advice, warning_signs, baby_development"
    )

    async def recommend(
        self,
        db: Session,
        pregnant: Pregnant,
        gest_week: int,
        gest_day: int,
        risk_tags: list[str],
    ) -> Optional[RecommendResponse]:
        try:
            client = get_llm_client()
            context = self._gather_context(db, pregnant.pregnant_id)
            prompt = self._build_prompt(pregnant, gest_week, gest_day, risk_tags, context)

            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await client.chat(messages)
            if not response or not response.strip():
                logger.warning("[Recommend] LLM 返回空内容, pregnant_id={}", pregnant.pregnant_id)
                return None

            data = parse_llm_json(response)
            if not data:
                logger.warning("[Recommend] LLM 返回 JSON 解析失败, pregnant_id={}", pregnant.pregnant_id)
                return None

            return RecommendResponse(
                pregnant_id=pregnant.pregnant_id,
                gestational_week=f"{gest_week}+{gest_day}",
                weekly_tips=data.get("weekly_tips", ""),
                diet_advice=data.get("diet_advice", ""),
                exercise_advice=data.get("exercise_advice", ""),
                warning_signs=data.get("warning_signs", ""),
                baby_development=data.get("baby_development", ""),
                source="AI_CARE",
            )
        except Exception as e:
            logger.warning("[Recommend] LLM 推荐失败: {}, pregnant_id={}", e, pregnant.pregnant_id)
            return None

    # ── 私有辅助方法 ──

    @staticmethod
    def _gather_context(db: Session, pregnant_id: str) -> dict:
        """聚合患者上下文：基础信息 + 近期健康数据 + 活跃预警"""
        basic = get_patient_basic(db, pregnant_id) or {}
        health_data = get_recent_health_data(db, pregnant_id, limit=5, days=7)
        alerts = get_active_alerts(db, pregnant_id, limit=3)
        return {"basic": basic, "health_data": health_data, "alerts": alerts}

    @staticmethod
    def _build_prompt(
        pregnant: Pregnant,
        gest_week: int,
        gest_day: int,
        risk_tags: list[str],
        context: dict,
    ) -> str:
        """构建富含上下文的推荐提示词"""
        risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"

        # BMI 计算
        bmi_info = ""
        if pregnant.height_cm and pregnant.pre_pregnancy_weight_kg:
            h_m = pregnant.height_cm / 100
            bmi = pregnant.pre_pregnancy_weight_kg / (h_m * h_m)
            bmi_info = f"- 孕前BMI: {bmi:.1f}"

        # 预产期倒计时
        edd_info = ""
        if pregnant.edd:
            days_left = (pregnant.edd - date.today()).days
            if days_left > 0:
                edd_info = f"- 距预产期还有: {days_left}天"

        # 近期健康数据摘要
        health_summary = ""
        health_data = context.get("health_data", [])
        if health_data:
            lines = []
            for d in health_data:
                lines.append(f"  - {d['metric']}: {d['value']}{d['unit']} ({d['recorded_at'][:10]})")
            health_summary = "- 最近7天健康数据:\n" + "\n".join(lines)

        # 活跃预警
        alert_summary = ""
        alerts = context.get("alerts", [])
        if alerts:
            lines = [f"  - [{a['level']}] {a['message']}" for a in alerts]
            alert_summary = "- 当前活跃预警:\n" + "\n".join(lines)

        # 组装额外信息块
        extra_parts = [p for p in (bmi_info, edd_info, health_summary, alert_summary) if p]
        extra_block = "\n".join(extra_parts) if extra_parts else ""

        prompt = f"""请为以下孕妇生成个性化孕期建议：

孕妇信息：
- 孕周：{gest_week}周+{gest_day}天
- 风险标签：{risk_text}
- 展示名称：{pregnant.display_name}
{extra_block}

请根据以上信息，提供以下五个方面的具体建议：
1. weekly_tips: 本周核心注意事项（50-100字）
2. diet_advice: 饮食建议（50-100字）
3. exercise_advice: 运动建议（50-100字）
4. warning_signs: 需要警惕的危险信号（30-80字）
5. baby_development: 本周胎儿发育情况描述（30-60字）

请以JSON格式返回结果，键名使用英文（weekly_tips, diet_advice, exercise_advice, warning_signs, baby_development），值使用中文。"""
        return prompt


# ── 模板兜底策略 ──────────────────────────────────────────────────

class TemplateRecommendStrategy(RecommendStrategy):
    """基于规则的模板推荐（LLM 不可用时的兜底方案）"""

    # 按孕周的胎儿发育里程碑（每4周一档，粒度优于原先的8个散点）
    MILESTONES: dict[int, str] = {
        4: "受精卵着床完成，胚胎约0.2cm，像罂粟籽大小。",
        8: "心脏开始跳动，四肢开始形成。宝宝约1.6cm，像覆盆子大小。",
        12: "手指脚趾已分离，面部特征明显。宝宝约5.4cm，像李子大小。",
        16: "能听到声音，开始有吮吸反射。宝宝约11.6cm，像牛油果大小。",
        20: "能感知光线，开始有规律的活动。宝宝约16.4cm，像香蕉大小。",
        24: "肺部开始发育，能辨别声音。宝宝约30cm，像玉米大小。",
        28: "眼睛睁开，大脑快速发育。宝宝约37.6cm，像茄子大小。",
        32: "骨骼完全形成，开始储存脂肪。宝宝约42.4cm，像南瓜大小。",
        36: "肺部已成熟，准备出生。宝宝约47.4cm，像生菜大小。",
        40: "已足月，随时准备出生。宝宝约51cm，像西瓜大小。",
    }

    async def recommend(
        self,
        db: Session,
        pregnant: Pregnant,
        gest_week: int,
        gest_day: int,
        risk_tags: list[str],
    ) -> RecommendResponse:
        baby_dev = self._get_milestone(gest_week)
        advice = self._get_base_advice(gest_week)
        self._apply_risk_overrides(risk_tags, advice)

        return RecommendResponse(
            pregnant_id=pregnant.pregnant_id,
            gestational_week=f"{gest_week}+{gest_day}",
            weekly_tips=advice[0],
            diet_advice=advice[1],
            exercise_advice=advice[2],
            warning_signs=advice[3],
            baby_development=baby_dev,
            source="TEMPLATE",
        )

    def _get_milestone(self, gest_week: int) -> str:
        closest = min(self.MILESTONES.keys(), key=lambda x: abs(x - gest_week))
        return self.MILESTONES[closest]

    @staticmethod
    def _get_base_advice(gest_week: int) -> list[str]:
        """根据孕期阶段返回基础建议 [weekly_tips, diet_advice, exercise_advice, warning_signs]"""
        if gest_week <= 12:
            return [
                "孕早期是胎儿器官发育关键期，请按时服用叶酸(0.4mg/天)，避免接触有害物质。",
                "少量多餐，选择易消化食物。增加富含叶酸的食物（深绿色蔬菜、豆类）。",
                "适度散步即可，避免剧烈运动和长时间站立。每天15-20分钟。",
                "如出现阴道出血、剧烈腹痛，请立即就医。",
            ]
        elif gest_week <= 28:
            return [
                "孕中期是胎儿快速生长期，注意补充钙和铁。可以开始进行胎教。",
                "增加优质蛋白（鱼、蛋、瘦肉），补充钙质（牛奶、豆制品），控制盐摄入。",
                "每天散步30分钟，可做孕妇瑜伽。避免仰卧位运动。每天注意胎动。",
                "如出现规律宫缩、阴道流液、胎动明显减少，请立即就医。",
            ]
        else:
            return [
                "孕晚期请准备好待产包，确认分娩医院和交通路线。保持左侧卧位休息。",
                "继续高蛋白饮食，控制碳水化合物，多吃含铁食物（红肉、动物肝脏）。",
                "每天散步20-30分钟，做骨盆底肌锻炼。避免长时间站立和弯腰。",
                "如出现规律宫缩（每10分钟一次）、见红、破水，请立即前往医院。",
            ]

    @staticmethod
    def _apply_risk_overrides(risk_tags: list[str], advice: list[str]) -> None:
        """根据风险标签就地追加针对性建议

        Args:
            risk_tags: 风险标签列表
            advice: [weekly_tips, diet_advice, exercise_advice, warning_signs]
        """
        if "FGR高危" in risk_tags:
            advice[0] += " 您是FGR高危孕妇，请严格按医嘱进行B超监测，注意胎动变化。"
        if "GDM" in risk_tags:
            advice[1] += " 请严格控制糖分摄入，监测空腹及餐后血糖。"
        if "高血压" in risk_tags:
            advice[3] += " 每日监测血压，如收缩压≥140或舒张压≥90请立即就医。"


# ── 服务门面（单例） ──────────────────────────────────────────────

class RecommendService:
    """推荐服务门面：聚合策略 + 缓存"""

    _instance: Optional[RecommendService] = None

    def __init__(self, cache_ttl: int = 14400):  # 默认 4 小时缓存
        self._llm_strategy = LLMRecommendStrategy()
        self._template_strategy = TemplateRecommendStrategy()
        self._cache = _TTLCache(ttl_seconds=cache_ttl)
        logger.info("[RecommendService] 初始化完成, cache_ttl={}s", cache_ttl)

    async def get_recommendation(
        self,
        db: Session,
        pregnant: Pregnant,
        gest_week: int,
        gest_day: int,
        risk_tags: list[str],
    ) -> RecommendResponse:
        """获取推荐：缓存优先 → LLM 生成 → 模板兜底"""
        cache_key = f"{pregnant.pregnant_id}:{pregnant.gestational_age_days or 0}"

        # 1. 缓存命中
        cached = self._cache.get(cache_key)
        if cached:
            logger.debug("[Recommend] 缓存命中 key={}", cache_key)
            return cached

        # 2. LLM 策略优先
        result = await self._llm_strategy.recommend(db, pregnant, gest_week, gest_day, risk_tags)

        # 3. 模板兜底
        if not result:
            logger.info("[Recommend] LLM 未返回结果，使用模板兜底, pregnant_id={}", pregnant.pregnant_id)
            result = await self._template_strategy.recommend(db, pregnant, gest_week, gest_day, risk_tags)

        # 4. 写入缓存
        self._cache.set(cache_key, result)
        return result

    @classmethod
    def get_instance(cls) -> RecommendService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# 模块级单例，与项目其他 service 风格一致
recommend_service = RecommendService.get_instance()
