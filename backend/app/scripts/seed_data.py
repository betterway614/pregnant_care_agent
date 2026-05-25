"""Mock 数据注入脚本"""
import uuid
import random
from datetime import datetime, date, timedelta
from ..utils.timezone import beijing_now
from sqlalchemy import text
from loguru import logger
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, ScheduleNode, FollowUpRecord, FgrAssessment, MedicalOrder, ConversationMessage, MentalHealthScreening, FetalMovementSession, Feedback

# 存储对话消息ID供反馈关联（seed_feedback 使用）
_generated_message_ids: list[str] = []


def seed_all():
    """注入全部Mock数据"""
    db = SessionLocal()
    try:
        _seed_patients(db)
        db.flush()  # 确保已添加的孕妇数据对后续查询可见（autoflush=False）
        _seed_health_data(db)
        seed_historical_baseline(db)
        _seed_schedules(db)
        _seed_fgr_assessments(db)
        seed_followup_records(db)
        seed_medical_orders(db)
        seed_conversation_messages(db)
        seed_mental_health_screenings(db)
        seed_fetal_movement_sessions(db)
        seed_feedback(db)
        supplement_health_data(db)
        db.commit()
        logger.info("Mock数据注入完成")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def _seed_patients(db):
    """生成20条匿名孕妇（含BMI分层），前10位绑定超声图像（模拟HIS集成）"""
    existing = db.query(Pregnant).count()
    if existing > 0:
        logger.info("孕妇数据已存在，跳过")
        return

    risk_configs = [
        ([], "正常"),
        ([], "正常"),
        (["FGR高危"], "FGR"),
        ([], "正常"),
        (["GDM"], "GDM"),
        (["FGR高危"], "FGR"),
        ([], "正常"),
        (["FGR高危"], "FGR"),
        (["FGR高危", "GDM"], "FGR+GDM"),
        (["FGR高危"], "FGR"),
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

    # 身高(cm) & 孕前体重(kg) — 与BMI分层对应
    heights = [160, 160, 162, 162, 162, 160, 160, 160, 158, 163,
               162, 158, 165, 162, 160, 160, 163, 160, 163, 160]
    pre_weights = [45, 55, 58, 52, 56, 54, 68, 53, 44, 57,
                   70, 55, 60, 82, 52, 46, 72, 55, 85, 54]

    # 记录前10位患者ID，用于图片绑���
    patient_ids_1_10 = []

    base_date = datetime.now() - timedelta(days=120)
    for i in range(20):
        gest_days = random.randint(84, 280)  # 12w ~ 40w
        lmp = (datetime.now() - timedelta(days=gest_days)).date()
        edd = lmp + timedelta(days=280)

        nicknames = ["小美", "阿芳", "静静", "思思", "晓月", "雨晴", "梦琪", "诗涵",
                     "欣怡", "雅茹", "婉清", "若兰", "雪婷", "慧敏", "嘉玲", "秀英",
                     "美琳", "丽华", "晓红", "艳芳"]
        phones = [f"138****{random.randint(1000,9999)}" for _ in range(20)]
        hospital_ids = [f"H2025{i+1:02d}" for i in range(20)]

        pid = f"PT_{uuid.uuid4().hex[:12].upper()}"
        if i < 10:
            patient_ids_1_10.append(f"孕妇{i+1:02d}|{pid}")

        pregnant = Pregnant(
            pregnant_id=pid,
            display_name=f"孕妇{i+1:02d}",
            nickname=nicknames[i],
            phone=phones[i],
            hospital_id=hospital_ids[i],
            gestational_age_days=gest_days,
            height_cm=heights[i],
            pre_pregnancy_weight_kg=pre_weights[i],
            lmp_date=lmp,
            edd=edd,
            risk_tags=risk_configs[i][0],
            created_at=base_date + timedelta(days=i * 3),
        )
        db.add(pregnant)
    logger.info("生成20 条孕妇数据")

    # 绑定超声图像：孕妇01-05 → NOR，孕妇06-10 → FGR
    _assign_patient_images(patient_ids_1_10)


def _assign_patient_images(patient_ids: list[str]) -> None:
    """将10张超声图像绑定到前10位患者（脱敏：仅存储 file_id 映射）"""
    try:
        from fgr_compete.image_registry import get_image_pairs, save_patient_map
        nor_pairs, fgr_pairs = get_image_pairs()

        if len(nor_pairs) < 5 or len(fgr_pairs) < 5:
            logger.warning("超声图像不足（NOR={} FGR={}），跳过绑定", len(nor_pairs), len(fgr_pairs))
            return

        mapping = {}
        # 孕妇01-05 → NOR 图像
        for idx in range(5):
            display, pid = patient_ids[idx].split("|", 1)
            raw_path, mask_path = nor_pairs[idx]
            mapping[pid] = {
                "display_name": display,
                "raw_path": raw_path,
                "mask_path": mask_path,
                "group": "NOR",
            }
        # 孕妇06-10 → FGR 图像
        for idx in range(5):
            display, pid = patient_ids[idx + 5].split("|", 1)
            raw_path, mask_path = fgr_pairs[idx]
            mapping[pid] = {
                "display_name": display,
                "raw_path": raw_path,
                "mask_path": mask_path,
                "group": "FGR",
            }
        save_patient_map(mapping)
        logger.info("已绑定10位患者的超声图像（01-05: NOR, 06-10: FGR）")
    except ImportError:
        logger.warning("image_registry 不可用，跳过图片绑定")


def _seed_health_data(db):
    """生成健康指标时间序列（动态孕周 + BMI分层体重 + 血压U形曲线）"""
    if db.query(HealthDataPoint).count() > 0:
        logger.info("健康数据已存在，跳过")
        return
    pregnant = db.query(Pregnant).all()
    count = 0

    # BMI分层配置（按 WS/T 801-2022 中国标准）
    bmi_configs = [
        {"pre_weight": 45, "weekly_gain": 0.46},  # 偏瘦
        {"pre_weight": 55, "weekly_gain": 0.37},  # 正常
        {"pre_weight": 58, "weekly_gain": 0.37},
        {"pre_weight": 52, "weekly_gain": 0.37},
        {"pre_weight": 56, "weekly_gain": 0.37},
        {"pre_weight": 54, "weekly_gain": 0.37},
        {"pre_weight": 68, "weekly_gain": 0.30},  # 超重
        {"pre_weight": 53, "weekly_gain": 0.37},
        {"pre_weight": 44, "weekly_gain": 0.46},  # 偏瘦
        {"pre_weight": 57, "weekly_gain": 0.37},
        {"pre_weight": 70, "weekly_gain": 0.30},  # 超重
        {"pre_weight": 55, "weekly_gain": 0.37},
        {"pre_weight": 60, "weekly_gain": 0.37},
        {"pre_weight": 82, "weekly_gain": 0.22},  # 肥胖
        {"pre_weight": 52, "weekly_gain": 0.37},
        {"pre_weight": 46, "weekly_gain": 0.46},  # 偏瘦
        {"pre_weight": 72, "weekly_gain": 0.30},  # 超重
        {"pre_weight": 55, "weekly_gain": 0.37},
        {"pre_weight": 85, "weekly_gain": 0.22},  # 肥胖
        {"pre_weight": 54, "weekly_gain": 0.37},
    ]

    for pregnant in pregnant:
        # 根据 display_name 解析索引（跳过非"孕妇N"名称的图片患者）
        if not pregnant.display_name or not pregnant.display_name.startswith("孕妇"):
            continue
        idx = int(pregnant.display_name.replace("孕妇", "")) - 1
        idx = max(0, min(idx, 19))
        bmi = bmi_configs[idx]
        pre_weight = bmi["pre_weight"]
        weekly_gain = bmi["weekly_gain"]
        init_gw = (pregnant.gestational_age_days or 168) // 7

        fm_value = random.randint(4, 8)  # 胎动初始值

        for days_ago in range(0, 56, 2):
            record_date = datetime.now() - timedelta(days=days_ago)
            # 动态孕周：随记录时间回溯而减小
            current_gw = max(12, (pregnant.gestational_age_days - days_ago) // 7)

            # === 体重：按孕前BMI分层 + 动态孕周 ===
            # 孕早期（≤12周）增重约1kg，之后按每周推荐速率
            early_gain = 1.0  # 孕早期基础增重
            weeks_after_12 = max(0, current_gw - 12)
            base_weight = pre_weight + early_gain + weeks_after_12 * weekly_gain
            weight = round(base_weight + random.uniform(-0.8, 0.8), 1)

            # === 血压：生理性U形曲线 ===
            # 孕中期（16-24周）最低，孕晚期回升
            bp_dip = 0
            if 16 <= current_gw <= 28:
                # 16-24周逐渐降低，24-28周逐渐回升
                if current_gw <= 22:
                    dip_factor = (current_gw - 16) / 6  # 0→1
                    bp_dip = round(dip_factor * 6)  # 最多降6mmHg
                else:
                    dip_factor = (current_gw - 22) / 6  # 0→1
                    bp_dip = round((1 - dip_factor) * 6)

            sbp = round(random.uniform(105, 125) - bp_dip, 0)
            dbp = round(random.uniform(65, 80) - bp_dip * 0.6, 0)

            # FGR高危：孕晚期（28周后）血压偏高
            if pregnant.risk_tags and "FGR高危" in pregnant.risk_tags and current_gw >= 28:
                sbp = round(min(145, sbp + random.uniform(8, 15)), 0)
                dbp = round(min(92, dbp + random.uniform(5, 10)), 0)

            # 高血压患者：持续偏高
            if pregnant.risk_tags and "高血压" in pregnant.risk_tags:
                sbp = round(random.uniform(130, 148), 0)
                dbp = round(random.uniform(82, 95), 0)

            # === 胎动：前后一致性随机游走 ===
            if days_ago > 0:
                fm_delta = random.randint(-2, 2)
                fm_value = max(3, min(12, fm_value + fm_delta))

            for metric, value, unit in [
                ("weight", weight, "kg"),
                ("systolic", sbp, "mmHg"),
                ("diastolic", dbp, "mmHg"),
                ("fetal_movement", fm_value, "次/小时"),
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
    logger.info("生成 {} 条健康数据", count)


def _seed_schedules(db):
    """生成全孕周排期"""
    if db.query(ScheduleNode).count() > 0:
        logger.info("排期数据已存在，跳过")
        return
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
            is_fgr = "FGR" in (pregnant.risk_tags or [])
            node_type = "fgr_high_risk" if is_fgr else "routine"
            is_published_flag = random.random() > 0.3
            node = ScheduleNode(
                pregnant_id=pregnant.pregnant_id,
                gest_week=gest_week,
                scheduled_date=node_date,
                item=item,
                node_type=node_type,
                status="published" if is_published_flag else "pending",
                is_published=1 if is_published_flag else 0,
            )
            # FGR高危增加B超节点（避免与常规排期同一周重叠）
            standard_weeks = {12, 16, 20, 24, 28, 30, 32, 34, 36, 37, 38, 39, 40}
            if is_fgr:
                for fgr_week in range(25, 37, 2):  # 用奇数周避免与常规排期偶数周重叠
                    if fgr_week < current_gw or fgr_week in standard_weeks:
                        continue
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
    logger.info("生成 {} 条排期数据", count)


def _seed_fgr_assessments(db):
    """生成FGR评估Mock记录"""
    if db.query(FgrAssessment).count() > 0:
        logger.info("FGR评估数据已存在，跳过")
        return
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
    logger.info("生成 {} 条FGR评估记录", count)



def seed_followup_records(db):
    """为每个孕妇生成2-3条随访记录，覆盖draft/confirmed/archived三态

    参照国家基本公共卫生服务规范(2024版)的随访记录表 + SOAP格式，
    生成具有临床真实性的mock数据：

    S(主观): self_reported_data + chief_complaint
    O(客观): obstetric_exam(宫高/腹围/胎位/胎心率) + lab_results(血红蛋白/尿蛋白)
    A(评估): classification(normal/abnormal/critical) + summary
    P(计划): guidance_tags(分类标签) + health_education + referral + next_followup
    """
    import random as _random

    if db.query(FollowUpRecord).count() > 0:
        logger.info("随访记录已存在，跳过")
        return

    pregnant_list = db.query(Pregnant).all()
    count = 0
    statuses = ["draft", "confirmed", "archived"]

    # 主诉词库
    complaints_pool = [
        "胎动减少", "下肢水肿", "轻微头晕", "食欲下降",
        "睡眠质量差，入睡困难", "腰背酸痛明显", "偶有腹部发紧",
        "近期体重增长较快", "偶有头痛", "无特殊不适",
    ]

    # 生理分布参数
    def _clamp(val, lo, hi):
        return max(lo, min(hi, val))

    def _norm(mean, std, lo=None, hi=None):
        """近似正态分布（Box-Muller简化版，用多个均匀随机数近似）"""
        # 用 6 个 [0,1] 均匀随机数的和近似 N(3*mean/mean, ...)
        # 更简单直接的方式: triangular 近似
        v = _random.triangular(mean - std * 2, mean + std * 2, mean)
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return round(v, 1)

    for p in pregnant_list:
        gw = (p.gestational_age_days or 168) // 7  # 当前孕周(整数)
        risk_tags = p.risk_tags or []
        is_hypertensive = any(t in risk_tags for t in ("高血压", "子痫前期"))
        is_gdm = "GDM" in risk_tags
        is_fgr = any(t in risk_tags for t in ("FGR高危", "FGR"))
        is_high_risk = is_hypertensive or is_gdm or is_fgr

        record_count = _random.randint(2, 3)
        for idx in range(record_count):
            record_gw = max(12, gw - _random.randint(4, 12) * idx)
            record_status = statuses[idx % 3]

            # ---- S: 主观数据 ----
            self_reported = {}
            # 体重: base 55 + 每周0.35kg
            base_weight = 55 + record_gw * 0.35 + _random.uniform(-2, 2)
            self_reported["weight"] = round(base_weight, 1)
            # 胎动自述
            if record_gw >= 18:
                self_reported["fetal_movement"] = _clamp(_random.randint(2, 10), 2, 12)
            else:
                self_reported["fetal_movement"] = "未感知"
            # 饮食
            self_reported["diet"] = _random.choice(["正常", "正常", "胃口不佳", "食欲好", "偏食"])
            # 情绪
            self_reported["mood"] = _random.choice(["良好", "良好", "良好", "一般", "焦虑"])

            chief_complaint = _random.choice(complaints_pool) if _random.random() > 0.3 else None

            # ---- O: 客观数据 ----
            # 宫高 (cm): 20w~18cm, 每周+0.8cm, ±2cm抖动
            fh = _clamp(round(18.0 + (record_gw - 20) * 0.8 + _random.uniform(-2, 2), 1), 10, 40)
            # 腹围 (cm): 20w~75cm, 每周+0.85cm, ±3cm抖动
            ac = _clamp(round(75.0 + (record_gw - 20) * 0.85 + _random.uniform(-3, 3), 1), 60, 110)
            # 胎心率 (bpm): N(140, 10), clip [110, 170]
            fhr = int(_clamp(_norm(140, 10, 110, 170), 110, 170))
            # 胎位: 28w前随机, 28w后90%头位
            if record_gw < 28:
                fp = _random.choice(["头位", "臀位", "横位", "头位", "头位"])
            else:
                fp = _random.choice(["头位"] * 9 + ["臀位"])
            obstetric_exam = {
                "fundal_height_cm": fh,
                "abdominal_circumference_cm": ac,
                "fetal_position": fp,
                "fetal_heart_rate_bpm": fhr,
                "blood_pressure": f"{_clamp(int(_norm(115, 12) + (20 if is_hypertensive else 0)), 95, 160)}/{_clamp(int(_norm(75, 8) + (10 if is_hypertensive else 0)), 55, 105)}",
            }

            # 化验结果
            hb = _norm(120, 8, lo=80, hi=150)
            lab_results = {
                "hemoglobin_g_L": round(hb, 1),
                "urine_protein": _random.choice(["阴性"] * 9 + ["弱阳性", "阳性"]),
            }
            if is_gdm and _random.random() > 0.5:
                lab_results["blood_sugar_fasting"] = round(_norm(5.5, 0.8, lo=4.0, hi=8.0), 1)
                lab_results["blood_sugar_2h"] = round(_norm(7.0, 1.2, lo=5.0, hi=12.0), 1)

            # 扩展生化指标（模拟产检化验单）
            lab_results["alt"] = round(_norm(18, 8, lo=5, hi=50), 1)
            lab_results["ast"] = round(_norm(22, 8, lo=5, hi=50), 1)
            lab_results["creatinine"] = round(_norm(55, 12, lo=35, hi=80), 1)
            lab_results["uric_acid"] = round(_norm(240, 50, lo=120, hi=400), 0)
            lab_results["albumin"] = round(_norm(38, 4, lo=28, hi=50), 1)
            lab_results["wbc"] = round(_norm(8.5, 2.0, lo=4.0, hi=14.0), 1)
            lab_results["platelet"] = round(_norm(200, 45, lo=100, hi=350), 0)
            lab_results["hct"] = round(_norm(36, 4, lo=30, hi=45), 1)

            # ---- A: 评估 ----
            has_abnormal_bp = int(obstetric_exam["blood_pressure"].split("/")[0]) >= 140
            has_low_hb = hb < 100
            has_high_glucose = lab_results.get("blood_sugar_fasting", 5.0) > 6.0
            has_abnormal_up = lab_results["urine_protein"] in ("弱阳性", "阳性")

            if has_abnormal_bp or has_low_hb or has_high_glucose or is_high_risk:
                if is_hypertensive and has_abnormal_bp:
                    classification = "critical"
                else:
                    classification = "abnormal"
            else:
                classification = "normal"

            # ---- P: 计划 ----
            guidance_tags = [
                {"tag": "营养", "content": "均衡饮食，每周体重增长控制在0.3-0.5kg"},
                {"tag": "运动", "content": "餐后散步30分钟，避免剧烈运动"},
                {"tag": "监护", "content": "每日固定时间自数胎动，每小时不少于3次"},
            ]
            if record_gw >= 36:
                guidance_tags.append({"tag": "分娩准备", "content": "确认待产包准备完毕，了解临产征兆"})
            if is_hypertensive:
                guidance_tags.append({"tag": "生活", "content": "低盐饮食（<6g/天），每日早晚测血压并记录"})
            if is_gdm:
                guidance_tags.append({"tag": "营养", "content": "控制碳水摄入，监测空腹及餐后血糖"})
            if is_fgr:
                guidance_tags.append({"tag": "监护", "content": "高蛋白饮食，左侧卧位，定期B超监测胎儿生长"})

            # health_education 保持兼容旧格式（纯文本列表）
            health_edu_texts = [f"{g['content']}" for g in guidance_tags]

            # 转诊
            referral = None
            if classification == "critical":
                referral = {
                    "has_referral": True,
                    "reason": "血压持续偏高，需专科评估",
                    "institution": "XX市妇幼保健院",
                    "department": "高危妊娠门诊",
                }

            # 下次随访日期
            if record_gw >= 36:
                interval = 7
            elif is_high_risk:
                interval = 10
            else:
                interval = 21
            nf_date = (datetime.now() + timedelta(days=interval)).date()

            # 审核追溯 (confirmed/archived 状态时写入)
            reviewed_by = None
            reviewed_at = None
            review_comment = None
            ai_snapshot = {}
            if record_status in ("confirmed", "archived"):
                reviewed_by = f"nurse_{_random.choice(['WANG', 'LI', 'ZHANG', 'CHEN'])}"
                reviewed_at = datetime.now() - timedelta(days=_random.randint(0, 30))

                # 用 _fallback_analysis_report 真实分析 mock 数据生成 AI 快照
                # 构造 answers 字典（映射自报数据+产科检查+化验结果，模拟真实分析输入）
                bp_str = obstetric_exam.get("blood_pressure", "")
                analysis_answers = {
                    "bp": bp_str,
                    "weight": str(self_reported.get("weight", "")),
                    "fetal_movement": str(self_reported.get("fetal_movement", "")),
                }
                if lab_results.get("blood_sugar_fasting"):
                    analysis_answers["blood_sugar_fasting"] = str(lab_results["blood_sugar_fasting"])
                if lab_results.get("blood_sugar_2h"):
                    analysis_answers["blood_sugar_postprandial"] = str(lab_results["blood_sugar_2h"])

                from ..routers.followup import _fallback_analysis_report
                analysis_result = _fallback_analysis_report(
                    patient_name=p.display_name,
                    gest_week=f"{record_gw}",
                    answers=analysis_answers,
                    risk_tags=risk_tags,
                )
                ai_snapshot = analysis_result

                # 审核意见与 AI 分析结论保持一致
                if analysis_result["abnormal_indicators"]:
                    review_comment = f"已复核，关注：{'；'.join(analysis_result['abnormal_indicators'][:2])}"
                else:
                    review_comment = "各项指标正常，确认通过"

            record = FollowUpRecord(
                pregnant_id=p.pregnant_id,
                gestational_week=f"{record_gw}+{_random.randint(0, 6)}",
                follow_up_date=datetime.now() - timedelta(days=_random.randint(0, 60)),
                # S
                self_reported_data=self_reported,
                chief_complaint=chief_complaint,
                # O
                obstetric_exam=obstetric_exam,
                lab_results=lab_results,
                # A
                classification=classification,
                summary=f"孕{record_gw}周随访完成，{'指标正常' if classification == 'normal' else '异常指标需关注' if classification == 'abnormal' else '高危需紧急处理'}",
                # P
                health_education=health_edu_texts,
                guidance_tags=guidance_tags,
                referral=referral,
                next_followup_date=nf_date,
                # 状态 + 追溯
                status=record_status,
                reviewed_by=reviewed_by,
                reviewed_at=reviewed_at,
                review_comment=review_comment,
                ai_snapshot=ai_snapshot,
            )
            db.add(record)
            count += 1
    logger.info("生成 {} 条随访记录（含产科检查/化验/追溯链）", count)


def seed_medical_orders(db):
    """为每个孕妇生成1-2条医嘱，覆盖draft/signed/executed三态"""
    if db.query(MedicalOrder).count() > 0:
        logger.info("医嘱数据已存在，跳过")
        return
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
                signed_at=beijing_now() - timedelta(days=random.randint(1, 30)) if order_status in ["signed", "executed"] else None,
                created_at=beijing_now() - timedelta(days=random.randint(0, 30)),
            )
            db.add(order)
            count += 1
    logger.info("生成 {} 条医嘱记录", count)


def seed_conversation_messages(db):
    """为每个孕妇生成对话历史，从预设对话模板中随机选择"""
    global _generated_message_ids
    if db.query(ConversationMessage).count() > 0:
        logger.info("对话记录已存在，跳过")
        return
    pregnant_list = db.query(Pregnant).all()
    count = 0
    _generated_message_ids = []

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
            db.flush()  # 刷出ID供反馈关联
            if msg["role"] == "assistant":
                _generated_message_ids.append(str(message.id))
            created_at += timedelta(minutes=random.randint(1, 5))
            count += 1
    logger.info("生成 {} 条对话记录", count)


def seed_mental_health_screenings(db):
    """为5-8个孕妇生成EPDS记录，10题答案0-3分"""
    if db.query(MentalHealthScreening).count() > 0:
        logger.info("心理筛查数据已存在，跳过")
        return
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

        # EPDS反向计分：Q3（自我责备）和Q10（自伤念头）为反向题（3→0, 2→1, 1→2, 0→3）
        reversed_answers = list(answers)
        for rev_q in [2, 9]:  # 0-indexed: Q3→index 2, Q10→index 9
            reversed_answers[rev_q] = 3 - answers[rev_q]
        total_score = sum(reversed_answers)

        # 风险等级（中国人群临界值9/10）
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
    logger.info("生成 {} 条心理筛查记录", count)


def seed_fetal_movement_sessions(db):
    """为5-8个孕妇生成2-3条胎动记录"""
    if db.query(FetalMovementSession).count() > 0:
        logger.info("胎动记录已存在，跳过")
        return
    pregnant_list = db.query(Pregnant).all()
    selected_patients = random.sample(pregnant_list, min(random.randint(5, 8), len(pregnant_list)))
    count = 0

    for p in selected_patients:
        session_count = random.randint(2, 3)
        for _ in range(session_count):
            start_time = datetime.now() - timedelta(days=random.randint(0, 14))
            duration = random.choice([30, 60, 120])
            # 胎动次数与持续时间成正比（按3-10次/小时的合理范围）
            expected_per_hour = random.randint(4, 8)
            total_kicks = max(2, round(duration / 60 * expected_per_hour))
            # 生成胎动时间点列表（间隔至少1分钟，避免连续胎动误计数）
            kick_times = []
            for _ in range(total_kicks):
                kick_offset = timedelta(minutes=random.randint(0, duration))
                kick_times.append((start_time + kick_offset).isoformat())

            session = FetalMovementSession(
                pregnant_id=p.pregnant_id,
                start_time=start_time,
                end_time=start_time + timedelta(minutes=duration),
                duration_minutes=duration,
                total_count=len(kick_times),
                kick_times=sorted(kick_times),
                notes=f"胎动计数{duration}分钟，共{len(kick_times)}次（{expected_per_hour}次/小时）",
            )
            db.add(session)
            count += 1
    logger.info("生成 {} 条胎动记录", count)


def seed_feedback(db):
    """为已生成的assistant对话消息生成反馈"""
    global _generated_message_ids
    if db.query(Feedback).count() > 0:
        logger.info("反馈数据已存在，跳过")
        return
    if not _generated_message_ids:
        # 对话已跳过（已存在），从数据库中查询已有的assistant消息ID
        msgs = db.query(ConversationMessage).filter(
            ConversationMessage.role == "assistant"
        ).all()
        _generated_message_ids = [str(m.id) for m in msgs]
        if not _generated_message_ids:
            logger.info("无对话消息可关联反馈，跳过")
            return

    pregnant_list = db.query(Pregnant).all()
    count = 0

    for p in pregnant_list:
        # 为每个孕妇生成0-2条反馈
        feedback_count = random.randint(0, 2)
        for _ in range(feedback_count):
            if not _generated_message_ids:
                break
            msg_id = random.choice(_generated_message_ids)
            rating = random.choice(["thumbs_up", "thumbs_up", "thumbs_down"])
            comment = None
            if rating == "thumbs_up":
                comment = random.choice(["感谢解答", "很有帮助", "明白了", "谢谢"])
            elif random.random() > 0.5:
                comment = random.choice(["不太明白", "需要更详细", "回答不够具体"])

            feedback = Feedback(
                pregnant_id=p.pregnant_id,
                message_id=msg_id,
                rating=rating,
                comment=comment,
                session_id=f"SESS_{uuid.uuid4().hex[:12].upper()}",
                created_at=datetime.now() - timedelta(days=random.randint(0, 14)),
            )
            db.add(feedback)
            count += 1
    logger.info("生成 {} 条反馈记录", count)


def seed_historical_baseline(db):
    """为每位孕妇从孕8周起每2周生成体重+血压历史基线数据

    与 _seed_health_data (近56天密集数据) 互补，提供孕早期至今的稀疏长程轨迹。
    仅生成 weight / systolic / diastolic 三项核心指标。
    """
    existing = db.query(HealthDataPoint).filter(
        HealthDataPoint.source == "HISTORICAL_BASELINE"
    ).count()
    if existing > 0:
        logger.info("历史基线数据已存在，跳过")
        return

    pregnant_list = db.query(Pregnant).all()
    count = 0

    # 每周增重速率（与 _seed_health_data bmi_configs 保持一致）
    def _weekly_gain(pre_w: float) -> float:
        if pre_w <= 47:
            return 0.46  # 偏瘦
        elif pre_w <= 62:
            return 0.37  # 正常
        elif pre_w <= 75:
            return 0.30  # 超重
        else:
            return 0.22  # 肥胖

    for p in pregnant_list:
        pre_w = p.pre_pregnancy_weight_kg or 55
        weekly_gain = _weekly_gain(pre_w)
        current_gw = (p.gestational_age_days or 168) // 7
        is_hypertensive = "高血压" in (p.risk_tags or [])
        is_fgr = "FGR高危" in (p.risk_tags or [])

        # 从孕8周到当前孕周，每2周一条记录
        for gw in range(8, current_gw + 1, 2):
            # 根据孕周推算日期: lmp + gw*7 天
            record_date = (p.lmp_date or datetime.now().date() - timedelta(days=current_gw * 7)) + timedelta(weeks=gw)

            # ---- 体重 ----
            early_gain = 1.0
            weeks_after_12 = max(0, gw - 12)
            base_weight = pre_w + early_gain + weeks_after_12 * weekly_gain
            weight = round(base_weight + random.uniform(-0.6, 0.6), 1)

            # ---- 血压 (U形曲线) ----
            bp_dip = 0
            if 16 <= gw <= 28:
                if gw <= 22:
                    bp_dip = round((gw - 16) / 6 * 6)
                else:
                    bp_dip = round((1 - (gw - 22) / 6) * 6)

            if is_hypertensive:
                sbp = round(random.uniform(130, 148), 0)
                dbp = round(random.uniform(82, 95), 0)
            elif is_fgr and gw >= 28:
                sbp = round(min(145, random.uniform(108, 125) - bp_dip + random.uniform(8, 15)), 0)
                dbp = round(min(92, random.uniform(68, 80) - bp_dip * 0.6 + random.uniform(5, 10)), 0)
            else:
                sbp = round(random.uniform(105, 125) - bp_dip, 0)
                dbp = round(random.uniform(65, 80) - bp_dip * 0.6, 0)

            for metric, value, unit in [
                ("weight", weight, "kg"),
                ("systolic", sbp, "mmHg"),
                ("diastolic", dbp, "mmHg"),
            ]:
                point = HealthDataPoint(
                    pregnant_id=p.pregnant_id,
                    metric_code=metric,
                    value=value,
                    unit=unit,
                    recorded_at=record_date,
                    source="HISTORICAL_BASELINE",
                )
                db.add(point)
                count += 1

    logger.info("生成 {} 条历史基线数据（8w起每2周体重+血压）", count)


def supplement_health_data(db):
    """补充blood_sugar/emotion_score/sleep_hours三种指标"""
    existing_supplement = db.query(HealthDataPoint).filter(
        HealthDataPoint.source == "SEED_SUPPLEMENT"
    ).count()
    if existing_supplement > 0:
        logger.info("补充健康数据已存在，跳过")
        return
    pregnant_list = db.query(Pregnant).all()
    count = 0

    for p in pregnant_list:
        is_gdm = "GDM" in (p.risk_tags or [])
        is_hypertension = "高血压" in (p.risk_tags or [])

        # 血糖基线：非GDM按正常空腹标准（<5.3），GDM按控制目标（<6.7餐后）
        base_bg = 5.5 if is_gdm else 4.6
        # 情绪评分基线（1-9分自定义量表，非EPDS）
        base_emotion = 5.5 if is_hypertension else 3.5
        prev_bg = base_bg
        prev_emo = base_emotion
        prev_sleep = round(random.uniform(7.0, 8.0), 1)

        for days_ago in range(0, 56, 2):
            record_date = datetime.now() - timedelta(days=days_ago)

            # 血糖：GDM患者偏高但控制良好（5.0-7.2），非GDM正常范围（3.8-5.3）
            bg_delta = random.uniform(-0.3, 0.3)
            if is_gdm:
                blood_sugar = round(max(5.0, min(7.2, prev_bg + bg_delta)), 1)
            else:
                blood_sugar = round(max(3.8, min(5.3, prev_bg + bg_delta)), 1)
            prev_bg = blood_sugar

            # 情绪评分（1-9分）：高血压患者偏高，前后±0.5变化
            emo_delta = random.uniform(-0.5, 0.5)
            if is_hypertension:
                emotion_score = round(max(3.0, min(9.0, prev_emo + emo_delta)), 1)
            else:
                emotion_score = round(max(1.0, min(7.0, prev_emo + emo_delta)), 1)
            prev_emo = emotion_score

            # 睡眠时长：稳定在7-8.5小时之间，前后±0.5变化
            sleep_delta = random.uniform(-0.5, 0.5)
            sleep_hours = round(max(6.5, min(8.5, prev_sleep + sleep_delta)), 1)
            prev_sleep = sleep_hours

            for metric, value, unit in [
                ("blood_sugar_fasting", round(blood_sugar - 0.3, 1), "mmol/L"),
                ("blood_sugar_postprandial", round(blood_sugar + 1.2, 1), "mmol/L"),
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
    logger.info("补充 {} 条健康数据", count)


if __name__ == "__main__":
    seed_all()
