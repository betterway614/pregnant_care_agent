"""排期引擎 - 基于孕周生成全周期随访计划"""
from datetime import date, datetime, timedelta
from typing import Optional


# 标准产检时间表（孕周 → 检查项目）
STANDARD_SCHEDULE = {
    6: "确认妊娠B超",
    8: "孕酮/HCG检查",
    12: "NT检查+早期唐筛",
    16: "中期唐筛/无创DNA",
    20: "大排畸B超",
    24: "OGTT糖耐量筛查",
    28: "妊娠期糖尿病复查",
    30: "常规产检+B超生长监测",
    32: "常规产检+胎心监护",
    34: "常规产检+胎心监护",
    36: "B超评估+胎心监护+GBS筛查",
    37: "胎心监护+产前评估",
    38: "胎心监护",
    39: "胎心监护+B超",
    40: "胎心监护+产前评估",
}


class ScheduleEngine:
    """排期计算引擎"""

    def generate(self, lmp_date: date, risk_tags: list[str] = None,
                 current_gest_week: Optional[int] = None) -> list[dict]:
        """生成全孕周排期"""
        risk_tags = risk_tags or []
        schedule = []

        for gest_week, item in STANDARD_SCHEDULE.items():
            if current_gest_week and gest_week < current_gest_week:
                continue

            # 计算日期
            node_date = lmp_date + timedelta(weeks=gest_week)

            node = {
                "gest_week": gest_week,
                "scheduled_date": node_date.isoformat(),
                "item": item,
                "node_type": "routine",
            }
            schedule.append(node)

        # 风险联动调整
        if "FGR" in risk_tags or "FGR高危" in risk_tags:
            schedule = self._add_fgr_monitoring(schedule)

        if "GDM" in risk_tags or "妊娠期糖尿病" in risk_tags:
            schedule = self._add_gdm_monitoring(schedule)

        if "高血压" in risk_tags:
            schedule = self._add_hypertension_monitoring(schedule)

        # 按日期排序
        schedule.sort(key=lambda x: (x["scheduled_date"], x["gest_week"]))

        return schedule

    def _add_fgr_monitoring(self, schedule: list[dict]) -> list[dict]:
        """FGR高危：增加B超监测频率"""
        additional = []
        for gest_week in range(24, 38, 2):  # 每2周一次
            # 检查是否已存在B超节点
            exists = any(
                n["gest_week"] == gest_week and "B超" in n["item"]
                for n in schedule
            )
            if not exists:
                node_date = self._get_base_date(schedule) + timedelta(weeks=gest_week)
                additional.append({
                    "gest_week": gest_week,
                    "scheduled_date": node_date.isoformat(),
                    "item": "B超生长监测(FGR专项)",
                    "node_type": "fgr_high_risk",
                })
        schedule.extend(additional)
        return schedule

    def _add_gdm_monitoring(self, schedule: list[dict]) -> list[dict]:
        """GDM：增加血糖监测节点"""
        additional = []
        for gest_week in range(26, 38, 2):
            node_date = self._get_base_date(schedule) + timedelta(weeks=gest_week)
            additional.append({
                "gest_week": gest_week,
                "scheduled_date": node_date.isoformat(),
                "item": "血糖监测复查",
                "node_type": "gdm_monitor",
            })
        schedule.extend(additional)
        return schedule

    def _add_hypertension_monitoring(self, schedule: list[dict]) -> list[dict]:
        """高血压：增加血压监测节点"""
        additional = []
        for gest_week in range(28, 38, 2):
            node_date = self._get_base_date(schedule) + timedelta(weeks=gest_week)
            additional.append({
                "gest_week": gest_week,
                "scheduled_date": node_date.isoformat(),
                "item": "血压监测+尿蛋白检查",
                "node_type": "bp_monitor",
            })
        schedule.extend(additional)
        return schedule

    def _get_base_date(self, schedule: list[dict]) -> date:
        """从已有排期反推LMP基准日期"""
        for item in schedule:
            if "scheduled_date" in item:
                d = date.fromisoformat(item["scheduled_date"])
                return d - timedelta(weeks=item["gest_week"])
        return date.today()


schedule_engine = ScheduleEngine()
