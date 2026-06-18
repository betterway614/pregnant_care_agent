"""归档流程 — 单元测试 & 集成测试

覆盖改动:
- GET  /records/{record_id}          获取单条记录 + 权限校验
- POST /records/{record_id}/sign     护士签名（角色校验 + 状态校验）
- POST /records/{record_id}/archive  归档（签名前置 + AI 总结 + 状态机）
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from uuid import uuid4
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pregnant, FollowUpRecord
from app.main import app
from app.routers import followup as followup_router
from app.database import get_db
from app.core.auth import get_current_user, TokenPayload, create_token
from app.schemas import FollowUpArchiveSummaryRequest, FollowUpSignatureRequest

# ── 测试数据库 ──
TEST_DB_URL = "sqlite:///./test_archive_flow.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


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
    monkeypatch.setattr(followup_router, "SessionLocal", TestSession)
    app.dependency_overrides[get_db] = _override_get_db
    mock_user = TokenPayload(sub="nurse-001", role="nurse", pregnant_id="")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    Base.metadata.drop_all(bind=test_engine)


# 认证 headers
_test_token = create_token(TokenPayload(sub="nurse-001", role="nurse", pregnant_id=""))
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


def _seed_record(db, pid="test-p001", status="confirmed", with_signature=False, **kwargs):
    """创建测试随访记录"""
    rec = FollowUpRecord(
        pregnant_id=pid,
        gestational_week="28+0",
        follow_up_date=datetime.utcnow(),
        status=status,
        self_reported_data=kwargs.get("self_reported_data", {"bp": "120/80", "weight": 65}),
        chief_complaint=kwargs.get("chief_complaint", "无不适"),
        summary=kwargs.get("summary", "测试摘要"),
        health_education=kwargs.get("health_education", ["保持均衡饮食"]),
        guidance_tags=kwargs.get("guidance_tags", []),
        classification=kwargs.get("classification", "normal"),
        record_snapshot=kwargs.get("record_snapshot", {}),
        record_text=kwargs.get("record_text", ""),
        ai_snapshot=kwargs.get("ai_snapshot", {"summary": "AI分析测试"}),
        signature_data=(
            {"image": "base64-fake-signature", "signer": "护士长", "signed_at": "2026-06-18T10:00:00"}
            if with_signature else {}
        ),
    )
    db.add(rec)
    db.commit()
    return rec


client = TestClient(app)


def _make_mock_record(status="confirmed", pregnant_id="P001", signature_data=None, **overrides):
    """创建 Mock 随访记录，包含所有必要字段用于 FollowUpRecordResponse 构造"""
    from app.models import FollowUpRecord

    defaults = {
        "id": uuid4(),
        "pregnant_id": pregnant_id,
        "gestational_week": "28+0",
        "follow_up_date": datetime.utcnow(),
        "self_reported_data": {"bp": "120/80", "weight": 65},
        "chief_complaint": "无不适",
        "obstetric_exam": {},
        "lab_results": {},
        "classification": "normal",
        "summary": "测试摘要",
        "health_education": ["均衡饮食"],
        "guidance_tags": [],
        "referral": None,
        "next_followup_date": None,
        "status": status,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_comment": None,
        "ai_snapshot": {"summary": "AI分析"},
        "record_snapshot": {},
        "record_text": "SOAP测试文本",
        "signature_data": signature_data or {},
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)

    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    mock.__table__ = FollowUpRecord.__table__
    return mock


# ═══════════════════════════════════════════════════════════
# 单元测试: GET /records/{record_id}
# ═══════════════════════════════════════════════════════════

class TestGetRecord:
    """单条记录获取 + 权限控制"""

    def test_get_record_success_nurse(self):
        """护士可以获取任意记录"""
        from app.routers.followup import get_record
        from app.core.auth import TokenPayload

        mock_record = _make_mock_record(status="confirmed")
        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "测试孕妇"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_record, mock_pregnant]

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        result = get_record(str(mock_record.id), db=mock_db, current_user=mock_user)
        assert result.patient_name == "测试孕妇"
        assert result.status == "confirmed"

    def test_get_record_not_found(self):
        """记录不存在返回 404"""
        from app.routers.followup import get_record
        from app.core.auth import TokenPayload

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            get_record(str(uuid4()), db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 404

    def test_get_record_pregnant_can_see_own(self):
        """孕妇可以查看自己的记录"""
        from app.routers.followup import get_record
        from app.core.auth import TokenPayload

        mock_record = _make_mock_record(status="confirmed", pregnant_id="P001")
        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "孕妇自己"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_record, mock_pregnant]

        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")

        result = get_record(str(mock_record.id), db=mock_db, current_user=mock_user)
        assert result.patient_name == "孕妇自己"

    def test_get_record_pregnant_cannot_see_others(self):
        """孕妇不能查看他人记录"""
        from app.routers.followup import get_record
        from app.core.auth import TokenPayload

        mock_record = _make_mock_record(status="confirmed", pregnant_id="P002")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")

        with pytest.raises(HTTPException) as exc:
            get_record(str(mock_record.id), db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 403


# ═══════════════════════════════════════════════════════════
# 单元测试: POST /records/{record_id}/sign
# ═══════════════════════════════════════════════════════════

class TestSignRecord:
    """护士签名 — 角色 & 状态校验"""

    def test_sign_nurse_can_sign(self):
        """护士可以对 confirmed 记录签名"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "confirmed"
        mock_record.signature_data = None
        mock_record.ai_snapshot = {
            "archive_summary_draft_text": "温馨总结：AI原稿\n\n趋势分析：稳定\n\n个性化建议：继续保持",
            "archive_summary_final_text": "温馨总结：护士已核对，当前整体平稳。\n\n趋势分析：血压与体重稳定。\n\n个性化建议：继续规律监测胎动。",
            "archive_summary_modified": True,
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        sign_req = FollowUpSignatureRequest(
            signature_image="data:image/png;base64,iVBOR...",
            signer_name="李护士",
        )
        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        result = sign_record(str(mock_record.id), sign_req, db=mock_db, current_user=mock_user)
        assert result["message"] == "签名已保存"
        assert mock_record.signature_data["signer"] == "李护士"
        assert mock_record.signature_data["image"] == "data:image/png;base64,iVBOR..."

    def test_sign_requires_nurse_modified_archive_summary(self):
        """签名前必须保存一版不同于 AI 原稿的护士归档总结"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "confirmed"
        mock_record.signature_data = None
        mock_record.ai_snapshot = {
            "archive_summary_draft_text": "温馨总结：AI原稿",
            "archive_summary_final_text": "温馨总结：AI原稿",
            "archive_summary_modified": False,
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        sign_req = FollowUpSignatureRequest(
            signature_image="data:image/png;base64,iVBOR...",
            signer_name="李护士",
        )
        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            sign_record(str(mock_record.id), sign_req, db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 400
        assert "归档总结" in str(exc.value.detail)

    def test_sign_blocks_non_nurse(self):
        """非护士角色不可签名"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload

        sign_req = FollowUpSignatureRequest(
            signature_image="data:image/png;base64,...",
            signer_name="孕妇",
        )
        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            sign_record(str(uuid4()), sign_req, db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 403
        assert "护士" in str(exc.value.detail)

    def test_sign_rejects_non_confirmed(self):
        """非 confirmed 状态不可签名"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "completed"  # 未确认

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        sign_req = FollowUpSignatureRequest(
            signature_image="base64...",
            signer_name="李护士",
        )
        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            sign_record(str(mock_record.id), sign_req, db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 400
        assert "confirmed" in str(exc.value.detail)


# ═══════════════════════════════════════════════════════════
# 单元测试: archive summary draft/final
# ═══════════════════════════════════════════════════════════

class TestArchiveSummary:
    """AI 原稿与护士定稿必须分离保存"""

    def test_save_archive_summary_rejects_unmodified_ai_draft(self):
        """护士定稿与 AI 原稿完全相同时拒绝保存"""
        from app.routers.followup import update_archive_summary
        from app.core.auth import TokenPayload

        mock_record = _make_mock_record(status="confirmed")
        mock_record.ai_snapshot = {
            "archive_summary_draft_text": "温馨总结：本次随访平稳\n趋势分析：稳定\n个性化建议：继续保持",
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        req = FollowUpArchiveSummaryRequest(
            summary_text="温馨总结：本次随访平稳\n趋势分析：稳定\n个性化建议：继续保持",
        )
        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            update_archive_summary(str(mock_record.id), req, db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 400
        assert "必须和 AI 原稿不同" in str(exc.value.detail)

    def test_save_archive_summary_marks_modified_when_changed(self):
        """护士定稿不同于 AI 原稿时保存为 final 并打修改标记"""
        from app.routers.followup import update_archive_summary
        from app.core.auth import TokenPayload

        mock_record = _make_mock_record(status="confirmed")
        mock_record.ai_snapshot = {
            "archive_summary_draft_text": "温馨总结：本次随访平稳\n趋势分析：稳定\n个性化建议：继续保持",
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        req = FollowUpArchiveSummaryRequest(
            summary_text="温馨总结：护士复核后确认本次随访平稳。\n趋势分析：血压和胎动记录稳定。\n个性化建议：继续按时监测并按期产检。",
        )
        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        result = update_archive_summary(str(mock_record.id), req, db=mock_db, current_user=mock_user)

        assert result.modified is True
        assert mock_record.ai_snapshot["archive_summary_modified"] is True
        assert mock_record.ai_snapshot["archive_summary_final_text"] == req.summary_text
        assert mock_record.ai_snapshot["archive_summary_modified_by"] == "N001"
        mock_db.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════
# 单元测试: POST /records/{record_id}/archive
# ═══════════════════════════════════════════════════════════

class TestArchiveRecord:
    """归档流程 — 签名检查 + 状态机 + AI 总结"""

    def test_archive_requires_signature(self):
        """没签名不可归档"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "confirmed"
        mock_record.signature_data = {}  # 无签名

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(archive_record(str(mock_record.id), db=mock_db, current_user=mock_user))
        assert exc.value.status_code == 400
        assert "签名" in str(exc.value.detail)

    def test_archive_requires_nurse_modified_archive_summary(self):
        """即使已有签名，归档前也必须存在护士修改后的总结"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_record = _make_mock_record(
            status="confirmed",
            signature_data={"image": "sig", "signer": "护士", "signed_at": "..."},
        )
        mock_record.ai_snapshot = {
            "archive_summary_draft_text": "温馨总结：AI原稿",
            "archive_summary_final_text": "温馨总结：AI原稿",
            "archive_summary_modified": False,
        }

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(archive_record(str(mock_record.id), db=mock_db, current_user=mock_user))
        assert exc.value.status_code == 400
        assert "归档总结" in str(exc.value.detail)

    def test_archive_with_signature_succeeds(self):
        """有签名 + confirmed 状态 → 归档成功"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_record = _make_mock_record(
            status="confirmed",
            signature_data={"image": "base64-sig", "signer": "护士长", "signed_at": "2026-06-18T10:00:00"},
            ai_snapshot={
                "archive_summary_draft_text": "温馨总结：AI原稿",
                "archive_summary_final_text": "温馨总结：护士复核后的归档总结",
                "archive_summary_modified": True,
            },
        )

        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "测试孕妇"
        mock_pregnant.nickname = "小测"
        mock_pregnant.risk_tags = []

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_record, mock_pregnant]

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with patch("app.routers.followup._generate_llm_summary", new_callable=AsyncMock) as mock_ai:
            result = asyncio.run(archive_record(str(mock_record.id), db=mock_db, current_user=mock_user))

        assert result.status == "archived"
        mock_ai.assert_not_called()
        assert mock_record.record_snapshot["archive_summary_final_text"] == "温馨总结：护士复核后的归档总结"

    def test_archive_blocks_non_nurse(self):
        """非护士不可归档"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_user = TokenPayload(sub="P001", role="pregnant", pregnant_id="P001")
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(archive_record(str(uuid4()), db=mock_db, current_user=mock_user))
        assert exc.value.status_code == 403

    def test_archive_rejects_non_confirmed_status(self):
        """非 confirmed 状态不可归档"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.status = "completed"
        mock_record.signature_data = {"image": "sig", "signer": "护士", "signed_at": "..."}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(archive_record(str(mock_record.id), db=mock_db, current_user=mock_user))
        assert exc.value.status_code == 400
        assert "状态转换" in str(exc.value.detail)

    def test_archive_ai_failure_still_proceeds(self):
        """AI 总结生成失败不应阻塞归档流程"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        mock_record = _make_mock_record(
            status="confirmed",
            signature_data={"image": "sig", "signer": "护士", "signed_at": "..."},
            ai_snapshot={
                "archive_summary_draft_text": "温馨总结：AI原稿",
                "archive_summary_final_text": "温馨总结：护士复核后的归档总结",
                "archive_summary_modified": True,
            },
        )

        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "测试孕妇"
        mock_pregnant.nickname = "小测"
        mock_pregnant.risk_tags = []

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_record, mock_pregnant]

        mock_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")

        with patch("app.routers.followup._generate_llm_summary", new_callable=AsyncMock) as mock_ai:
            mock_ai.side_effect = RuntimeError("AI service unavailable")
            result = asyncio.run(archive_record(str(mock_record.id), db=mock_db, current_user=mock_user))

        # 归档仍然成功
        assert result.status == "archived"
        mock_ai.assert_not_called()


# ═══════════════════════════════════════════════════════════
# 集成测试: 完整归档链路 (TestClient + SQLite)
# ═══════════════════════════════════════════════════════════

class TestArchiveFlowIntegration:
    """端到端: get → sign → archive 完整链路"""

    @patch("app.routers.followup._generate_llm_summary", new_callable=AsyncMock)
    def test_full_archive_flow(self, mock_ai):
        """完整归档链路: 确认 → 获取记录 → 签名 → 归档"""
        mock_ai.return_value = {
            "warm_summary": "各项指标正常",
            "abnormal_indicators": [],
            "trend_analysis": "稳定",
            "personalized_advice": "继续保持",
        }

        # 使用 override 注入测试 DB
        db = TestSession()
        try:
            # 1. 准备数据
            _seed_pregnant(db, "P-ARCHIVE-01")
            rec = _seed_record(db, "P-ARCHIVE-01", status="confirmed", with_signature=False)

            # 2.1 生成 AI 原稿并保存护士定稿（定稿必须不同）
            draft_resp = client.post(
                f"/api/v1/followup/records/{rec.id}/archive-summary/generate",
                headers=_auth_headers,
            )
            assert draft_resp.status_code == 200
            ai_draft_text = draft_resp.json()["ai_draft_text"]

            same_resp = client.put(
                f"/api/v1/followup/records/{rec.id}/archive-summary",
                json={"summary_text": ai_draft_text},
                headers=_auth_headers,
            )
            assert same_resp.status_code == 400
            assert "必须和 AI 原稿不同" in same_resp.json()["detail"]

            final_text = ai_draft_text + "\n护士复核补充：已电话确认孕妇理解本次指导，建议按期产检。"
            save_resp = client.put(
                f"/api/v1/followup/records/{rec.id}/archive-summary",
                json={"summary_text": final_text},
                headers=_auth_headers,
            )
            assert save_resp.status_code == 200
            assert save_resp.json()["modified"] is True

            # 2. GET 获取记录，验证状态
            resp = client.get(f"/api/v1/followup/records/{rec.id}", headers=_auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "confirmed"
            assert not data.get("signature_data") or not data["signature_data"].get("image")

            # 3. 签名
            sign_resp = client.post(
                f"/api/v1/followup/records/{rec.id}/sign",
                json={"signature_image": "data:image/png;base64,FAKE", "signer_name": "李护士"},
                headers=_auth_headers,
            )
            assert sign_resp.status_code == 200
            assert sign_resp.json()["message"] == "签名已保存"

            # 4. 再次 GET 验证签名已存储
            resp2 = client.get(f"/api/v1/followup/records/{rec.id}", headers=_auth_headers)
            assert resp2.status_code == 200
            sig_data = resp2.json()["signature_data"]
            assert sig_data["signer"] == "李护士"

            # 5. 归档
            arch_resp = client.post(
                f"/api/v1/followup/records/{rec.id}/archive",
                headers=_auth_headers,
            )
            assert arch_resp.status_code == 200
            assert arch_resp.json()["status"] == "archived"

            # 6. 验证归档后状态
            resp3 = client.get(f"/api/v1/followup/records/{rec.id}", headers=_auth_headers)
            assert resp3.status_code == 200
            assert resp3.json()["status"] == "archived"
            # 护士定稿应已进入归档快照
            ai_snap = resp3.json()["ai_snapshot"]
            assert ai_snap["archive_summary_modified"] is True
            assert ai_snap["archive_summary_final_text"] == final_text
            assert resp3.json()["record_snapshot"]["archive_summary_final_text"] == final_text

        finally:
            db.close()

    def test_document_endpoint_handles_legacy_string_guidance_tags(self):
        """旧记录 guidance_tags 为字符串数组时，document 接口不应 500。"""
        db = TestSession()
        try:
            _seed_pregnant(db, "P-DOC-LEGACY-01")
            rec = _seed_record(
                db,
                "P-DOC-LEGACY-01",
                status="confirmed",
                guidance_tags=["营养", "运动"],
            )

            resp = client.get(
                f"/api/v1/followup/records/{rec.id}/document",
                headers=_auth_headers,
            )

            assert resp.status_code == 200
            assert resp.json()["has_document"] is True
            assert "[营养]" in resp.json()["text"]
            assert "[运动]" in resp.json()["text"]
        finally:
            db.close()

    def test_archive_without_signature_blocked(self):
        """未签名时归档应被拒绝"""
        db = TestSession()
        try:
            _seed_pregnant(db, "P-NOSIG-01")
            rec = _seed_record(db, "P-NOSIG-01", status="confirmed", with_signature=False)

            resp = client.post(
                f"/api/v1/followup/records/{rec.id}/archive",
                headers=_auth_headers,
            )
            assert resp.status_code == 400
            assert "签名" in resp.json()["detail"]

        finally:
            db.close()

    def test_get_record_pregnant_unauthorized(self):
        """孕妇无权查看他人记录（直接调用端点函数，绕过 DI override）"""
        from app.routers.followup import get_record
        from app.core.auth import TokenPayload

        db = TestSession()
        try:
            _seed_pregnant(db, "P-MINE-01")
            _seed_pregnant(db, "P-OTHER-02")
            rec = _seed_record(db, "P-OTHER-02", status="confirmed")

            pregnant_user = TokenPayload(sub="P-MINE-01", role="pregnant", pregnant_id="P-MINE-01")
            with pytest.raises(HTTPException) as exc:
                get_record(str(rec.id), db=db, current_user=pregnant_user)
            assert exc.value.status_code == 403
        finally:
            db.close()

    def test_sign_as_pregnant_blocked(self):
        """孕妇角色签名应被拒绝（直接调用端点函数）"""
        from app.routers.followup import sign_record
        from app.core.auth import TokenPayload
        from app.schemas import FollowUpArchiveSummaryRequest, FollowUpSignatureRequest

        db = TestSession()
        try:
            _seed_pregnant(db, "P-SIGN-01")
            rec = _seed_record(db, "P-SIGN-01", status="confirmed")

            pregnant_user = TokenPayload(sub="P-SIGN-01", role="pregnant", pregnant_id="P-SIGN-01")
            sign_req = FollowUpSignatureRequest(signature_image="img", signer_name="孕妇")
            with pytest.raises(HTTPException) as exc:
                sign_record(str(rec.id), sign_req, db=db, current_user=pregnant_user)
            assert exc.value.status_code == 403
        finally:
            db.close()

    def test_archive_wrong_status_blocked(self):
        """draft 状态不可归档（直接调用端点函数）"""
        from app.routers.followup import archive_record
        from app.core.auth import TokenPayload
        import asyncio

        db = TestSession()
        try:
            _seed_pregnant(db, "P-DRAFT-01")
            rec = _seed_record(db, "P-DRAFT-01", status="draft")

            nurse_user = TokenPayload(sub="N001", role="nurse", pregnant_id="")
            with pytest.raises(HTTPException) as exc:
                asyncio.run(archive_record(str(rec.id), db=db, current_user=nurse_user))
            assert exc.value.status_code == 400
            assert "状态转换" in str(exc.value.detail)
        finally:
            db.close()

    def test_get_records_list_includes_new_endpoint_result(self):
        """验证 get_records 列表和 get_record 单条返回格式一致"""
        db = TestSession()
        try:
            _seed_pregnant(db, "P-LIST-01")
            rec = _seed_record(db, "P-LIST-01", status="archived", with_signature=True)

            # 列表查询
            list_resp = client.get(
                "/api/v1/followup/records",
                params={"pregnant_id": "P-LIST-01"},
                headers=_auth_headers,
            )
            assert list_resp.status_code == 200
            records = list_resp.json()
            assert len(records) >= 1

            # 单条查询
            single_resp = client.get(
                f"/api/v1/followup/records/{rec.id}",
                headers=_auth_headers,
            )
            assert single_resp.status_code == 200

            # 关键字段一致性
            s = single_resp.json()
            m = [r for r in records if r["id"] == str(rec.id)][0]
            assert s["status"] == m["status"] == "archived"
            assert s["pregnant_id"] == m["pregnant_id"] == "P-LIST-01"

        finally:
            db.close()
