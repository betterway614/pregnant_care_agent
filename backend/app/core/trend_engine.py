"""健康趋势分析引擎 - 分析孕妇历史健康数据，生成趋势洞察"""
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class TrendResult:
    metric: str
    current_value: float | None
    unit: str
    trend: str  # "rising", "falling", "stable", "insufficient_data"
    summary: str
    is_normal: bool | None  # None = 无法判断


class TrendEngine:
    """分析 HealthDataPoint 历史数据，生成趋势摘要"""

    # 各指标正常范围（简化版，实际应基于孕周动态调整）
    NORMAL_RANGES = {
        "weight": {"min": 40, "max": 120, "unit": "kg"},
        "systolic": {"min": 90, "max": 140, "unit": "mmHg"},
        "diastolic": {"min": 60, "max": 90, "unit": "mmHg"},
        "fetal_movement": {"min": 3, "max": 10, "unit": "次/小时"},
        "blood_sugar": {"min": 3.5, "max": 6.0, "unit": "mmol/L"},
        "heart_rate": {"min": 60, "max": 100, "unit": "bpm"},
        "emotion_score": {"min": 0, "max": 8, "unit": "分"},
        "sleep_hours": {"min": 6, "max": 10, "unit": "小时"},
        "steps": {"min": 2000, "max": 15000, "unit": "步"},
    }

    def analyze(self, health_records: list[dict], gest_week: int = 0) -> list[TrendResult]:
        """
        分析健康数据记录，返回各指标趋势

        health_records: [{"metric": "weight", "value": 65.0, "unit": "kg", "recorded_at": "..."}]
        """
        # 按指标分组
        by_metric: dict[str, list[dict]] = {}
        for r in health_records:
            m = r.get("metric", "")
            if m not in by_metric:
                by_metric[m] = []
            by_metric[m].append(r)

        results = []
        for metric, records in by_metric.items():
            result = self._analyze_metric(metric, records, gest_week)
            if result:
                results.append(result)
        return results

    def _analyze_metric(self, metric: str, records: list[dict], gest_week: int) -> TrendResult | None:
        if len(records) < 2:
            return None

        values = [r["value"] for r in records if r.get("value") is not None]
        if len(values) < 2:
            return None

        unit = records[0].get("unit", "")
        current = values[-1]
        first_half = values[:len(values) // 2]
        second_half = values[len(values) // 2:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        diff = avg_second - avg_first
        threshold = max(abs(avg_first) * 0.1, 0.3)  # 10% 或 0.3 作为变化阈值（对低值指标更敏感）

        if diff > threshold:
            trend = "rising"
        elif diff < -threshold:
            trend = "falling"
        else:
            trend = "stable"

        # 判断是否正常
        is_normal = None
        norm = self.NORMAL_RANGES.get(metric)
        if norm:
            is_normal = norm["min"] <= current <= norm["max"]

        # 生成摘要
        summary = self._generate_summary(metric, current, unit, trend, is_normal, gest_week, len(values))

        return TrendResult(
            metric=metric,
            current_value=current,
            unit=unit,
            trend=trend,
            summary=summary,
            is_normal=is_normal,
        )

    def _generate_summary(self, metric: str, current: float, unit: str,
                          trend: str, is_normal: bool | None, gest_week: int, data_count: int) -> str:
        metric_names = {
            "weight": "体重",
            "systolic": "收缩压",
            "diastolic": "舒张压",
            "fetal_movement": "胎动",
            "blood_sugar": "血糖",
            "heart_rate": "心率",
            "emotion_score": "情绪评分",
            "sleep_hours": "睡眠时长",
            "steps": "运动步数",
        }
        name = metric_names.get(metric, metric)

        trend_text = {
            "rising": "呈上升趋势",
            "falling": "呈下降趋势",
            "stable": "保持稳定",
        }.get(trend, "数据不足")

        if trend == "stable":
            if is_normal is True:
                return f"您的{name}最近稳定在 {current}{unit}，处于正常范围。"
            elif is_normal is False:
                return f"您的{name}最近稳定在 {current}{unit}，需要关注。建议咨询医生。"
            else:
                return f"您的{name}最近稳定在 {current}{unit}。"
        else:
            direction = "升高" if trend == "rising" else "降低"
            if is_normal is False:
                return f"您的{name}最近{direction}，当前 {current}{unit}，需要关注。建议咨询医生。"
            else:
                return f"您的{name}最近{trend_text}，当前 {current}{unit}。"


# 全局单例
trend_engine = TrendEngine()
