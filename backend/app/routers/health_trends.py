"""健康趋势 + 随访历史 API"""
from datetime import datetime, date, timedelta
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, FollowUpRecord
from ..core.trend_engine import TrendEngine
from ..schemas.schemas import (
    HealthTrendResponse, TrendSeries, TrendDataPoint,
    FollowUpHistoryResponse, FollowUpHistoryRecord,
)

router = APIRouter(prefix="/api/v1/pregnant", tags=["健康趋势"])

# 指标元数据: metric_code -> (中文名, 单位, normal_range)
METRIC_META = {
    "weight": ("体重", "kg", {"min": 40, "max": 120}),
    "systolic": ("收缩压", "mmHg", {"min": 90, "max": 140}),
    "diastolic": ("舒张压", "mmHg", {"min": 60, "max": 90}),
    "blood_sugar_fasting": ("空腹血糖", "mmol/L", {"min": 3.5, "max": 5.1}),
    "blood_sugar_postprandial": ("餐后血糖", "mmol/L", {"min": 3.5, "max": 8.5}),
    "fetal_movement": ("胎动", "次/小时", {"min": 3, "max": 10}),
    "heart_rate": ("心率", "bpm", {"min": 60, "max": 100}),
    "sleep_hours": ("睡眠", "小时", {"min": 6, "max": 10}),
    "steps": ("步数", "步", {"min": 2000, "max": 15000}),
    "emotion_score": ("情绪", "分", {"min": 1, "max": 3}),
}


@router.get("/{pregnant_id}/health-trends", response_model=HealthTrendResponse)
def get_health_trends(
    pregnant_id: str,
    metrics: str = Query(..., description="指标列表，逗号分隔"),
    start_date: str | None = Query(None, description="起始日期 ISO"),
    end_date: str | None = Query(None, description="结束日期 ISO"),
    axis_mode: str = Query("date", description="date 或 gestational_week"),
    granularity: str = Query("daily", description="daily 或 weekly"),
):
    """获取健康数据时间趋势"""
    db: Session = SessionLocal()
    try:
        # 验证孕妇存在
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        # 计算当前孕周
        gest_days = pregnant.gestational_age_days or 0
        gest_week = gest_days // 7
        gest_day = gest_days % 7

        # 解析日期范围
        today = date.today()
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
            end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
        except ValueError:
            raise HTTPException(400, "日期格式错误，请使用 YYYY-MM-DD")

        # 解析指标列表
        metric_codes = [m.strip() for m in metrics.split(",") if m.strip()]
        valid_codes = [m for m in metric_codes if m in METRIC_META]
        if not valid_codes:
            raise HTTPException(400, f"无有效指标，可选: {', '.join(METRIC_META.keys())}")

        # LMP 日期（用于计算数据点对应孕周）
        lmp = pregnant.lmp_date

        series_list = []

        for metric_code in valid_codes:
            name, unit, normal_range = METRIC_META[metric_code]

            # 查询数据点
            points = (
                db.query(HealthDataPoint)
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code == metric_code,
                    func.date(HealthDataPoint.recorded_at) >= start,
                    func.date(HealthDataPoint.recorded_at) <= end,
                )
                .order_by(HealthDataPoint.recorded_at.asc())
                .all()
            )

            # 构建时序数据
            data = []
            for p in points:
                rec_date = p.recorded_at.date() if p.recorded_at else start
                gw = 0
                if lmp:
                    gw = (rec_date - lmp).days // 7
                data.append(TrendDataPoint(
                    date=rec_date.isoformat(),
                    gest_week=gw,
                    value=p.value,
                ))

            # 趋势分析
            trend_result = None
            if len(data) >= 2:
                records_for_trend = [
                    {"metric": metric_code, "value": d.value, "unit": unit, "recorded_at": d.date}
                    for d in data
                ]
                trend_engine = TrendEngine()
                results = trend_engine.analyze(records_for_trend, gest_week)
                if results:
                    trend_result = results[0]

            series_list.append(TrendSeries(
                metric=metric_code,
                name=name,
                unit=unit,
                normal_range=normal_range,
                data=data,
                trend=trend_result.trend if trend_result else "insufficient_data",
                latest_value=data[-1].value if data else None,
                is_normal=trend_result.is_normal if trend_result else None,
            ))

        return HealthTrendResponse(
            pregnant_id=pregnant_id,
            gestational_week=f"{gest_week}+{gest_day}",
            axis_mode=axis_mode,
            series=series_list,
        )
    finally:
        db.close()


@router.get("/{pregnant_id}/follow-up-history", response_model=FollowUpHistoryResponse)
def get_follow_up_history(
    pregnant_id: str,
    status: str | None = Query(None, description="筛选状态"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取随访历史记录"""
    db: Session = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        query = db.query(FollowUpRecord).filter(FollowUpRecord.pregnant_id == pregnant_id)
        if status:
            query = query.filter(FollowUpRecord.status == status)

        records = query.order_by(FollowUpRecord.follow_up_date.desc()).limit(limit).all()

        result = []
        for r in records:
            result.append(FollowUpHistoryRecord(
                id=str(r.id),
                follow_up_date=r.follow_up_date.isoformat() if r.follow_up_date else None,
                gestational_week=r.gestational_week,
                status=r.status,
                summary=r.summary,
                chief_complaint=r.chief_complaint,
                self_reported_data=r.self_reported_data or {},
                health_education=r.health_education or [],
            ))

        return FollowUpHistoryResponse(
            pregnant_id=pregnant_id,
            records=result,
        )
    finally:
        db.close()
