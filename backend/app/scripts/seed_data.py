"""Mock 数据注入脚本"""
import uuid
import random
from datetime import datetime, date, timedelta
from sqlalchemy import text
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, ScheduleNode, FollowUpRecord, FgrAssessment, Alert, MedicalOrder, ConversationMessage, MentalHealthScreening, FetalMovementSession, Feedback


def seed_all():
    """注入全部Mock数据"""
    db = SessionLocal()
    try:
        _seed_patients(db)
        _seed_health_data(db)
        _seed_schedules(db)
        _seed_fgr_assessments(db)
        _seed_alerts(db)
        seed_followup_records(db)
        seed_medical_orders(db)
        seed_conversation_messages(db)
        seed_mental_health_screenings(db)
        seed_fetal_movement_sessions(db)
        seed_feedback(db)
        supplement_health_data(db)
        db.commit()
        print("[OK] Mock数据注入完成")
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
        hospital_ids = [f"H2025{i:02d}" for i in range(1, 21)]

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
    print(f"   [OK] 生成 20 条孕妇数据")


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
    print(f"   [OK] 生成 {count} 条健康数据")


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
    print(f"   [OK] 生成 {count} 条排期数据")


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
    print(f"   [OK] 生成 {count} 条FGR评估记录")


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
    print(f"   [OK] 生成 {count} 条预警记录")


def seed_followup_records(db):
    """为每个孕妇生成2-3条随访记录，覆盖draft/confirmed/archived三态"""
    pregnant_list = db.query(Pregnant).all()
    count = 0
    statuses = ["draft", "confirmed", "archived"]
    complaints = ["胎动减少", "下肢水肿", "轻微头晕", "食欲下降", "睡眠质量差", "腰背酸痛"]
    education_topics = ["饮食指导", "运动建议", "情绪管理", "产检提醒", "体重控制"]

    for p in pregnant_list:
        current_gw = (p.gestational_age_days or 168) // 7
        record_count = random.randint(2, 3)
        for idx in range(record_count):
            gw = max(12, current_gw - random.randint(4, 12) * idx)
            record_status = statuses[idx % 3]
            self_reported = {
                "weight": round(55 + (gw - 12) * 0.3 + random.uniform(-1, 1), 1),
                "blood_pressure": f"{random.randint(105, 135)}/{random.randint(65, 85)}",
                "fetal_movement": random.randint(3, 10),
                "sleep_quality": random.choice(["好", "一般", "差"]),
            }
            record = FollowUpRecord(
                pregnant_id=p.pregnant_id,
                gestational_week=f"{gw}周",
                follow_up_date=datetime.now() - timedelta(days=random.randint(0, 60)),
                self_reported_data=self_reported,
                chief_complaint=random.choice(complaints) if random.random() > 0.4 else None,
                health_education=random.sample(education_topics, random.randint(1, 3)),
                status=record_status,
                summary=f"孕{gw}周随访完成，{'各项指标正常' if record_status == 'confirmed' else '待医生确认' if record_status == 'draft' else '已归档'}",
            )
            db.add(record)
            count += 1
    print(f"   [OK] 生成 {count} 条随访记录")


def seed_medical_orders(db):
    """为每个孕妇生成1-2条医嘱，覆盖draft/signed/executed三态"""
    pregnant_list = db.query(Pregnant).all()
    count = 0
    statuses = ["draft", "signed", "executed"]
    sources = ["AI_RECOMMENDED", "DOCTOR_WRITTEN"]
    order_templates = [
        "建议增加蛋白质摄入，每日2个鸡蛋、200ml牛奶",
        "建议每日步行30分钟，避免久坐",
        "建议每日数胎动2次，每次1小时",
        "建议监测血压，每日早晚各一次",
        "建议控制碳水化合物摄入，少食多餐",
        "建议补充叶酸和铁剂",
        "建议左侧卧位休息，改善胎盘血流",
        "建议进行OGTT糖耐量检查",
    ]

    for p in pregnant_list:
        order_count = random.randint(1, 2)
        for idx in range(order_count):
            order_status = statuses[idx % 3]
            source = random.choice(sources)
            created_by = f"AI_{uuid.uuid4().hex[:8].upper()}" if source == "AI_RECOMMENDED" else "医生张XX"
            order = MedicalOrder(
                pregnant_id=p.pregnant_id,
                content=random.choice(order_templates),
                order_type=random.choice(["standard", "urgent"]),
                source=source,
                status=order_status,
                created_by=created_by,
                signed_at=datetime.now() - timedelta(days=random.randint(1, 30)) if order_status in ["signed", "executed"] else None,
                created_at=datetime.now() - timedelta(days=random.randint(0, 30)),
            )
            db.add(order)
            count += 1
    print(f"   [OK] 生成 {count} 条医嘱记录")


