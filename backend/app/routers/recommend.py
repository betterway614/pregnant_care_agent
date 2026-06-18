"""AI 个性化推荐 API

路由层仅负责：请求校验 + 权限控制 + 调度服务层
业务逻辑全部委托给 RecommendService (SRP)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Pregnant
from ..schemas import RecommendResponse
from ..core.auth import get_current_user, TokenPayload
from ..services.recommend_service import recommend_service

router = APIRouter(prefix="/api/v1/recommend", tags=["AI推荐"])


@router.get("/{pregnant_id}", response_model=RecommendResponse)
async def get_recommend(
    pregnant_id: str,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    """基于孕周+风险标签返回个性化推荐（LLM优先，模板兜底）"""
    # 权限校验
    if user.role == "pregnant" and user.pregnant_id != pregnant_id:
        raise HTTPException(status_code=403, detail="无权访问该孕妇数据")

    # 查询孕妇
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    from ..services.patient_context_service import compute_gestational_days

    gest_days = compute_gestational_days(pregnant)
    gest_week = gest_days // 7
    gest_day = gest_days % 7
    risk_tags = pregnant.risk_tags or []

    # 委托服务层处理所有业务逻辑
    return await recommend_service.get_recommendation(
        db, pregnant, gest_week, gest_day, risk_tags
    )
