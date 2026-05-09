"""随访服务"""
import re
from typing import Optional


# 随访模板
FOLLOWUP_TEMPLATES = {
    "standard": {
        "name": "标准随访",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有不舒服的地方？"},
            {"key": "weight", "question": "今天的体重是多少？"},
            {"key": "bp", "question": "血压有测量吗？数值是多少？"},
            {"key": "fetal_movement", "question": "最近胎动感觉如何？每小时大概几次？"},
            {"key": "diet", "question": "饮食和睡眠情况如何？"},
        ]
    },
    "fgr_high_risk": {
        "name": "FGR高危随访",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有腹痛或其他不适？"},
            {"key": "fetal_movement", "question": "请详细描述近24小时胎动情况？"},
            {"key": "weight", "question": "今天的体重是多少？"},
            {"key": "bp", "question": "血压测量结果如何？"},
            {"key": "medication", "question": "是否按时使用医生开的药物？"},
        ]
    },
    "post_discharge": {
        "name": "出院后随访",
        "questions": [
            {"key": "feeling", "question": "出院后感觉如何？"},
            {"key": "wound", "question": "伤口愈合情况如何？"},
            {"key": "bp", "question": "血压是否正常？"},
            {"key": "medication", "question": "是否按时服药？"},
        ]
    }
}


class FollowUpService:
    """随访服务"""

    def get_template(self, template_id: str = "standard") -> dict:
        """获取随访模板"""
        return FOLLOWUP_TEMPLATES.get(template_id, FOLLOWUP_TEMPLATES["standard"])

    def get_template_from_questions(self, answered: dict) -> dict:
        """根据已回答的 key 反向推断最适合的模板"""
        keys = set(answered.keys())
        best_match = "standard"
        max_overlap = 0
        for tmpl_id, tmpl in FOLLOWUP_TEMPLATES.items():
            tmpl_keys = {q["key"] for q in tmpl["questions"]}
            overlap = len(keys & tmpl_keys)
            if overlap > max_overlap:
                max_overlap = overlap
                best_match = tmpl_id
        return self.get_template(best_match)

    def extract_health_value(self, question_key: str, answer_text: str) -> Optional[dict]:
        """从回答文本中提取可量化的健康数据"""
        extractors = {
            "weight": [
                (r"(\d+\.?\d*)\s*(kg|公斤)", lambda m: {
                    "metric_code": "weight", "value": float(m.group(1)), "unit": "kg"
                }),
                (r"(\d+\.?\d*)\s*(斤)", lambda m: {
                    "metric_code": "weight", "value": float(m.group(1)) / 2, "unit": "kg"
                }),
            ],
            "bp": [
                (r"(\d{2,3})\s*/\s*(\d{2,3})", lambda m: {
                    "sbp": float(m.group(1)), "dbp": float(m.group(2)),
                }),
            ],
            "fetal_movement": [
                (r"(\d+)\s*(次|回)", lambda m: {
                    "metric_code": "fetal_movement", "value": float(m.group(1)), "unit": "次/小时"
                }),
            ],
        }
        patterns = extractors.get(question_key)
        if not patterns:
            return None
        for pattern, builder in patterns:
            match = re.search(pattern, answer_text)
            if match:
                return builder(match)
        return None

    def generate_record_summary(self, patient_name: str, gest_week: str,
                                 answers: dict) -> str:
        """根据对话答案生成随访摘要"""
        summary_parts = [f"【{patient_name}】孕{gest_week}周随访"]
        if answers.get("feeling"):
            summary_parts.append(f"主诉：{answers['feeling']}")
        if answers.get("weight"):
            summary_parts.append(f"体重：{answers['weight']}kg")
        if answers.get("bp"):
            summary_parts.append(f"血压：{answers['bp']}")
        if answers.get("fetal_movement"):
            summary_parts.append(f"胎动：{answers['fetal_movement']}次/小时")
        return " | ".join(summary_parts)

    def generate_health_education(self, gest_week: int, risk_tags: list[str] = None) -> list[str]:
        """根据孕周生成健康教育内容"""
        education = []
        risk_tags = risk_tags or []

        if gest_week <= 12:
            education.append("早孕期保健指导：补充叶酸，避免剧烈运动")
            education.append("早孕期常见不适及应对方法")
        elif gest_week <= 28:
            education.append("中孕期营养指导：均衡饮食，控制体重增长")
            education.append("胎动计数方法指导")
            if "FGR" in risk_tags:
                education.append("FGR高危管理：加强营养，定期B超监测")
        else:
            education.append("晚孕期保健指导：左侧卧位休息，注意临产征兆")
            education.append("分娩准备指导")
            if "高血压" in risk_tags:
                education.append("高血压管理：低盐饮食，监测血压")

        return education


followup_service = FollowUpService()
