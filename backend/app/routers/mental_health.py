"""心理健康筛查 API - EPDS爱丁堡产后抑郁量表"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..database import SessionLocal
from ..models import MentalHealthScreening, Alert

router = APIRouter(prefix="/api/v1/mental-health", tags=["心理健康筛查"])

# EPDS 10题标准内容（中文版）
EPDS_QUESTIONS = [
    {"id": 1, "text": "我能看到事物有趣的一面，并笑得开心", "options": ["同以前一样", "没有以前那么多", "肯定比以前少", "完全不能"]},
    {"id": 2, "text": "我欣然期待未来的一切", "options": ["同以前一样", "没有以前那么多", "肯定比以前少", "几乎没有"]},
    {"id": 3, "text": "当事情出错时，我会不必要地责备自己", "options": ["没有这样", "不经常这样", "有时会这样", "大部分时间会"]},
    {"id": 4, "text": "我无缘无故感到焦虑和担心", "options": ["一点也没有", "偶尔这样", "时常这样", "经常这样"]},
    {"id": 5, "text": "我无缘无故感到害怕和惊慌", "options": ["一点也没有", "不太多", "有时这样", "相当多"]},
    {"id": 6, "text": "很多东西令我感到压力", "options": ["没有这样", "不经常这样", "有时会这样", "大部分时间会"]},
    {"id": 7, "text": "我很不开心，以至于很难入睡", "options": ["没有这样", "不经常这样", "有时会这样", "大部分时间会"]},
    {"id": 8, "text": "我感到难过和悲伤", "options": ["没有这样", "不经常这样", "有时会这样", "大部分时间会"]},
    {"id": 9, "text": "我感到不开心到要哭", "options": ["没有这样", "不经常这样", "有时会这样", "大部分时间会"]},
    {"id": 10, "text": "我有伤害自己的想法", "options": ["完全没有", "偶尔这样", "有时这样", "相当多"]},
]

# EPDS评分：第1、2题正向计分(0-3)，其余反向计分(3-0)
# 实际临床中第1、2题：0=同以前一样, 1=没有以前那么多, 2=肯定比以前少, 3=完全不能
# 其余题：0=没有这样, 1=不经常这样, 2=有时会这样, 3=大部分时间会


class EPDSSubmitRequest(BaseModel):
    pregnant_id: str
    answers: dict[int, int]  # {题目ID: 选择的选项索引(0-3)}


class EPDSResult(BaseModel):
    id: str
    total_score: int
    risk_level: str
    risk_description: str
    recommendations: list[str]


@router.get("/epds/questions")
async def get_epds_questions():
    """获取EPDS量表题目"""
    return {"questions": EPDS_QUESTIONS, "total": len(EPDS_QUESTIONS)}


@router.post("/epds/submit", response_model=EPDSResult)
async def submit_epds(req: EPDSSubmitRequest):
    """提交EPDS量表答案并计算评分"""
    # 计算总分
    total_score = 0
    for q_id, answer_idx in req.answers.items():
        if q_id in (1, 2):
            # 正向计分
            total_score += answer_idx
        else:
            # 反向计分
            total_score += (3 - answer_idx)

    # 确定风险等级
    if total_score <= 9:
        risk_level = "low"
        risk_desc = "正常范围，心理健康状况良好"
        recommendations = ["保持良好的生活习惯", "继续定期产检"]
    elif total_score <= 12:
        risk_level = "moderate"
        risk_desc = "轻度抑郁倾向，建议关注"
        recommendations = [
            "建议与家人多沟通，寻求支持",
            "适当增加户外活动和运动",
            "如症状持续2周以上，建议咨询心理医生",
        ]
    elif total_score <= 15:
        risk_level = "high"
        risk_desc = "中度抑郁风险，建议专业评估"
        recommendations = [
            "强烈建议咨询专业心理医生",
            "告知家人您的感受，获得支持",
            "保持规律作息，避免独处",
        ]
    else:
        risk_level = "severe"
        risk_desc = "重度抑郁风险，需要立即关注"
        recommendations = [
            "请立即联系心理医生或前往医院",
            "拨打心理援助热线：400-161-9995",
            "不要独处，确保身边有人陪伴",
        ]

    # 存储筛查结果
    db = SessionLocal()
    try:
        screening = MentalHealthScreening(
            pregnant_id=req.pregnant_id,
            screening_type="EPDS",
            answers=req.answers,
            total_score=total_score,
            risk_level=risk_level,
        )
        db.add(screening)

        # 如果是高风险，自动创建告警
        if risk_level in ("high", "severe"):
            alert = Alert(
                pregnant_id=req.pregnant_id,
                trigger_source="EPDS_SCREENING",
                rule_id="EPDS_HIGH_RISK",
                domain="mental",
                level="RED" if risk_level == "severe" else "ORANGE",
                message=f"EPDS心理健康筛查结果：{risk_desc}（得分：{total_score}/30）",
                details={"score": total_score, "risk_level": risk_level},
                status="PENDING",
            )
            db.add(alert)

        db.commit()
        return EPDSResult(
            id=str(screening.id),
            total_score=total_score,
            risk_level=risk_level,
            risk_description=risk_desc,
            recommendations=recommendations,
        )
    finally:
        db.close()


@router.get("/epds/history/{pregnant_id}")
async def get_epds_history(pregnant_id: str):
    """获取EPDS筛查历史"""
    db = SessionLocal()
    try:
        screenings = db.query(MentalHealthScreening).filter(
            MentalHealthScreening.pregnant_id == pregnant_id,
            MentalHealthScreening.screening_type == "EPDS",
        ).order_by(MentalHealthScreening.created_at.desc()).limit(10).all()

        return {
            "screenings": [
                {
                    "id": str(s.id),
                    "total_score": s.total_score,
                    "risk_level": s.risk_level,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in screenings
            ]
        }
    finally:
        db.close()
