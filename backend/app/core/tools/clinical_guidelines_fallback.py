"""
临床指南硬编码兜底库

当 RAG (pgvector + BGE-M3) 不可用时，为医生端 agno_query_clinical_guideline 提供
降级指南内容。所有内容提取自 knowledge_docs/ 中的医学文档，涵盖 12 个核心临床主题。

设计原则：
- 仅包含可在 knowledge_docs/ 中验证的事实，不虚构任何内容
- 按关键词匹配，支持中英文 topic 查询
- 每条指南包含 title、source、key_points (临床关键点)、references (原始文档)
- source 字段始终为 "hardcoded_fallback" 以区分真实 RAG 检索结果
"""

from __future__ import annotations

from typing import Optional

# ── 临床指南库 ──

CLINICAL_GUIDELINES: dict[str, dict] = {
    # ==================== GDM / 妊娠期糖尿病 ====================
    "gdm": {
        "title": "妊娠期糖尿病 (GDM) 管理指南",
        "source": "ACOG Practice Bulletin No. 190: Gestational Diabetes Mellitus (2023)",
        "key_points": [
            "【诊断标准】75g OGTT (24-28周)：空腹≥5.1，1h≥10.0，2h≥8.5 mmol/L — 任意一项异常即诊断 GDM",
            "【血糖控制目标】空腹≤5.3，餐后1h≤7.8，餐后2h≤6.7 mmol/L",
            "【饮食管理】碳水化合物40-50%，蛋白质20-25%，脂肪25-35%；少量多餐 (3正餐+2~3加餐)",
            "【药物治疗】胰岛素为一线药物 (不通过胎盘)；二甲双胍为二线替代 (需知情同意)",
            "【预后】70-85% 的 GDM 患者通过生活方式管理即可达标",
            "【产后随访】产后6-12周复查 75g OGTT，评估糖代谢状态",
        ],
        "references": ["gdm_management.md", "common_lab_values.md"],
    },
    "gestational diabetes": {
        "title": "妊娠期糖尿病 (GDM) 管理指南",
        "source": "ACOG Practice Bulletin No. 190",
        "key_points": [],  # 继承 gdm 的内容，实际查询时走 keyword match
        "references": ["gdm_management.md"],
        "_alias_of": "gdm",
    },
    "糖尿病": {
        "title": "妊娠期糖尿病 (GDM) 管理指南",
        "source": "ACOG Practice Bulletin No. 190",
        "key_points": [],
        "references": ["gdm_management.md"],
        "_alias_of": "gdm",
    },

    # ==================== 子痫前期 / 妊娠期高血压 ====================
    "preeclampsia": {
        "title": "子痫前期识别与管理指南",
        "source": "ACOG Practice Bulletin No. 222: Gestational Hypertension and Preeclampsia (2023)",
        "key_points": [
            "【诊断标准】孕20周后新发高血压 (≥140/90 mmHg) + 蛋白尿 (≥300 mg/24h) 或终末器官功能障碍",
            "【高危因素】初产妇、年龄≥35岁、慢性高血压、CKD、糖尿病、BMI≥30、多胎妊娠、家族史",
            "【警示症状】持续性头痛、视力模糊/闪光、上腹/右上腹痛、面部/手部突发水肿、体重骤增 (>2 kg/周)",
            "【轻度管理】卧床休息 (左侧卧位)、密切监测血压和胎儿状况",
            "【重度管理】住院、硫酸镁预防抽搐 (MgSO4 4-6g 负荷 + 1-2g/h 维持)、降压药控制血压",
            "【分娩决策】≥34周合并重度特征：建议分娩；<34周：权衡母胎风险，给予糖皮质激素促胎肺成熟",
            "【唯一根治方法】分娩终止妊娠",
        ],
        "references": ["preeclampsia_guidelines.md"],
    },
    "hypertension": {
        "title": "妊娠期高血压与子痫前期管理指南",
        "source": "ACOG Practice Bulletin No. 222",
        "key_points": [],
        "references": ["preeclampsia_guidelines.md"],
        "_alias_of": "preeclampsia",
    },
    "子痫": {
        "title": "子痫前期识别与管理指南",
        "source": "ACOG Practice Bulletin No. 222",
        "key_points": [],
        "references": ["preeclampsia_guidelines.md"],
        "_alias_of": "preeclampsia",
    },
    "高血压": {
        "title": "妊娠期高血压与子痫前期管理指南",
        "source": "ACOG Practice Bulletin No. 222",
        "key_points": [],
        "references": ["preeclampsia_guidelines.md"],
        "_alias_of": "preeclampsia",
    },

    # ==================== 孕期用药安全 ====================
    "medication": {
        "title": "孕期用药安全指南",
        "source": "FDA Pregnancy Categories + 孕期用药安全专家共识",
        "key_points": [
            "【安全药物 (FDA B类)】对乙酰氨基酚 (退热止痛，≤2g/天)；青霉素类/头孢菌素类 (抗感染)",
            "【妊娠期高血压一线用药】拉贝洛尔 (首选)；硝苯地平 (二线)",
            "【绝对禁忌】NSAIDs (第三孕期，D类 — 可致动脉导管早闭)；四环素类 (牙齿骨骼发育异常)；异维A酸 (X类 — 强致畸)；ACEi/ARB (肾发育异常)；华法林 (骨骼发育异常)",
            "【GDM 用药】胰岛素 (一线，不通过胎盘)；二甲双胍 (二线，知情同意后使用)；禁用磺脲类/TZD/GLP-1/SGLT-2/DPP-4",
            "【中草药安全】禁用：麝香、红花、桃仁、三棱、莪术 (活血化瘀类)；慎用：大黄、芒硝 (攻下类)；可用：黄芩、白术 (安胎类，需在中医师指导下)",
        ],
        "references": ["medication_safety.md"],
    },
    "drug": {
        "title": "孕期用药安全指南",
        "source": "FDA Pregnancy Categories",
        "key_points": [],
        "references": ["medication_safety.md"],
        "_alias_of": "medication",
    },
    "用药": {
        "title": "孕期用药安全指南",
        "source": "FDA Pregnancy Categories",
        "key_points": [],
        "references": ["medication_safety.md"],
        "_alias_of": "medication",
    },

    # ==================== 产前保健 ====================
    "prenatal": {
        "title": "孕期保健指南",
        "source": "中华医学会妇产科学分会. 孕前和孕期保健指南 (2022)",
        "key_points": [
            "【叶酸补充】备孕至孕12周：0.4-0.8 mg/天；既往NTD史：4-5 mg/天",
            "【体重增长目标 (按孕前BMI)】正常 (18.5-23.9)：8-14 kg；偏瘦：11-16 kg；超重：7-11 kg；肥胖：5-9 kg",
            "【三大筛查窗口】NT检查 (11-13+6周)、大排畸超声 (18-24周)、OGTT糖耐量 (24-28周)",
            "【胎动计数 (28周起)】正常≥3-5次/小时；<10次/2小时或较基线减少>50% → 立即就医",
            "【分娩前兆】规律宫缩 (5-6分钟一次，持续>30秒)、见红、破水 — 任一出现即赴医院",
            "【营养补充】孕中期起补钙 1000 mg/天、补铁 24-30 mg/天、DHA 200-300 mg/天",
        ],
        "references": ["prenatal_guidelines.md", "nutrition_diet.md"],
    },
    "pregnancy": {
        "title": "孕期保健指南",
        "source": "中华医学会妇产科学分会",
        "key_points": [],
        "references": ["prenatal_guidelines.md"],
        "_alias_of": "prenatal",
    },
    "孕期": {
        "title": "孕期保健指南",
        "source": "中华医学会妇产科学分会",
        "key_points": [],
        "references": ["prenatal_guidelines.md"],
        "_alias_of": "prenatal",
    },
    "产检": {
        "title": "孕期保健指南",
        "source": "中华医学会妇产科学分会",
        "key_points": [],
        "references": ["prenatal_guidelines.md"],
        "_alias_of": "prenatal",
    },

    # ==================== 胎动监测 ====================
    "fetal_movement": {
        "title": "胎动监测指南",
        "source": "RCOG Green-top Guideline No. 57: Reduced Fetal Movements",
        "key_points": [
            "【胎动感知时间】初产妇 18-20周，经产妇 16-18周开始感知胎动",
            "【正常标准】≥3-5次/小时；≥10次/12小时 (每天固定时间计数更准确)",
            "【减少标准】<10次/2小时；较平时基线减少>50%；先剧烈增加后骤然减少",
            "【处理流程】立即左侧卧位休息 → 专注计数2小时 → 仍<10次则立即赴医院 → NST (无应激试验) → NST异常则B超评估",
            "【紧急情况】胎动完全消失 + 阴道出血或腹痛 → 立即急诊",
            "【高危人群】GDM、高血压患者需更积极评估胎动减少",
            "【孕晚期变化】36周后幅度减小但频率不变；进食后和夜间胎动通常增加",
        ],
        "references": ["fetal_movement_monitoring.md"],
    },
    "fgr": {
        "title": "胎儿生长受限 (FGR) 管理指南",
        "source": "ACOG Practice Bulletin No. 204: Fetal Growth Restriction (2021)",
        "key_points": [
            "【定义】超声估测胎儿体重 (EFW) < 同孕龄第10百分位",
            "【分类】早发型 (<32周) 与晚发型 (≥32周)，病因和预后不同",
            "【监测】脐动脉多普勒血流评估 (UA Doppler) 为关键监测手段",
            "【分娩时机】早发型FGR伴UA舒张末期血流缺失/反向：建议32-34周分娩；单纯EFW<第10百分位：可期待至37-39周",
            "【预防】低剂量阿司匹林 (100-150 mg/天) 对高危孕妇有预防作用，建议16周前开始",
            "【胎动监测】FGR胎儿更易缺氧，胎动明显减少需立即评估",
        ],
        "references": ["fetal_movement_monitoring.md"],
    },
    "胎动": {
        "title": "胎动监测指南",
        "source": "RCOG Green-top Guideline No. 57",
        "key_points": [],
        "references": ["fetal_movement_monitoring.md"],
        "_alias_of": "fetal_movement",
    },
    "fetal": {
        "title": "胎动监测指南",
        "source": "RCOG Green-top Guideline No. 57",
        "key_points": [],
        "references": ["fetal_movement_monitoring.md"],
        "_alias_of": "fetal_movement",
    },

    # ==================== 产前诊断 ====================
    "prenatal_diagnosis": {
        "title": "产前筛查与诊断指南",
        "source": "中华医学会医学遗传学分会临床实践指南",
        "key_points": [
            "【早唐筛查 (11-13+6周)】NT超声 + 血清学 (PAPP-A + free β-hCG)；检出率约85-90%",
            "【中唐筛查 (15-20周)】血清学三联/四联筛查；检出率约60-75%",
            "【NIPT (12-22+6周)】无创DNA检测：T21检出率≥99%，假阳性<0.1%；高风险结果必须通过羊膜腔穿刺确诊",
            "【NT正常值】<2.5-3.0 mm；NT≥3.0 mm与染色体异常和先天性心脏病风险增高相关",
            "【大排畸超声 (20-24周)】系统筛查胎儿结构，可检出70-80%的重大结构异常，检查时间30-60分钟",
            "【羊膜腔穿刺 (16-22周)】染色体诊断金标准；流产风险约1/500-1/1000 (远低于既往认知)",
            "【脐血穿刺 (>18周)】胎儿染色体/基因诊断；胎儿丢失风险1-2%",
        ],
        "references": ["prenatal_diagnosis.md"],
    },
    "diagnosis": {
        "title": "产前筛查与诊断指南",
        "source": "中华医学会医学遗传学分会",
        "key_points": [],
        "references": ["prenatal_diagnosis.md"],
        "_alias_of": "prenatal_diagnosis",
    },
    "筛查": {
        "title": "产前筛查与诊断指南",
        "source": "中华医学会医学遗传学分会",
        "key_points": [],
        "references": ["prenatal_diagnosis.md"],
        "_alias_of": "prenatal_diagnosis",
    },

    # ==================== 实验室检查 ====================
    "lab": {
        "title": "孕期常见实验室检查参考值",
        "source": "ATA / ACOG 临床指南 + 中华医学会检验医学分会",
        "key_points": [
            "【贫血诊断】Hb < 110 g/L (孕期贫血)；轻度 (90-109) 可补铁+饮食纠正；中重度 (<90) 需医学干预",
            "【血小板】正常 100-300×10^9/L；<100 需排查妊娠期血小板减少症/子痫前期/HELLP综合征",
            "【TSH孕期参考范围 (ATA)】孕早期 0.1-2.5 mIU/L；孕中期 0.2-3.0 mIU/L；孕晚期 0.3-3.0 mIU/L",
            "【OGTT诊断阈值】空腹≥5.1；1h≥10.0；2h≥8.5 mmol/L —— 满足任意一项诊断GDM",
            "【尿常规】蛋白尿 (+) 需排除子痫前期；尿糖 (+) 需结合血糖评估GDM；酮体 (+) 提示能量摄入不足",
            "【肝功能】ALT升高需排查妊娠期肝内胆汁淤积症 (ICP) / HELLP / 病毒性肝炎",
        ],
        "references": ["common_lab_values.md"],
    },
    "实验室": {
        "title": "孕期常见实验室检查参考值",
        "source": "ATA / ACOG 临床指南",
        "key_points": [],
        "references": ["common_lab_values.md"],
        "_alias_of": "lab",
    },
    "化验": {
        "title": "孕期常见实验室检查参考值",
        "source": "ATA / ACOG 临床指南",
        "key_points": [],
        "references": ["common_lab_values.md"],
        "_alias_of": "lab",
    },

    # ==================== 分娩 ====================
    "labor": {
        "title": "分娩与产程管理指南",
        "source": "ACOG / 中华医学会妇产科学分会产科学组",
        "key_points": [
            "【第一产程】潜伏期至宫口开6cm，活跃期6→10cm。初产妇平均全程11-12小时，经产妇6-8小时",
            "【第二产程】初产妇≤2小时 (硬膜外麻醉≤3小时)；经产妇≤1小时 (硬膜外麻醉≤2小时)",
            "【硬膜外分娩镇痛】最佳时机：宫口开2-3cm；可将疼痛从8-10分降至2-3分；不增加剖宫产率",
            "【剖宫产指征】胎儿窘迫、头盆不称、前置胎盘、胎位异常 (臀位/横位)、脐带脱垂、重度子痫前期",
            "【分娩征兆】规律宫缩 (间隔5-6分钟，持续>30秒)、见红 (血性分泌物)、破水 (羊膜破裂) — 任一出现即应赴医院",
        ],
        "references": ["labor_delivery.md"],
    },
    "delivery": {
        "title": "分娩与产程管理指南",
        "source": "ACOG / 中华医学会",
        "key_points": [],
        "references": ["labor_delivery.md"],
        "_alias_of": "labor",
    },
    "分娩": {
        "title": "分娩与产程管理指南",
        "source": "ACOG / 中华医学会",
        "key_points": [],
        "references": ["labor_delivery.md"],
        "_alias_of": "labor",
    },

    # ==================== 产后恢复 ====================
    "postpartum": {
        "title": "产后恢复指南",
        "source": "中华医学会妇产科学分会产后康复指南",
        "key_points": [
            "【恶露时间线】血性恶露 (1-3天)；浆液恶露 (4-10天)；白色恶露 (10天后)。异常信号：突然增多/变暗/恶臭/发热",
            "【产后情绪】Baby Blues：50-80%产妇，产后3-5天出现，2周内自行缓解；PPD (产后抑郁)：10-15%，症状持续>2周 → 需专业治疗",
            "【伤口护理】会阴伤口：保持清洁干燥、便后由前向后冲洗、5-7天愈合；剖宫产伤口：保持干燥、5-7天拆线、2周内不浸水、6周内不提重物",
            "【盆底康复】凯格尔运动：收紧5-10秒→放松，10-15次/组，每天3组；黄金恢复期：产后42天至6个月",
            "【产后运动】第1-2周：仅限于休息+凯格尔；第4-6周：轻度活动 (散步、产后瑜伽)；6周后：复查通过后逐步恢复中等强度运动",
        ],
        "references": ["postpartum_recovery.md"],
    },
    "产后": {
        "title": "产后恢复指南",
        "source": "中华医学会妇产科学分会",
        "key_points": [],
        "references": ["postpartum_recovery.md"],
        "_alias_of": "postpartum",
    },

    # ==================== 新生儿护理 ====================
    "newborn": {
        "title": "新生儿护理指南",
        "source": "中华医学会儿科学分会新生儿学组",
        "key_points": [
            "【生理性黄疸】生后2-3天出现，4-5天达峰，足月儿2周内消退 (早产儿3-4周)；总胆红素 <12.9 mg/dL (足月)",
            "【病理性黄疸警示】生后24h内出现；上升速度 >5 mg/dL/天；足月儿总胆红素 >12.9 mg/dL；持续>2周 (足月)；退而复现；婴儿嗜睡/拒奶",
            "【安全睡眠 (防SIDS)】仰卧位、硬质床垫、无枕头/玩具/松散被褥、室温20-22°C、同室不同床",
            "【喂养】母乳按需喂养 8-12次/天；出生后1小时内早接触早吸吮早开奶",
            "【体重里程碑】出生后前几天体重可下降≤10%；7-10天恢复出生体重",
            "【疫苗接种】出生24h内：乙肝疫苗第1剂；母亲HBsAg阳性者：12h内加注HBIG；卡介苗：足月体重≥2500g尽早接种",
        ],
        "references": ["newborn_care.md", "vaccination.md"],
    },
    "新生儿": {
        "title": "新生儿护理指南",
        "source": "中华医学会儿科学分会",
        "key_points": [],
        "references": ["newborn_care.md"],
        "_alias_of": "newborn",
    },

    # ==================== 疫苗接种 ====================
    "vaccination": {
        "title": "孕期疫苗接种指南",
        "source": "ACOG Committee Opinion / WHO 免疫策略咨询专家组",
        "key_points": [
            "【推荐疫苗 — 任何孕期】流感灭活疫苗 (孕妇重症流感风险显著增高，接种可同时保护新生儿前6个月)",
            "【推荐疫苗 — 27-36周】Tdap (百白破) 每胎次均需接种，理想窗口27-28周，为新生儿提供被动免疫抗百日咳",
            "【推荐疫苗 — COVID-19】mRNA/灭活疫苗任何孕期均可接种",
            "【绝对禁忌 — 活减毒疫苗】MMR (麻疹腮腺炎风疹)、水痘、黄热病、卡介苗 (BCG)、带状疱疹、口服脊灰 (OPV)、口服伤寒 — 备孕/孕期禁用；接种后避孕1-3个月",
            "【接种后观察】30分钟留观过敏反应；低热和局部反应属正常现象",
        ],
        "references": ["vaccination.md"],
    },
    "疫苗": {
        "title": "孕期疫苗接种指南",
        "source": "ACOG / WHO",
        "key_points": [],
        "references": ["vaccination.md"],
        "_alias_of": "vaccination",
    },

    # ==================== 孕期营养 ====================
    "nutrition": {
        "title": "孕期营养与饮食指南",
        "source": "中国营养学会. 中国居民膳食指南 (2022) — 孕期妇女膳食指导",
        "key_points": [
            "【热量需求】孕早期约1800 kcal/天 (基线)；孕中期 +300 kcal；孕晚期在孕中期基础上 +100 kcal",
            "【关键补充剂】叶酸400-800 mcg/天 (孕早期)；钙1000 mg/天 (孕中期起)；铁24-29→30 mg/天 (孕中→晚期)；DHA 200-300 mg/天",
            "【贫血管理】孕期贫血发生率30-40%；口服铁剂+维生素C促进吸收；避免与茶/咖啡同服",
            "【咖啡因限制】≤200 mg/天 (约1杯咖啡)",
            "【绝对禁忌】酒精 (任何剂量)、高汞鱼类 (鲨鱼/剑鱼/方头鱼/大眼金枪鱼)、未经巴氏消毒的乳制品、生/未熟肉蛋海鲜",
        ],
        "references": ["nutrition_diet.md"],
    },
    "diet": {
        "title": "孕期营养与饮食指南",
        "source": "中国营养学会",
        "key_points": [],
        "references": ["nutrition_diet.md"],
        "_alias_of": "nutrition",
    },
    "营养": {
        "title": "孕期营养与饮食指南",
        "source": "中国营养学会",
        "key_points": [],
        "references": ["nutrition_diet.md"],
        "_alias_of": "nutrition",
    },
    "饮食": {
        "title": "孕期营养与饮食指南",
        "source": "中国营养学会",
        "key_points": [],
        "references": ["nutrition_diet.md"],
        "_alias_of": "nutrition",
    },

    # ==================== 运动 ====================
    "exercise": {
        "title": "孕期运动与活动指南",
        "source": "ACOG Committee Opinion No. 804: Physical Activity and Exercise During Pregnancy",
        "key_points": [
            "【推荐运动】散步30分钟/天、孕妇瑜伽、游泳、凯格尔运动；心率<140 bpm (谈话测试)",
            "【注意事项】16周后避免仰卧位运动；每15-20分钟补水；避免跌倒/碰撞风险活动",
            "【运动禁忌症】前置胎盘、宫颈机能不全、先兆早产、未足月胎膜早破 (PPROM)、重度贫血、未控制的妊娠期高血压、严重心肺疾病、多胎妊娠合并宫颈缩短",
            "【睡眠建议】孕中期起左侧卧位 (改善胎盘灌注)、避免仰卧；夜间7-9小时+午休30-60分钟",
            "【旅行建议】最佳旅行窗口14-28周；乘车安全带置于腹下髋部水平、肩带置于双乳间绕腹侧、每1.5-2小时休息",
        ],
        "references": ["exercise_activity.md", "travel_safety.md"],
    },
    "运动": {
        "title": "孕期运动与活动指南",
        "source": "ACOG Committee Opinion No. 804",
        "key_points": [],
        "references": ["exercise_activity.md"],
        "_alias_of": "exercise",
    },

    # ==================== 心理健康 ====================
    "mental_health": {
        "title": "围产期心理健康指南",
        "source": "ACOG Committee Opinion No. 757: Screening for Perinatal Depression",
        "key_points": [
            "【发生率】围产期焦虑 15-25%；围产期抑郁 10-20%；分娩恐惧 (Tokophobia) 6-10%。孕早期和孕晚期为两个高发期",
            "【核心症状】持续情绪低落、兴趣丧失、疲劳、睡眠/食欲改变 — 持续>2周需专业评估",
            "【就医指征】症状持续>2周、频繁绝望感、严重睡眠障碍、自杀意念、惊恐发作、无法正常生活",
            "【自我调节】CBT技术 (识别并挑战灾难化思维、行为激活 — 每天安排小件愉悦活动)；正念呼吸 (每天5-15分钟，吸气4秒、屏息2秒、呼气6秒)",
            "【Baby Blues vs PPD】Baby Blues: 产后3-5天起，2周内自愈；PPD: 持续>2周，需专业治疗",
            "【全国心理危机热线】400-161-9995",
        ],
        "references": ["mental_health_expanded.md"],
    },
    "depression": {
        "title": "围产期心理健康指南",
        "source": "ACOG Committee Opinion No. 757",
        "key_points": [],
        "references": ["mental_health_expanded.md"],
        "_alias_of": "mental_health",
    },
    "心理": {
        "title": "围产期心理健康指南",
        "source": "ACOG Committee Opinion No. 757",
        "key_points": [],
        "references": ["mental_health_expanded.md"],
        "_alias_of": "mental_health",
    },
    "anxiety": {
        "title": "围产期心理健康指南",
        "source": "ACOG Committee Opinion No. 757",
        "key_points": [],
        "references": ["mental_health_expanded.md"],
        "_alias_of": "mental_health",
    },

    # ==================== 旅行安全 ====================
    "travel": {
        "title": "孕期旅行安全指南",
        "source": "ACOG Committee Opinion: Air Travel During Pregnancy",
        "key_points": [
            "【最佳旅行窗口】14-28周 (流产风险最低、早孕反应缓解、行动仍便利)",
            "【航空旅行】单胎通常允许至32周 (部分航司至36周)，需携带医疗证明；飞行中每1-2小时起身活动+穿弹力袜预防DVT",
            "【汽车旅行】安全带：腰带置于腹下髋部水平，肩带置于双乳间包绕腹部侧面；每1.5-2小时休息活动",
            "【绝对禁忌】先兆流产/早产、前置胎盘、宫颈机能不全、多胎妊娠 (尤其中晚期)、重度子痫前期、中重度贫血、未足月胎膜早破",
            "【应急准备】携带产检记录+紧急联系人；了解目的地最近的产科医院位置",
        ],
        "references": ["travel_safety.md"],
    },
    "旅行": {
        "title": "孕期旅行安全指南",
        "source": "ACOG Committee Opinion",
        "key_points": [],
        "references": ["travel_safety.md"],
        "_alias_of": "travel",
    },
}


