from typing import Optional, Union


# ===================== 公共常量文案（抽离重复内容，统一维护） =====================
TIP_FOLATE_NORMAL = "普通孕妇叶酸补充至孕12周即可；有流产史、多胎、神经管缺陷生育史等高风险人群，建议全程每日0.4mg叶酸。"
TIP_LEFT_SLEEP = "优先左侧卧位休息，提升子宫胎盘供血，减轻大血管压迫；可搭配孕妇枕垫腰腹、双腿之间提升舒适度。"
TIP_COUNT_FETAL_MOVE = "每日固定晚饭后1小时左侧卧数胎动，正常1小时≥3-5次，2小时累计≥10次；胎动骤增/骤减50%以上立刻就医监护。"
TIP_LOW_SALT = "每日食盐摄入控制6g以内，少吃腌制品、加工零食，冬瓜、红豆、黄瓜有助缓解生理性水肿。"
TIP_CALCIUM_VD = "每日奶制品300-500ml补充钙（全天总钙1000mg）；每日15-20分钟温和日晒，促进维生素D合成助力钙吸收。"
TIP_IRON_VC = "孕中晚期重点补铁，红肉、动物血、肝脏（每周1-2次，单次≤50g）搭配橙子、番茄、猕猴桃等维C食物，大幅提升铁吸收率；孕期推荐铁摄入：早15mg/中25mg/晚30mg。"
TIP_GDM_DIET = "控精制糖、奶茶、蛋糕、白米白面；替换低GI主食：燕麦、糙米、杂豆、薯类；少食多餐避免餐后血糖飙升。"
TIP_KEGEL = "每日坚持凯格尔运动，强化盆底肌，预防产后漏尿、痔疮、盆底松弛。"
TIP_WARNING_COMMON = "【普通不适】轻微坠胀、单侧牵拉痛、轻度水肿晨轻暮重、偶发无痛假性宫缩无需过度紧张；改变姿势、抬高下肢、充分休息可缓解。"
TIP_WARNING_EMERGENCY = "【高危急症，立即急诊】1.阴道鲜红出血/大量流水疑似破水；2.规律宫缩10分钟内≥1次、持续30秒以上；3.胎动显著减少；4.持续剧烈头痛、视力模糊、上腹部剧痛、全身突发水肿（面部/手掌）；5.全身无皮疹但手掌脚掌夜间瘙痒难忍；6.单侧下腹撕裂痛伴肩背放射痛。"


class WeekData:
    """单周孕期结构化数据，使用 __slots__ 零开销访问。
    测量标准：1-20周顶臀长CRL，21-40周从头到脚跟全长
    数据源：
    - 胎儿尺寸体重：WHO/WPRO 胎儿生长标准
    - 水果类比：Femia Health (2025 updated)
    - 发育里程碑：ACOG, Mayo Clinic, BabyCenter
    - 母体变化：Mayo Clinic, U.S. Office on Women's Health, What to Expect
    - 孕期建议：ACOG, WHO, 《孕产妇营养健康教育核心信息及释义》(2025), 《中国居民膳食指南(2022)》
    """
    __slots__ = (
        "week", "size", "size_cm", "weight",
        "milestone", "mom_changes",
        "weekly_tips", "diet_advice", "exercise_advice", "warning_signs",
    )

    def __init__(
        self, week: int, *,
        size: str, size_cm: str, weight: str,
        milestone: str, mom_changes: str,
        weekly_tips: str, diet_advice: str,
        exercise_advice: str, warning_signs: str,
    ):
        self.week = week
        self.size = size
        self.size_cm = size_cm
        self.weight = weight
        self.milestone = milestone
        self.mom_changes = mom_changes
        self.weekly_tips = weekly_tips
        self.diet_advice = diet_advice
        self.exercise_advice = exercise_advice
        self.warning_signs = warning_signs

    def as_baby_info(self) -> dict:
        """转换为 /home 端点 baby_info 字段格式。"""
        return {
            "size": self.size,
            "size_cm": self.size_cm,
            "weight": self.weight,
            "milestone": self.milestone,
            "current_week": self.week,
        }

    def as_mom_changes(self) -> dict:
        """转换为 /home 端点 mom_changes 字段格式。"""
        return {"week": self.week, "changes": self.mom_changes}

    def as_recommendations(self) -> dict:
        """转换为 /home 端点 recommendations 字段格式。"""
        return {
            "weekly_tips": self.weekly_tips,
            "diet_advice": self.diet_advice,
            "exercise_advice": self.exercise_advice,
            "warning_signs": self.warning_signs,
        }


# ── 40周完整知识数据 ──────────────────────────────────────────────────
# 索引 0 = 第1周，索引 39 = 第40周
# 测量规则：1–20周 CRL顶臀长，21–40周 从头到脚跟全长
_WEEKS: list[WeekData] = []


