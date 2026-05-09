"""测试 Agno 随访工具"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_agno_get_followup_context():
    """验证 get_followup_context 工具返回正确格式"""
    from app.core.agno_tools import _get_followup_context_impl as agno_get_followup_context

    mock_db = MagicMock()
    mock_record = MagicMock()
    mock_record.id = uuid4()
    mock_record.pregnant_id = "test-pid"
    mock_record.gestational_week = "30+2"
    mock_record.status = "in_progress"
    mock_record.self_reported_data = {}
    mock_record.health_education = []

    mock_pregnant = MagicMock()
    mock_pregnant.nickname = "小明"
    mock_pregnant.display_name = "张小明"
    mock_pregnant.risk_tags = ["GDM"]

    mock_db.query.side_effect = lambda model: MagicMock(
        filter=MagicMock(return_value=MagicMock(
            first=MagicMock(return_value=mock_record if model.__name__ == "FollowUpRecord" else mock_pregnant)
        ))
    )

    with patch("app.database.SessionLocal", return_value=mock_db):
        with patch("app.services.followup_service") as mock_svc:
            mock_svc.get_template_from_questions.return_value = {
                "questions": [{"key": "feeling", "question": "感觉如何？"}]
            }
            result = await agno_get_followup_context(str(uuid4()))
            assert "record_id" in result
            assert "pending_questions" in result


@pytest.mark.asyncio
async def test_agno_record_answer():
    """验证 record_answer 工具保存数据"""
    from app.core.agno_tools import _record_answer_impl as agno_record_answer

    mock_db = MagicMock()
    mock_record = MagicMock()
    mock_record.id = uuid4()
    mock_record.pregnant_id = "test-pid"
    mock_record.status = "in_progress"
    mock_record.self_reported_data = {}
    mock_record.chief_complaint = None

    mock_db.query.return_value.filter.return_value.first.return_value = mock_record

    with patch("app.database.SessionLocal", return_value=mock_db):
        with patch("app.services.followup_service") as mock_svc:
            mock_svc.get_template_from_questions.return_value = {
                "questions": [
                    {"key": "feeling", "question": "感觉如何？"},
                    {"key": "weight", "question": "体重多少？"},
                ]
            }
            mock_svc.extract_health_value.return_value = None
            result = await agno_record_answer(str(uuid4()), "feeling", "很好")
            assert result["success"] is True
            assert result["answered_count"] == 1
            assert result["all_questions_answered"] is False
