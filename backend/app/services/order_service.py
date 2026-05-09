"""医嘱模板服务 - 根据风险类型推荐医嘱"""
from typing import Optional


# 医嘱模板库
ORDER_TEMPLATES = {
    "fgr_high_before_34": {
        "condition": "FGR高风险 + 孕周<34w",
        "content": "收治入院，予地塞米松促胎肺成熟，并行脐动脉血流监测。密切监测胎心变化，每日胎动计数，每周两次B超生长评估。",
        "source": "FGR高风险诊疗指南"
    },
    "fgr_high_after_34": {
        "condition": "FGR高风险 + 孕周≥34w",
        "content": "建议收治入院，加强胎心监护（每日1次），每3日B超评估生长速率。评估分娩时机，做好剖宫产准备。",
        "source": "FGR高风险诊疗指南"
    },
    "fgr_medium": {
        "condition": "FGR中风险",
        "content": "门诊密切随访，48小时内复查B超评估生长速率。每周胎心监护2次，每日胎动计数并记录。注意休息，加强营养。",
        "source": "FGR中风险管理指南"
    },
    "hypertension_severe": {
        "condition": "重度高血压",
        "content": "收治入院，予拉贝洛尔/硝苯地平控制血压。监测尿蛋白、肝肾功能、血小板计数。每日胎心监护。",
        "source": "妊娠期高血压疾病诊治指南"
    },
    "hypertension_mild": {
        "condition": "轻度高血压",
        "content": "门诊降压治疗，低盐饮食，每日监测血压并记录。每周复查尿蛋白，每2周B超监测胎儿生长。如血压持续升高或出现蛋白尿，立即就诊。",
        "source": "妊娠期高血压疾病诊治指南"
    },
    "gestational_diabetes": {
        "condition": "妊娠期糖尿病",
        "content": "糖尿病饮食指导，血糖监测（空腹+三餐后2小时），每周复查血糖谱。适量运动（餐后散步30分钟），如血糖控制不达标启动胰岛素治疗。",
        "source": "妊娠期糖尿病诊治指南"
    },
    "threatened_preterm": {
        "condition": "先兆早产",
        "content": "收治入院，安胎治疗（硫酸镁/利托君）。促胎肺成熟（地塞米松）。绝对卧床休息，监测宫缩及胎心变化。",
        "source": "早产临床诊断与治疗指南"
    },
    "anemia": {
        "condition": "妊娠期贫血",
        "content": "口服铁剂（硫酸亚铁/富马酸亚铁），维生素C促进吸收。饮食指导：增加红肉、动物肝脏、深绿色蔬菜摄入。2周后复查血常规。",
        "source": "妊娠期贫血诊疗指南"
    },
    "emotion_concern": {
        "condition": "情绪心理关注",
        "content": "建议心理科会诊评估。必要时启动心理咨询/认知行为治疗。家人加强陪伴与沟通。2周后复评。",
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


order_service = OrderService()
