"""排期引擎 - 基于孕周生成全周期产检计划

数据来源（2025-2026 最新指南）：
- 附录一：13次标准产检完整时间表（ACOG/中华医学会）
- 附录二：5个超声关键节点
- 附录三：8项常见产检项目速查
"""
from datetime import date, timedelta
from typing import Optional


# =============================================================================
# 附录一：标准产检完整时间表（13次）
# 每项包含：序号、建议孕周范围、检查频率、必查项目、备查项目、注意事项
# =============================================================================
COMPLETE_PRENATAL_SCHEDULE = [
    {
        "visit_number": 1,
        "gest_week_range": (6, 10),
        "frequency": "once",
        "category": "checkup",
        "item": "首次产检+建档",
        "mandatory_items": [
            "确认妊娠B超（排除宫外孕、确认胎心胎芽）",
            "血HCG、孕酮",
            "基础检查：身高、体重、血压、血尿常规",
            "血型（ABO+Rh）、肝肾功能、凝血功能",
            "乙肝、梅毒、HIV筛查",
            "甲状腺功能、心电图",
        ],
        "optional_items": [
            "孕酮检测（有流产史/出血史）",
            "叶酸代谢能力基因检测",
        ],
        "notes": "首次产检同时完成建档；建议空腹前往；携带身份证、医保卡",
    },
    {
        "visit_number": 2,
        "gest_week_range": (11, 13),
        "frequency": "once",
        "category": "checkup",
        "item": "NT筛查+早期唐筛",
        "mandatory_items": [
            "NT超声（颈项透明层测量）",
            "早期唐筛（血清PAPP-A、β-hCG）",
        ],
        "optional_items": [
            "NIPT无创DNA（10-22周）",
            "绒毛穿刺（11-14周，有指征时）",
        ],
        "notes": "NT需严格在窗口期内完成（CRL 45-84mm）；NT值≥3.0mm需遗传咨询",
    },
    {
        "visit_number": 3,
        "gest_week_range": (15, 20),
        "frequency": "every_4_weeks",
        "category": "checkup",
        "item": "中期唐筛+常规产检",
        "mandatory_items": [
            "中期唐筛（血清学筛查）",
            "血压、体重、宫高、胎心率",
        ],
        "optional_items": [
            "NIPT无创DNA（12-22周）",
            "羊水穿刺（16-22周，诊断金标准）",
        ],
        "notes": "NIPT为筛查非诊断，高风险需羊穿确认；准确率＞95%",
    },
    {
        "visit_number": 4,
        "gest_week_range": (20, 24),
        "frequency": "every_4_weeks",
        "category": "checkup",
        "item": "大排畸（系统超声筛查）",
        "mandatory_items": [
            "系统超声筛查（头颅、颜面、心脏、脊柱、腹部、四肢）",
            "血压、体重、宫高、胎心率",
        ],
        "optional_items": [
            "三维/四维超声（可留存照片，非临床必需）",
        ],
        "notes": "需提前1-2周预约；无需空腹，可适当进食；检查时间40-60分钟",
    },
    {
        "visit_number": 5,
        "gest_week_range": (24, 28),
        "frequency": "every_4_weeks",
        "category": "checkup",
        "item": "OGTT糖耐量筛查",
        "mandatory_items": [
            "75g葡萄糖OGTT糖耐筛查（诊断妊娠期糖尿病）",
            "血压、体重、宫高、胎心率",
        ],
        "optional_items": [
            "血常规（复查贫血状况）",
        ],
        "notes": "前晚禁食8-12小时；携带300ml水杯溶解糖粉；空腹/1h/2h三次采血",
    },
    {
        "visit_number": 6,
        "gest_week_range": (28, 32),
        "frequency": "biweekly",
        "category": "checkup",
        "item": "小排畸+常规产检",
        "mandatory_items": [
            "小排畸补充超声（评估晚发型畸形、胎儿生长发育）",
            "血压、体重、宫高、胎心率、胎位",
            "血尿常规",
        ],
        "optional_items": [
            "胎心监护NST（34周后每周1次，高危人群可能提前至32周）",
        ],
        "notes": "进入孕晚期后加强胎动计数；每日固定晚饭后1小时左侧卧数胎动",
    },
    {
        "visit_number": 7,
        "gest_week_range": (33, 36),
        "frequency": "biweekly",
        "category": "checkup",
        "item": "常规产检+超声复查",
        "mandatory_items": [
            "血压、体重、宫高、胎心率、胎位",
            "尿常规",
        ],
        "optional_items": [
            "超声复查（评估胎儿体重、羊水量、胎盘成熟度）",
        ],
        "notes": "33周后应确定分娩方式（顺产/剖宫产）",
    },
    {
        "visit_number": 8,
        "gest_week_range": (35, 37),
        "frequency": "biweekly",
        "category": "checkup",
        "item": "GBS筛查+常规产检",
        "mandatory_items": [
            "GBS B族链球菌筛查（阴道+直肠采样）",
            "血压、体重、宫高、胎心率、胎位",
        ],
        "optional_items": [
            "铁蛋白（筛查贫血）",
            "心电图",
        ],
        "notes": "GBS阳性者分娩时需抗生素预防新生儿感染；结果有效期5周",
    },
    {
        "visit_number": 9,
        "gest_week_range": (37, 38),
        "frequency": "weekly",
        "category": "checkup",
        "item": "胎心监护+产前评估",
        "mandatory_items": [
            "胎心监护NST（每周1次）",
            "血压、体重、宫高、胎位",
        ],
        "optional_items": [
            "超声评估（胎儿大小、胎位、羊水量、胎盘成熟度）",
            "骨盆内检（评估宫颈软化扩张程度）",
        ],
        "notes": "出现临产信号随时入院；异常胎动立即就医",
    },
    {
        "visit_number": 10,
        "gest_week_range": (38, 39),
        "frequency": "weekly",
        "category": "checkup",
        "item": "胎心监护",
        "mandatory_items": [
            "胎心监护NST",
            "血压、体重、宫高、胎位",
        ],
        "optional_items": [],
        "notes": "每周复查；注意胎动变化",
    },
    {
        "visit_number": 11,
        "gest_week_range": (39, 40),
        "frequency": "weekly",
        "category": "checkup",
        "item": "胎心监护+B超",
        "mandatory_items": [
            "胎心监护NST",
            "超声评估（胎儿大小、胎位、羊水量、胎盘成熟度）",
            "血压、体重、宫高、胎位",
        ],
        "optional_items": [],
        "notes": "评估分娩条件；关注羊水指数",
    },
    {
        "visit_number": 12,
        "gest_week_range": (40, 41),
        "frequency": "weekly",
        "category": "checkup",
        "item": "胎心监护+产前评估",
        "mandatory_items": [
            "胎心监护NST",
            "血压、体重、宫高、胎位",
        ],
        "optional_items": [],
        "notes": "41周后常规引产；密切监测胎动",
    },
    {
        "visit_number": 13,
        "gest_week_range": (41, 42),
        "frequency": "weekly",
        "category": "checkup",
        "item": "产前终评+分娩准备",
        "mandatory_items": [
            "胎心监护NST",
            "超声评估",
            "血压、体重、宫高、胎位",
        ],
        "optional_items": [
            "骨盆内检",
        ],
        "notes": "41周后常规引产；确认分娩医院及方案",
    },
]


