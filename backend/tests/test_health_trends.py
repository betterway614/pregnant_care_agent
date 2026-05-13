"""测试健康趋势 API 和随访历史 API"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pregnant, HealthDataPoint, FollowUpRecord
from app.main import app
from app.routers import health_trends

# ── 测试数据库 ──
TEST_DB_URL = "sqlite:///./test_health_trends.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


# 覆盖路由中的 SessionLocal
import app.database as db_module
original_session_local = db_module.SessionLocal


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库"""
    Base.metadata.create_all(bind=test_engine)
    # 覆盖 health_trends 中的 SessionLocal
    health_trends.SessionLocal = TestSession
    yield
    Base.metadata.drop_all(bind=test_engine)
    health_trends.SessionLocal = original_session_local


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seed_pregnant():
    """创建测试孕妇"""
    db = TestSession()
    pregnant = Pregnant(
        pregnant_id="test-p001",
        display_name="测试孕妇",
        gestational_age_days=168,  # 24周
        lmp_date=date.today() - timedelta(days=168),
    )
    db.add(pregnant)
    db.commit()
    db.close()
    return "test-p001"


@pytest.fixture
def seed_health_data(seed_pregnant):
    """创建测试健康数据"""
    db = TestSession()
    today = date.today()
    for i in range(10):
        d = today - timedelta(days=9 - i)
        db.add(HealthDataPoint(
            pregnant_id=seed_pregnant,
            metric_code="systolic",
            value=100 + i * 5,  # 100, 105, ..., 145 (明显递增)
            unit="mmHg",
            source="SEED_DATA",
            recorded_at=datetime.combine(d, datetime.min.time()),
        ))
        db.add(HealthDataPoint(
            pregnant_id=seed_pregnant,
            metric_code="diastolic",
            value=70 + i,  # 70, 71, ..., 79
            unit="mmHg",
            source="SEED_DATA",
            recorded_at=datetime.combine(d, datetime.min.time()),
        ))
        db.add(HealthDataPoint(
            pregnant_id=seed_pregnant,
            metric_code="weight",
            value=60 + i * 0.3,  # 60, 60.3, ..., 62.7
            unit="kg",
            source="SEED_DATA",
            recorded_at=datetime.combine(d, datetime.min.time()),
        ))
    db.commit()
    db.close()


@pytest.fixture
def seed_followup(seed_pregnant):
    """创建测试随访记录"""
    db = TestSession()
    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i * 7)
        db.add(FollowUpRecord(
            pregnant_id=seed_pregnant,
            gestational_week=str(24 - i),
            follow_up_date=datetime.combine(d, datetime.min.time()),
            status="archived" if i > 0 else "confirmed",
            summary=f"第{i+1}次随访摘要",
            chief_complaint="无特殊" if i == 0 else None,
            self_reported_data={"weight": 60 + i},
            health_education=["注意休息"] if i == 0 else [],
        ))
    db.commit()
    db.close()


# ── 健康趋势 API 测试 ──

class TestHealthTrends:
    def test_get_health_trends_single_metric(self, client, seed_pregnant, seed_health_data):
        """单指标查询"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pregnant_id"] == seed_pregnant
        assert len(data["series"]) == 1
        s = data["series"][0]
        assert s["metric"] == "systolic"
        assert s["name"] == "收缩压"
        assert s["unit"] == "mmHg"
        assert len(s["data"]) == 10
        assert s["normal_range"] == {"min": 90, "max": 140}
        assert s["trend"] in ("rising", "falling", "stable")
        assert s["latest_value"] is not None

    def test_get_health_trends_multiple_metrics(self, client, seed_pregnant, seed_health_data):
        """多指标查询"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic,diastolic,weight")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["series"]) == 3
        metrics = [s["metric"] for s in data["series"]]
        assert "systolic" in metrics
        assert "diastolic" in metrics
        assert "weight" in metrics

    def test_get_health_trends_date_range(self, client, seed_pregnant, seed_health_data):
        """日期范围筛选"""
        today = date.today()
        start = (today - timedelta(days=4)).isoformat()
        resp = client.get(
            f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic&start_date={start}"
        )
        assert resp.status_code == 200
        data = resp.json()
        # 应该只有最近5天的数据
        assert len(data["series"][0]["data"]) == 5

    def test_get_health_trends_gest_week_in_data(self, client, seed_pregnant, seed_health_data):
        """数据点包含孕周信息"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic")
        assert resp.status_code == 200
        data = resp.json()
        for point in data["series"][0]["data"]:
            assert "gest_week" in point
            assert isinstance(point["gest_week"], int)
            assert point["gest_week"] >= 0

    def test_get_health_trends_invalid_metric(self, client, seed_pregnant):
        """无效指标"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=invalid_metric")
        assert resp.status_code == 400

    def test_get_health_trends_nonexistent_pregnant(self, client):
        """不存在的孕妇"""
        resp = client.get("/api/v1/pregnant/nonexistent/health-trends?metrics=systolic")
        assert resp.status_code == 404

    def test_get_health_trends_no_data(self, client, seed_pregnant):
        """无数据时返回空序列"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["series"][0]["data"] == []
        assert data["series"][0]["trend"] == "insufficient_data"

    def test_get_health_trends_trend_direction(self, client, seed_pregnant, seed_health_data):
        """趋势方向判断正确（数据递增 → rising）"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/health-trends?metrics=systolic")
        assert resp.status_code == 200
        data = resp.json()
        # systolic 数据是 110, 112, ..., 128（递增），应为 rising
        assert data["series"][0]["trend"] == "rising"


# ── 随访历史 API 测试 ──

class TestFollowUpHistory:
    def test_get_follow_up_history(self, client, seed_pregnant, seed_followup):
        """获取随访历史"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/follow-up-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pregnant_id"] == seed_pregnant
        assert len(data["records"]) == 3
        # 按日期倒序
        assert data["records"][0]["follow_up_date"] >= data["records"][1]["follow_up_date"]

    def test_get_follow_up_history_with_status_filter(self, client, seed_pregnant, seed_followup):
        """按状态筛选"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/follow-up-history?status=archived")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["status"] == "archived" for r in data["records"])
        assert len(data["records"]) == 2

    def test_get_follow_up_history_with_limit(self, client, seed_pregnant, seed_followup):
        """限制返回条数"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/follow-up-history?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) == 1

    def test_get_follow_up_history_record_fields(self, client, seed_pregnant, seed_followup):
        """记录字段完整"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/follow-up-history")
        assert resp.status_code == 200
        record = resp.json()["records"][0]
        assert "id" in record
        assert "follow_up_date" in record
        assert "gestational_week" in record
        assert "status" in record
        assert "summary" in record
        assert "self_reported_data" in record
        assert "health_education" in record

    def test_get_follow_up_history_nonexistent_pregnant(self, client):
        """不存在的孕妇"""
        resp = client.get("/api/v1/pregnant/nonexistent/follow-up-history")
        assert resp.status_code == 404

    def test_get_follow_up_history_empty(self, client, seed_pregnant):
        """无随访记录"""
        resp = client.get(f"/api/v1/pregnant/{seed_pregnant}/follow-up-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["records"] == []
