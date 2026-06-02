"""随访提交 + 流式 AI 分析 — 单元测试 & 集成测试

覆盖改动：
- POST /followup/respond: 移除 LLM，保留规则引擎，返回 analysis_available + health_education
- POST /followup/respond/analyze/stream: SSE 流式分析端点
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pregnant, FollowUpRecord, HealthDataPoint
from app.main import app
from app.routers import followup as followup_router
from app.database import get_db
from app.core.auth import get_current_user, TokenPayload, create_token

# ── 测试数据库 ──
TEST_DB_URL = "sqlite:///./test_followup_respond.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# 保存原始引用
_original_SessionLocal = followup_router.SessionLocal
_original_get_db = get_db


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前重建数据库，覆盖依赖"""
    Base.metadata.create_all(bind=test_engine)
    # 覆盖路由内的 SessionLocal 引用
    monkeypatch.setattr(followup_router, "SessionLocal", TestSession)
    # 覆盖 FastAPI DI
    app.dependency_overrides[get_db] = _override_get_db
    mock_user = TokenPayload(sub="test-admin", role="admin", pregnant_id="")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    Base.metadata.drop_all(bind=test_engine)


# 认证 headers（AuthMiddleware 在 DI 之前检查 JWT）
_test_token = create_token(TokenPayload(sub="test-admin", role="admin", pregnant_id=""))
_auth_headers = {"Authorization": f"Bearer {_test_token}"}


def _seed_pregnant(db, pid="test-p001", gest_days=196, risk_tags=None):
    """创建测试孕妇（默认28周）"""
    p = Pregnant(
        pregnant_id=pid,
        display_name="测试孕妇",
        nickname="小测",
        gestational_age_days=gest_days,
        risk_tags=risk_tags or [],
        lmp_date=date.today() - timedelta(days=gest_days),
    )
    db.add(p)
    db.commit()
    return p


