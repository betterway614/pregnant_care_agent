"""Mock 数据注入脚本"""
import uuid
import random
from datetime import datetime, date, timedelta
from sqlalchemy import text
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, ScheduleNode, FollowUpRecord, FgrAssessment, Alert


def seed_all():
    """注入全部Mock数据"""
    db = SessionLocal()
    try:
        _seed_patients(db)
        _seed_health_data(db)
        _seed_schedules(db)
        _seed_fgr_assessments(db)
        _seed_alerts(db)
        db.commit()
        print("✅ Mock数据注入完成")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def _seed_patients(db):
    """生成20条匿名孕妇"""
    existing = db.query(Pregnant).count()
    if existing > 0:
        print("   孕妇数据已存在，跳过")
        return

    risk_configs = [
        ([], "正常"),  # 正常孕妇
        ([], "正常"),
        (["FGR高危"], "FGR"),
        (["FGR高危"], "FGR"),
        (["GDM"], "GDM"),
        ([], "正常"),
        (["高血压"], "高血压"),
        ([], "正常"),
        (["FGR高危", "GDM"], "FGR+GDM"),
        ([], "正常"),
        (["高血压"], "高血压"),
        ([], "正常"),
        (["FGR高危"], "FGR"),
        ([], "正常"),
        (["GDM"], "GDM"),
        ([], "正常"),
        (["FGR高危", "高血压"], "FGR+高血压"),
        ([], "正常"),
        ([], "正常"),
        (["GDM"], "GDM"),
    ]

    base_date = datetime.now() - timedelta(days=120)
    for i in range(20):
        gest_days = random.randint(84, 280)  # 12w ~ 40w
        lmp = (datetime.now() - timedelta(days=gest_days)).date()
        edd = lmp + timedelta(days=280)

        nicknames = ["小美", "阿芳", "静静", "思思", "晓月", "雨晴", "梦琪", "诗涵",
                     "欣怡", "雅茹", "婉清", "若兰", "雪婷", "慧敏", "嘉玲", "秀英",
                     "美琳", "丽华", "晓红", "艳芳"]
        phones = [f"138****{random.randint(1000,9999)}" for _ in range(20)]
        hospital_ids = [f"H2025{i:03d}" for i in range(1, 21)]

        pregnant = Pregnant(
            pregnant_id=f"PT_{uuid.uuid4().hex[:12].upper()}",
            display_name=f"孕妇{i+1:02d}",
            nickname=nicknames[i],
            phone=phones[i],
            hospital_id=hospital_ids[i],
            gestational_age_days=gest_days,
            lmp_date=lmp,
            edd=edd,
            risk_tags=risk_configs[i][0],
            created_at=base_date + timedelta(days=i * 3),
        )
        db.add(pregnant)
    print(f"   ✅ 生成 20 条孕妇数据")


def _seed_health_data(db):
    """生成健康指标时间序列"""
    pregnant = db.query(Pregnant).all()
    count = 0
    for pregnant in pregnant:
        for days_ago in range(0, 56, 2):  # 每2天一条
            record_date = datetime.now() - timedelta(days=days_ago)
            gw = (pregnant.gestational_age_days or 168) // 7

            # 体重：随孕周增加
            base_weight = 55 + (gw - 12) * 0.3
            weight = round(base_weight + random.uniform(-1, 1), 1)

            # 血压：正常范围内
            sbp = round(random.uniform(105, 135), 0)
            dbp = round(random.uniform(65, 85), 0)

            # FGR高危有较高概率血压偏高
            if pregnant.risk_tags and "FGR高危" in pregnant.risk_tags:
                sbp = round(random.uniform(110, 145), 0)
                dbp = round(random.uniform(70, 92), 0)

            for metric, value, unit in [
                ("weight", weight, "kg"),
                ("sbp", sbp, "mmHg"),
                ("dbp", dbp, "mmHg"),
                ("fetal_movement", random.randint(3, 10), "次/小时"),
            ]:
                point = HealthDataPoint(
                    pregnant_id=pregnant.pregnant_id,
                    metric_code=metric,
                    value=value,
                    unit=unit,
                    recorded_at=record_date,
                    source="AUTO_FOLLOWUP",
                )
                db.add(point)
                count += 1
    print(f"   ✅ 生成 {count} 条健康数据")


