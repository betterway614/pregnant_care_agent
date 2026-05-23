"""随访服务

随访模板覆盖 8 种场景，基于以下医学指南设计：
- 《孕前和孕期保健指南》— 国家卫健委
- 《妊娠期高血糖诊治指南(2022)》— 中华医学会妇产科学分会产科学组
- 《妊娠期高血压疾病诊治指南(2020)》— 中华医学会
- FGR相关共识 — 中华医学会围产医学分会
- EPDS量表规范 — Cox JL等

每种模板包含：
- questions: 问题列表（key + question + type + unit）
- type 枚举: text / number / select / scale
- 用于前端渲染不同输入控件和后端结构化解析
"""
import re
from typing import Optional

# 字段标签映射（用于归档文档生成）
FIELD_LABELS = {
    "weight": "体重", "bp": "血压", "fetal_movement": "胎动", "diet": "饮食",
    "mood": "情绪", "sleep": "睡眠", "stress": "压力", "medication": "用药",
    "nausea": "孕吐", "feeling": "感受", "blood_sugar_fasting": "空腹血糖",
    "blood_sugar_postprandial": "餐后血糖", "blood_sugar_2h": "餐后血糖",
    "sleep_quality": "睡眠质量", "exercise": "运动", "edema": "水肿",
    "support": "社会支持", "coping": "应对方式",
}

EXAM_LABELS = {
    "fundal_height_cm": "宫高(cm)", "abdominal_circumference_cm": "腹围(cm)",
    "fetal_position": "胎位", "fetal_heart_rate_bpm": "胎心率(bpm)",
    "blood_pressure": "血压(mmHg)",
}

LAB_LABELS = {
    "hemoglobin_g_L": "血红蛋白(g/L)", "urine_protein": "尿蛋白",
    "blood_sugar_fasting": "空腹血糖(mmol/L)", "blood_sugar_2h": "餐后血糖(mmol/L)",
}


