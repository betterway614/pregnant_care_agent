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
    found_any = False  # 标记是否识别到了任何数字
    # 处理"X百Y十Z"格式
    if "百" in s:
        parts = s.split("百", 1)
        hundred_part = parts[0] or "一"  # "百"前无数字默认"一"
        digit = _CN_DIGITS.get(hundred_part, 0)
        if digit > 0 or hundred_part in _CN_DIGITS:
            found_any = True
        result += digit * 100
        s = parts[1]
    if "十" in s:
        parts = s.split("十", 1)
        ten_part = parts[0] or "一"  # "十"前无数字默认"一"
        digit = _CN_DIGITS.get(ten_part, 0)
        if digit > 0 or ten_part in _CN_DIGITS:
            found_any = True
        result += digit * 10
        s = parts[1]
    if s:
        digit = _CN_DIGITS.get(s, 0)
        if s in _CN_DIGITS:
            found_any = True
        result += digit
    return result if found_any else None


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
    # ═══════════════════════════════════════════════════════════════
    # KNOWLEDGE_QUERY 门控策略:
    #   必须同时满足「医学主题词 + 疑问句式」才触发知识检索，
    #   避免"今天怎么办"、"我需要记录什么"等日常对话误触发 RAG。
    #   顺序按优先级排列，匹配即停止。
    # ═══════════════════════════════════════════════════════════════
    _MEDICAL_TOPICS = (
        # 通用孕期上下文
        "孕期|怀孕|孕早|孕中|孕晚|孕妇|产妇|胎儿|宝宝|"
        # 疾病/症状
        "糖尿病|GDM|子痫|贫血|贫血|黄疸|水肿|出血|感染|HELLP|ICP|"
        "前置胎盘|胎盘早剥|脐带脱垂|宫外孕|异位妊娠|羊水|胎膜早破|"
        "早产|流产|畸形|染色体|遗传|"
        # 检查/指标
        "唐筛|唐氏|NIPT|NT|OGTT|糖耐|糖筛|大排畸|小排畸|B超|四维|"
        "无创|羊穿|羊水穿刺|脐血|胎心监护|NST|胎监|"
        "血压|血糖|血红蛋白|血小板|TSH|甲功|肝功能|肾功能|尿蛋白|"
        # 用药/营养
        "叶酸|钙片|铁剂|DHA|维生素|阿司匹林|胰岛素|二甲双胍|拉贝洛尔|"
        "硝苯地平|硫酸镁|疫苗|流感|Tdap|百白破|用药|吃药|药物|禁忌|副作用|"
        "咖啡|酒精|抽烟|吸烟|海鲜|生鱼片|"
        # 孕期知识
        "胎动|孕周|预产期|分娩|顺产|剖腹产|剖宫产|无痛|硬膜外|"
        "产后|恶露|盆底|凯格尔|母乳|奶粉|喂养|新生儿|脐带|"
        # 指南/标准
        "正常值|正常范围|标准|指南|诊断|指标|参考值|多少算|"
        "注意事项|能不能吃|可以吃吗|安全吗|有影响吗|可以吗"
    )

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
            # 优先级 1: 医学主题 + 疑问词/模态词 (双向匹配, 任意顺序)
            #   主题在前: "叶酸要吃多久" → 叶酸(topic).*?多久(疑问) → ✅
            #   疑问在前: "能喝咖啡吗" → 能(modal).*?咖啡(topic) → ✅
            rf"(?:{_MEDICAL_TOPICS}).*?(什么|怎么|为什么|如何|能否|能|可以|可|需要|应该|会|有|多少|多久|哪些|几周|几个月|什么时候|有没有|会不会|是什么|叫什么|怎么办|严重吗|危险吗|有影响吗|可以吗)",
            rf"(什么|怎么|为什么|如何|能|可以|可|会|需要|应该|多少|多久|哪些|几周|有没有|会不会|能不能).*?(?:{_MEDICAL_TOPICS})",
            # 优先级 2: 医学操作/指南类 (自带医学上下文, 无需疑问词)
            r"(饮食|运动|睡觉|吃药|检查|注意事项|禁忌|副作用|诊断|标准|指南)",
            # 优先级 3: 安全/可行性咨询句式 (匹配 能不能|可以吃吗|安全吗 等)
            r"(能不能|可不可以|要不要|有没有影响|可以吃吗|安全吗|可以吗|能吃吗|能喝吗|会.*?影响)",
            # 优先级 4: 正常值/标准查询
            r"(正常.*?(范围|值|标准)|标准.*?(是|为).*?(多少|什么))",
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
            r"(你是谁|你有什么功能|你能做什么|你会什么|你可以做什么|介绍一下自己|你能干嘛|你有什么能力|你能帮我什么|你都会什么|你能干啥|你叫什么|你是什么)",
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
        "脐带脱垂", "胎膜早破", "前置胎盘",
        "大出血不止", "阴道大量出血", "剧烈宫缩",
        # "子痫" 仅在非"子痫前期"语境下触发 (子痫=抽搐，是急症；子痫前期≠抽搐)
    ]
    # 需要上下文判断的紧急模式 (避免子痫前期误触)
    EMERGENCY_CTX_PRECISE: list[str] = [
        r"(?<!\w)子痫(?!前期)",   # 单独的"子痫"而非"子痫前期"
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
        if not is_emergency:
            for pattern in self.EMERGENCY_CTX_PRECISE:
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

        # GREETING 意图不推荐工具（用户可能在寒暄或询问功能）
        if intent == "GREETING":
            return []

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

    # LLM 分类 — 统一意图空间（与规则引擎 parse() 一致）
    _LLM_CLASSIFY_INTENTS = (
        "HEALTH_DATA_REPORT / EMOTION_EXPRESS / KNOWLEDGE_QUERY / "
        "SCHEDULE_INQUIRY / GREETING"
    )
    _LLM_CLASSIFY_VALID = {
        "HEALTH_DATA_REPORT", "EMOTION_EXPRESS", "KNOWLEDGE_QUERY",
        "SCHEDULE_INQUIRY", "GREETING",
    }
    _LLM_CLASSIFY_HINTS = {
        "HEALTH": "HEALTH_DATA_REPORT", "体重": "HEALTH_DATA_REPORT", "血压": "HEALTH_DATA_REPORT", "记录": "HEALTH_DATA_REPORT",
        "EMOTION": "EMOTION_EXPRESS", "焦虑": "EMOTION_EXPRESS", "心情": "EMOTION_EXPRESS", "情绪": "EMOTION_EXPRESS",
        "KNOWLEDGE": "KNOWLEDGE_QUERY", "知识": "KNOWLEDGE_QUERY", "什么": "KNOWLEDGE_QUERY", "怎么": "KNOWLEDGE_QUERY",
        "SCHEDULE": "SCHEDULE_INQUIRY", "产检": "SCHEDULE_INQUIRY", "预约": "SCHEDULE_INQUIRY",
        "GREETING": "GREETING", "你好": "GREETING", "嗨": "GREETING", "你是谁": "GREETING", "功能": "GREETING",
    }

    def classify_with_llm(self, text: str, role: str = "pregnant") -> str:
        """LLM 辅助意图分类（仅在规则引擎返回 UNKNOWN 时调用）。

        统一使用与规则引擎一致的通用意图空间。role 仅影响选用哪个角色的 LLM 模型。
        意图→变体的路由映射由 routing.py 按角色处理。

        Args:
            text: 用户输入文本
            role: 角色标识 (pregnant/nurse/doctor)，仅用于选择 LLM 模型
        Returns:
            重新判定的 NLU intent 字符串，失败时返回 "UNKNOWN"。
        """
        try:
            from agno.models.message import Message
            from .agno_client import get_agno_model
            model = get_agno_model(role=role)

            classify_msg = Message(
                role="user",
                content=(
                    "判断用户消息的意图，只返回一个标签（不要解释）：\n"
                    f"{self._LLM_CLASSIFY_INTENTS} / UNKNOWN\n"
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

            # 提取有效意图标签
            for intent in self._LLM_CLASSIFY_VALID:
                if intent in result_text:
                    return intent
            # 模糊推断（兜底）
            for hint_kw, hint_intent in self._LLM_CLASSIFY_HINTS.items():
                if hint_kw in result_text:
                    return hint_intent
            return "UNKNOWN"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("LLM意图分类失败 role=%s text=%s: %s", role, text[:50], exc)
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
