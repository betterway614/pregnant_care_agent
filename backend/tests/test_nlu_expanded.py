from app.core.nlu_engine import nlu_engine

def test_natural_fetal_movement():
    result = nlu_engine.parse("我最近感觉宝宝动得少了")
    assert result.intent != "UNKNOWN"

def test_vague_discomfort():
    result = nlu_engine.parse("感觉今天有点不对劲")
    assert result.intent != "UNKNOWN"

def test_emergency_still_works():
    result = nlu_engine.parse("大出血了怎么办")
    assert result.is_emergency is True

def test_numeric_data():
    result = nlu_engine.parse("今天血压130/85")
    assert result.intent == "HEALTH_DATA_REPORT"
    assert result.entities.get("sbp") == 130.0