# =============================================================================
# 附录二：超声检查关键节点（5个里程碑）
# =============================================================================
ULTRASOUND_MILESTONES = [
    {
        "gest_week_range": (6, 8),
        "item": "早期确认妊娠超声",
        "purpose": "确认宫内妊娠、胎心胎芽、排除宫外孕及葡萄胎",
        "technical_notes": "需憋尿（腹超）或排空膀胱（阴超）",
    },
    {
        "gest_week_range": (11, 13),
        "item": "NT筛查超声",
        "purpose": "测量颈项透明层厚度，筛查染色体异常",
        "technical_notes": "CRL需在45-84mm范围内；NT≥3.0mm需遗传咨询",
    },
    {
        "gest_week_range": (20, 24),
        "item": "大排畸（系统超声）",
        "purpose": "筛查胎儿严重结构畸形：无脑畸形、严重脊柱裂、先心病等9大类",
        "technical_notes": "持续40-60分钟；最全面的胎儿结构检查",
    },
    {
        "gest_week_range": (28, 32),
        "item": "小排畸（补充超声）",
        "purpose": "补充筛查迟发性畸形（约15%先天性心脏病在晚孕期才明显表现）",
        "technical_notes": "侧脑室＞10mm提示脑积水风险；肾盂分离＞10mm警惕泌尿系梗阻",
    },
    {
        "gest_week_range": (37, 41),
        "item": "分娩前评估超声",
        "purpose": "评估胎儿大小、胎位、羊水量、胎盘成熟度，为分娩决策提供依据",
        "technical_notes": "羊水指数＜5cm时胎儿窘迫风险增加3倍",
    },
]