def seed_conversation_messages(db):
    """为每个孕妇生成对话历史，从预设对话模板中随机选择"""
    pregnant_list = db.query(Pregnant).all()
    count = 0

    conversation_templates = [
        [
            {"role": "assistant", "content": "您好！我是您的孕期健康助手，有什么可以帮您？"},
            {"role": "user", "content": "最近胎动好像少了，有点担心"},
            {"role": "assistant", "content": "胎动减少需要关注。建议您左侧卧位休息1小时后，专注感受胎动，正常应不少于10次/小时。如果持续减少请及时就医。"},
        ],
        [
            {"role": "assistant", "content": "您好！请问今天有什么需要咨询的吗？"},
            {"role": "user", "content": "血糖偏高怎么办？"},
            {"role": "assistant", "content": "血糖偏高需要注意饮食控制。建议减少精制碳水化合物，增加蔬菜和蛋白质摄入，少食多餐，餐后适当散步。"},
        ],
        [
            {"role": "assistant", "content": "您好！请问有什么可以帮助您的？"},
            {"role": "user", "content": "最近情绪不太好，总是焦虑"},
            {"role": "assistant", "content": "孕期焦虑是常见的。建议您尝试深呼吸放松、适当运动、与家人朋友多沟通。如果持续加重，可以考虑专业心理支持。"},
        ],
        [
            {"role": "assistant", "content": "您好！我是您的健康顾问，请问有什么问题？"},
            {"role": "user", "content": "下次产检是什么时候？"},
            {"role": "assistant", "content": "根据您的孕周，下次产检建议在1周后。届时需要监测血压、体重和胎心，请按时就诊。"},
        ],
    ]

    for p in pregnant_list:
        session_id = f"SESS_{uuid.uuid4().hex[:12].upper()}"
        template = random.choice(conversation_templates)
        created_at = datetime.now() - timedelta(days=random.randint(1, 14))
        for msg in template:
            message = ConversationMessage(
                session_id=session_id,
                pregnant_id=p.pregnant_id,
                role=msg["role"],
                content=msg["content"],
                extra_data={"source": "SEED_DATA"},
                created_at=created_at,
            )
            db.add(message)
            created_at += timedelta(minutes=random.randint(1, 5))
            count += 1
    print(f"   [OK] 生成 {count} 条对话记录")


def seed_mental_health_screenings(db):
    """为5-8个孕妇生成EPDS记录，10题答案0-3分"""
    pregnant_list = db.query(Pregnant).all()
    selected_patients = random.sample(pregnant_list, min(random.randint(5, 8), len(pregnant_list)))
    count = 0

    for p in selected_patients:
        # EPDS 10题，每题0-3分，总分0-30
        # 通常低风险<10，中等10-12，高风险13-19，严重>=20
        risk_scenario = random.choice(["low", "low", "moderate", "high"])
        if risk_scenario == "low":
            answers = [random.choice([0, 1, 2]) for _ in range(10)]
        elif risk_scenario == "moderate":
            answers = [random.choice([0, 1, 2, 3]) for _ in range(10)]
            # 确保有几个高分题
            for i in random.sample(range(10), 3):
                answers[i] = 3
        elif risk_scenario == "high":
            answers = [random.choice([1, 2, 3]) for _ in range(10)]
            for i in random.sample(range(10), 5):
                answers[i] = 3
        else:
            answers = [3] * 10

        # Q3和Q10是反向计分题，需要反转
        total_score = sum(answers)
        # 调整风险等级
        if total_score >= 13:
            risk_level = "high"
        elif total_score >= 10:
            risk_level = "moderate"
        elif total_score >= 7:
            risk_level = "low"
        else:
            risk_level = "low"

        screening = MentalHealthScreening(
            pregnant_id=p.pregnant_id,
            screening_type="EPDS",
            answers=answers,
            total_score=total_score,
            risk_level=risk_level,
            created_at=datetime.now() - timedelta(days=random.randint(0, 90)),
        )
        db.add(screening)
        count += 1
    print(f"   [OK] 生成 {count} 条心理筛查记录")


