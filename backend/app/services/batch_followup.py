"""批量随访服务

提供批量触发随访和批量分析随访记录的能力。
- batch_trigger: 为一批孕妇批量创建随访草稿，已存在活跃随访的自动跳过。
- batch_analyze: 对已完成的随访记录进行规则分析，识别异常指标（血压、血糖、胎动）。

异常判定标准（依据临床指南）：
- 血压: SBP >= 140 mmHg 或 DBP >= 90 mmHg（妊娠期高血压诊治指南 2020）
- 空腹血糖: > 5.3 mmol/L（妊娠期高血糖诊治指南 2022）
- 胎动: < 3 次/小时（胎动减少警示阈值）
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session
from loguru import logger

from ..models import FollowUpRecord, Pregnant
from ..utils.timezone import beijing_now


# ---------------------------------------------------------------------------
# 结果模型（dataclass 风格的轻量对象）
# ---------------------------------------------------------------------------

class BatchTriggerResult:
    """批量触发随访的结果"""

    def __init__(self) -> None:
        self.triggered: int = 0
        self.skipped: int = 0
        self.errors: list[str] = []

    def __repr__(self) -> str:
        return (
            f"BatchTriggerResult(triggered={self.triggered}, "
            f"skipped={self.skipped}, errors={self.errors!r})"
        )

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class BatchAnalyzeSummary:
    """批量分析随访记录的汇总"""

    def __init__(self) -> None:
        self.total: int = 0
        self.analyzed: int = 0
        self.abnormal_count: int = 0
        self.summaries: list[dict] = []

    def __repr__(self) -> str:
        return (
            f"BatchAnalyzeSummary(total={self.total}, analyzed={self.analyzed}, "
            f"abnormal_count={self.abnormal_count})"
        )

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "analyzed": self.analyzed,
            "abnormal_count": self.abnormal_count,
            "summaries": self.summaries,
        }


# ---------------------------------------------------------------------------
# 服务类
# ---------------------------------------------------------------------------

class BatchFollowupService:
    """批量随访服务"""

    # 异常判定阈值
    BP_SBP_THRESHOLD = 140   # mmHg
    BP_DBP_THRESHOLD = 90    # mmHg
    BLOOD_SUGAR_THRESHOLD = 5.3  # mmol/L
    FETAL_MOVEMENT_THRESHOLD = 3  # 次/小时

    # 活跃随访状态集合（在这些状态下不应重复创建）
    _ACTIVE_STATUSES = {"draft", "in_progress"}

    # ------------------------------------------------------------------
    # 批量触发
    # ------------------------------------------------------------------

    def batch_trigger(
        self,
        db: Session,
        pregnant_ids: list[str],
        template_id: str | None = None,
    ) -> BatchTriggerResult:
        """为一批孕妇批量触发随访记录。

        对每个孕妇：
        1. 检查是否已存在活跃（draft / in_progress）的随访记录，若存在则跳过。
        2. 校验孕妇是否存在，若不存在则记入 errors。
        3. 创建一条 draft 状态的 FollowUpRecord。

        Args:
            db: SQLAlchemy 数据库会话。
            pregnant_ids: 需要触发随访的孕妇 ID 列表。
            template_id: 可选的随访模板 ID，暂存于 self_reported_data 供后续渲染使用。

        Returns:
            BatchTriggerResult 包含 triggered / skipped / errors 统计。
        """
        result = BatchTriggerResult()

        # 预加载所有目标孕妇，减少逐条查询开销
        pregnant_map: dict[str, Pregnant] = {
            p.pregnant_id: p
            for p in db.query(Pregnant).filter(
                Pregnant.pregnant_id.in_(pregnant_ids)
            ).all()
        }

        for pid in pregnant_ids:
            try:
                # 校验孕妇存在性
                pregnant = pregnant_map.get(pid)
                if pregnant is None:
                    result.errors.append(f"孕妇不存在: {pid}")
                    continue

                # 检查是否存在活跃随访
                active_exists = (
                    db.query(FollowUpRecord.id)
                    .filter(
                        FollowUpRecord.pregnant_id == pid,
                        FollowUpRecord.status.in_(self._ACTIVE_STATUSES),
                    )
                    .first()
                )
                if active_exists is not None:
                    result.skipped += 1
                    logger.debug("孕妇 {} 已存在活跃随访，跳过", pid)
                    continue

                # 创建 draft 随访记录
                record = FollowUpRecord(
                    id=uuid4(),
                    pregnant_id=pid,
                    status="draft",
                    follow_up_date=beijing_now(),
                    self_reported_data=(
                        {"template_id": template_id} if template_id else {}
                    ),
                )
                db.add(record)
                result.triggered += 1
                logger.info("为孕妇 {} 创建随访草稿: {}", pid, record.id)

            except Exception as exc:
                msg = f"孕妇 {pid} 触发失败: {exc}"
                result.errors.append(msg)
                logger.error(msg)

        # 统一提交
        if result.triggered > 0:
            try:
                db.commit()
                logger.info(
                    "批量触发完成: triggered={}, skipped={}, errors={}",
                    result.triggered, result.skipped, len(result.errors),
                )
            except Exception as exc:
                db.rollback()
                msg = f"批量提交失败: {exc}"
                result.errors.append(msg)
                logger.error(msg)

        return result

    # ------------------------------------------------------------------
    # 批量分析
    # ------------------------------------------------------------------

    def batch_analyze(
        self,
        db: Session,
        record_ids: list[str],
    ) -> BatchAnalyzeSummary:
        """对已完成的随访记录进行批量规则分析。

        仅分析 status="completed" 的记录。对每条记录的 self_reported_data
        执行以下异常检测规则：
        - 血压（bp 字段 "sbp/dbp" 格式）: SBP >= 140 或 DBP >= 90
        - 空腹血糖（blood_sugar_fasting）: > 5.3 mmol/L
        - 胎动（fetal_movement）: < 3 次/小时

        Args:
            db: SQLAlchemy 数据库会话。
            record_ids: 需要分析的随访记录 ID 列表。

        Returns:
            BatchAnalyzeSummary 包含总数、已分析数、异常数和逐条摘要。
        """
        summary = BatchAnalyzeSummary()
        summary.total = len(record_ids)

        records = (
            db.query(FollowUpRecord)
            .filter(FollowUpRecord.id.in_(record_ids))
            .all()
        )
        record_map = {str(r.id): r for r in records}

        for rid in record_ids:
            record = record_map.get(str(rid))
            if record is None:
                summary.summaries.append({
                    "record_id": str(rid),
                    "status": "not_found",
                    "abnormal": False,
                    "findings": ["记录不存在"],
                })
                continue

            if record.status != "completed":
                summary.summaries.append({
                    "record_id": str(rid),
                    "status": record.status,
                    "abnormal": False,
                    "findings": [f"状态为 {record.status}，非 completed，跳过分析"],
                })
                continue

            summary.analyzed += 1
            findings: list[str] = []
            is_abnormal = False

            srd: dict = record.self_reported_data or {}

            # -- 血压检测 --
            bp_abnormal = self._check_blood_pressure(srd)
            if bp_abnormal is not None:
                findings.append(bp_abnormal)
                is_abnormal = True

            # -- 空腹血糖检测 --
            sugar_abnormal = self._check_blood_sugar(srd)
            if sugar_abnormal is not None:
                findings.append(sugar_abnormal)
                is_abnormal = True

            # -- 胎动检测 --
            fm_abnormal = self._check_fetal_movement(srd)
            if fm_abnormal is not None:
                findings.append(fm_abnormal)
                is_abnormal = True

            if is_abnormal:
                summary.abnormal_count += 1
                record.classification = "abnormal"
                logger.warning(
                    "随访记录 {} 存在异常指标: {}",
                    rid, "; ".join(findings),
                )

            summary.summaries.append({
                "record_id": str(rid),
                "status": record.status,
                "pregnant_id": record.pregnant_id,
                "abnormal": is_abnormal,
                "findings": findings if findings else ["各项指标正常"],
            })

        # 持久化分类变更
        if summary.abnormal_count > 0:
            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error("批量分析结果提交失败: {}", exc)

        logger.info(
            "批量分析完成: total={}, analyzed={}, abnormal={}",
            summary.total, summary.analyzed, summary.abnormal_count,
        )
        return summary

    # ------------------------------------------------------------------
    # 内部规则检测方法
    # ------------------------------------------------------------------

    def _check_blood_pressure(self, srd: dict) -> str | None:
        """检查血压是否异常。支持 bp / bp_morning / bp_evening 三个字段。

        血压格式为 "sbp/dbp"（如 "140/90"）或 dict {"sbp": 140, "dbp": 90}。
        返回异常描述字符串，正常则返回 None。
        """
        bp_keys = ("bp", "bp_morning", "bp_evening")
        for key in bp_keys:
            raw = srd.get(key)
            if raw is None:
                continue
            sbp, dbp = self._parse_bp(raw)
            if sbp is not None and dbp is not None:
                if sbp >= self.BP_SBP_THRESHOLD or dbp >= self.BP_DBP_THRESHOLD:
                    label = {"bp": "血压", "bp_morning": "晨血压", "bp_evening": "晚血压"}.get(key, key)
                    return (
                        f"{label}异常: {int(sbp)}/{int(dbp)} mmHg "
                        f"(阈值 >= {self.BP_SBP_THRESHOLD}/{self.BP_DBP_THRESHOLD})"
                    )
        return None

    def _check_blood_sugar(self, srd: dict) -> str | None:
        """检查空腹血糖是否异常。

        返回异常描述字符串，正常则返回 None。
        """
        sugar_keys = ("blood_sugar_fasting", "blood_sugar")
        for key in sugar_keys:
            raw = srd.get(key)
            if raw is None:
                continue
            value = self._to_float(raw)
            if value is not None and value > self.BLOOD_SUGAR_THRESHOLD:
                return (
                    f"空腹血糖异常: {value} mmol/L "
                    f"(阈值 > {self.BLOOD_SUGAR_THRESHOLD})"
                )
        return None

    def _check_fetal_movement(self, srd: dict) -> str | None:
        """检查胎动是否异常（偏少）。

        返回异常描述字符串，正常则返回 None。
        """
        raw = srd.get("fetal_movement")
        if raw is None:
            return None
        value = self._to_float(raw)
        if value is not None and value < self.FETAL_MOVEMENT_THRESHOLD:
            return (
                f"胎动偏少: {value} 次/小时 "
                f"(阈值 < {self.FETAL_MOVEMENT_THRESHOLD})"
            )
        return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_bp(raw) -> tuple[float | None, float | None]:
        """解析血压值，支持字符串 '140/90' 和 dict {'sbp': 140, 'dbp': 90}。"""
        if isinstance(raw, dict):
            sbp = raw.get("sbp") or raw.get("systolic")
            dbp = raw.get("dbp") or raw.get("diastolic")
            return BatchFollowupService._to_float(sbp), BatchFollowupService._to_float(dbp)
        if isinstance(raw, str):
            parts = raw.replace(" ", "").split("/")
            if len(parts) == 2:
                return BatchFollowupService._to_float(parts[0]), BatchFollowupService._to_float(parts[1])
        return None, None

    @staticmethod
    def _to_float(value) -> float | None:
        """安全地将值转换为 float，失败返回 None。"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# 模块级单例
batch_followup_service = BatchFollowupService()
