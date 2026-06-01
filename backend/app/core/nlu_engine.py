"""NLU引擎 - 意图识别、实体提取、情绪分析"""
import re
from enum import Enum
from typing import Optional


class IntentCategory(str, Enum):
    """高层意图分类（供路由和 Workflow 使用）"""
    CHAT = "chat"
    ANALYZE = "analyze"
    EMERGENCY = "emergency"
    KNOWLEDGE = "knowledge"
    FOLLOWUP = "followup"
    ALERT = "alert"
    REPORT = "report"


# 中文数字到阿拉伯数字映射
_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
}


def _parse_cn_number(s: str) -> Optional[int]:
    """解析中文数字（支持百位，如一百二十=120，两百=200）"""
    result = 0
    # 处理"X百Y十Z"格式
    if "百" in s:
        parts = s.split("百", 1)
        hundred_part = parts[0] or "一"  # "百"前无数字默认"一"
        result += _CN_DIGITS.get(hundred_part, 0) * 100
        s = parts[1]
    if "十" in s:
        parts = s.split("十", 1)
        ten_part = parts[0] or "一"  # "十"前无数字默认"一"
        result += _CN_DIGITS.get(ten_part, 0) * 10
        s = parts[1]
    if s:
        result += _CN_DIGITS.get(s, 0)
    return result if result > 0 else None


def _cn_to_arabic(text: str) -> str:
    """将文本中的常见中文数字替换为阿拉伯数字"""
    # 先处理百位数（如"一百二十" -> "120"）
    import re as _re
    _cn_unit = "[零一二两三四五六七八九]"
    _cn_tens = f"(?:{_cn_unit}?十{_cn_unit}?|十{_cn_unit}?)"
    _cn_hundreds = f"(?:{_cn_unit}百{_cn_tens}?|{_cn_unit}百)"
    _cn_pattern = _re.compile(f"({_cn_hundreds}|{_cn_tens}|(?:二十|三十)?{_cn_unit})")

    def _replace_cn(match):
        s = match.group(0)
        v = _parse_cn_number(s)
        return str(v) if v is not None else s

    text = _cn_pattern.sub(_replace_cn, text)
    # 再处理简单的个位数/两位数替换（兜底）
    for cn, ar in sorted(_CN_DIGITS.items(), key=lambda x: -len(x[0])):
        text = text.replace(cn, str(ar))
    return text


class NLUResult:
    """NLU解析结果"""
    def __init__(self, intent: str = "", entities: dict = None,
                 emotion: Optional[dict] = None, is_emergency: bool = False,
                 category: IntentCategory = IntentCategory.CHAT,
                 suggested_tools: list[str] | None = None):
        self.intent = intent
        self.entities = entities or {}
        self.emotion = emotion or {"level": "neutral", "score": 0}
        self.is_emergency = is_emergency
        self.category = category
        self.suggested_tools = suggested_tools or []