# 随访模板
FOLLOWUP_TEMPLATES = {
    "standard": {
        "name": "标准随访",
        "description": "适用于低风险孕妇的常规随访（依据：《孕前和孕期保健指南》）",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有不舒服的地方？", "type": "text"},
            {"key": "weight", "question": "今天的体重是多少？（公斤）", "type": "number", "unit": "kg"},
            {"key": "bp", "question": "血压有测量吗？数值是多少？（如 120/80）", "type": "text", "format": "sbp/dbp"},
            {"key": "fetal_movement", "question": "最近胎动感觉如何？每小时大概几次？", "type": "number", "unit": "次/小时"},
            {"key": "diet", "question": "饮食和睡眠情况如何？", "type": "text"},
        ]
    },
    "fgr_high_risk": {
        "name": "FGR高危随访",
        "description": "适用于胎儿生长受限高危孕妇，侧重孕妇可自测的指标",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有腹痛或其他不适？", "type": "text"},
            {"key": "fetal_movement", "question": "请详细描述近24小时胎动情况？每天早中晚各数1小时，每小时大概几次？", "type": "text"},
            {"key": "weight", "question": "今天的体重是多少？（公斤）", "type": "number", "unit": "kg"},
            {"key": "bp", "question": "血压测量结果如何？（如 120/80）", "type": "text", "format": "sbp/dbp"},
            {"key": "position", "question": "是否有左侧卧位休息？每天大约多长时间？", "type": "text"},
            {"key": "nutrition", "question": "最近饮食情况如何？有没有保证高蛋白摄入？", "type": "text"},
        ]
    },
    "post_discharge": {
        "name": "出院后随访",
        "description": "适用于产后出院的产妇",
        "questions": [
            {"key": "feeling", "question": "出院后感觉如何？", "type": "text"},
            {"key": "wound", "question": "伤口愈合情况如何？有无红肿、渗液？", "type": "text"},
            {"key": "bp", "question": "血压是否正常？（如 120/80）", "type": "text", "format": "sbp/dbp"},
            {"key": "bleeding", "question": "恶露量如何？颜色正常吗？", "type": "text"},
            {"key": "breastfeeding", "question": "母乳喂养顺利吗？有没有涨奶或乳头疼痛？", "type": "text"},
            {"key": "medication", "question": "是否按时服药？", "type": "text"},
        ]
    },
    "gdm": {
        "name": "妊娠期糖尿病随访",
        "description": "适用于确诊GDM的孕妇（依据：《妊娠期高血糖诊治指南(2022)》）",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有头晕、心慌、出汗等低血糖症状？", "type": "text"},
            {"key": "blood_sugar_fasting", "question": "今早空腹血糖是多少？（mmol/L，目标≤5.3）", "type": "number", "unit": "mmol/L"},
            {"key": "blood_sugar_postprandial", "question": "餐后2小时血糖是多少？（mmol/L，目标≤6.7）", "type": "number", "unit": "mmol/L"},
            {"key": "diet", "question": "最近饮食控制情况如何？有无严格执行糖尿病饮食？", "type": "text"},
            {"key": "weight", "question": "今天的体重是多少？（公斤）", "type": "number", "unit": "kg"},
            {"key": "fetal_movement", "question": "最近胎动感觉如何？", "type": "text"},
            {"key": "exercise", "question": "最近有运动吗？每天大约多少分钟？建议餐后散步30分钟。", "type": "text"},
        ]
    },
    "hypertension": {
        "name": "妊娠期高血压随访",
        "description": "适用于妊娠期高血压或子痫前期孕妇（依据：《妊娠期高血压疾病诊治指南(2020)》）",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有头痛、眼花、上腹痛、恶心呕吐等症状？", "type": "text"},
            {"key": "bp", "question": "今天血压是多少？（如 140/90，SBP≥140 或 DBP≥90 需警惕）", "type": "text", "format": "sbp/dbp"},
            {"key": "bp_morning", "question": "今早血压是多少？（如 130/85）", "type": "text", "format": "sbp/dbp"},
            {"key": "bp_evening", "question": "今晚血压是多少？（如 135/88）", "type": "text", "format": "sbp/dbp"},
            {"key": "weight", "question": "今天的体重是多少？（公斤，1周增>1kg需警惕）", "type": "number", "unit": "kg"},
            {"key": "edema", "question": "手脚有没有肿胀？程度如何？面部有没有肿？", "type": "text"},
            {"key": "fetal_movement", "question": "最近胎动感觉如何？", "type": "text"},
            {"key": "urine", "question": "尿量有没有变化？有没有泡沫尿？", "type": "text"},
            {"key": "medication", "question": "是否按时服用降压药？有无不适？", "type": "text"},
        ]
    },
    "mental_health": {
        "name": "心理健康随访",
        "description": "适用于EPDS筛查中高风险或主动求助的孕妇（依据：EPDS量表规范）",
        "questions": [
            {"key": "mood", "question": "最近心情怎么样？有没有感到焦虑或低落？", "type": "text"},
            {"key": "sleep", "question": "最近睡眠质量如何？每晚大概睡几个小时？", "type": "number", "unit": "小时"},
            {"key": "appetite", "question": "食欲有没有变化？是增加还是减少？", "type": "text"},
            {"key": "support", "question": "身边有人陪伴和支持吗？和家人关系如何？", "type": "text"},
            {"key": "stress", "question": "最近最大的压力或困扰是什么？", "type": "text"},
            {"key": "coping", "question": "平时用什么方式缓解压力？有没有觉得喘不过气？", "type": "text"},
            {"key": "self_harm", "question": "有没有伤害自己的想法？（如有，请务必告知）", "type": "text"},
        ]
    },
    "early_pregnancy": {
        "name": "孕早期随访",
        "description": "适用于孕12周以内的孕妇（依据：《孕前和孕期保健指南》）",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有恶心、呕吐等早孕反应？", "type": "text"},
            {"key": "nausea", "question": "恶心呕吐严重吗？能正常进食吗？一天能吃几顿饭？", "type": "text"},
            {"key": "bleeding", "question": "有没有阴道出血或褐色分泌物？", "type": "text"},
            {"key": "weight", "question": "现在的体重是多少？（公斤）", "type": "number", "unit": "kg"},
            {"key": "supplement", "question": "有没有在补充叶酸？每天多少剂量？（建议0.4-0.8mg/天）", "type": "text"},
        ]
    },
    "late_pregnancy": {
        "name": "孕晚期随访",
        "description": "适用于孕36周以上的孕妇（依据：《孕前和孕期保健指南》）",
        "questions": [
            {"key": "feeling", "question": "最近感觉怎么样？有没有宫缩、腹痛？", "type": "text"},
            {"key": "fetal_movement", "question": "最近胎动感觉如何？每小时大概几次？（应≥3次/小时）", "type": "number", "unit": "次/小时"},
            {"key": "contraction", "question": "有没有感觉到宫缩？频率大约是多少？是否规律？", "type": "text"},
            {"key": "weight", "question": "今天的体重是多少？（公斤）", "type": "number", "unit": "kg"},
            {"key": "bp", "question": "血压测量了吗？（如 120/80）", "type": "text", "format": "sbp/dbp"},
            {"key": "edema", "question": "有没有水肿？手脚肿胀程度如何？", "type": "text"},
            {"key": "preparation", "question": "待产包准备好了吗？分娩计划有没有和医生讨论？", "type": "text"},
            {"key": "signs", "question": "有没有见红、破水、规律宫缩等临产征兆？", "type": "text"},
        ]
    },
}


