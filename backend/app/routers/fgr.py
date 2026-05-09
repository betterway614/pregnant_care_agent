"""FGR评估 API"""
import random
import uuid as uuid_lib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import FgrAssessment, Pregnant, Alert
from ..schemas import FgrAssessRequest, FgrAssessResponse, FgrTrendPoint
from ..core import rule_engine

router = APIRouter(prefix="/api/v1/fgr", tags=["FGR评估"])


def _mock_fgr_assess(gestational_weeks: float) -> dict:
    """Mock FGR评估（开发阶段用）"""
    # 基于孕周的模拟：早期低风险，晚期可能有风险
    base_risk = min(0.8, max(0.05, (gestational_weeks - 20) / 50))

    # 加入随机波动
    risk_score = base_risk + random.uniform(-0.15, 0.15)
    risk_score = max(0.01, min(0.95, risk_score))

    # 确定风险等级
    if risk_score >= 0.7:
        risk_level = "critical"
        risk_label = "极高风险"
    elif risk_score >= 0.5:
        risk_level = "high"
        risk_label = "高风险"
    elif risk_score >= 0.25:
        risk_level = "medium"
        risk_label = "中风险"
    else:
        risk_level = "low"
        risk_label = "低风险"

    ci_width = random.uniform(0.04, 0.08)
    return {
        "case_id": f"CASE_{uuid_lib.uuid4().hex[:8].upper()}",
        "risk_level": risk_level,
        "risk_label": risk_label,
        "confidence_interval": {
            "lowerBound": round(max(0, risk_score - ci_width), 2),
            "upperBound": round(min(0.99, risk_score + ci_width), 2),
        },
        "explanation": {
            "critical": "基于多项生长指标严重滞后及血流阻力指数显著升高",
            "high": "基于腹围增长滞后及血流阻力指数升高",
            "medium": "部分生长指标偏低，需要持续监测",
            "low": "各项生长指标在正常范围内",
        }.get(risk_level, "评估完成，各项指标正常"),
        "processing_time": random.randint(2500, 4500),
    }


@router.post("/assess", response_model=FgrAssessResponse)
async def assess_fgr(req: FgrAssessRequest, db: Session = Depends(get_db)):
    """FGR风险评估"""
    # Mock评估
    result = _mock_fgr_assess(req.gestational_weeks)

    # 存入数据库
    assessment = FgrAssessment(
        pregnant_id=req.pregnant_id,
        case_id=result["case_id"],
        image_type=req.image_type,
        gestational_weeks=req.gestational_weeks,
        risk_level=result["risk_level"],
        confidence_lower=result["confidence_interval"]["lowerBound"],
        confidence_upper=result["confidence_interval"]["upperBound"],
        explanation=result["explanation"],
        processing_time_ms=result["processing_time"],
    )
    db.add(assessment)

    # 规则引擎评估
    rule_hits = rule_engine.evaluate_fgr_risk(result["risk_level"])
    for hit in rule_hits:
        alert = Alert(
            pregnant_id=req.pregnant_id,
            trigger_source="FGR_ALGORITHM",
            rule_id=hit["rule_id"],
            level=hit["level"],
            message=hit["message"],
            details={"case_id": result["case_id"], "risk_level": result["risk_level"]},
        )
        db.add(alert)

    db.commit()

    return FgrAssessResponse(
        case_id=result["case_id"],
        risk_level=result["risk_level"],
        risk_label=result["risk_label"],
        confidence_interval=result["confidence_interval"],
        explanation=result["explanation"],
        processing_time=result["processing_time"],
        hardware="NPU",
    )


@router.get("/trend/{pregnant_id}", response_model=list[FgrTrendPoint])
def get_fgr_trend(pregnant_id: str, db: Session = Depends(get_db)):
    """获取FGR趋势数据"""
    assessments = db.query(FgrAssessment).filter(
        FgrAssessment.pregnant_id == pregnant_id
    ).order_by(FgrAssessment.gestational_weeks).all()

    if not assessments:
        # 生成Mock趋势数据
        from datetime import timedelta
        base_date = datetime.now() - timedelta(days=56)
        mock_trend = []
        for i in range(6):
            gw = 24 + i * 2
            result = _mock_fgr_assess(gw)
            mock_trend.append(FgrTrendPoint(
                gestational_weeks=float(gw),
                risk_score={
                    "low": 0.1, "medium": 0.35,
                    "high": 0.6, "critical": 0.8,
                }.get(result["risk_level"], 0.1),
                confidence_lower=result["confidence_interval"]["lowerBound"],
                confidence_upper=result["confidence_interval"]["upperBound"],
                assessed_at=(base_date + timedelta(days=i * 14)).isoformat(),
            ))
        return mock_trend

    return [
        FgrTrendPoint(
            gestational_weeks=a.gestational_weeks,
            risk_score={"low": 0.1, "medium": 0.35, "high": 0.6, "critical": 0.8}.get(a.risk_level, 0.1),
            confidence_lower=a.confidence_lower or 0,
            confidence_upper=a.confidence_upper or 0,
            assessed_at=a.assessed_at.isoformat() if a.assessed_at else "",
        )
        for a in assessments
    ]
