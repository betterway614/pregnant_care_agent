"""审计日志 + Agent 路由 集成测试"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock


# ==================== Agent 路由集成测试 ====================


@pytest.mark.asyncio
async def test_chat_routing_uses_chat_variant():
    """集成测试：问候消息应路由到 chat 变体（3 tools）"""
    from app.schemas import ChatSendRequest

    req = ChatSendRequest(pregnant_id="P001", message="你好小安", message_type="TEXT")

    mock_response = MagicMock()
    mock_response.content = "你好！有什么可以帮助你的吗？"
    mock_response.metrics = MagicMock()
    mock_response.metrics.input_tokens = 450
    mock_response.metrics.output_tokens = 80
    mock_response.metrics.total_tokens = 530
    mock_response.metrics.details = {}
    mock_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_response)

    # Mock NLU 引擎返回 GREETING 意图
    mock_nlu_result = MagicMock()
    mock_nlu_result.intent = "GREETING"
    mock_nlu_result.entities = {}
    mock_nlu_result.emotion = "neutral"
    mock_nlu_result.is_emergency = False

    with patch("app.core.agno_chat_handler.settings") as mock_settings:
        mock_settings.persist_chat_messages = False
        with patch("app.core.agno_agent.AGENT_VARIANT_MAP") as mock_map:
            mock_map.get.return_value = lambda: mock_agent
            with patch("app.core.agno_chat_handler._save_audit_log") as mock_audit:
                with patch("app.core.nlu_engine.nlu_engine.parse", return_value=mock_nlu_result):
                    from app.core.agno_chat_handler import handle_chat_with_agno
                    resp = await handle_chat_with_agno(req)

                    # 验证路由正确
                    mock_map.get.assert_called_once()
                    variant_arg = mock_map.get.call_args[0][0]
                    assert variant_arg == "chat", f"应路由到 chat，实际为 {variant_arg}"

                    # 验证审计日志已调用
                    mock_audit.assert_called_once()
                    audit_kwargs = mock_audit.call_args[1]
                    assert audit_kwargs["agent_role"] == "pregnant"
                    assert audit_kwargs["agent_variant"] == "chat"

                    assert resp.content == "你好！有什么可以帮助你的吗？"


@pytest.mark.asyncio
async def test_record_routing_uses_record_variant():
    """集成测试：记录体重应路由到 record 变体（4 tools）"""
    from app.schemas import ChatSendRequest

    req = ChatSendRequest(pregnant_id="P001", message="我今天体重55公斤", message_type="TEXT")

    mock_response = MagicMock()
    mock_response.content = "已为您记录体重55kg"
    mock_response.metrics = MagicMock()
    mock_response.metrics.input_tokens = 500
    mock_response.metrics.output_tokens = 100
    mock_response.metrics.total_tokens = 600
    mock_response.metrics.details = {}
    mock_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_response)

    mock_nlu_result = MagicMock()
    mock_nlu_result.intent = "RECORD_WEIGHT"
    mock_nlu_result.entities = {"weight": 55}
    mock_nlu_result.emotion = "neutral"
    mock_nlu_result.is_emergency = False

    with patch("app.core.agno_chat_handler.settings") as mock_settings:
        mock_settings.persist_chat_messages = False
        with patch("app.core.agno_agent.AGENT_VARIANT_MAP") as mock_map:
            mock_map.get.return_value = lambda: mock_agent
            with patch("app.core.agno_chat_handler._save_audit_log") as mock_audit:
                with patch("app.core.nlu_engine.nlu_engine.parse", return_value=mock_nlu_result):
                    from app.core.agno_chat_handler import handle_chat_with_agno
                    resp = await handle_chat_with_agno(req)

                    variant_arg = mock_map.get.call_args[0][0]
                    assert variant_arg == "record"
                    mock_audit.assert_called_once()
                    assert mock_audit.call_args[1]["agent_variant"] == "record"


@pytest.mark.asyncio
async def test_qa_routing_uses_qa_variant():
    """集成测试：知识问答应路由到 qa 变体（3 tools）"""
    from app.schemas import ChatSendRequest

    req = ChatSendRequest(pregnant_id="P001", message="孕期可以喝咖啡吗？", message_type="TEXT")

    mock_response = MagicMock()
    mock_response.content = "孕期建议每天咖啡因摄入不超过200mg"
    mock_response.metrics = MagicMock()
    mock_response.metrics.input_tokens = 600
    mock_response.metrics.output_tokens = 150
    mock_response.metrics.total_tokens = 750
    mock_response.metrics.details = {}
    mock_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_response)

    mock_nlu_result = MagicMock()
    mock_nlu_result.intent = "ASK_KNOWLEDGE"
    mock_nlu_result.entities = {}
    mock_nlu_result.emotion = "neutral"
    mock_nlu_result.is_emergency = False

    with patch("app.core.agno_chat_handler.settings") as mock_settings:
        mock_settings.persist_chat_messages = False
        with patch("app.core.agno_agent.AGENT_VARIANT_MAP") as mock_map:
            mock_map.get.return_value = lambda: mock_agent
            with patch("app.core.agno_chat_handler._save_audit_log") as mock_audit:
                with patch("app.core.nlu_engine.nlu_engine.parse", return_value=mock_nlu_result):
                    from app.core.agno_chat_handler import handle_chat_with_agno
                    resp = await handle_chat_with_agno(req)

                    variant_arg = mock_map.get.call_args[0][0]
                    assert variant_arg == "qa"
                    mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_nlu_failure_falls_back_to_complex():
    """集成测试：NLU 引擎异常时回退到 complex（全量10 tools）"""
    from app.schemas import ChatSendRequest

    req = ChatSendRequest(pregnant_id="P001", message="你好", message_type="TEXT")

    mock_response = MagicMock()
    mock_response.content = "你好！"
    mock_response.metrics = None
    mock_response.messages = []

    mock_agent = MagicMock()
    mock_agent.arun = AsyncMock(return_value=mock_response)

    with patch("app.core.agno_chat_handler.settings") as mock_settings:
        mock_settings.persist_chat_messages = False
        with patch("app.core.agno_agent.AGENT_VARIANT_MAP") as mock_map:
            mock_map.get.return_value = lambda: mock_agent
            with patch("app.core.agno_chat_handler._save_audit_log") as mock_audit:
                # NLU 抛出异常
                with patch("app.core.nlu_engine.nlu_engine.parse", side_effect=RuntimeError("NLU error")):
                    from app.core.agno_chat_handler import handle_chat_with_agno
                    resp = await handle_chat_with_agno(req)

                    # 应回退到 complex
                    variant_arg = mock_map.get.call_args[0][0]
                    assert variant_arg == "complex"
                    mock_audit.assert_called_once()


# ==================== _save_audit_log 单元测试 ====================


def test_save_audit_log_writes_to_db():
    """验证 _save_audit_log 正确写入 AgentAuditLog"""
    from app.core.agno_chat_handler import _save_audit_log

    mock_response = MagicMock()
    mock_response.content = "测试回复内容"
    mock_metrics = MagicMock()
    mock_metrics.input_tokens = 400
    mock_metrics.output_tokens = 100
    mock_metrics.total_tokens = 500
    mock_metrics.details = {}
    mock_response.metrics = mock_metrics
    mock_response.messages = []

    mock_db = MagicMock()
    mock_db_instance = mock_db.return_value

    with patch("app.core.agno_chat_handler.SessionLocal", mock_db):
        _save_audit_log(
            session_id="test-session",
            user_id="P001",
            agent_role="pregnant",
            agent_variant="chat",
            intent_classification="GREETING",
            run_response=mock_response,
            total_latency_ms=1000,
        )

        # 验证 add 被调用
        mock_db_instance.add.assert_called_once()
        # 验证 commit 被调用
        mock_db_instance.commit.assert_called_once()
        # 验证 close 被调用
        mock_db_instance.close.assert_called_once()


def test_save_audit_log_handles_missing_metrics():
    """验证 metrics 为 None 时也不会崩溃"""
    from app.core.agno_chat_handler import _save_audit_log

    mock_response = MagicMock()
    mock_response.content = "回复"
    mock_response.metrics = None
    mock_response.messages = []

    mock_db = MagicMock()
    mock_db_instance = mock_db.return_value

    with patch("app.core.agno_chat_handler.SessionLocal", mock_db):
        _save_audit_log(
            session_id="test-session",
            user_id="P001",
            agent_role="pregnant",
            agent_variant="chat",
            intent_classification=None,
            run_response=mock_response,
            total_latency_ms=500,
        )
        # 不应该抛出异常
        mock_db_instance.add.assert_called_once()


def test_save_audit_log_handles_db_error_gracefully():
    """验证 DB 写入失败时不会抛出异常"""
    from app.core.agno_chat_handler import _save_audit_log

    mock_response = MagicMock()
    mock_response.content = "回复"
    mock_response.metrics = None
    mock_response.messages = []

    mock_db = MagicMock()
    mock_db_instance = mock_db.return_value
    mock_db_instance.commit.side_effect = RuntimeError("DB error")

    with patch("app.core.agno_chat_handler.SessionLocal", mock_db):
        # 不应该抛出异常
        _save_audit_log(
            session_id="test-session",
            user_id="P001",
            agent_role="pregnant",
            agent_variant="chat",
            intent_classification=None,
            run_response=mock_response,
            total_latency_ms=500,
        )
        mock_db_instance.rollback.assert_called_once()


def test_save_audit_log_handles_none_run_response():
    """验证流式异常时 run_response=None 被守卫处理"""
    from app.core.agno_chat_handler import _save_audit_log

    mock_db = MagicMock()
    mock_db_instance = mock_db.return_value

    with patch("app.core.agno_chat_handler.SessionLocal", mock_db):
        _save_audit_log(
            session_id="test-session",
            user_id="P001",
            agent_role="pregnant",
            agent_variant="chat",
            intent_classification="GREETING",
            run_response=None,
            total_latency_ms=500,
        )
        # 不应崩溃，应写入0值
        mock_db_instance.add.assert_called_once()


# ==================== Admin API 集成测试 ====================


def test_admin_daily_endpoint_empty():
    """验证 admin daily API 在无数据时返回空列表"""
    from app.routers.admin import get_token_daily
    from app.models import AgentAuditLog
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value = mock_query

    with patch("app.routers.admin.SessionLocal", return_value=mock_db):
        result = get_token_daily(date_from="2026-01-01", date_to="2026-01-02")
        assert result == {"data": []}


def test_admin_daily_endpoint_with_data():
    """验证 admin daily API 正确聚合数据"""
    from app.routers.admin import get_token_daily

    mock_row = MagicMock()
    mock_row.date = "2026-05-23"
    mock_row.total_tokens = 1500
    mock_row.input_tokens = 1000
    mock_row.output_tokens = 500
    mock_row.call_count = 3
    mock_row.avg_latency_ms = 1234.5

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = [mock_row]
    mock_db.query.return_value = mock_query

    with patch("app.routers.admin.SessionLocal", return_value=mock_db):
        result = get_token_daily(date_from="2026-05-23", date_to="2026-05-23")
        assert len(result["data"]) == 1
        assert result["data"][0]["date"] == "2026-05-23"
        assert result["data"][0]["total_tokens"] == 1500
        assert result["data"][0]["call_count"] == 3


def test_admin_by_agent_endpoint():
    """验证 admin by-agent API 正确分组"""
    from app.routers.admin import get_token_by_agent

    mock_row = MagicMock()
    mock_row.agent_role = "pregnant"
    mock_row.agent_variant = "chat"
    mock_row.total_tokens = 800
    mock_row.call_count = 2
    mock_row.avg_input_tokens = 400.0
    mock_row.avg_output_tokens = 100.0
    mock_row.avg_latency_ms = 900.0

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = [mock_row]
    mock_db.query.return_value = mock_query

    with patch("app.routers.admin.SessionLocal", return_value=mock_db):
        result = get_token_by_agent(date_from="2026-05-23", date_to="2026-05-23")
        assert len(result["data"]) == 1
        assert result["data"][0]["agent_role"] == "pregnant"
        assert result["data"][0]["agent_variant"] == "chat"


def test_admin_session_endpoint():
    """验证 admin session API 返回会话审计链"""
    from app.routers.admin import get_session_audit
    from app.models import AgentAuditLog

    mock_log = MagicMock()
    mock_log.id = 1
    mock_log.agent_role = "pregnant"
    mock_log.agent_variant = "chat"
    mock_log.intent_classification = "GREETING"
    mock_log.routed_agent = "小安-chat"
    mock_log.input_tokens = 500
    mock_log.output_tokens = 100
    mock_log.total_tokens = 600
    mock_log.tool_calls_json = [{"name": "agno_parse_nlu", "success": True}]
    mock_log.model_id = "qwen3-30b"
    mock_log.total_latency_ms = 1200
    mock_log.guardrail_triggered = False
    mock_log.response_preview = "你好！有什么可以帮你的？"
    mock_log.created_at = None

    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_log]
    mock_db.query.return_value = mock_query

    with patch("app.routers.admin.SessionLocal", return_value=mock_db):
        result = get_session_audit(session_id="test-session")
        assert result["session_id"] == "test-session"
        assert result["run_count"] == 1
        assert result["runs"][0]["agent_variant"] == "chat"
        assert result["runs"][0]["total_tokens"] == 600


# ==================== 数据库迁移测试 ====================


def test_ensure_audit_log_table_creates_table():
    """验证迁移函数在表不存在时创建表"""
    from app.main import _ensure_audit_log_table
    from unittest.mock import MagicMock, patch

    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["other_table"]

    with patch("sqlalchemy.inspect", return_value=mock_inspector):
        with patch("app.main.Base") as mock_base:
            with patch("app.main.logger") as mock_logger:
                _ensure_audit_log_table()
                # 应调用 create_all
                mock_base.metadata.create_all.assert_called_once()
                mock_logger.info.assert_called_once()


def test_ensure_audit_log_table_skips_existing():
    """验证迁移函数在表已存在时跳过"""
    from app.main import _ensure_audit_log_table
    from unittest.mock import MagicMock, patch

    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["agent_audit_logs", "other_table"]

    with patch("sqlalchemy.inspect", return_value=mock_inspector):
        with patch("app.main.Base") as mock_base:
            with patch("app.main.logger") as mock_logger:
                _ensure_audit_log_table()
                # 不应调用 create_all
                mock_base.metadata.create_all.assert_not_called()