class FollowUpService:
    """随访服务"""

    def get_template(self, template_id: str = "standard") -> dict:
        """获取随访模板"""
        return FOLLOWUP_TEMPLATES.get(template_id, FOLLOWUP_TEMPLATES["standard"])

    def select_template(self, risk_tags: list[str] = None, gest_week: int = 20) -> tuple[str, dict]:
        """根据风险标签和孕周自动选择最合适的随访模板

        返回 (template_id, template_dict)
        """
        risk_tags = risk_tags or []

        # 按优先级匹配
        if any(t in risk_tags for t in ("GDM", "妊娠期糖尿病")):
            return "gdm", FOLLOWUP_TEMPLATES["gdm"]
        if any(t in risk_tags for t in ("高血压", "妊娠期高血压", "子痫前期")):
            return "hypertension", FOLLOWUP_TEMPLATES["hypertension"]
        if any(t in risk_tags for t in ("FGR", "FGR高危")):
            return "fgr_high_risk", FOLLOWUP_TEMPLATES["fgr_high_risk"]
        if any(t in risk_tags for t in ("心理健康", "抑郁风险")):
            return "mental_health", FOLLOWUP_TEMPLATES["mental_health"]

        # 按孕周匹配
        if gest_week < 12:
            return "early_pregnancy", FOLLOWUP_TEMPLATES["early_pregnancy"]
        if gest_week >= 36:
            return "late_pregnancy", FOLLOWUP_TEMPLATES["late_pregnancy"]

        return "standard", FOLLOWUP_TEMPLATES["standard"]

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
            "bp_morning": [
                (r"(\d{2,3})\s*/\s*(\d{2,3})", lambda m: {
                    "sbp": float(m.group(1)), "dbp": float(m.group(2)),
                }),
            ],
            "bp_evening": [
                (r"(\d{2,3})\s*/\s*(\d{2,3})", lambda m: {
                    "sbp": float(m.group(1)), "dbp": float(m.group(2)),
                }),
            ],
            "fetal_movement": [
                (r"(\d+)\s*(次|回)", lambda m: {
                    "metric_code": "fetal_movement", "value": float(m.group(1)), "unit": "次/小时"
                }),
            ],
            "blood_sugar_fasting": [
                (r"(\d+\.?\d*)", lambda m: {
                    "metric_code": "blood_sugar_fasting", "value": float(m.group(1)), "unit": "mmol/L"
                }),
            ],
            "blood_sugar_postprandial": [
                (r"(\d+\.?\d*)", lambda m: {
                    "metric_code": "blood_sugar_postprandial", "value": float(m.group(1)), "unit": "mmol/L"
                }),
            ],
            "sleep": [
                (r"(\d+\.?\d*)\s*(小时|个?小时|h)", lambda m: {
                    "metric_code": "sleep_hours", "value": float(m.group(1)), "unit": "小时"
                }),
                (r"(\d+\.?\d*)", lambda m: {
                    "metric_code": "sleep_hours", "value": float(m.group(1)), "unit": "小时"
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
            summary_parts.append(f"体重：{answers['weight']}")
        if answers.get("bp"):
            summary_parts.append(f"血压：{answers['bp']}")
        if answers.get("bp_morning"):
            summary_parts.append(f"晨血压：{answers['bp_morning']}")
        if answers.get("bp_evening"):
            summary_parts.append(f"晚血压：{answers['bp_evening']}")
        if answers.get("fetal_movement"):
            summary_parts.append(f"胎动：{answers['fetal_movement']}")
        if answers.get("blood_sugar_fasting"):
            summary_parts.append(f"空腹血糖：{answers['blood_sugar_fasting']}")
        if answers.get("blood_sugar_postprandial"):
            summary_parts.append(f"餐后血糖：{answers['blood_sugar_postprandial']}")
        if answers.get("mood"):
            summary_parts.append(f"情绪：{answers['mood']}")
        if answers.get("medication"):
            summary_parts.append(f"用药：{answers['medication']}")
        return " | ".join(summary_parts)

    def generate_health_education(self, gest_week: int, risk_tags: list[str] = None) -> list[str]:
        """根据孕周和风险标签生成健康教育内容"""
        education = []
        risk_tags = risk_tags or []

        # 按孕周分段
        if gest_week <= 12:
            education.append("早孕期保健指导：补充叶酸0.4-0.8mg/天，避免剧烈运动和性生活")
            education.append("早孕期常见不适及应对：少量多餐缓解孕吐，保证充足休息")
            education.append("NT检查最佳时间为孕11-13+6周，请按时预约")
        elif gest_week <= 28:
            education.append("中孕期营养指导：均衡饮食，每周体重增长控制在0.3-0.5kg")
            education.append("胎动计数方法：每天早中晚各数1小时，每小时≥3次为正常")
            education.append("唐氏筛查/无创DNA检测窗口期，请关注产检安排")
        else:
            education.append("晚孕期保健指导：左侧卧位休息，每天计数胎动")
            education.append("临产征兆识别：见红、破水、规律宫缩（5分钟一次持续1小时）")
            education.append("待产包准备：证件、母婴用品、住院生活用品")

        # 按风险标签补充
        if any(t in risk_tags for t in ("FGR高危", "FGR")):
            education.append("FGR管理：高蛋白饮食，左侧卧位，定期B超监测胎儿生长")
        if "GDM" in risk_tags:
            education.append("GDM管理：控制碳水摄入，餐后散步30分钟，每日监测血糖")
        if "高血压" in risk_tags:
            education.append("高血压管理：低盐饮食（<6g/天），每日早晚测血压，警惕头痛眼花")
        if any(t in risk_tags for t in ("心理健康", "抑郁风险")):
            education.append("心理健康：保持社交活动，适当运动，必要时寻求专业心理支持")

        return education

    async def generate_health_education_with_llm(
        self, gest_week: int, risk_tags: list[str], answers: dict
    ) -> list[str]:
        """使用 LLM 生成个性化健康教育内容

        根据孕妇的随访回答、孕周和风险标签，生成 3-5 条针对性的健康教育。
        LLM 失败时回退到模板。
        """
        from ..config import settings

        template_education = self.generate_health_education(gest_week, risk_tags)

        # 构造上下文
        answer_lines = [f"- {k}: {v}" for k, v in answers.items() if v]
        answer_text = "\n".join(answer_lines) if answer_lines else "暂无回答数据"
        risk_text = "、".join(risk_tags) if risk_tags else "无"

        prompt = (
            f"你是一位专业的孕期健康教育专家。请根据以下孕妇的随访回答，生成 3-5 条个性化健康教育建议。\n\n"
            f"孕妇信息：孕{gest_week}周，风险标签：{risk_text}\n"
            f"随访回答：\n{answer_text}\n\n"
            f"要求：\n"
            f"1. 每条建议针对孕妇回答中的具体问题\n"
            f"2. 语言简洁、实用、温暖\n"
            f"3. 绝不给出诊断结论或用药建议\n"
            f"4. 以JSON数组格式返回，如：[\"建议1\", \"建议2\", \"建议3\"]\n"
            f"5. 不要包含markdown代码块标记"
        )

        try:
            from ..core import get_llm_client
            from ..core.json_parser import parse_llm_json
            client = get_llm_client()
            messages = [
                {"role": "system", "content": "你是孕期健康教育专家，请以JSON数组格式返回健康教育建议。"},
                {"role": "user", "content": prompt},
            ]
            response = await client.chat(messages)
            if response and response.strip():
                data = parse_llm_json(response)
                if isinstance(data, list) and len(data) >= 2:
                    return [str(item) for item in data[:5]]
        except Exception:
            pass

        # 降级：检查回答中是否有特定问题，添加针对性建议
        personalized = list(template_education)

        if answers.get("feeling"):
            feeling = str(answers["feeling"]).lower()
            if any(w in feeling for w in ("失眠", "睡不好", "睡眠差")):
                personalized.append("针对睡眠问题：建议睡前温水泡脚、左侧卧位、避免睡前使用手机")
            if any(w in feeling for w in ("腰痛", "背痛", "腰酸")):
                personalized.append("针对腰背疼痛：避免久坐久站，可适当做孕妇瑜伽缓解")

        if answers.get("stress"):
            personalized.append("心理健康提示：适当倾诉压力，保持社交活动，必要时寻求专业心理支持")

        return personalized


    def generate_record_document(
        self, patient_name: str, gest_week: str, follow_up_date: str,
        record: dict,
    ) -> tuple[dict, str]:
        """确认时生成归档文档：结构化快照 + 格式化纯文本

        Args:
            patient_name: 孕妇展示名称
            gest_week: 孕周字符串
            follow_up_date: 随访日期
            record: FollowUpRecord 各字段的字典

        Returns:
            (record_snapshot, record_text)
            - record_snapshot: 全量字段冻结快照 (JSON dict)
            record_text: 格式化纯文本 (用于检索/打印/导出)
        """
        from ..utils.timezone import beijing_now

        classification = record.get("classification", "normal")
        cls_label = {"normal": "正常", "abnormal": "异常", "critical": "高危"}.get(classification, classification)
        status = record.get("status", "confirmed")
        status_label = {
            "draft": "草稿", "in_progress": "进行中",
            "completed": "已完成", "confirmed": "已确认", "archived": "已归档",
        }.get(status, status)

        # ---- 结构化快照 ----
        snapshot = {
            "patient_name": patient_name,
            "gestational_week": gest_week,
            "follow_up_date": follow_up_date,
            "status": status,
            "classification": classification,
            "chief_complaint": record.get("chief_complaint"),
            "self_reported_data": record.get("self_reported_data", {}),
            "obstetric_exam": record.get("obstetric_exam", {}),
            "lab_results": record.get("lab_results", {}),
            "summary": record.get("summary"),
            "health_education": record.get("health_education", []),
            "guidance_tags": record.get("guidance_tags", []),
            "referral": record.get("referral"),
            "next_followup_date": str(record.get("next_followup_date", "")),
            "reviewed_by": record.get("reviewed_by"),
            "reviewed_at": str(record.get("reviewed_at", "")),
            "review_comment": record.get("review_comment"),
            "ai_snapshot": record.get("ai_snapshot", {}),
            "generated_at": beijing_now().isoformat(),
        }

        # ---- 格式化纯文本 ----
        lines = []
        lines.append("=" * 50)
        lines.append("随访记录单".center(40))
        lines.append("=" * 50)
        lines.append(f"孕妇：{patient_name}  孕周：{gest_week}  日期：{follow_up_date}")
        lines.append(f"状态：{status_label}  分类：{cls_label}")
        lines.append("")

        # S
        lines.append("S 主观数据")
        srd = record.get("self_reported_data", {})
        if srd:
            items = [f"  {FIELD_LABELS.get(k, k)}：{v}" for k, v in srd.items()]
            for i in range(0, len(items), 2):
                lines.append("    ".join(items[i:i+2]))
        cc = record.get("chief_complaint")
        if cc:
            lines.append(f"  主诉：{cc}")
        lines.append("")

        # O
        lines.append("O 客观检查")
        oe = record.get("obstetric_exam", {})
        if oe:
            lines.append("  产科检查")
            items = [f"    {EXAM_LABELS.get(k, k)}：{v}" for k, v in oe.items()]
            for i in range(0, len(items), 2):
                lines.append("    ".join(items[i:i+2]))
        lr = record.get("lab_results", {})
        if lr:
            lines.append("  化验结果")
            items = [f"    {LAB_LABELS.get(k, k)}：{v}" for k, v in lr.items()]
            for i in range(0, len(items), 2):
                lines.append("    ".join(items[i:i+2]))
        lines.append("")

        # A
        lines.append("A 评估")
        summary = record.get("summary", "暂无评估")
        lines.append(f"  {summary}")
        lines.append("")

        # P
        lines.append("P 计划")
        gt = record.get("guidance_tags", [])
        if gt:
            for g in gt:
                lines.append(f"  [{g.get('tag', '')}] {g.get('content', '')}")
        nfd = record.get("next_followup_date")
        if nfd:
            lines.append(f"  下次随访日期：{nfd}")
        ref = record.get("referral")
        if ref and ref.get("has_referral"):
            lines.append(f"  转诊：{ref.get('reason', '')} → {ref.get('institution', '')} {ref.get('department', '')}")
        lines.append("")

        # 审核信息
        rb = record.get("reviewed_by")
        if rb:
            lines.append("审核信息")
            lines.append(f"  审核人：{rb}")
            ra = record.get("reviewed_at")
            if ra:
                lines.append(f"  审核时间：{ra}")
            rc = record.get("review_comment")
            if rc:
                lines.append(f"  审核意见：{rc}")
            lines.append("")

        # 签名栏（日期预填，签名区域由前端渲染）
        lines.append("-" * 50)
        lines.append(f"随访护士签名：__________________  日期：{follow_up_date}")
        lines.append("=" * 50)

        record_text = "\n".join(lines)
        return snapshot, record_text


followup_service = FollowUpService()
