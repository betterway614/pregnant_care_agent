"""测试 Agno RAG / Knowledge 模块

原始测试针对已重构的 AgnoRAGEngine 类。
当前实现使用 Agno 原生 Knowledge + PgVector（见 agno_knowledge.py）。
相关 RAG 端点测试在 test_rag_agno.py 中。
"""
import pytest


@pytest.mark.skip(reason="AgnoRAGEngine 已重构为 agno.knowledge.Knowledge，见 agno_knowledge.py")
def test_agno_rag_search_returns_list():
    pass


@pytest.mark.skip(reason="AgnoRAGEngine 已重构为 agno.knowledge.Knowledge，见 agno_knowledge.py")
def test_agno_rag_ask_returns_dict():
    pass


@pytest.mark.skip(reason="AgnoRAGEngine 已重构为 agno.knowledge.Knowledge，见 agno_knowledge.py")
def test_agno_rag_ask_no_results():
    pass
