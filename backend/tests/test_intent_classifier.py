"""测试意图分类器"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.intent_classifier import IntentCategory, classify_intent


def test_emergency_intent():
    assert classify_intent("我大出血了") == IntentCategory.EMERGENCY


def test_analyze_intent_for_nurse():
    assert classify_intent("帮我分析一下这个孕妇的情况", role="nurse") == IntentCategory.ANALYZE


def test_followup_intent():
    assert classify_intent("安排一次随访") == IntentCategory.FOLLOWUP


def test_chat_default():
    assert classify_intent("你好") == IntentCategory.CHAT
