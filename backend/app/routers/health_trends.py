"""健康趋势 + 随访历史 + 生化指标 API"""
from datetime import datetime, date, timedelta
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import SessionLocal
from ..models import Pregnant, HealthDataPoint, FollowUpRecord
from ..core.trend_engine import trend_engine
from ..core.metric_registry import get_metric_meta
from ..schemas.schemas import (
    HealthTrendResponse, TrendSeries, TrendDataPoint,
    FollowUpHistoryResponse, FollowUpHistoryRecord,
    LabTrendResponse, LabTrendItem,
)

router = APIRouter(prefix="/api/v1/pregnant", tags=["健康趋势"])

# 从统一注册表派生
METRIC_META = get_metric_meta()

# 指标别名：旧版数据可能使用不同的 metric_code，查询时一并包含
METRIC_ALIASES: dict[str, list[str]] = {
    "blood_sugar_fasting": ["blood_sugar_fasting", "blood_sugar"],
    "blood_sugar_postprandial": ["blood_sugar_postprandial", "blood_sugar"],
}

# 生化指标元数据: lab_key -> (中文名, 单位, normal_low, normal_high, is_qualitative)
# qualitative指标用文本显示（如尿蛋白），quantitative指标可绘制趋势图
LAB_METRIC_META = {
    "hemoglobin_g_L": ("血红蛋白", "g/L", 100, 160, False),
    "urine_protein": ("尿蛋白", "", None, None, True),
    "blood_sugar_fasting": ("空腹血糖", "mmol/L", 3.5, 5.3, False),
    "blood_sugar_2h": ("餐后2h血糖", "mmol/L", 3.5, 6.7, False),
    "alt": ("谷丙转氨酶(ALT)", "U/L", 0, 40, False),
    "ast": ("谷草转氨酶(AST)", "U/L", 0, 40, False),
    "creatinine": ("肌酐", "μmol/L", 45, 84, False),
    "uric_acid": ("尿酸", "μmol/L", 150, 360, False),
    "albumin": ("白蛋白", "g/L", 35, 55, False),
    "wbc": ("白细胞", "×10⁹/L", 4.0, 10.0, False),
    "platelet": ("血小板", "×10⁹/L", 100, 300, False),
    "hct": ("红细胞压积", "%", 35, 50, False),
    "bilirubin_total": ("总胆红素", "μmol/L", 0, 21, False),
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

            # 查询数据点（支持旧版 metric_code 别名兼容）
            query_codes = METRIC_ALIASES.get(metric_code, [metric_code])
            points = (
                db.query(HealthDataPoint)
                .filter(
                    HealthDataPoint.pregnant_id == pregnant_id,
                    HealthDataPoint.metric_code.in_(query_codes),
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
                lab_results=r.lab_results or {},
                obstetric_exam=r.obstetric_exam or {},
                classification=r.classification or "normal",
                health_education=r.health_education or [],
                guidance_tags=r.guidance_tags or [],
                signature_data=r.signature_data or {},
            ))

        return FollowUpHistoryResponse(
            pregnant_id=pregnant_id,
            records=result,
        )
    finally:
        db.close()


@router.get("/{pregnant_id}/lab-trends", response_model=LabTrendResponse)
def get_lab_trends(
    pregnant_id: str,
    limit: int = Query(20, ge=1, le=100, description="最近记录条数"),
):
    """获取生化指标历史趋势（从随访记录的lab_results中提取）

    返回所有随访记录中的生化指标数据，按时间排序。
    数值型指标可绘制定量趋势图，定性指标（如尿蛋白）返回文字值。
    """
    db: Session = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
        if not pregnant:
            raise HTTPException(404, "孕妇不存在")

        lmp = pregnant.lmp_date

        # 获取最近的已完成/已确认随访记录（含lab_results）
        records = (
            db.query(FollowUpRecord)
            .filter(
                FollowUpRecord.pregnant_id == pregnant_id,
                FollowUpRecord.status.in_(["completed", "confirmed", "archived"]),
                FollowUpRecord.lab_results.isnot(None),
            )
            .order_by(FollowUpRecord.follow_up_date.desc())
            .limit(limit)
            .all()
        )

        # 从各随访记录中提取生化指标，按指标分组
        lab_series: dict[str, list[dict]] = {}  # lab_key -> [{date, gest_week, value, raw_value}]

        for r in reversed(records):  # 按时间正序
            lr = r.lab_results or {}
            if not lr:
                continue

            rec_date = r.follow_up_date or r.created_at
            date_str = rec_date.isoformat()[:10] if rec_date else ""
            gw = 0
            if lmp and rec_date:
                gw = (rec_date.date() - lmp).days // 7

            for key, raw_val in lr.items():
                if key not in LAB_METRIC_META:
                    continue  # 跳过未注册的指标

                meta = LAB_METRIC_META[key]
                is_qualitative = meta[4]

                if is_qualitative:
                    # 定性指标：存文字值，不绘图
                    if key not in lab_series:
                        lab_series[key] = []
                    lab_series[key].append({
                        "date": date_str,
                        "gest_week": gw,
                        "value": None,
                        "raw_value": str(raw_val),
                    })
                else:
                    # 定量指标：解析数值
                    try:
                        val = float(raw_val)
                    except (ValueError, TypeError):
                        continue
                    if key not in lab_series:
                        lab_series[key] = []
                    lab_series[key].append({
                        "date": date_str,
                        "gest_week": gw,
                        "value": val,
                        "raw_value": str(raw_val),
                    })

        # 构建返回结果
        items = []
        for key, data_points in lab_series.items():
            name, unit, low, high, is_qualitative = LAB_METRIC_META[key]

            # 最新值
            latest = data_points[-1] if data_points else None
            latest_value = latest["raw_value"] if latest else ""

            # 判断是否正常（定量指标）
            is_normal = None
            if latest and latest["value"] is not None and low is not None and high is not None:
                is_normal = low <= latest["value"] <= high

            items.append(LabTrendItem(
                lab_key=key,
                name=name,
                unit=unit,
                normal_low=low,
                normal_high=high,
                is_qualitative=is_qualitative,
                data_points=data_points,
                latest_value=latest_value,
                is_normal=is_normal,
            ))

        return LabTrendResponse(
            pregnant_id=pregnant_id,
            gestational_week=f"{(pregnant.gestational_age_days or 0) // 7}+{(pregnant.gestational_age_days or 0) % 7}",
            items=items,
        )
    finally:
        db.close()