def _seed_schedules(db):
    """生成全孕周排期"""
    pregnant = db.query(Pregnant).all()
    count = 0
    for pregnant in pregnant:
        if not pregnant.lmp_date:
            continue
        for gest_week, item in [
            (12, "NT检查"), (16, "中期唐筛"), (20, "大排畸B超"),
            (24, "OGTT糖耐量"), (28, "常规产检"), (30, "B超生长监测"),
            (32, "胎心监护"), (34, "常规产检"), (36, "B超评估"),
            (37, "产前评估"), (38, "胎心监护"), (39, "B超"),
            (40, "产前评估"),
        ]:
            current_gw = (pregnant.gestational_age_days or 168) // 7
            if gest_week < current_gw:
                continue
            node_date = pregnant.lmp_date + timedelta(weeks=gest_week)
            node = ScheduleNode(
                pregnant_id=pregnant.pregnant_id,
                gest_week=gest_week,
                scheduled_date=node_date,
                item=item,
                node_type="routine" if gest_week <= 28 else "fgr_high_risk" if "FGR" in (pregnant.risk_tags or []) else "routine",
                status="published" if random.random() > 0.3 else "pending",
                is_published=1 if random.random() > 0.3 else 0,
            )
            # FGR高危增加B超节点
            if "FGR高危" in (pregnant.risk_tags or []):
                for fgr_week in range(26, 38, 2):
                    extra_node = ScheduleNode(
                        pregnant_id=pregnant.pregnant_id,
                        gest_week=fgr_week,
                        scheduled_date=pregnant.lmp_date + timedelta(weeks=fgr_week),
                        item="B超生长监测(FGR专项)",
                        node_type="fgr_high_risk",
                        status="published",
                        is_published=1,
                    )
                    db.add(extra_node)
                    count += 1
            db.add(node)
            count += 1
    print(f"   ✅ 生成 {count} 条排期数据")


def _seed_fgr_assessments(db):
    """生成FGR评估Mock记录"""
    fgr_patients = db.query(Pregnant).filter(
        Pregnant.risk_tags.contains("FGR高危")
    ).all()
    count = 0
    for pregnant in fgr_patients:
        current_gw = (pregnant.gestational_age_days or 168) // 7
        for gw in range(24, current_gw + 1, 2):
            risk_score = max(0.1, min(0.9, 0.2 + (gw - 24) * 0.03 + random.uniform(-0.1, 0.1)))
            if risk_score >= 0.7:
                level, label = "critical", "极高风险"
            elif risk_score >= 0.5:
                level, label = "high", "高风险"
            elif risk_score >= 0.25:
                level, label = "medium", "中风险"
            else:
                level, label = "low", "低风险"

            assessment = FgrAssessment(
                pregnant_id=pregnant.pregnant_id,
                case_id=f"CASE_{uuid.uuid4().hex[:8].upper()}",
                image_type=random.choice(["HC", "AC", "FL", "UA_Doppler"]),
                gestational_weeks=float(gw),
                risk_level=level,
                confidence_lower=max(0, risk_score - 0.06),
                confidence_upper=min(0.99, risk_score + 0.06),
                explanation=f"孕{gw}周评估: {label}",
                processing_time_ms=random.randint(2500, 4500),
                assessed_at=datetime.now() - timedelta(days=(current_gw - gw) * 7),
            )
            db.add(assessment)
            count += 1
    print(f"   ✅ 生成 {count} 条FGR评估记录")


def _seed_alerts(db):
    """生成预警记录"""
    pregnant = db.query(Pregnant).all()
    levels = ["RED", "ORANGE", "YELLOW"]
    count = 0
    for pregnant in pregnant:
        alert_count = random.randint(0, 5)
        for _ in range(alert_count):
            level = random.choice(levels)
            if "FGR高危" in (pregnant.risk_tags or []):
                level = random.choice(["RED", "ORANGE"])
            messages = {
                "RED": ["血压异常升高", "胎动显著减少", f"FGR评估: {random.choice(['高风险', '极高风险'])}"],
                "ORANGE": ["体重周增长过快", "血压偏高", "血糖偏高"],
                "YELLOW": ["近7日情绪评分偏高", "体重增长偏慢", "轻微贫血"],
            }
            alert = Alert(
                pregnant_id=pregnant.pregnant_id,
                trigger_source=random.choice(["RULE_ENGINE", "FGR_ALGORITHM"]),
                rule_id=f"RULE_{random.choice(['BP_HIGH', 'FETAL_DROP', 'WEIGHT_GAIN', 'EMOTION_HIGH'])}",
                level=level,
                message=random.choice(messages[level]),
                status=random.choice(["PENDING", "CONFIRMED", "DISMISSED"]),
                created_at=datetime.now() - timedelta(days=random.randint(0, 14)),
            )
            db.add(alert)
            count += 1
    print(f"   ✅ 生成 {count} 条预警记录")


if __name__ == "__main__":
    seed_all()
