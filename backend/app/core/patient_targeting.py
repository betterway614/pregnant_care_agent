"""护士/医生端对话中的孕妇目标解析。

目标解析放在路由层，避免让 LLM 仅凭上下文或患者列表猜测 pregnant_id。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Any


_PATIENT_NOUN = r"(?:孕妇|患者|产妇|孕妈|病人)"
_CN_NUMBER = "零一二两三四五六七八九十百"
_TOKEN = rf"(?:[A-Za-z]{{0,8}}[_-]?\d+[A-Za-z0-9_-]*|\d+|[{_CN_NUMBER}]+)"

_MENTION_PATTERNS = [
    re.compile(rf"(?P<raw>{_PATIENT_NOUN}\s*(?P<token>{_TOKEN}))"),
    re.compile(rf"(?P<raw>(?P<token>{_TOKEN})\s*号\s*{_PATIENT_NOUN})"),
    re.compile(r"(?P<raw>(?:ID|id|编号)[:：\s]*(?P<token>[A-Za-z0-9_-]+))"),
]


@dataclass(frozen=True)
class PatientTargetMention:
    raw: str
    token: str
    normalized_token: str
    pregnant_id_candidates: tuple[str, ...] = field(default_factory=tuple)
    display_name_candidates: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PatientTargetResolution:
    explicit: bool
    pregnant_id: str = ""
    display_name: str = ""
    mention: str = ""
    source: str = ""
    unresolved_reason: str = ""


def _normalize_token(token: str) -> str:
    token = (token or "").strip()
    try:
        from .nlu_engine import _cn_to_arabic

        token = _cn_to_arabic(token)
    except Exception:
        pass
    return token.strip()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _build_candidates(token: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized = _normalize_token(token)
    id_candidates = [token, normalized]
    display_candidates = [token, normalized]

    if normalized.isdigit():
        number = int(normalized)
        display_candidates.extend([
            f"孕妇{number}",
            f"孕妇{number:02d}",
            f"患者{number}",
            f"患者{number:02d}",
        ])
    elif not normalized.startswith(("孕妇", "患者")):
        display_candidates.append(f"孕妇{normalized}")

    return _unique(id_candidates), _unique(display_candidates)


def extract_patient_target_mention(text: str) -> PatientTargetMention | None:
    """从自然语言中提取显式孕妇目标，如“孕妇20”“20号孕妇”。"""
    if not text:
        return None

    for pattern in _MENTION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group("raw").strip()
        token = match.group("token").strip()
        normalized = _normalize_token(token)
        id_candidates, display_candidates = _build_candidates(token)
        return PatientTargetMention(
            raw=raw,
            token=token,
            normalized_token=normalized,
            pregnant_id_candidates=id_candidates,
            display_name_candidates=display_candidates,
        )
    return None


def _value(row: Any, attr: str) -> str:
    value = getattr(row, attr, "")
    return str(value or "").strip()


def _load_patients(db) -> list[Any]:
    from ..models import Pregnant

    return list(db.query(Pregnant).all())


def resolve_patient_target_from_text(
    text: str,
    *,
    db=None,
    fallback_pregnant_id: str = "",
) -> PatientTargetResolution:
    """解析本轮对话目标孕妇。

    有显式目标时只接受精确 ID、hospital_id 或 display_name 命中；
    未命中则返回 unresolved，调用方应停止执行，避免错查默认孕妇。
    """
    mention = extract_patient_target_mention(text)
    if mention is None:
        return PatientTargetResolution(
            explicit=False,
            pregnant_id=fallback_pregnant_id or "",
            source="fallback" if fallback_pregnant_id else "",
        )

    own_db = None
    if db is None:
        from ..database import SessionLocal

        own_db = SessionLocal()
        db = own_db

    try:
        patients = _load_patients(db)
    finally:
        if own_db is not None:
            own_db.close()

    id_candidates = set(mention.pregnant_id_candidates)
    display_candidates = set(mention.display_name_candidates)

    for patient in patients:
        pregnant_id = _value(patient, "pregnant_id")
        display_name = _value(patient, "display_name")
        hospital_id = _value(patient, "hospital_id")
        if pregnant_id in id_candidates:
            return PatientTargetResolution(True, pregnant_id, display_name, mention.raw, "pregnant_id")
        if hospital_id and hospital_id in id_candidates:
            return PatientTargetResolution(True, pregnant_id, display_name, mention.raw, "hospital_id")
        if display_name in display_candidates:
            return PatientTargetResolution(True, pregnant_id, display_name, mention.raw, "display_name")

    return PatientTargetResolution(
        explicit=True,
        mention=mention.raw,
        source="unresolved",
        unresolved_reason=f"未找到指定孕妇：{mention.raw}",
    )


def build_patient_target_system_prefix(target: PatientTargetResolution) -> str:
    """构造注入 Agent 输入的目标约束前缀。"""
    if not target.explicit or not target.pregnant_id:
        return ""
    return (
        "[系统目标孕妇] "
        f"用户本轮明确指定 {target.mention}；"
        f"pregnant_id={target.pregnant_id}；display_name={target.display_name or '未知'}。"
        "所有患者数据、趋势、规则评估、随访、上报、医嘱工具都必须使用该 pregnant_id；"
        "不得使用历史会话、患者列表第一项或页面默认孕妇替代。"
    )


def build_patient_target_session_state(target: PatientTargetResolution) -> dict[str, str]:
    if not target.explicit or not target.pregnant_id:
        return {}
    return {
        "explicit_patient_target_id": target.pregnant_id,
        "explicit_patient_target_display_name": target.display_name,
        "explicit_patient_target_mention": target.mention,
    }
