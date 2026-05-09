"""AI 个性化推荐 API"""
import json
from fastapi import APIRouter, HTTPException
from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, ScheduleNode, Alert
from ..schemas import RecommendResponse
from ..core import get_llm_client

router = APIRouter(prefix="/api/v1/recommend", tags=["AI推荐"])


@router.get("/{pregnant_id}", response_model=RecommendResponse)
async def get_recommend(pregnant_id: str):
    """基于孕周+风险标签返回个性化推荐（LLM优先，模板兜底）"""
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7
        risk_tags = pregnant.risk_tags or []

        # 尝试调用LLM生成个性化推荐
        llm_result = await _try_llm_recommend(pregnant, gest_week, gest_day, risk_tags)

        if llm_result:
            return llm_result

        # 模板兜底
        return _fallback_recommend(pregnant, gest_week, gest_day, risk_tags)
    finally:
        db.close()


async def _try_llm_recommend(pregnant: Pregnant, gest_week: int, gest_day: int, risk_tags: list) -> RecommendResponse | None:
    """尝试通过LLM生成个性化推荐，失败返回None"""
    try:
        client = get_llm_client()
        prompt = _build_recommend_prompt(pregnant, gest_week, gest_day, risk_tags)
        messages = [
            {"role": "system", "content": "你是一位资深的产科医生和孕期营养专家，请为孕妇提供专业、个性化的孕期建议。请严格按JSON格式返回，不要包含markdown代码块标记。返回字段：weekly_tips, diet_advice, exercise_advice, warning_signs, baby_development"},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat(messages)
        if not response or not response.strip():
            return None

        # 尝试解析JSON
        data = _parse_llm_json(response)
        if not data:
            return None

        return RecommendResponse(
            pregnant_id=pregnant.pregnant_id,
            gestational_week=f"{gest_week}+{gest_day}",
            weekly_tips=data.get("weekly_tips", ""),
            diet_advice=data.get("diet_advice", ""),
            exercise_advice=data.get("exercise_advice", ""),
            warning_signs=data.get("warning_signs", ""),
            baby_development=data.get("baby_development", ""),
            source="AI_CARE"
        )
    except Exception:
        return None


def _build_recommend_prompt(pregnant: Pregnant, gest_week: int, gest_day: int, risk_tags: list) -> str:
    """构建推荐提示词"""
    risk_text = "、".join(risk_tags) if risk_tags else "无特殊风险"
    return f"""请为以下孕妇生成个性化孕期建议：

孕妇信息：
- 孕周：{gest_week}周+{gest_day}天
- 风险标签：{risk_text}
- 展示名称：{pregnant.display_name}

请根据孕周和风险标签，提供以下四个方面的具体建议：
1. weekly_tips: 本周核心注意事项（50-100字）
2. diet_advice: 饮食建议（50-100字）
3. exercise_advice: 运动建议（50-100字）
4. warning_signs: 需要警惕的危险信号（30-80字）
5. baby_development: 本周胎儿发育情况描述（30-60字）

请以JSON格式返回结果，键名使用英文（weekly_tips, diet_advice, exercise_advice, warning_signs, baby_development），值使用中文。"""


def _parse_llm_json(response: str) -> dict | None:
    """解析LLM返回的JSON，支持多种格式"""
    import re
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    # 尝试提取代码块中的JSON
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, KeyError):
            pass
    # 尝试提取花括号包裹的JSON
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _fallback_recommend(pregnant: Pregnant, gest_week: int, gest_day: int, risk_tags: list) -> RecommendResponse:
    """模板兜底推荐"""
    milestones = {
        8: "心脏开始跳动，四肢开始形成。宝宝约1.6cm，像覆盆子大小。",
        12: "手指脚趾已分离，面部特征明显。宝宝约5.4cm，像李子大小。",
        16: "能听到声音，开始有吮吸反射。宝宝约11.6cm，像牛油果大小。",
        20: "能感知光线，开始有规律的活动。宝宝约16.4cm，像香蕉大小。",
        24: "肺部开始发育，能辨别声音。宝宝约30cm，像玉米大小。",
        28: "眼睛睁开，大脑快速发育。宝宝约37.6cm，像茄子大小。",
        32: "骨骼完全形成，开始储存脂肪。宝宝约42.4cm，像南瓜大小。",
        36: "肺部已成熟，准备出生。宝宝约47.4cm，像生菜大小。",
        40: "已足月，随时准备出生。宝宝约51cm，像西瓜大小。",
    }
    closest = min(milestones.keys(), key=lambda x: abs(x - gest_week))
    baby_dev = milestones[closest]

    if gest_week <= 12:
        weekly_tips = "孕早期是胎儿器官发育关键期，请按时服用叶酸(0.4mg/天)，避免接触有害物质。"
        diet_advice = "少量多餐，选择易消化食物。增加富含叶酸的食物（深绿色蔬菜、豆类）。"
        exercise_advice = "适度散步即可，避免剧烈运动和长时间站立。每天15-20分钟。"
        warning_signs = "如出现阴道出血、剧烈腹痛，请立即就医。"
    elif gest_week <= 28:
        weekly_tips = "孕中期是胎儿快速生长期，注意补充钙和铁。可以开始进行胎教。"
        diet_advice = "增加优质蛋白（鱼、蛋、瘦肉），补充钙质（牛奶、豆制品），控制盐摄入。"
        exercise_advice = "每天散步30分钟，可做孕妇瑜伽。避免仰卧位运动。每天注意胎动。"
        warning_signs = "如出现规律宫缩、阴道流液、胎动明显减少，请立即就医。"
    else:
        weekly_tips = "孕晚期请准备好待产包，确认分娩医院和交通路线。保持左侧卧位休息。"
        diet_advice = "继续高蛋白饮食，控制碳水化合物，多吃含铁食物（红肉、动物肝脏）。"
        exercise_advice = "每天散步20-30分钟，做骨盆底肌锻炼。避免长时间站立和弯腰。"
        warning_signs = "如出现规律宫缩（每10分钟一次）、见红、破水，请立即前往医院。"

    if "FGR高危" in risk_tags:
        weekly_tips += " 您是FGR高危孕妇，请严格按医嘱进行B超监测，注意胎动变化。"
    if "GDM" in risk_tags:
        diet_advice += " 请严格控制糖分摄入，监测空腹及餐后血糖。"
    if "高血压" in risk_tags:
        warning_signs += " 每日监测血压，如收缩压≥140或舒张压≥90请立即就医。"

    return RecommendResponse(
        pregnant_id=pregnant.pregnant_id,
        gestational_week=f"{gest_week}+{gest_day}",
        weekly_tips=weekly_tips,
        diet_advice=diet_advice,
        exercise_advice=exercise_advice,
        warning_signs=warning_signs,
        baby_development=baby_dev,
        source="TEMPLATE"
    )
