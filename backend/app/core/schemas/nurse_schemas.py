"""护士端结构化输出 Schema"""
from pydantic import BaseModel, Field


class FollowUpQuestion(BaseModel):
    """随访问题条目"""
    question: str = Field(description="问题文本")
    purpose: str = Field(description="该问题的目的/考察重点")


class NurseAnalysisOutput(BaseModel):
    """护士分析结果 — 结构化输出"""
    summary: str = Field(description="综合概述（100-200字），概括孕妇当前整体状况")
    risk_assessment: str = Field(description="风险评估（100-200字），分析当前主要风险因素")
    alert_level: str = Field(description="预警级别：RED（红色高危）、ORANGE（橙色预警）、YELLOW（黄色关注）或 NONE（无需预警）")
    nursing_suggestions: str = Field(description="护理建议（150-300字），具体的护理措施和健康教育要点")
    followup_focus: list[str] = Field(description="随访重点（3-5个项目），列出随访时需要特别关注的内容")
