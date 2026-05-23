"""统一指标元数据注册表 — 所有模块的单一来源

各消费方按需派生所需格式：
- trend_engine: NORMAL_RANGES = {k: {"min", "max", "unit"} ...}
- health_trends: METRIC_META = {k: (name, unit, normal_range) ...}
- rule_engine: 保持原变量映射不变（不同关注点）
"""

METRIC_REGISTRY: dict[str, dict] = {
    # === 日常自报指标 ===
    "weight": {
        "name": "体重", "unit": "kg",
        "normal_range": {"min": 40, "max": 120},
        "category": "daily",
    },
    "systolic": {
        "name": "收缩压", "unit": "mmHg",
        "normal_range": {"min": 90, "max": 140},
        "category": "daily",
    },
    "diastolic": {
        "name": "舒张压", "unit": "mmHg",
        "normal_range": {"min": 60, "max": 90},
        "category": "daily",
    },
    "fetal_movement": {
        "name": "胎动", "unit": "次/小时",
        "normal_range": {"min": 3, "max": 10},
        "category": "daily",
    },
    "blood_sugar": {
        "name": "血糖", "unit": "mmol/L",
        "normal_range": {"min": 3.5, "max": 6.0},
        "category": "daily",
    },
    "blood_sugar_fasting": {
        "name": "空腹血糖", "unit": "mmol/L",
        "normal_range": {"min": 3.5, "max": 5.1},
        "category": "daily",
    },
    "blood_sugar_postprandial": {
        "name": "餐后血糖", "unit": "mmol/L",
        "normal_range": {"min": 3.5, "max": 8.5},
        "category": "daily",
    },
    "heart_rate": {
        "name": "心率", "unit": "bpm",
        "normal_range": {"min": 60, "max": 100},
        "category": "daily",
    },
    "sleep_hours": {
        "name": "睡眠", "unit": "小时",
        "normal_range": {"min": 6, "max": 10},
        "category": "daily",
    },
    "steps": {
        "name": "步数", "unit": "步",
        "normal_range": {"min": 2000, "max": 15000},
        "category": "daily",
    },
    "emotion_score": {
        "name": "情绪", "unit": "分",
        "normal_range": {"min": 1, "max": 3},
        "category": "daily",
    },
}


def get_normal_ranges() -> dict[str, dict]:
    """派生 TrendEngine 需要的 NORMAL_RANGES 格式"""
    return {
        k: {"min": v["normal_range"]["min"], "max": v["normal_range"]["max"], "unit": v["unit"]}
        for k, v in METRIC_REGISTRY.items()
    }


def get_metric_meta() -> dict[str, tuple[str, str, dict]]:
    """派生 health_trends 需要的 METRIC_META 格式: (name, unit, normal_range)"""
    return {
        k: (v["name"], v["unit"], v["normal_range"])
        for k, v in METRIC_REGISTRY.items()
    }


def get_metric_names() -> dict[str, str]:
    """派生中文名称映射: metric_code -> 中文名"""
    return {k: v["name"] for k, v in METRIC_REGISTRY.items()}