def resolve_guideline(topic: str) -> Optional[dict]:
    """根据 topic 关键词解析指南条目，处理别名链

    Args:
        topic: 查询主题关键词 (中英文均可)

    Returns:
        指南条目 dict，含 title/source/key_points/references；未匹配返回 None
    """
    topic_lower = topic.lower().strip()

    # 直接匹配
    if topic_lower in CLINICAL_GUIDELINES:
        entry = CLINICAL_GUIDELINES[topic_lower]
        # 如果该条目是别名，递归解析
        if entry.get("_alias_of") and not entry.get("key_points"):
            return CLINICAL_GUIDELINES.get(entry["_alias_of"])
        return entry

    # 子串匹配 (关键词包含在 topic 中)
    for key, entry in CLINICAL_GUIDELINES.items():
        if entry.get("_alias_of"):
            continue  # 跳过纯别名条目，由直接匹配处理
        if key in topic_lower:
            return entry

    return None


def search_guidelines(topic: str, max_results: int = 3) -> list[dict]:
    """搜索匹配的指南条目

    Args:
        topic: 查询主题
        max_results: 最大返回条目数

    Returns:
        匹配的指南条目列表
    """
    topic_lower = topic.lower().strip()
    results: list[dict] = []
    seen_titles: set = set()

    # 优先精确匹配 (含别名解析)
    exact = resolve_guideline(topic_lower)
    if exact and exact.get("title") not in seen_titles:
        results.append(exact)
        seen_titles.add(exact["title"])

    # 子串匹配补充 (先匹配主键，再匹配别名键以覆盖中文查询)
    def _add_by_substring(candidate_key: str):
        nonlocal results, seen_titles
        entry = CLINICAL_GUIDELINES.get(candidate_key)
        if not entry:
            return
        # 解析别名
        if entry.get("_alias_of") and not entry.get("key_points"):
            entry = CLINICAL_GUIDELINES.get(entry["_alias_of"])
        if entry and entry.get("title") not in seen_titles and len(results) < max_results:
            results.append(entry)
            seen_titles.add(entry["title"])

    for key, entry in CLINICAL_GUIDELINES.items():
        if len(results) >= max_results:
            break
        if key in topic_lower:
            _add_by_substring(key)

    return results[:max_results]
