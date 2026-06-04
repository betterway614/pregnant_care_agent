"""随访相关结构化输出 Schema"""
from pydantic import BaseModel, Field
from .nurse_schemas import FollowUpQuestion


class FollowUpGenerateOutput(BaseModel):
    """随访对话脚本生成结果"""
    opening_message: str = Field(description="亲切的开场白（30-50字）")
    questions: list[FollowUpQuestion] = Field(description="随访问题列表（4-6个问题）")
    closing_message: str = Field(description="温暖的结束语（30-50字）")


class FollowUpAnalysisOutput(BaseModel):
    """随访完成后 LLM 结构化分析结果"""
    warm_summary: str = Field(description="温馨总结（30-50字），语气温和自然")
    abnormal_indicators: list[str] = Field(description="异常指标列表，无异常则为空列表")
    trend_analysis: str = Field(description="与历史数据对比的趋势分析（50-100字）")
    personalized_advice: str = Field(description="基于回答内容的个性化建议（50-100字）")
    nurse_action_suggestion: str = Field(description="护士行动建议")


class FollowUpAiReviewOutput(BaseModel):
    """护士审核随访时的 AI 辅助分析结果"""
    summary: str = Field(description="本次随访要点摘要（100-200字）")
    abnormal_flags: list[str] = Field(description="异常指标标红列表，无异常则为空列表")
    action_needed: bool = Field(description="是否需要上报医生")
    recommendation: str = Field(description="审核建议：确认通过/需进一步沟通/紧急上报")
    detail_analysis: str = Field(description="详细分析（100-200字）")