# =============================================================================
# 附录三：常见产检项目速查
# =============================================================================
CHECKUP_ITEMS_REFERENCE = {
    "NT超声": {
        "timing": "11-13+6周",
        "method": "B超",
        "report_cycle": "即时",
        "notes": "染色体异常筛查软指标，正常值＜2.5-3.0mm",
    },
    "NIPT无创DNA": {
        "timing": "12-22+6周（最佳13-20+6周）",
        "method": "母体外周血",
        "report_cycle": "7-14天",
        "notes": "筛查21/18/13三体，NIPT-Plus可检测更多微缺失综合征",
    },
    "中期唐筛": {
        "timing": "15-20周",
        "method": "血清学",
        "report_cycle": "5-10天",
        "notes": "准确率60-70%，NIPT准确率更高",
    },
    "羊水穿刺": {
        "timing": "16-22周",
        "method": "穿刺获取羊水",
        "report_cycle": "2-4周（含细胞培养）",
        "notes": "产前诊断金标准，流产风险约1/1000",
    },
    "大排畸": {
        "timing": "20-24周",
        "method": "系统B超",
        "report_cycle": "即时",
        "notes": "最全面的胎儿结构筛查，需提前预约",
    },
    "OGTT糖耐": {
        "timing": "24-28周",
        "method": "静脉采血3次",
        "report_cycle": "1-2天",
        "notes": "前晚禁食8-12小时，筛查妊娠期糖尿病",
    },
    "GBS筛查": {
        "timing": "35-37周",
        "method": "阴道+直肠拭子",
        "report_cycle": "2-5天",
        "notes": "筛查B族链球菌携带，结果有效期5周",
    },
    "NST胎心监护": {
        "timing": "34周起每周",
        "method": "胎心监护仪",
        "report_cycle": "即时",
        "notes": "每次20-40分钟，评估胎儿宫内储备能力",
    },
}


