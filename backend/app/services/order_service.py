"""医嘱模板服务 - 根据风险类型推荐医嘱"""
from typing import Optional


# 医嘱模板库
ORDER_TEMPLATES = {
    "fgr_high_before_34": {
        "condition": "FGR高风险 + 孕周<34w",
        "content": "建议收治入院评估，考虑予地塞米松促胎肺成熟，并行脐动脉血流监测。建议密切监测胎心变化，每日胎动计数，每周两次B超生长评估。以上为医疗建议，具体方案需经主治医生评估后确定。",
        "source": "FGR高风险诊疗指南"
    },
    "fgr_high_after_34": {
        "condition": "FGR高风险 + 孕周≥34w",
        "content": "建议收治入院评估，加强胎心监护（每日1次），每3日B超评估生长速率。评估分娩时机，做好剖宫产准备。以上为医疗建议，具体方案需经主治医生评估后确定。",
        "source": "FGR高风险诊疗指南"
    },
    "fgr_medium": {
        "condition": "FGR中风险",
        "content": "建议门诊密切随访，48小时内复查B超评估生长速率。建议每周胎心监护2次，每日胎动计数并记录。注意休息，加强营养。以上为医疗建议，具体方案需经主治医生评估后确定。",
        "source": "FGR中风险管理指南"
    },
    "hypertension_severe": {
        "condition": "重度高血压",
        "content": "建议收治入院评估，考虑予拉贝洛尔/硝苯地平控制血压。建议监测尿蛋白、肝肾功能、血小板计数。每日胎心监护。具体用药方案需医生根据患者情况制定。",
        "source": "妊娠期高血压疾病诊治指南"
    },
    "hypertension_mild": {
        "condition": "轻度高血压",
        "content": "建议门诊降压治疗，低盐饮食，每日监测血压并记录。建议每周复查尿蛋白，每2周B超监测胎儿生长。如血压持续升高或出现蛋白尿，建议立即就诊。具体方案需经主治医生评估后确定。",
        "source": "妊娠期高血压疾病诊治指南"
    },
    "gestational_diabetes": {
        "condition": "妊娠期糖尿病",
        "content": "建议糖尿病饮食指导，血糖监测（空腹+三餐后2小时），每周复查血糖谱。建议适量运动（餐后散步30分钟），如血糖控制不达标建议咨询医生评估胰岛素治疗。以上为医疗建议，具体方案需经主治医生评估后确定。",
        "source": "妊娠期糖尿病诊治指南"
    },
    "threatened_preterm": {
        "condition": "先兆早产",
        "content": "建议收治入院评估，考虑安胎治疗（硫酸镁/利托君）。建议促胎肺成熟（地塞米松）。绝对卧床休息，监测宫缩及胎心变化。具体用药方案需医生根据患者情况制定。",
        "source": "早产临床诊断与治疗指南"
    },
    "anemia": {
        "condition": "妊娠期贫血",
        "content": "建议口服铁剂（硫酸亚铁/富马酸亚铁），维生素C促进吸收。饮食指导：增加红肉、动物肝脏、深绿色蔬菜摄入。建议2周后复查血常规。具体用药方案需经主治医生评估后确定。",
        "source": "妊娠期贫血诊疗指南"
    },
    "emotion_concern": {
        "condition": "情绪心理关注",
        "content": "建议心理科会诊评估。必要时启动心理咨询/认知行为治疗。建议家人加强陪伴与沟通。建议2周后复评。以上为医疗建议，具体方案需经主治医生评估后确定。",
        "source": "围产期心理健康管理指南"
    }
}


class OrderService:
    """医嘱服务"""

    def get_recommendation(self, risk_level: str, gestational_weeks: float,
                           risk_tags: list[str] = None) -> Optional[dict]:
        """根据风险评估推荐医嘱"""
        risk_tags = risk_tags or []

        # FGR相关
        if risk_level in ("high", "critical") and "FGR" in " ".join(risk_tags + [risk_level]):
            if gestational_weeks < 34:
                return dict(ORDER_TEMPLATES["fgr_high_before_34"])
            return dict(ORDER_TEMPLATES["fgr_high_after_34"])

        if risk_level == "medium" and risk_tags:
            if "FGR" in " ".join(risk_tags):
                return dict(ORDER_TEMPLATES["fgr_medium"])

        # 通用匹配
        for tag in risk_tags:
            if "高血压" in tag and risk_level in ("high", "critical"):
                return dict(ORDER_TEMPLATES["hypertension_severe"])
            if "高血压" in tag:
                return dict(ORDER_TEMPLATES["hypertension_mild"])
            if "GDM" in tag or "糖尿病" in tag:
                return dict(ORDER_TEMPLATES["gestational_diabetes"])
            if "情绪" in tag or "焦虑" in tag:
                return dict(ORDER_TEMPLATES["emotion_concern"])

        return None

    def get_all_templates(self) -> dict:
        """获取所有医嘱模板"""
        return dict(ORDER_TEMPLATES)

    def generate_order_document(
        self, patient_name: str, gest_week: str, order_content: str,
        order_type: str, source: str, doctor_name: str = "",
    ) -> tuple[dict, str]:
        """签署时生成归档文档：结构化快照 + 格式化纯文本

        Args:
            patient_name: 孕妇展示名称
            gest_week: 孕周字符串
            order_content: 医嘱内容
            order_type: 医嘱类型
            source: 来源 (AI_RECOMMENDED/DOCTOR_WRITTEN)
            doctor_name: 医生姓名

        Returns:
            (order_snapshot, order_text)
        """
        from datetime import datetime as _dt

        source_label = {"AI_RECOMMENDED": "AI辅助生成", "DOCTOR_WRITTEN": "医生手写"}.get(source, source)
        type_label = {"standard": "标准医嘱", "custom": "自定义医嘱"}.get(order_type, order_type)

        # ---- 结构化快照 ----
        snapshot = {
            "patient_name": patient_name,
            "gestational_week": gest_week,
            "order_content": order_content,
            "order_type": order_type,
            "source": source,
            "doctor_name": doctor_name,
            "generated_at": _dt.utcnow().isoformat(),
        }

        # ---- 格式化纯文本（含红色警告） ----
        lines = []
        lines.append("=" * 50)
        lines.append("AI-Care 孕期智能管理平台".center(40))
        lines.append("医 嘱 单".center(40))
        lines.append("=" * 50)
        lines.append(f"孕妇：{patient_name}  孕周：{gest_week}")
        lines.append(f"类型：{type_label}  来源：{source_label}")
        lines.append(f"签署日期：{_dt.utcnow().strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append("-" * 50)
        lines.append("【医嘱内容】")
        lines.append(order_content)
        lines.append("-" * 50)
        lines.append("")
        lines.append("【重要提醒】")
        lines.append(">>> 本医嘱经医生审核修改并手写签名确认 <<<")
        lines.append(">>> 如有疑问请咨询您的产检医生 <<<")
        lines.append("")
        lines.append("-" * 50)
        lines.append(f"医生签名：{'__________________' if not doctor_name else doctor_name}")
        lines.append(f"日期：{_dt.utcnow().strftime('%Y-%m-%d')}")
        lines.append("=" * 50)
        lines.append("本记录由 AI-Care 孕期智能管理平台生成")

        order_text = "\n".join(lines)
        return snapshot, order_text


order_service = OrderService()