def _build_weeks() -> list[WeekData]:
    """构建40周知识库。数据基于权威医学来源，已校准Femia水果类比、WHO尺寸体重、国内产科指南。"""

    # ===================== 孕早期 (1-12周) 胚胎分化器官形成 =====================
    w1 = WeekData(1,
        size="—", size_cm="—", weight="—",
        milestone="这是孕期的计算起点。虽然宝宝还没有到来，但你的身体已经开始为TA准备温暖的小家了——卵泡正在发育，子宫内膜也在更新。",
        mom_changes="经期尾声，身体进入全新排卵周期，暂无怀孕相关体征。",
        weekly_tips=f"备孕期每日补充0.4mg叶酸。{TIP_FOLATE_NORMAL}；戒烟戒酒，远离染发剂、高温桑拿等有害环境，规律作息。",
        diet_advice="均衡三餐，多深绿蔬菜、豆类、全谷物；忌食生食、半生肉类、高汞海鱼；少辛辣刺激。",
        exercise_advice="日常散步、轻柔拉伸维持代谢；有多囊、反复流产史避免高强度跳操、负重训练。",
        warning_signs=f"{TIP_WARNING_COMMON} 经期经量暴增、剧烈痛经、非经期不规则出血，及时妇科就诊排查内分泌/内膜问题。{TIP_WARNING_EMERGENCY}",
    )

    w2 = WeekData(2,
        size="—", size_cm="—", weight="—",
        milestone="卵巢释放出一颗珍贵的卵子，它正沿着输卵管旅行，等待与精子的相遇。子宫内膜持续增厚，为小生命的到来做好准备。",
        mom_changes="排卵期宫颈黏液清稀拉丝；备孕黄金窗口期，暂无早孕反应。",
        weekly_tips=f"咖啡因每日≤200mg；坚持叶酸补充。{TIP_FOLATE_NORMAL}；不擅自服用感冒药、止痛药等非必需药物。",
        diet_advice="增加叶酸食物：菠菜、芦笋、牛油果、动物肝脏；搭配优质蛋白鸡蛋、鱼虾、豆制品。",
        exercise_advice="低冲击运动：快走、瑜伽、游泳，平衡内分泌，优化着床环境；禁止负重深蹲、腹部挤压训练。",
        warning_signs=f"{TIP_WARNING_COMMON} 单侧轻微排卵痛1-2天自行缓解无需干预。{TIP_WARNING_EMERGENCY}",
    )

    w3 = WeekData(3,
        size="罂粟籽大小", size_cm="~0.2cm", weight="<1g",
        milestone="奇迹发生了！精子和卵子结合成受精卵，经过持续细胞分裂形成囊胚，正沿着输卵管向子宫移动，准备安家。",
        mom_changes="囊胚即将着床；少数人出现微量粉色/褐色着床出血，量极少仅擦拭可见，持续1-2天。",
        weekly_tips="着床期远离高温热水浴、桑拿；全程禁酒、烟草、化工清洁剂；未确诊怀孕不自行服药。",
        diet_advice="持续补叶酸，坚果、橄榄油补充维E，改善子宫内膜容受性；三餐温和易消化。",
        exercise_advice="仅短时间慢走、轻柔拉伸；严禁剧烈有氧、卷腹、负重。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 出血量等同月经、单侧下腹撕裂剧痛警惕宫外孕，立刻急诊。",
    )

    w4 = WeekData(4,
        size="芝麻大小", size_cm="~0.4cm", weight="<1g",
        milestone="小囊胚成功着床啦！胎盘和羊膜腔开始分化，三个胚层也已经形成——未来宝宝全身所有的器官和组织都将从这里发育而来。",
        mom_changes="月经推迟，早孕试纸可检出阳性；乳房胀痛、嗜睡乏力、基础体温持续升高。",
        weekly_tips="确认怀孕立刻预约首次产检建档；每日0.4mg叶酸，持续至12周，高危人群全程补充。",
        diet_advice="少食多餐规避空腹恶心；香蕉、全谷物补充B6缓解早期反胃；每日饮水2000ml。",
        exercise_advice="仅慢走15分钟，多卧床休息；避免久站弯腰、提重物。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY}",
    )

    w5 = WeekData(5,
        size="蓝莓大小", size_cm="~0.8cm", weight="~1g",
        milestone="宝宝现在像一只小蝌蚪，神经管正在闭合，这可是未来大脑和脊髓的雏形哦。原始心脏也开始成型，胎盘和脐带逐步建立起营养输送通道。",
        mom_changes="早孕反应爆发：全天恶心反胃、嗅觉敏感、乳房胀痛、尿频、持续性疲惫，hCG快速升高。",
        weekly_tips="轻度孕吐无需用药；完全无法进食进水、体重下降为妊娠剧吐，必须住院补液治疗。",
        diet_advice="晨起空腹吃苏打饼干防晨吐；生姜柠檬水缓解恶心；每日保证130g碳水基础摄入。",
        exercise_advice="以休息为主，体力允许短时散步，不强迫运动。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 出血伴随组织物排出、下腹坠痛警惕先兆流产。",
    )

    w6 = WeekData(6,
        size="橄榄大小", size_cm="~1.3cm", weight="~2g",
        milestone="小心脏开始跳动了！通过阴道B超可以看到这激动人心的一幕。大脑泡、眼睛和耳朵的雏形也出现了，小小的上肢肢芽也长了出来。",
        mom_changes="孕吐峰值，气味耐受度极低；乳晕加深，情绪波动易怒、焦虑；子宫轻微增大下腹坠胀。",
        weekly_tips="本次B超核心确认宫内孕+胎心胎芽；同步预约11-13+6周NT筛查，超13周6天无法检测。",
        diet_advice="孕吐严重优先保证液体清汤、温水；镁+B6食物缓解恶心；禁食生食、高汞深海鱼。",
        exercise_advice="减少活动，禁止弯腰负重；有出血史遵医嘱卧床静养。",
        warning_signs=f"{TIP_WARNING_COMMON} B超未见胎心胎芽遵医嘱1-2周复查；出现急症信号立即就医。{TIP_WARNING_EMERGENCY}",
    )

    w7 = WeekData(7,
        size="樱桃大小", size_cm="~2.0cm", weight="~3g",
        milestone="大脑正在飞速增殖，手臂和腿开始分化成型，眼睛、鼻子和嘴巴都完整出现了。脐带稳定地给宝宝输送着营养和氧气。",
        mom_changes="孕吐接近顶峰；子宫如鹅蛋，外观暂无孕肚；基础代谢上升，易燥热多汗；牙龈充血易出血。",
        weekly_tips="软毛牙刷清洁口腔，禁用酒精漱口水；皮肤提前涂抹保湿油预防后期妊娠纹。",
        diet_advice=f"{TIP_IRON_VC}；持续叶酸补充；少吃辛辣上火食物保护牙龈。",
        exercise_advice=f"{TIP_KEGEL}；每日20分钟慢走舒缓胀气、反胃。",
        warning_signs=f"{TIP_WARNING_COMMON} 持续剧烈呕吐、尿酮阳性为妊娠剧吐需住院。{TIP_WARNING_EMERGENCY}",
    )

    w8 = WeekData(8,
        size="青枣大小", size_cm="~2.3cm", weight="~5g",
        milestone="胚胎期进入尾声啦。心脏四个腔室成型，小手指小脚趾的芽芽冒了出来，小尾巴也在慢慢消失——所有重要器官都已经初步奠基。",
        mom_changes="子宫如橙子；乳晕长出蒙氏结节；孕吐持续，身体缓慢适应激素变化。",
        weekly_tips="启动正式建档全套产检：血常规、尿常规、血型、传染病、甲状腺功能筛查。",
        diet_advice="每日饮水2000ml；全谷物、绿叶菜补充膳食纤维预防胀气便秘。",
        exercise_advice="短时间散步；禁止剧烈跳跃、腹部受压动作；出血史严格静养。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY}",
    )

    w9 = WeekData(9,
        size="无花果大小", size_cm="~3.1cm", weight="~14g",
        milestone="内脏器官都具备了基础功能，手指和脚趾轮廓清晰，眼睑和耳垂也成型了。宝宝在羊水中轻轻活动，虽然妈妈暂时还感觉不到呢。",
        mom_changes="孕吐逐步缓解；胀气导致腰围变紧；激素波动情绪起伏大。",
        weekly_tips="全身皮肤坚持保湿护理；留意尿频尿痛，警惕孕期尿路感染。",
        diet_advice=f"{TIP_CALCIUM_VD}；每日300ml以上奶制品补钙。",
        exercise_advice=f"{TIP_KEGEL}；规律轻度散步维持体能。",
        warning_signs=f"{TIP_WARNING_COMMON} 发热、尿痛、腰酸为尿路感染，必须用药治疗避免上行感染肾脏。{TIP_WARNING_EMERGENCY}",
    )

    w10 = WeekData(10,
        size="西梅大小", size_cm="~4.1cm", weight="~25g",
        milestone="恭喜，宝宝从胚胎期正式进入胎儿阶段！所有器官框架都已成型，接下来进入功能发育期。小指甲和牙胚也开始萌发了。",
        mom_changes="子宫如葡萄柚；腹白线色素加深出现淡妊娠线；情绪趋于平稳，疲劳减轻。",
        weekly_tips="10周起可做NIPT无创DNA筛查，准确率＞99%，筛查三体染色体异常；务必锁定NT检查窗口期。",
        diet_advice="每周2-3次三文鱼等低汞深海鱼补充DHA，促进脑与视网膜发育；或选择藻油补剂。",
        exercise_advice="孕妇瑜伽、每日30分钟散步；禁止仰卧训练、跳跃跑跳。",
        warning_signs=f"{TIP_WARNING_COMMON} 大量出血排出葡萄样组织警惕葡萄胎。{TIP_WARNING_EMERGENCY}",
    )

    w11 = WeekData(11,
        size="柠檬大小", size_cm="~6.1cm", weight="~49g",
        milestone="宝宝能自己吞咽羊水、蹬蹬小腿了！指纹正在形成，肠道开始蠕动，肾脏也开始产生尿液，面部五官越来越清晰可爱。",
        mom_changes="子宫填满盆腔，下腹可触及；孕吐大幅消退食欲回升；血管扩张易体位性头晕。",
        weekly_tips="NT筛查窗口期11-13+6周，超期无法检测，立刻预约；结合NIPT/血清唐筛综合评估风险。",
        diet_advice=f"{TIP_FOLATE_NORMAL}；均衡营养不暴饮暴食；海带、碘盐补碘，保障胎儿甲状腺发育。",
        exercise_advice="每日20-30分钟快走；避免久躺仰卧。",
        warning_signs=f"{TIP_WARNING_COMMON} NT增厚遵医嘱进一步穿刺/无创复核。{TIP_WARNING_EMERGENCY}",
    )

    w12 = WeekData(12,
        size="桃子大小", size_cm="~7.4cm", weight="~60g",
        milestone="手指和脚趾完全分开了，宝宝学会了吮吸和打嗝。20颗乳牙的牙胚全部形成，眼睛也移到了面部正中。流产风险大幅下降，可以稍微松一口气啦。",
        mom_changes="早期流产风险断崖式下降；孕吐基本消失精力恢复；子宫上升出耻骨，小腹轻微隆起。",
        weekly_tips="完成NT+早期唐筛整套排畸；普通人群可停止单独补充叶酸，高危全程服用。",
        diet_advice="坚持碘摄入；荤素搭配均衡，无需刻意加倍进食；控制油炸甜食。",
        exercise_advice="每日30分钟中等强度运动：散步、游泳、孕妇瑜伽；每周不少于5天。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY}",
    )

    # ===================== 孕中期 (13-28周) 胎儿快速生长 =====================
    w13 = WeekData(13,
        size="牛油果大小", size_cm="~8.7cm", weight="~100g",
        milestone="宝宝拥有了独一无二的指纹！骨骼持续变硬，声带开始发育，肠道从脐带移入腹腔。全身覆盖着一层柔软的胎毛，保护着娇嫩的皮肤。",
        mom_changes="孕中期舒适期到来，精力充沛；孕吐完全消失；下腹持续隆起，生理性白带增多。",
        weekly_tips="启动温和胎教：轻声说话、轻音乐抚摸腹部；重点持续补钙补铁。",
        diet_advice=f"每日增加优质蛋白20g；{TIP_CALCIUM_VD}；{TIP_LOW_SALT}。",
        exercise_advice="每日30分钟有氧，微微出汗可正常交谈为宜；游泳、瑜伽优先推荐。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 规律宫缩、破水、胎动骤减立刻就医。",
    )

    w14 = WeekData(14,
        size="苹果大小", size_cm="~10.0cm", weight="~120g",
        milestone="宝宝会做表情了——能皱眉头、微笑、扮鬼脸呢！肝脏开始分泌胆汁，脾脏也加入了造血的行列，胎毛布满了全身。",
        mom_changes="早孕不适完全消退；面部易长妊娠黄褐斑，日晒后加重；乳房持续增大乳晕加深。",
        weekly_tips="严格物理防晒，氧化锌防晒霜孕期最安全；避免正午强光暴晒。",
        diet_advice="维C果蔬搭配红肉，促进铁吸收；少食腌菜等高盐食物。",
        exercise_advice="水中健身、固定单车减轻关节压力；每次20-30分钟。",
        warning_signs=f"{TIP_WARNING_COMMON} 皮肤莫名瘀斑、牙龈大量出血排查血小板。{TIP_WARNING_EMERGENCY}",
    )

    w15 = WeekData(15,
        size="梨大小", size_cm="~11.6cm", weight="~150g",
        milestone="宝宝建立了固定的睡眠和活动周期，关节成型、骨骼变硬。味蕾已经发育到能分辨羊水的味道了，头发的模样也定了型。",
        mom_changes="妊娠线加深；经产妇可能感知初次胎动（气泡/蝴蝶扇动），初产妇普遍18-20周感知属正常。",
        weekly_tips="开始主动留意胎动规律，不必焦虑初次胎动早晚。",
        diet_advice=f"{TIP_LOW_SALT}；每日饮水2000-2500ml，冬瓜红豆缓解水肿。",
        exercise_advice=f"{TIP_KEGEL}；禁止长时间仰卧运动。",
        warning_signs=f"{TIP_WARNING_COMMON} 15周无胎动但B超正常无需紧张，个体差异极大。{TIP_WARNING_EMERGENCY}",
    )

    w16 = WeekData(16,
        size="彩甜椒大小", size_cm="~13.0cm", weight="~200g",
        milestone="宝宝的听觉结构成熟了，能听到妈妈的心跳和血液流动的声音。TA还学会了吮吸大拇指，B超已经可以分辨性别了哦。",
        mom_changes="腹部稳步隆起；食欲大幅恢复；血容量增加50%，易出汗燥热。",
        weekly_tips="16-20周完成中期血清唐氏筛查，与早期NT/NIPT联合评估风险。",
        diet_advice=f"{TIP_CALCIUM_VD}；控制每周增重≤0.5kg；全谷物替代精制米面。",
        exercise_advice="每日30分钟瑜伽、快走；运动全程侧卧位/坐姿休息。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY}",
    )

    w17 = WeekData(17,
        size="小芒果大小", size_cm="~14.2cm", weight="~250g",
        milestone="宝宝开始囤积皮下脂肪——这是出生后保暖的关键准备！脐带变得更粗更坚韧，TA还能对巨大的声响做出反应了。",
        mom_changes="宫底位于肚脐耻骨中间；BMI正常人群每周增重0.4-0.5kg；孕期鼻炎鼻塞高发，饥饿感频繁。",
        weekly_tips="管控全孕期增重：标准BMI 11.5-16kg，偏瘦12.5-18kg，超重7-11.5kg。",
        diet_advice="减少精制糖、甜点；燕麦、糙米增强饱腹感，控制体重增速。",
        exercise_advice="孕妇普拉提、水中操，单次30-40分钟中等强度。",
        warning_signs=f"{TIP_WARNING_COMMON} 每次产检监测血压，子痫前期风险自20周后上升。{TIP_WARNING_EMERGENCY}",
    )

    w18 = WeekData(18,
        size="西柚大小", size_cm="~15.3cm", weight="~300g",
        milestone="宝宝形成了稳定的作息时间，神经纤维正在加速包裹，让信号传递越来越快。肺泡开始合成活性物质，触觉也全面发育了。",
        mom_changes="胎动清晰可感；子宫压迫坐骨神经，臀部腿部刺痛；重心前移引发腰背酸痛。",
        weekly_tips="伴侣协同胎教，说话、轻揉腹部，胎儿可清晰接收外界声波。",
        diet_advice="瘦肉、坚果补锌；每日日晒15分钟促维D，辅助钙吸收。",
        exercise_advice="运动避免过度拉伸，松弛素软化关节易扭伤；温和瑜伽、散步最佳。",
        warning_signs=f"{TIP_WARNING_COMMON} 规律宫缩、持续腰坠警惕晚期流产。{TIP_WARNING_EMERGENCY}",
    )

    w19 = WeekData(19,
        size="香蕉大小", size_cm="~25.7cm", weight="~340g",
        milestone="宝宝全身覆盖着一层白白的胎脂，保护娇嫩的皮肤不被羊水浸蚀。大脑分区成型，五感同步发育，皮肤薄得能透过它看到血管。",
        mom_changes="宫底平齐肚脐；腹部皮肤拉伸发痒；夜间小腿抽筋高发；圆韧带牵拉单侧下腹隐痛。",
        weekly_tips="润肤油按摩缓解肚皮干痒；抽筋时伸直腿部勾脚尖快速缓解。",
        diet_advice="香蕉、深绿蔬菜补镁，搭配钙消除抽筋；足量饮水避免脱水诱发痉挛。",
        exercise_advice="睡前小腿拉伸、轻柔按摩；变换姿势缓解韧带牵拉痛。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 全身瘙痒、手掌脚掌夜间剧痒无皮疹，排查妊娠期肝内胆汁淤积症ICP，查胆汁酸+肝功能。",
    )

    w20 = WeekData(20,
        size="胡萝卜大小", size_cm="~26.7cm", weight="~360g",
        milestone="孕期已经走过一半啦！宝宝现在能感知明暗光线了，用手电筒照肚皮TA可能会转头回应哦。肠道里开始蓄积胎粪，胎动也越来越有规律了。",
        mom_changes="宫底平齐肚脐，孕肚明显；无痛不规律假性宫缩出现；体重增速加快。",
        weekly_tips="20-26周完成系统大排畸超声（四维），全身脏器结构筛查，不可错过窗口期。",
        diet_advice=f"{TIP_IRON_VC}；孕中期每日推荐铁25mg，红肉、动物血为最优来源。",
        exercise_advice="每日30分钟运动；假宫缩立刻停下侧卧休息。",
        warning_signs=f"{TIP_WARNING_COMMON} 区分真假宫缩：假宫缩无规律、休息缓解；真宫缩渐进增强、间隔缩短。{TIP_WARNING_EMERGENCY}",
    )

    w21 = WeekData(21,
        size="小木瓜大小", size_cm="~27.4cm", weight="~400g",
        milestone="宝宝每天会吞咽200-500毫升羊水，既练习了吞咽能力，也为消化系统提供营养。骨髓接替肝脏承担起造血任务，胎动也越来越协调有力了。",
        mom_changes="胎动频繁有力；每周增重0.4-0.5kg；子宫上抬挤压横膈，轻微活动易气短。",
        weekly_tips=f"{TIP_COUNT_FETAL_MOVE}；固定时间每日计数胎动。",
        diet_advice="每日额外增加300kcal热量；持续补铁补钙，均衡三餐。",
        exercise_advice="游泳、侧卧位散步；禁止平躺运动，运动前后足量补水。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 2小时胎动不足10次立刻胎心监护。",
    )

    w22 = WeekData(22,
        size="茄子大小", size_cm="~29.0cm", weight="~470g",
        milestone="宝宝的五官接近足月新生儿的样子了，睫毛和眉毛都长了出来。大脑神经元快速建立连接，触觉灵敏到能触碰自己的小脸。",
        mom_changes="子宫压迫膀胱尿频复发；日间脚踝生理性水肿，晨起消退；阴道分泌物增多。",
        weekly_tips="区分生理性水肿与病理性水肿：抬高下肢可缓解多为正常；面部手部持续水肿为高危信号。",
        diet_advice=f"{TIP_LOW_SALT}；每日蛋白70-80g，充足蛋白维持血浆渗透压减轻水肿。",
        exercise_advice="每小时起身活动5分钟，避免久站久坐；睡前抬高双脚15分钟。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 水肿蔓延面部手部+头痛视力模糊，高度怀疑子痫前期急诊。",
    )

    w23 = WeekData(23,
        size="玉米棒大小", size_cm="~30.6cm", weight="~540g",
        milestone="内耳平衡器官发育完善，胰腺开始分泌胰岛素调节血糖。皮肤还有些皱褶，皮下脂肪还在慢慢积累。到了23周，宝宝就有了生机，这是孕期的一个重要里程碑。",
        mom_changes="胎儿规律性打嗝（腹部节律跳动数分钟）；重心偏移腰背酸痛加重。",
        weekly_tips="站姿收腹挺胸，座椅腰后放置靠枕；鞋跟≤3cm平底低跟鞋减少腰椎压力。",
        diet_advice=f"{TIP_CALCIUM_VD}；每日温和日晒补钙吸收。",
        exercise_advice="猫牛式骨盆倾斜瑜伽，有效缓解腰背酸痛。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 23周早产存活率偏低，出现早产征兆立即就医保胎促胎肺成熟。",
    )

    w24 = WeekData(24,
        size="笋瓜大小", size_cm="~32.0cm", weight="~630g",
        milestone="肺部大量合成表面活性物质，为出生后呼吸做准备。宝宝能完整分辨酸甜苦辣了，对妈妈的声音反应也最灵敏。",
        mom_changes="宫底脐上3-5cm；胸廓受压肋骨胀痛；全身皮肤瘙痒概率上升。",
        weekly_tips="24-28周完成75g葡萄糖OGTT糖耐筛查；有肥胖、多囊、糖尿病家族史高危人群提前至20周筛查。",
        diet_advice=f"{TIP_GDM_DIET}；全谷物、杂豆替代精制碳水，预防妊娠期糖尿病。",
        exercise_advice="餐后散步20分钟平稳餐后血糖；游泳、瑜伽安全低冲击。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 每10分钟一次规律宫缩、破水为早产急症。",
    )

    w25 = WeekData(25,
        size="花椰菜大小", size_cm="~34.0cm", weight="~750g",
        milestone="肺部血管快速增殖，嗅觉成熟到能感知羊水的气味。抓握反射已经很完善了，宝宝会抓着脐带玩耍呢。",
        mom_changes="胎动幅度大，腹部可见凸起；子宫挤压胃部胃酸反流烧心高发。",
        weekly_tips="缓解烧心：少食多餐，餐后直立30分钟；辛辣、甜食、油炸全部减少。严重遵医嘱使用孕期安全抑酸药。",
        diet_advice="每餐七分饱，睡前2小时禁止进食；多膳食纤维防便秘。",
        exercise_advice="避免餐后立刻平躺、腹部受压动作；短时间慢走助消化。",
        warning_signs=f"{TIP_WARNING_COMMON} 烧心伴随左臂下颌放射痛排除心脏问题，单纯胸骨灼烧为胃酸反流。{TIP_WARNING_EMERGENCY}",
    )

    w26 = WeekData(26,
        size="生菜大小", size_cm="~35.5cm", weight="~900g",
        milestone="宝宝的眼睑完全睁开了，视网膜发育完成——用手电筒照肚子，TA会主动转头躲避光线呢。大脑沟回快速增殖，短期记忆也开始形成。",
        mom_changes="标准BMI孕妇增重7-9kg；夜间频繁起夜、找不到睡姿导致失眠；身体负荷增大易疲惫。",
        weekly_tips=f"{TIP_LEFT_SLEEP}；孕妇枕垫腹、膝间提升睡眠质量。",
        diet_advice="每日饮水2000ml，高纤维蔬果预防便秘；均衡营养控制增重速度。",
        exercise_advice="白天轻度活动改善夜间睡眠；睡前仅轻柔拉伸，禁止剧烈运动。",
        warning_signs=f"{TIP_WARNING_COMMON} 持续失眠、低落焦虑、心慌需筛查围产期抑郁，主动咨询产科心理门诊。{TIP_WARNING_EMERGENCY}",
    )

    w27 = WeekData(27,
        size="西兰花大小", size_cm="~37.0cm", weight="~1000g",
        milestone="大脑皮层高速发育，宝宝有了固定的20-40分钟睡眠循环。TA从妈妈体内获取基础免疫抗体，为出生后的健康打下基础。孕中期结束啦。",
        mom_changes="呼吸不畅平躺加重；盆腔血管受压，痔疮、下肢静脉曲张高发；精力明显下滑。",
        weekly_tips="预防痔疮：不久坐久蹲，高纤维饮食；温水坐浴10分钟每日1-2次消肿止痛。",
        diet_advice="高纤维果蔬、全谷物、豆类；禁食辛辣刺激加重肛周充血。",
        exercise_advice=f"{TIP_KEGEL}；每小时起身活动促进盆腔血液循环。",
        warning_signs=f"{TIP_WARNING_COMMON} 痔疮大量出血、剧痛咨询产科开具孕期专用药膏，禁止自行购药。{TIP_WARNING_EMERGENCY}",
    )

    w28 = WeekData(28,
        size="菠萝大小", size_cm="~38.5cm", weight="~1100g",
        milestone="宝宝的眼睛能自主开合了，还能区分白天和黑夜。TA出现了REM梦境睡眠——说不定正在做梦呢！神经系统持续成熟，正式进入孕晚期啦。",
        mom_changes="产检频率改为每2周一次；假性宫缩频发；烧心、腰背痛、尿频全部加重。",
        weekly_tips="备齐待产包，确认分娩医院路线；坚持左侧卧+每日胎动计数；学习分娩基础流程。",
        diet_advice="每日蛋白80g；足量红肉补铁；奶制品保证每日1000mg钙摄入。",
        exercise_advice="每日20-30分钟慢走；坚持盆底肌训练；禁止久站弯腰负重。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 见红、破水、10分钟一次规律宫缩立刻入院；28周后早产儿存活率超90%。",
    )

    # ===================== 孕晚期 (29-40周) 胎儿成熟待产 =====================
    w29 = WeekData(29,
        size="大菠萝大小", size_cm="~40.0cm", weight="~1300g",
        milestone="皮下脂肪快速囤积，皮肤褶皱在逐步抚平。全身骨骼在硬化，但头骨之间还保留着柔软的缝隙，为通过产道做准备。胎位也在逐步转为头朝下。",
        mom_changes="每周增重约0.5kg；胸廓受压呼吸短促，烧心加重；假性宫缩频繁模拟分娩。",
        weekly_tips="妊娠期高血压、糖尿病人群增加胎心监护NST频次，遵医嘱定期复查B超评估胎儿生长。",
        diet_advice="每周2-3次低汞深海鱼补充DHA（每日200-300mg）；控制精制糖，均衡脂肪蛋白。",
        exercise_advice="短时间散步、分娩呼吸训练；左侧卧位休息保障胎盘供血。",
        warning_signs=f"{TIP_WARNING_COMMON} 胎动较日常减半立刻监护。{TIP_WARNING_EMERGENCY}",
    )

    w30 = WeekData(30,
        size="椰子大小", size_cm="~41.5cm", weight="~1500g",
        milestone="宝宝能清晰分辨明暗了，骨髓完全接替了造血任务，肺部持续成熟。TA还在储存铁和钙等矿物质，这些储备够出生后前半年使用呢。",
        mom_changes="坐骨神经痛、骨盆压迫感明显；身体负重顶峰，失眠、乏力常态化。",
        weekly_tips="报名产前课程：拉玛泽呼吸、母乳喂养、新生儿基础护理；熟悉无痛分娩、顺产剖宫产区别。",
        diet_advice="Omega3藻油/深海鱼促进脑发育；足量膳食纤维+饮水预防便秘。",
        exercise_advice="温和散步；骨盆疼痛立刻减少活动告知产检医生。",
        warning_signs=f"{TIP_WARNING_COMMON} 30周出现规律宫缩，医生会使用激素促胎肺成熟保胎。{TIP_WARNING_EMERGENCY}",
    )

    w31 = WeekData(31,
        size="哈密瓜大小", size_cm="~43.0cm", weight="~1700g",
        milestone="五感全部成熟，大脑里神经连接多达数十亿条。肺部已经能完成基础气体交换了，大量妈妈的抗体正在传递给宝宝，为TA建立被动免疫保护。",
        mom_changes="乳房分泌淡黄色初乳易渗漏；子宫顶至肋骨下缘，平躺呼吸困难加剧。",
        weekly_tips="防溢乳垫吸收初乳，禁止挤压乳房；并发症人群每周1-2次胎心监护。",
        diet_advice="绿叶菜、西兰花补充维K，保障分娩正常凝血功能；持续补铁补钙。",
        exercise_advice="熟练练习分娩呼吸法；全程侧卧/半卧，杜绝平躺。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 规律腹痛伴腰酸下坠、流水为早产信号。",
    )

    w32 = WeekData(32,
        size="大芒果大小", size_cm="~44.5cm", weight="~1800g",
        milestone="骨骼完全成型，脂肪持续增厚。大多数宝宝已经自然转成头位了，指甲和头发还在持续生长，免疫记忆也在建立中。",
        mom_changes="胎头轻微下降，呼吸稍顺畅但骨盆压迫尿频加重；脚踝水肿常态化，假宫缩变多。",
        weekly_tips="32-34周第三次生长B超，评估胎位、胎盘成熟度、羊水量、胎儿体重，制定分娩方案。",
        diet_advice="胎儿偏大则减少精制碳水、甜食；偏小适度增加优质蛋白与复合主食。",
        exercise_advice="慢走助入盆；34周后可在医生指导下会阴按摩减少撕裂。",
        warning_signs=f"{TIP_WARNING_COMMON} B超提示臀位/横位遵医嘱膝胸卧位，医院评估外倒转术。{TIP_WARNING_EMERGENCY}",
    )

    w33 = WeekData(33,
        size="小蜜瓜大小", size_cm="~46.0cm", weight="~2000g",
        milestone="大脑神经高速发育，头骨之间的囟门保持柔软——这样分娩时颅骨可以轻微重叠缩小头围哦。皮下脂肪持续填充，宝宝越来越饱满可爱了。",
        mom_changes="手脚肿胀加重；夜间频繁起夜睡眠差；无规律宫缩增多。",
        weekly_tips="每日抬高双脚缓解水肿；牢记子痫前期典型三联征：高血压+水肿+蛋白尿。",
        diet_advice=f"{TIP_IRON_VC}；为分娩失血储备足量铁元素。",
        exercise_advice="温和产前瑜伽、拉伸放松，疲惫立刻停止休息。",
        warning_signs=f"{TIP_WARNING_COMMON} {TIP_WARNING_EMERGENCY} 持续头痛、视物模糊、上腹剧痛、突发全身水肿为子痫前期急症。",
    )

    w34 = WeekData(34,
        size="小型南瓜大小", size_cm="~47.0cm", weight="~2300g",
        milestone="肺部基本成熟了，34周出生的宝宝存活率接近100%，一般不需要长期呼吸机支持。妈妈的抗体持续输入，宝宝的皮肤变得粉嫩光滑。",
        mom_changes="产检升级为每周1次；医生定期内检评估宫颈成熟度；体重增长接近峰值。",
        weekly_tips="待产包、入院手续、24小时急诊电话全部确认；熟记临产三大信号：规律宫缩、见红、破水。",
        diet_advice="均衡营养储备分娩、哺乳能量；维C果蔬促进铁吸收，足量优质蛋白。",
        exercise_advice="有人陪同慢走、温和爬楼梯促胎头入盆；每日练习拉玛泽呼吸。",
        warning_signs=f"{TIP_WARNING_COMMON} B超提示前置胎盘禁止同房、阴道内检，择期剖宫产。{TIP_WARNING_EMERGENCY}",
    )

    w35 = WeekData(35,
        size="标准南瓜大小", size_cm="~48.0cm", weight="~2600g",
        milestone="脏器发育基本完成，接下来的几周主要是增重和完善肺部功能。肾脏完全成熟，肝脏能代谢废物了，绝大多数宝宝都已固定为头位。",
        mom_changes="子宫紧贴肋骨底部；宫腔空间缩小，胎动以扭动、推挤为主；全天尿频达顶峰。",
        weekly_tips="35-37周完成GBS B族链球菌筛查；阳性分娩全程静脉抗生素，预防新生儿肺炎脑膜炎；最佳采样36-37周。",
        diet_advice="复合碳水薯类、杂粮储备分娩能量；持续补钙补铁，每日足量饮水。",
        exercise_advice="骨盆摇动缓解骨盆酸胀，辅助入盆；疲劳立刻休息。",
        warning_signs=f"{TIP_WARNING_COMMON} 区分破水与漏尿：破水持续无法自控流出、液体含白色胎脂絮状物，怀疑破水立刻就医不等待。{TIP_WARNING_EMERGENCY}",
    )

    w36 = WeekData(36,
        size="大哈密瓜大小", size_cm="~49.0cm", weight="~2800g",
        milestone="肺部完全成熟，宝宝可以自主呼吸了！脸颊上长出了饱满的吸吮脂肪垫——这可是出生后有效吮吸母乳的秘密武器哦。胎毛大量脱落，消化系统也准备好迎接母乳了。",
        mom_changes="每周一次产检；胎头入盆，呼吸通畅但走路骨盆坠痛呈鸭步；随时可能临产。",
        weekly_tips="全部待产物资到位；区分真假临产：真宫缩间隔5-10分钟、持续增强、休息不缓解，伴随见红/破水。",
        diet_advice="清淡易消化轻食；提前备巧克力、蜂蜜水、能量棒，分娩快速补能。",
        exercise_advice="慢走、轻柔拉伸；会阴按摩可持续；避免过度消耗体力。",
        warning_signs=f"{TIP_WARNING_COMMON} 出现任意临产信号直接入院；36周后一般不再保胎。{TIP_WARNING_EMERGENCY}",
    )

    w37 = WeekData(37,
        size="小西瓜大小", size_cm="~50.0cm", weight="~3000g",
        milestone="宝宝正式足月啦！所有器官都已成熟，TA在练习模拟呼吸运动，为人生第一次真正的吸气和啼哭做准备。",
        mom_changes="随时发动分娩；宫颈黏液栓排出即见红，粉色褐色黏稠分泌物，提示宫颈软化扩张。",
        weekly_tips="见红后多数24-72小时发动宫缩，少数持续一周；无需频繁往返医院，重点监测宫缩强度频率。",
        diet_advice="清淡三餐，少油腻难消化食物；持续补水，备分娩能量零食。",
        exercise_advice="短时间散步促自然发动；保存体力，多深呼吸放松。",
        warning_signs=f"{TIP_WARNING_COMMON} 每5-10分钟一次持续宫缩、破水、出血量超月经量立刻急诊入院。{TIP_WARNING_EMERGENCY}",
    )

    w38 = WeekData(38,
        size="中等西瓜大小", size_cm="~50.5cm", weight="~3200g",
        milestone="宝宝每天增重约14-28克，胎脂只残留在皮肤褶皱处了。肠道里的胎粪完整储存着等待出生后排出，肺部完成了最终的成熟准备。",
        mom_changes="期待与焦虑情绪交织；假性宫缩强度、频次大幅提升；睡眠质量孕期最差，起夜频繁+临产焦虑。",
        weekly_tips="放松心态，仅5%宝宝精准在预产期当天分娩，前后一周均正常。",
        diet_advice="正常均衡饮食，无需刻意增减；红枣水、淡蜂蜜水快速补充体力。",
        exercise_advice="以静养休息为主，保留分娩体力；轻柔深呼吸舒缓焦虑。",
        warning_signs=f"{TIP_WARNING_COMMON} 临产前胎动不可明显减少，胎动减半立刻监护。{TIP_WARNING_EMERGENCY}",
    )

    w39 = WeekData(39,
        size="完整西瓜大小", size_cm="~51.0cm", weight="~3350g",
        milestone="宝宝完全发育成熟了！肺部可以独立换气，从妈妈那里获得的抗体能保护TA抵御常见感染长达6个月。TA随时准备与你见面啦。",
        mom_changes="随时临产；前列腺素刺激肠道，腹泻、恶心为分娩前正常排空反应；宫颈逐步软化扩张。",
        weekly_tips="超过预产期未发动，提前了解引产指征；临床普遍41周启动引产预防胎盘老化。",
        diet_advice="少食多餐清淡流食；硬膜外麻醉术前避免大量进食。",
        exercise_advice="短时散步刺激宫缩；减少消耗，多放松呼吸。",
        warning_signs=f"{TIP_WARNING_COMMON} 5分钟一次规律宫缩、破水、强烈便意（胎头压迫直肠）为标准临产信号。{TIP_WARNING_EMERGENCY}",
    )

    w40 = WeekData(40,
        size="完整西瓜大小", size_cm="~51.5cm", weight="3400~3600g",
        milestone="宝宝已经准备好来到这个世界了！全身发育完善，头骨骨板可以巧妙重叠以适应产道——出生后头型可能会暂时有点变形，几周内就会自然恢复。很快就能抱到TA了！",
        mom_changes="预产期当日；仅少数宝宝准时分娩；未发动需每2-3天复查胎心监护+B超评估羊水、胎盘功能。",
        weekly_tips="41周常规安排引产，降低胎盘老化、羊水过少、胎儿宫内缺氧风险；产后42天预约复查。",
        diet_advice="清淡易消化、充足补水；分娩前禁止大量高脂主食。",
        exercise_advice="全程静养保存体力；每日坚持分娩放松呼吸练习。",
        warning_signs=f"{TIP_WARNING_COMMON} 规律宫缩、破水、大量出血、胎动骤减立刻入院；产后42天复查盆底、子宫、血常规。{TIP_WARNING_EMERGENCY}",
    )

    return [
        w1, w2, w3, w4, w5, w6, w7, w8, w9, w10,
        w11, w12, w13, w14, w15, w16, w17, w18, w19, w20,
        w21, w22, w23, w24, w25, w26, w27, w28, w29, w30,
        w31, w32, w33, w34, w35, w36, w37, w38, w39, w40,
    ]


_WEEKS = _build_weeks()


def get_week_data(week: Union[int, float]) -> WeekData:
    """根据孕周返回对应的 WeekData。
    健壮性处理：
    1. 非数字自动兜底第1周
    2. week < 1 钳位第1周
    3. week > 40 钳位第40周
    """
    try:
        week_int = int(float(week))
    except (ValueError, TypeError):
        week_int = 1

    idx = max(0, min(week_int - 1, 39))
    return _WEEKS[idx]


# 示例调用
if __name__ == "__main__":
    data = get_week_data(20)
    print("宝宝发育信息：", data.as_baby_info())
    print("母体变化：", data.as_mom_changes())
    print("孕期建议：", data.as_recommendations())