def seed_fetal_movement_sessions(db):
    """为5-8个孕妇生成2-3条胎动记录"""
    pregnant_list = db.query(Pregnant).all()
    selected_patients = random.sample(pregnant_list, min(random.randint(5, 8), len(pregnant_list)))
    count = 0

    for p in selected_patients:
        session_count = random.randint(2, 3)
        for _ in range(session_count):
            start_time = datetime.now() - timedelta(days=random.randint(0, 14))
            duration = random.choice([30, 60, 120])
            # 生成胎动时间点列表
            kick_times = []
            for _ in range(random.randint(5, 15)):
                kick_offset = timedelta(minutes=random.randint(0, duration))
                kick_times.append((start_time + kick_offset).isoformat())

            session = FetalMovementSession(
                pregnant_id=p.pregnant_id,
                start_time=start_time,
                end_time=start_time + timedelta(minutes=duration),
                duration_minutes=duration,
                total_count=len(kick_times),
                kick_times=sorted(kick_times),
                notes=f"胎动计数{duration}分钟，共{len(kick_times)}次",
            )
            db.add(session)
            count += 1
    print(f"   [OK] 生成 {count} 条胎动记录")


def seed_feedback(db):
    """为部分assistant消息生成反馈"""
    pregnant_list = db.query(Pregnant).all()
    count = 0

    for p in pregnant_list:
        # 为每个孕妇生成0-2条反馈
        feedback_count = random.randint(0, 2)
        for _ in range(feedback_count):
            rating = random.choice(["thumbs_up", "thumbs_up", "thumbs_down"])
            comment = None
            if rating == "thumbs_up":
                comment = random.choice(["感谢解答", "很有帮助", "明白了", "谢谢"])
            elif random.random() > 0.5:
                comment = random.choice(["不太明白", "需要更详细", "回答不够具体"])

            feedback = Feedback(
                pregnant_id=p.pregnant_id,
                message_id=f"MSG_{uuid.uuid4().hex[:12].upper()}",
                rating=rating,
                comment=comment,
                session_id=f"SESS_{uuid.uuid4().hex[:12].upper()}",
                created_at=datetime.now() - timedelta(days=random.randint(0, 14)),
            )
            db.add(feedback)
            count += 1
    print(f"   [OK] 生成 {count} 条反馈记录")


def supplement_health_data(db):
    """补充blood_sugar/emotion_score/sleep_hours三种指标"""
    pregnant_list = db.query(Pregnant).all()
    count = 0

    for p in pregnant_list:
        is_gdm = "GDM" in (p.risk_tags or [])
        is_hypertension = "高血压" in (p.risk_tags or [])

        for days_ago in range(0, 56, 2):
            record_date = datetime.now() - timedelta(days=days_ago)

            # 血糖：GDM患者偏高
            if is_gdm:
                blood_sugar = round(random.uniform(5.5, 7.8), 1)
            else:
                blood_sugar = round(random.uniform(4.0, 5.8), 1)

            # 情绪评分：高血压患者可能偏高
            if is_hypertension:
                emotion_score = round(random.uniform(4.0, 9.0), 1)
            else:
                emotion_score = round(random.uniform(2.0, 6.0), 1)

            # 睡眠时长
            sleep_hours = round(random.uniform(5.5, 9.0), 1)

            for metric, value, unit in [
                ("blood_sugar", blood_sugar, "mmol/L"),
                ("emotion_score", emotion_score, "分"),
                ("sleep_hours", sleep_hours, "小时"),
            ]:
                point = HealthDataPoint(
                    pregnant_id=p.pregnant_id,
                    metric_code=metric,
                    value=value,
                    unit=unit,
                    recorded_at=record_date,
                    source="SEED_SUPPLEMENT",
                )
                db.add(point)
                count += 1
    print(f"   [OK] 补充 {count} 条健康数据")


if __name__ == "__main__":
    seed_all()