class RuleBaseNLU:
    """基于规则的NLU引擎（轻量，CPU运行）"""

    # 意图识别模式
    INTENT_PATTERNS = {
        "HEALTH_DATA_REPORT": [
            r"(体重|血压|胎动|血糖|心率).*?(\d+)",
            r"(\d+\.?\d*)\s*(kg|斤|mmHg|次)",
            r"(记录|上报|提交|输入).*?(体重|血压|血糖|胎动)",  # NEW
            r"(今天|刚才|刚刚).*?(称了|量了|测了)",              # NEW
        ],
        "EMOTION_EXPRESS": [
            r"(焦虑|紧张|害怕|担心|抑郁|难过|失眠|压力)",
            r"(不开心|好烦|睡不着|很累)",
            r"(宝宝.*?动.*?(少|没|不怎么))",                    # NEW
            r"(感觉.*?(不对|不好|有问题|不舒服))",              # NEW
            r"(心情.*?(差|不好|低落))",                         # NEW
        ],
        "KNOWLEDGE_QUERY": [
            r"(什么|怎么|为什么|能否|可以|需要|应该)",
            r"(饮食|运动|睡觉|吃药|检查|注意事项)",
            r"(能不能|可不可以|要不要|有没有影响)",              # NEW
            r"(正常.*?(范围|值|标准))",                         # NEW
        ],
        "SCHEDULE_INQUIRY": [
            r"(产检|检查|预约|什么时候|提醒)",
            r"(下次|这周|下周).*?(去|来|做).*?(检查|产检)",      # NEW
        ],
        "EMERGENCY": [
            r"(大出血|剧烈腹痛|昏倒|昏迷|呼吸困难|休克)",
            r"(急诊|120|救护车)",
            r"(出血.*?(多|不止|很多))",                         # NEW
            r"(肚子.*?(剧痛|绞痛|一阵一阵.*?痛))",              # NEW
            r"(羊水栓塞|胎盘早剥|宫外孕|异位妊娠|脐带脱垂|子痫|胎膜早破|前置胎盘)",
        ],
        "SUICIDE_RISK": [
            r"(自杀|不想活|想死|活着没意思)",
        ],
        "GREETING": [
            r"^(你好|您好|嗨|hi|hello|早上好|下午好|晚上好)",
        ],
    }

    # 实体提取模式（支持自然语言表述）
    ENTITY_PATTERNS = {
        "weight": r"(\d+\.?\d*)\s*(kg|斤|千克|公斤)",
        "sbp": r"(?:收缩压|高压|上压|sbp|SBP)[：:\s]*(\d+)",
        "dbp": r"(?:舒张压|低压|下压|dbp|DBP)[：:\s]*(\d+)",
        "bp": r"(?:血压|bp|BP)[：:\s]*(\d+)\s*[/／]\s*(\d+)",
        "bp_alt": r"(?:收缩压|高压|上压)[：:\s]*(\d+).{0,15}(?:舒张压|低压|下压)[：:\s]*(\d+)",
        "fetal_movement": r"(?:胎动|宝宝.{0,5}动|宝宝.{0,5}踢|宝宝.{0,5}[动踢])[^\d]*(\d+)\s*(?:次|下)?",
        "blood_sugar": r"(?:血糖|糖)[：:\s]*(\d+\.?\d*)",
        "heart_rate": r"(?:心率|脉搏|心跳)[：:\s]*(\d+)",
        "sleep_hours": r"(?:睡眠|睡了|睡觉)[^\d]*(\d+\.?\d*)\s*(?:小时|个?小时|h)",
    }

    # 紧急关键词
    EMERGENCY_KEYWORDS = [
        "大出血", "剧烈腹痛", "昏倒", "昏迷", "呼吸困难",
        "休克", "急诊",
        # 产科急症
        "羊水栓塞", "胎盘早剥", "宫外孕", "异位妊娠",
        "脐带脱垂", "子痫", "胎膜早破", "前置胎盘",
        "大出血不止", "阴道大量出血", "剧烈宫缩",
    ]
    # 需要上下文的紧急关键词（避免"120"被血压值误匹配）
    EMERGENCY_CONTEXT_PATTERNS = [
        r"(?:打|拨打|叫|拨)\s*120",
        r"120\s*(?:急救|救护车)",
    ]
    SUICIDE_KEYWORDS = [
        "自杀", "不想活", "想死", "活着没意思", "割腕", "跳楼",
        "吃药自杀", "遗书", "解脱", "活不下去", "不想面对",
        "想结束一切", "没有意义", "不如死了", "轻生",
    ]

    # 分类关键词（从 intent_classifier.py 迁移）
    _ANALYZE_KEYWORDS = ("分析", "评估", "解读", "看看", "怎么样", "情况如何")
    _KNOWLEDGE_KEYWORDS = ("指南", "标准", "什么是", "怎么算", "正常范围", "知识")
    _FOLLOWUP_KEYWORDS = ("随访", "回访", "打电话", "问卷")
    _ALERT_KEYWORDS = ("预警", "告警", "异常")
    _REPORT_KEYWORDS = ("上报医生", "通知医生", "转医生", "escalate")

    def parse(self, text: str) -> NLUResult:
        """解析用户输入，返回意图、实体和情绪"""
        entities = {}
        is_emergency = False

        # 0. 中文数字预处理（用于实体提取）
        normalized = _cn_to_arabic(text)

        # 1. 提取实体（在预处理后的文本上匹配）
        for key, pattern in self.ENTITY_PATTERNS.items():
            if key == "bp_alt":
                # bp_alt 是血压的备用匹配，只在 bp 未匹配到时使用
                if "sbp" in entities:
                    continue
                match = re.search(pattern, normalized)
                if match:
                    entities["sbp"] = float(match.group(1))
                    entities["dbp"] = float(match.group(2))
                continue
            match = re.search(pattern, normalized)
            if match:
                if key == "bp":
                    entities["sbp"] = float(match.group(1))
                    entities["dbp"] = float(match.group(2))
                else:
                    value = float(match.group(1))
                    if key == "weight" and ("斤" in text):
                        value = value / 2  # 斤转kg
                    entities[key] = value

        # 2. 紧急检测
        for kw in self.EMERGENCY_KEYWORDS:
            if kw in text:
                is_emergency = True
                break
        if not is_emergency:
            for pattern in self.EMERGENCY_CONTEXT_PATTERNS:
                if re.search(pattern, text):
                    is_emergency = True
                    break

        for kw in self.SUICIDE_KEYWORDS:
            if kw in text:
                return NLUResult(
                    intent="SUICIDE_RISK",
                    entities=entities,
                    is_emergency=True,
                    category=IntentCategory.EMERGENCY
                )

        if is_emergency:
            return NLUResult(
                intent="EMERGENCY",
                entities=entities,
                is_emergency=True,
                category=IntentCategory.EMERGENCY
            )

        # 3. 意图识别
        intent = "UNKNOWN"
        for intent_name, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    intent = intent_name
                    break
            if intent != "UNKNOWN":
                break

        # 4. 情绪分析
        emotion = self._analyze_emotion(text)

        # 5. 高层意图分类
        category = self._classify_category(intent, entities, text)

        # 6. 工具推荐
        suggested_tools = self._suggest_tools(intent, entities, text)

        return NLUResult(intent=intent, entities=entities, emotion=emotion,
                         category=category, suggested_tools=suggested_tools)

    def _classify_category(self, intent: str, entities: dict,
                           text: str = "") -> IntentCategory:
        """基于 NLU 意图 + 关键词的高层意图分类"""
        # 紧急优先
        if intent in ("EMERGENCY", "SUICIDE_RISK"):
            return IntentCategory.EMERGENCY

        # NLU 意图直接映射
        _INTENT_MAP = {
            "HEALTH_DATA_REPORT": IntentCategory.CHAT,
            "EMOTION_EXPRESS": IntentCategory.CHAT,
            "GREETING": IntentCategory.CHAT,
            "KNOWLEDGE_QUERY": IntentCategory.KNOWLEDGE,
            "SCHEDULE_INQUIRY": IntentCategory.CHAT,
        }
        if intent in _INTENT_MAP:
            return _INTENT_MAP[intent]

        # UNKNOWN 意图：使用关键词补充分类
        if text:
            if any(kw in text for kw in self._REPORT_KEYWORDS):
                return IntentCategory.REPORT
            if any(kw in text for kw in self._ALERT_KEYWORDS):
                return IntentCategory.ALERT
            if any(kw in text for kw in self._FOLLOWUP_KEYWORDS):
                return IntentCategory.FOLLOWUP
            if any(kw in text for kw in self._ANALYZE_KEYWORDS):
                return IntentCategory.ANALYZE
            if any(kw in text for kw in self._KNOWLEDGE_KEYWORDS):
                return IntentCategory.KNOWLEDGE

        return IntentCategory.CHAT

    # 工具推荐关键词
    _TREND_KEYWORDS = ("趋势", "变化", "走势", "对比", "最近", "历史")
    _ASSESS_KEYWORDS = ("评估", "规则", "正常", "是否正常", "有没有问题")
    _EPDS_KEYWORDS = ("心理", "抑郁", "情绪评估", "epds", "EPDS", "心理测试")
    _KNOW_TOOL_KEYWORDS = ("知识", "什么", "怎么", "指南", "能不能吃", "注意事项")

    def _suggest_tools(self, intent: str, entities: dict, text: str) -> list[str]:
        """根据实体和关键词推荐具体工具，供 Agent 优先调用。"""
        tools: list[str] = []

        # 有健康数据实体 → 建议保存
        data_entities = {"weight", "sbp", "dbp", "fetal_movement", "blood_sugar", "heart_rate", "sleep_hours"}
        if data_entities & set(entities.keys()):
            tools.append("agno_save_health_data")

        # 意图 + 关键词 → 具体工具推荐
        if intent == "HEALTH_DATA_REPORT" or any(kw in text for kw in self._TREND_KEYWORDS):
            tools.append("agno_analyze_health_trends")

        if any(kw in text for kw in self._ASSESS_KEYWORDS):
            tools.append("agno_evaluate_vital_rules")

        if any(kw in text for kw in self._EPDS_KEYWORDS):
            tools.append("agno_get_epds_result")

        if intent == "KNOWLEDGE_QUERY" or any(kw in text for kw in self._KNOW_TOOL_KEYWORDS):
            tools.append("agno_search_knowledge")

        # 去重保序
        seen = set()
        unique = []
        for t in tools:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique

    def classify_with_llm(self, text: str) -> str:
        """LLM 辅助意图分类（仅在规则引擎返回 UNKNOWN 时调用）。

        使用项目配置的 LLM 做极简分类，max_tokens=30。
        Returns:
            重新判定的 NLU intent 字符串，失败时返回 "UNKNOWN"。
        """
        try:
            from agno.models.message import Message
            from .agno_client import get_agno_model
            model = get_agno_model(role="pregnant")

            classify_msg = Message(
                role="user",
                content=(
                    "判断用户消息的意图，只返回一个标签（不要解释）：\n"
                    "HEALTH_DATA_REPORT / EMOTION_EXPRESS / KNOWLEDGE_QUERY / "
                    "SCHEDULE_INQUIRY / GREETING / UNKNOWN\n"
                    f"消息：{text[:100]}"
                ),
            )

            response = model.generate(
                messages=[classify_msg],
                max_tokens=30,
            )
            result_text = ""
            if hasattr(response, "content") and response.content:
                result_text = response.content.strip().upper()
            elif hasattr(response, "text"):
                result_text = response.text.strip().upper()

            valid_intents = {
                "HEALTH_DATA_REPORT", "EMOTION_EXPRESS", "KNOWLEDGE_QUERY",
                "SCHEDULE_INQUIRY", "GREETING", "UNKNOWN",
            }
            if result_text in valid_intents:
                return result_text
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def _analyze_emotion(self, text: str) -> dict:
        """简单情绪分析（含否定词过滤）"""
        anxiety_words = ["焦虑", "紧张", "担心", "害怕", "不安", "压力"]
        sad_words = ["难过", "抑郁", "伤心", "孤独", "低落", "沮丧"]
        positive_words = ["开心", "高兴", "很好", "不错", "好", "棒", "愉快", "幸福"]

        anxiety_score = sum(1 for w in anxiety_words if w in text)
        sad_score = sum(1 for w in sad_words if w in text)
        # 否定前缀过滤：不/没/别 + 正面词 = 非正面
        positive_score = sum(
            1 for w in positive_words
            if w in text and not re.search(rf'(不|没|别|无){re.escape(w)}', text)
        )

        if anxiety_score > 0 or sad_score > 0:
            total = anxiety_score + sad_score
            if total >= 2:
                return {"level": "high", "score": total, "label": "需要关注"}
            return {"level": "medium", "score": total, "label": "轻微情绪波动"}
        if positive_score > 0:
            return {"level": "positive", "score": 0, "label": "情绪积极"}

        return {"level": "neutral", "score": 0, "label": "平稳"}


# 全局单例
nlu_engine = RuleBaseNLU()
