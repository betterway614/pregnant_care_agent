"""结构化输出 Schema 定义

从 agno_medical_agents.py 中分离，遵循 SRP。
"""
from .nurse_schemas import NurseAnalysisOutput, FollowUpQuestion
from .doctor_schemas import DoctorAnalysisOutput
from .followup_schemas import (
    FollowUpGenerateOutput, FollowUpAnalysisOutput, FollowUpAiReviewOutput,
)
from .chat_schemas import ChatOutput

__all__ = [
    "NurseAnalysisOutput", "FollowUpQuestion",
    "DoctorAnalysisOutput",
    "FollowUpGenerateOutput", "FollowUpAnalysisOutput", "FollowUpAiReviewOutput",
    "ChatOutput",
]