class ScheduleEngine:
    """产检排期计算引擎"""

    def generate(
        self,
        lmp_date: date,
        risk_tags: list[str] = None,
        current_gest_week: Optional[int] = None,
    ) -> list[dict]:
        """生成全孕周排期

        Args:
            lmp_date: 末次月经日期
            risk_tags: 风险标签列表（如 ["FGR高危", "GDM"]）
            current_gest_week: 当前孕周（用于跳过已过期检查）

        Returns:
            排期节点列表，每个节点包含完整字段
        """
        risk_tags = risk_tags or []
        schedule = []

        # ---- 1. 生成标准13次产检 ----
        for visit in COMPLETE_PRENATAL_SCHEDULE:
            gest_start, gest_end = visit["gest_week_range"]

            # 跳过已完全过去的孕周范围
            if current_gest_week and gest_end < current_gest_week:
                continue

            # 取范围中点作为计划孕周
            mid_week = (gest_start + gest_end) // 2
            node_date = lmp_date + timedelta(weeks=mid_week)

            node = {
                "gest_week": mid_week,
                "gest_week_start": gest_start,
                "gest_week_end": gest_end,
                "scheduled_date": node_date.isoformat(),
                "item": visit["item"],
                "node_type": "routine",
                "visit_number": visit["visit_number"],
                "category": visit["category"],
                "frequency": visit["frequency"],
                "mandatory_items": list(visit["mandatory_items"]),
                "optional_items": list(visit["optional_items"]),
                "notes": visit["notes"],
            }
            schedule.append(node)

        # ---- 2. 合并超声里程碑（去重） ----
        for us in ULTRASOUND_MILESTONES:
            us_start, us_end = us["gest_week_range"]
            if current_gest_week and us_end < current_gest_week:
                continue

            # 检查是否已存在同名超声节点
            already_covered = any(
                "超声" in n.get("item", "")
                and n.get("gest_week_start", 99) <= us_start
                and n.get("gest_week_end", 0) >= us_end
                for n in schedule
            )
            if already_covered:
                continue

            mid_week = (us_start + us_end) // 2
            node_date = lmp_date + timedelta(weeks=mid_week)

            schedule.append({
                "gest_week": mid_week,
                "gest_week_start": us_start,
                "gest_week_end": us_end,
                "scheduled_date": node_date.isoformat(),
                "item": us["item"],
                "node_type": "ultrasound",
                "visit_number": None,  # 超声里程碑不属于13次标准产检序号
                "category": "ultrasound",
                "frequency": "once",
                "mandatory_items": [],
                "optional_items": [],
                "notes": f"{us['purpose']}。{us['technical_notes']}",
            })

        # ---- 3. 风险联动调整 ----
        if any(t in ("FGR", "FGR高危") for t in risk_tags):
            schedule = self._add_fgr_monitoring(schedule)

        if any(t in ("GDM", "妊娠期糖尿病") for t in risk_tags):
            schedule = self._add_gdm_monitoring(schedule)

        if "高血压" in risk_tags:
            schedule = self._add_hypertension_monitoring(schedule)

        # ---- 4. 按日期排序 ----
        schedule.sort(key=lambda x: (x["scheduled_date"], x["gest_week"]))

        return schedule

    # =========================================================================
    # 风险联动规则
    # =========================================================================

    def _add_fgr_monitoring(self, schedule: list[dict]) -> list[dict]:
        """FGR高危：孕24-38周每2周增加B超生长监测"""
        additional = []
        for gest_week in range(24, 38, 2):
            exists = any(
                n.get("gest_week") == gest_week and "B超" in n.get("item", "")
                for n in schedule
            )
            if not exists:
                base_date = self._get_base_date(schedule)
                additional.append({
                    "gest_week": gest_week,
                    "gest_week_start": gest_week,
                    "gest_week_end": gest_week + 1,
                    "scheduled_date": (base_date + timedelta(weeks=gest_week)).isoformat(),
                    "item": "B超生长监测(FGR专项)",
                    "node_type": "fgr_high_risk",
                    "visit_number": None,
                    "category": "ultrasound",
                    "frequency": "biweekly",
                    "mandatory_items": ["B超生长监测"],
                    "optional_items": [],
                    "notes": "FGR高危专项监测：每2周评估胎儿生长速度、血流动力学",
                })
        schedule.extend(additional)
        return schedule

    def _add_gdm_monitoring(self, schedule: list[dict]) -> list[dict]:
        """GDM：孕26-38周每2周增加血糖监测复查"""
        additional = []
        for gest_week in range(26, 38, 2):
            base_date = self._get_base_date(schedule)
            additional.append({
                "gest_week": gest_week,
                "gest_week_start": gest_week,
                "gest_week_end": gest_week + 1,
                "scheduled_date": (base_date + timedelta(weeks=gest_week)).isoformat(),
                "item": "血糖监测复查",
                "node_type": "gdm_monitor",
                "visit_number": None,
                "category": "lab",
                "frequency": "biweekly",
                "mandatory_items": ["空腹血糖", "餐后2h血糖"],
                "optional_items": ["糖化血红蛋白"],
                "notes": "GDM专项：每2周监测血糖控制情况；控精制糖、低GI饮食",
            })
        schedule.extend(additional)
        return schedule

    def _add_hypertension_monitoring(self, schedule: list[dict]) -> list[dict]:
        """高血压：孕28-38周每2周增加血压监测+尿蛋白"""
        additional = []
        for gest_week in range(28, 38, 2):
            base_date = self._get_base_date(schedule)
            additional.append({
                "gest_week": gest_week,
                "gest_week_start": gest_week,
                "gest_week_end": gest_week + 1,
                "scheduled_date": (base_date + timedelta(weeks=gest_week)).isoformat(),
                "item": "血压监测+尿蛋白检查",
                "node_type": "bp_monitor",
                "visit_number": None,
                "category": "checkup",
                "frequency": "biweekly",
                "mandatory_items": ["血压测量", "尿蛋白定性/定量"],
                "optional_items": ["24小时尿蛋白定量", "肝肾功能"],
                "notes": "高血压专项：每2周监测；警惕子痫前期（头痛/视力模糊/上腹痛/水肿）",
            })
        schedule.extend(additional)
        return schedule

    def _get_base_date(self, schedule: list[dict]) -> date:
        """从已有排期反推LMP基准日期"""
        for item in schedule:
            if "scheduled_date" in item and "gest_week" in item:
                d = date.fromisoformat(item["scheduled_date"])
                return d - timedelta(weeks=item["gest_week"])
        return date.today()


schedule_engine = ScheduleEngine()
