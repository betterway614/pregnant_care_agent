"""NLU引擎 - 意图识别、实体提取、情绪分析"""
import re
from typing import Optional


class NLUResult:
    """NLU解析结果"""
    def __init__(self, intent: str = "", entities: dict = None,
                 emotion: Optional[dict] = None, is_emergency: bool = False):
        self.intent = intent
        self.entities = entities or {}
        self.emotion = emotion or {"level": "neutral", "score": 0}
        self.is_emergency = is_emergency


class RuleBaseNLU:
    """基于规则的NLU引擎（轻量，CPU运行）"""

    # 意图识别模式
    INTENT_PATTERNS = {
        "HEALTH_DATA_REPORT": [
            r"(体重|血压|胎动|血糖|心率).*?(\d+)",
            r"(\d+\.?\d*)\s*(kg|斤|mmHg|次)",
        ],
        "EMOTION_EXPRESS": [
            r"(焦虑|紧张|害怕|担心|抑郁|难过|失眠|压力)",
            r"(不开心|好烦|睡不着|很累)",
        ],
        "KNOWLEDGE_QUERY": [
            r"(什么|怎么|为什么|能否|可以|需要|应该)",
            r"(饮食|运动|睡觉|吃药|检查|注意事项)",
        ],
        "SCHEDULE_INQUIRY": [
            r"(产检|检查|预约|什么时候|提醒)",
        ],
        "EMERGENCY": [
            r"(大出血|剧烈腹痛|昏倒|昏迷|呼吸困难|休克)",
            r"(急诊|120|救护车)",
        ],
        "SUICIDE_RISK": [
            r"(自杀|不想活|想死|活着没意思)",
        ],
        "GREETING": [
            r"^(你好|您好|嗨|hi|hello|早上好|下午好|晚上好)",
        ],
    }

    # 实体提取模式
    ENTITY_PATTERNS = {
        "weight": r"(\d+\.?\d*)\s*(kg|斤|千克)",
        "sbp": r"收缩压[：:\s]*(\d+)",
        "dbp": r"舒张压[：:\s]*(\d+)",
        "bp": r"血压[：:\s]*(\d+)/(\d+)",
        "fetal_movement": r"胎动[：:\s]*(\d+)",
        "blood_sugar": r"血糖[：:\s]*(\d+\.?\d*)",
        "heart_rate": r"心率[：:\s]*(\d+)",
        "sleep_hours": r"睡眠[：:\s]*(\d+\.?\d*)\s*小时",
    }

    # 紧急关键词
    EMERGENCY_KEYWORDS = [
        "大出血", "剧烈腹痛", "昏倒", "昏迷", "呼吸困难",
        "休克", "急诊", "120",
    ]
    SUICIDE_KEYWORDS = ["自杀", "不想活", "想死", "活着没意思"]

    def parse(self, text: str) -> NLUResult:
        """解析用户输入，返回意图、实体和情绪"""
        entities = {}
        is_emergency = False

        # 1. 提取实体
        for key, pattern in self.ENTITY_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                if key == "bp":
                    entities["sbp"] = float(match.group(1))
                    entities["dbp"] = float(match.group(2))
                else:
                    value = float(match.group(1))
                    if key == "weight" and "斤" in text:
                        value = value / 2  # 斤转kg
                    entities[key] = value

        # 2. 紧急检测
        for kw in self.EMERGENCY_KEYWORDS:
            if kw in text:
                is_emergency = True
                break

        for kw in self.SUICIDE_KEYWORDS:
            if kw in text:
                return NLUResult(
                    intent="SUICIDE_RISK",
                    entities=entities,
                    is_emergency=True
                )

        if is_emergency:
            return NLUResult(
                intent="EMERGENCY",
                entities=entities,
                is_emergency=True
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

        return NLUResult(intent=intent, entities=entities, emotion=emotion)

    def _analyze_emotion(self, text: str) -> dict:
        """简单情绪分析"""
        anxiety_words = ["焦虑", "紧张", "担心", "害怕", "不安", "压力"]
        sad_words = ["难过", "抑郁", "伤心", "孤独", "低落", "沮丧"]
        positive_words = ["开心", "高兴", "很好", "不错", "好", "棒"]

        anxiety_score = sum(1 for w in anxiety_words if w in text)
        sad_score = sum(1 for w in sad_words if w in text)
        positive_score = sum(1 for w in positive_words if w in text)

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