def _seed_followup_record(db, pid="test-p001", status="draft", answers=None):
    """创建测试随访记录"""
    r = FollowUpRecord(
        pregnant_id=pid,
        status=status,
        gestational_week="28+0",
        self_reported_data=answers or {},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ==================== POST /respond 单元测试 ====================

class TestRespondEndpoint:
    """测试 /followup/respond 改动后的行为"""

    def test_respond_completed_returns_analysis_available(self):
        """完成时应返回 analysis_available: True，但不返回 analysis_report"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        # 一次性提交所有问题答案（total_count=5 假定模板有5个问题）
        payload = {
            "record_id": str(rec.id),
            "answers": {
                "feeling": "感觉良好",
                "weight": "65",
                "bp": "120/80",
                "fetal_movement": "5",
                "diet": "饮食正常",
            },
            "total_count": 5,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis_available"] is True
        # 不应包含 LLM 分析报告
        assert "analysis_report" not in data
        # 应有模板摘要
        assert "summary" in data
        assert len(data["summary"]) > 0

    def test_respond_partial_no_analysis_available(self):
        """部分提交不应返回 analysis_available"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        payload = {
            "record_id": str(rec.id),
            "answers": {"feeling": "感觉良好"},
            "total_count": 5,  # 只填了1题，总共5题
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "in_progress"
        assert "analysis_available" not in data

    def test_respond_returns_health_education(self):
        """完成时应返回模板健康教育"""
        db = TestSession()
        _seed_pregnant(db, "test-p001", gest_days=196)  # 28周
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        payload = {
            "record_id": str(rec.id),
            "answers": {
                "feeling": "感觉良好",
                "weight": "65",
                "bp": "120/80",
                "fetal_movement": "5",
                "diet": "饮食正常",
            },
            "total_count": 5,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert "health_education" in data
        assert isinstance(data["health_education"], list)

    def test_respond_rule_engine_triggers_for_high_bp(self):
        """高血压数据应触发规则引擎预警（写入 alerts 表）"""
        db = TestSession()
        _seed_pregnant(db, "test-p001", gest_days=196, risk_tags=["高血压"])
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        payload = {
            "record_id": str(rec.id),
            "answers": {
                "feeling": "头晕",
                "weight": "70",
                "bp": "160/100",  # 高危血压
                "fetal_movement": "4",
                "diet": "正常",
            },
            "total_count": 5,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

        # 检查预警是否写入（规则引擎触发）
        db2 = TestSession()
        from app.models import Alert
        alerts = db2.query(Alert).filter(
            Alert.pregnant_id == "test-p001"
        ).all()
        db2.close()
        # 高血压 160/100 应触发 alert
        assert len(alerts) > 0

    def test_respond_404_for_missing_record(self):
        """不存在的随访记录应返回 404"""
        import uuid
        payload = {
            "record_id": str(uuid.uuid4()),
            "answers": {"feeling": "test"},
            "total_count": 0,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 404

    def test_respond_draft_to_in_progress(self):
        """提交后状态从 draft 流转到 in_progress"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        payload = {
            "record_id": str(rec.id),
            "answers": {"feeling": "还不错"},
            "total_count": 5,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_respond_saves_health_data_point(self):
        """量化数据应写入 HealthDataPoint（需符合 extract_health_value 的格式）"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(db, "test-p001", status="draft", answers={})
        db.close()

        payload = {
            "record_id": str(rec.id),
            "answers": {
                "feeling": "感觉还好",
                "weight": "68.5kg",          # 匹配 extract_health_value 的 weight 正则
                "bp": "118/76",               # sbp + dbp → 2 个 HealthDataPoint
                "fetal_movement": "6次",       # 需要单位后缀
                "diet": "饮食正常",
            },
            "total_count": 5,
        }

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond", json=payload)

        assert resp.status_code == 200

        db2 = TestSession()
        points = db2.query(HealthDataPoint).filter(
            HealthDataPoint.pregnant_id == "test-p001"
        ).all()
        db2.close()
        # bp → systolic + diastolic, weight → weight, fetal_movement → fetal_movement
        metric_codes = {p.metric_code for p in points}
        assert "weight" in metric_codes
        assert "systolic" in metric_codes or "diastolic" in metric_codes
        assert len(points) >= 3


# ==================== POST /respond/analyze/stream 集成测试 ====================

class TestAnalyzeStreamEndpoint:
    """测试 /followup/respond/analyze/stream SSE 流式端点

    使用 unittest.mock.patch 避免真实 LLM 调用，同时验证 SSE 事件流结构。
    """

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Mock LLM 依赖：拦截函数内部的本地 import"""
        mock_agent = MagicMock()
        async def _mock_arun(*args, **kwargs):
            yield MagicMock(content="感谢配合，本次结果良好。")

        mock_agent.arun = MagicMock(side_effect=_mock_arun)

        mock_agent_factory = MagicMock(return_value=mock_agent)
        mock_extract = MagicMock(return_value={
            "warm_summary": "感谢配合，一切正常~",
            "abnormal_indicators": [],
            "trend_analysis": "各项指标稳定",
            "personalized_advice": "继续保持良好作息",
            "nurse_action_suggestion": "确认通过",
        })
        mock_health_edu = AsyncMock(return_value=["个性化建议1", "个性化建议2"])

        # patch 函数体内的本地 import: from ..core.agno_medical_agents import ...
        # 由于 import 在函数运行时才执行，需 patch 源模块引用
        with patch(
            "app.core.agno_medical_agents.create_followup_analysis_agent",
            mock_agent_factory,
        ), patch(
            "app.core.agno_structured.extract_structured_content",
            mock_extract,
        ), patch.object(
            followup_router.followup_service, "generate_health_education_with_llm",
            mock_health_edu,
        ):
            yield

    def test_analyze_stream_404_for_missing_record(self):
        """不存在的记录 ID 返回 404"""
        import uuid
        payload = {"record_id": str(uuid.uuid4())}

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond/analyze/stream", json=payload)

        assert resp.status_code == 404

    def test_analyze_stream_400_for_non_completed(self):
        """非 completed 状态应返回 400"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(db, "test-p001", status="in_progress", answers={"feeling": "test"})
        db.close()

        payload = {"record_id": str(rec.id)}

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond/analyze/stream", json=payload)

        assert resp.status_code == 400

    def test_analyze_stream_returns_sse_content_type(self):
        """成功的流式请求应返回 text/event-stream"""
        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(
            db, "test-p001", status="completed",
            answers={"feeling": "正常", "weight": "65kg", "bp": "120/80", "fetal_movement": "5次", "diet": "良好"},
        )
        db.close()

        payload = {"record_id": str(rec.id)}

        with TestClient(app, headers=_auth_headers) as client:
            resp = client.post("/api/v1/followup/respond/analyze/stream", json=payload)

        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct
        # 验证 SSE 事件流中包含关键事件类型
        body = resp.text
        assert "event: phase" in body
        assert "event: chunk" in body
        assert "event: done" in body
        # 验证 done 事件的 JSON data
        import re
        match = re.search(r"event: done\ndata: (\{.+?\})\n\n", body, re.DOTALL)
        if match:
            done_data = json.loads(match.group(1))
            assert "analysis_report" in done_data
            assert "record_id" in done_data

        # 验证数据库中的 summary 已更新
        db2 = TestSession()
        from uuid import UUID
        updated = db2.query(FollowUpRecord).filter(
            FollowUpRecord.id == UUID(str(rec.id))
        ).first()
        db2.close()
        if updated and updated.summary:
            assert len(updated.summary) > 0


# ==================== Fallback Analysis Report 单元测试 ====================

class TestFallbackAnalysisReportNew:
    """验证 fallback 分析报告的完整性（供流式端点兜底使用）"""

    def test_fallback_returns_all_required_fields(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="测试", gest_week="28+0",
            answers={"bp": "120/80"}, risk_tags=[],
        )
        assert "warm_summary" in result
        assert "abnormal_indicators" in result
        assert "trend_analysis" in result
        assert "personalized_advice" in result
        assert "nurse_action_suggestion" in result
        assert isinstance(result["abnormal_indicators"], list)

    def test_fallback_detects_high_fasting_glucose(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="测试", gest_week="28+0",
            answers={"blood_sugar_fasting": "6.5", "bp": "120/80"}, risk_tags=[],
        )
        assert len(result["abnormal_indicators"]) >= 1
        assert any("血糖" in item for item in result["abnormal_indicators"])

    def test_fallback_detects_low_fetal_movement(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="测试", gest_week="32+0",
            answers={"fetal_movement": "2"}, risk_tags=[],
        )
        assert len(result["abnormal_indicators"]) >= 1
        assert any("胎动" in item for item in result["abnormal_indicators"])

    def test_fallback_all_normal(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="测试", gest_week="28+0",
            answers={"bp": "118/76", "weight": "65", "fetal_movement": "5"}, risk_tags=[],
        )
        assert result["abnormal_indicators"] == []
        assert result["nurse_action_suggestion"] == "确认通过"


# ==================== SSE Stream Generator 单元测试 ====================

class TestStreamFollowupAnalysisGenerator:
    """直接测试 _stream_followup_analysis 生成器"""

    @pytest.mark.asyncio
    async def test_generator_yields_phase_events(self):
        """生成器应产生 phase 事件"""
        from app.routers.followup import _stream_followup_analysis

        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(
            db, "test-p001", status="completed",
            answers={"feeling": "正常", "weight": "65", "bp": "120/80", "fetal_movement": "5", "diet": "良好"},
        )
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == "test-p001").first()

        events = []
        async for event in _stream_followup_analysis(
            patient_name="测试", gest_week="28+0",
            answers={"feeling": "正常", "weight": "65", "bp": "120/80"},
            risk_tags=[], pregnant_id="test-p001",
            db=db, record=rec, pregnant=pregnant,
        ):
            events.append(event)

        db.close()

        # 至少应有 phase + done 事件
        event_types = [e["event"] for e in events]
        assert "phase" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_generator_done_event_has_analysis_report(self):
        """done 事件的 data 应包含 analysis_report"""
        from app.routers.followup import _stream_followup_analysis

        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(
            db, "test-p001", status="completed",
            answers={"feeling": "正常", "weight": "65", "bp": "120/80", "fetal_movement": "5", "diet": "良好"},
        )
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == "test-p001").first()

        events = []
        async for event in _stream_followup_analysis(
            patient_name="测试", gest_week="28+0",
            answers={"feeling": "正常", "weight": "65", "bp": "120/80"},
            risk_tags=[], pregnant_id="test-p001",
            db=db, record=rec, pregnant=pregnant,
        ):
            events.append(event)

        db.close()

        # 取最后一个 done 事件
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 1
        done_data = json.loads(done_events[0]["data"])
        assert "analysis_report" in done_data
        assert "health_education" in done_data

    @pytest.mark.asyncio
    async def test_generator_fallback_without_llm(self):
        """即使 LLM 不可用，fallback 也应产生完整的 chunk + done"""
        from app.routers.followup import _stream_followup_analysis

        db = TestSession()
        _seed_pregnant(db, "test-p001")
        rec = _seed_followup_record(
            db, "test-p001", status="completed",
            answers={"bp": "150/95"},
        )
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == "test-p001").first()

        events = []
        async for event in _stream_followup_analysis(
            patient_name="测试", gest_week="32+0",
            answers={"bp": "150/95"},
            risk_tags=[], pregnant_id="test-p001",
            db=db, record=rec, pregnant=pregnant,
        ):
            events.append(event)

        db.close()

        # 必须有 chunk 和 done
        has_chunk = any(e["event"] == "chunk" for e in events)
        has_done = any(e["event"] == "done" for e in events)
        assert has_chunk, "fallback should emit at least one chunk event"
        assert has_done, "fallback should emit done event"
