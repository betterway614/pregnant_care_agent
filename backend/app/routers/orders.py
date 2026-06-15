"""医嘱管理 API"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime
from ..database import get_db
from ..utils.timezone import beijing_now
from ..models import MedicalOrder, Pregnant, Alert
from ..schemas import OrderGenerateRequest, OrderResponse, OrderSignRequest, OrderUpdateRequest, OrderExplainResponse, OrderDocumentResponse
from ..services import order_service
from ..core import get_llm_client
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/orders", tags=["医嘱管理"])
llm = get_llm_client()

# 允许签署医嘱的角色
_SIGN_ALLOWED_ROLES = {"doctor", "admin"}


@router.post("/generate")
async def generate_order(
    req: OrderGenerateRequest,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """生成医嘱建议（LLM增强版）"""
    if current_user.role not in _SIGN_ALLOWED_ROLES:
        raise HTTPException(403, "仅医生或管理员可以生成医嘱")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == req.pregnant_id).first()
    if not pregnant:
        raise HTTPException(404, "孕妇不存在")

    recommendation = order_service.get_recommendation(
        risk_level=req.risk_level,
        gestational_weeks=req.gestational_weeks,
        risk_tags=pregnant.risk_tags or [],
    )

    if not recommendation:
        recommendation = {
            "content": "密切观察，定期产检，如有不适及时就诊。",
            "source": "常规诊疗建议"
        }

    # 2.1 LLM驱动医嘱生成：用孕妇上下文个性化医嘱
    final_content = recommendation["content"]
    final_source = recommendation["source"]

    # 构建孕妇上下文
    patient_context = f"孕妇孕周：{req.gestational_weeks}周。"
    if pregnant.risk_tags:
        patient_context += f" 风险标签：{', '.join(pregnant.risk_tags)}。"
    if pregnant.nickname:
        patient_context += f" 孕妇昵称：{pregnant.nickname}。"

    # 2.1.1 RAG 检索相关临床指南作为参考上下文
    rag_context = ""
    try:
        from ..core.agno_knowledge import knowledge
        if knowledge is not None:
            from agno.filters import IN
            # 用风险标签构建检索查询
            rag_query = " ".join(pregnant.risk_tags) if pregnant.risk_tags else recommendation.get("source", "")
            if rag_query:
                results = knowledge.search(
                    query=rag_query, max_results=2,
                    filters=[IN("audience", ["doctor", "nurse", "all"])],
                )
                if results:
                    guidelines = []
                    for doc in results:
                        text = doc.content[:300] if hasattr(doc, "content") else str(doc)[:300]
                        guidelines.append(text)
                    rag_context = "\n\n参考临床指南：\n" + "\n---\n".join(guidelines)
    except Exception:
        # RAG 不可用时静默跳过，不影响模板生成
        pass

    try:
        system_prompt = {
            "role": "system",
            "content": (
                "你是一位专业的产科医生助手，负责生成个性化医嘱内容。\n"
                "请基于模板医嘱内容，结合孕妇的具体孕周和风险情况，用更贴近孕妇的专业语言优化医嘱。\n"
                "要求：\n"
                "1. 保持专业医学准确性\n"
                "2. 适当个性化（结合孕周、风险）\n"
                "3. 保留所有关键医疗指令\n"
                "4. 直接输出优化后的医嘱文本，不要加额外说明\n"
                f"参考来源：{recommendation['source']}"
            )
        }
        user_msg = {
            "role": "user",
            "content": f"{patient_context}\n\n原始医嘱模板：{recommendation['content']}{rag_context}\n\n请优化上述医嘱内容，使其更加个性化和孕妇友好。"
        }
        enhanced = await llm.chat([system_prompt, user_msg], max_tokens=2048)
        if enhanced and len(enhanced.strip()) > 10:
            final_content = enhanced.strip()
            final_source = f"AI_CARE ({recommendation['source']})"
    except Exception:
        # LLM不可用时回退到模板
        pass

    # 创建草稿医嘱
    alert_id = UUID(req.alert_id) if req.alert_id else None

    # 应用医嘱安全过滤：禁止诊断性结论，只保留医疗建议/诊疗指导
    from ..core.agno_guardrails import apply_order_draft_safety
    final_content = apply_order_draft_safety(final_content)

    order = MedicalOrder(
        pregnant_id=req.pregnant_id,
        alert_id=alert_id,
        content=final_content,
        order_type="standard",
        source="AI_RECOMMENDED",
        status="draft",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name,
    )


@router.get("", response_model=list[OrderResponse])
def get_orders(
    status: Optional[str] = None,
    pregnant_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """获取医嘱列表（孕妇仅可查看自身；医护可查看全部）"""
    # 孕妇角色：只能看自己的医嘱
    if current_user.role == "pregnant":
        if not current_user.pregnant_id:
            raise HTTPException(403, "孕妇账号未关联孕妇档案")
        pregnant_id = current_user.pregnant_id

    query = db.query(MedicalOrder)
    if status:
        # 支持逗号分隔的多状态查询（如 "draft,pending_sign"），大小写不敏感
        status_list = [s.strip().lower() for s in status.split(",")]
        query = query.filter(MedicalOrder.status.in_(status_list))
    if pregnant_id:
        query = query.filter(MedicalOrder.pregnant_id == pregnant_id)
    orders = query.order_by(MedicalOrder.created_at.desc()).limit(50).all()

    # 批量查询孕妇信息，避免 N+1 查询
    pregnant_ids = list(set(o.pregnant_id for o in orders))
    pregnant_map = {}
    if pregnant_ids:
        pregnants = db.query(Pregnant).filter(Pregnant.pregnant_id.in_(pregnant_ids)).all()
        pregnant_map = {p.pregnant_id: p for p in pregnants}

    result = []
    for o in orders:
        pregnant = pregnant_map.get(o.pregnant_id)
        result.append(OrderResponse(
            **{c.name: getattr(o, c.name) for c in o.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
        ))
    return result


@router.get("/pregnant/{pregnant_id}", response_model=list[OrderResponse])
def get_pregnant_orders(
    pregnant_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """获取孕妇的医嘱列表（孕妇仅可查看自身；医护可查看全部）"""
    # 孕妇角色：只能看自己的医嘱
    if current_user.role == "pregnant" and current_user.pregnant_id != pregnant_id:
        raise HTTPException(403, "无权访问该孕妇数据")

    orders = db.query(MedicalOrder).filter(
        MedicalOrder.pregnant_id == pregnant_id,
    ).order_by(MedicalOrder.created_at.desc()).limit(10).all()

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    return [
        OrderResponse(
            **{c.name: getattr(o, c.name) for c in o.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
        )
        for o in orders
    ]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """获取单条医嘱详情（孕妇仅可查看自身；医护可查看全部）"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    # 孕妇角色：只能看自己的医嘱
    if current_user.role == "pregnant" and current_user.pregnant_id != order.pregnant_id:
        raise HTTPException(403, "无权访问该医嘱")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
    )


@router.put("/{order_id}/sign", response_model=OrderResponse)
def sign_order(
    order_id: str,
    req: OrderSignRequest,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """签署发布医嘱（增强版：支持手写签名 + 验证医生已修改）

    签署前验证：
    1. 当前用户必须是医生或管理员角色
    2. modified_by_doctor == True（医生必须已修改AI生成的医嘱）
    3. 医嘱必须处于 draft 状态（防止重复签署）
    4. 生成归档文档快照
    """
    # 角色校验：仅医生/管理员可签署
    if current_user.role not in _SIGN_ALLOWED_ROLES:
        raise HTTPException(403, "仅医生或管理员可以签署医嘱")

    # 使用 SELECT ... FOR UPDATE 防止并发签署竞态条件
    order = db.query(MedicalOrder).filter(
        MedicalOrder.id == UUID(order_id)
    ).with_for_update().first()
    if not order:
        raise HTTPException(404, "医嘱不存在")

    # 状态校验：仅 draft 状态允许签署
    if order.status != "draft":
        raise HTTPException(400, f"当前状态 '{order.status}' 不允许签署，仅 'draft' 状态可签署")

    # 验证：AI生成的医嘱必须经医生修改后才能签署
    if order.source == "AI_RECOMMENDED" and not order.modified_by_doctor:
        raise HTTPException(400, "AI生成的医嘱必须经医生修改确认后方可签署，请先编辑医嘱内容")

    # 从JWT token提取签署者身份（客户端字段降级为可选覆盖）
    doctor_id = req.doctor_id or current_user.sub
    signer_name = req.signer_name or current_user.sub

    # 保存手写签名
    if req.signature_image:
        order.signature_data = {
            "image": req.signature_image,
            "signer": signer_name,
            "signed_at": beijing_now().isoformat(),
        }

    # 生成归档文档
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    patient_name = pregnant.display_name if pregnant else "未知"
    gest_days = pregnant.gestational_age_days if pregnant else 0
    gest_week = f"{gest_days // 7}+{gest_days % 7}" if gest_days else "未知"

    snapshot, text = order_service.generate_order_document(
        patient_name=patient_name,
        gest_week=gest_week,
        order_content=order.content,
        order_type=order.order_type,
        source=order.source,
        doctor_name=signer_name,
    )
    order.order_snapshot = snapshot
    order.order_text = text

    order.status = "signed"
    order.created_by = doctor_id
    order.signed_at = beijing_now()
    db.commit()
    db.refresh(order)

    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
    )


@router.put("/{order_id}/acknowledge")
def acknowledge_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """孕妇确认阅读医嘱"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    if order.acknowledged_at:
        return {"success": True, "message": "已确认阅读"}
    order.acknowledged_at = beijing_now()
    db.commit()
    return {"success": True, "message": "已确认阅读"}


@router.put("/{order_id}", response_model=OrderResponse)
def update_order(
    order_id: str,
    data: OrderUpdateRequest,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """更新医嘱（内容修改时自动标记 modified_by_doctor）

    仅 draft 状态的医嘱允许修改。仅医生/管理员可修改。
    """
    if current_user.role not in _SIGN_ALLOWED_ROLES:
        raise HTTPException(403, "仅医生或管理员可以修改医嘱")
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")

    # 状态校验：仅 draft 状态允许修改
    if order.status != "draft":
        raise HTTPException(400, f"当前状态 '{order.status}' 不允许修改，仅 'draft' 状态可修改")

    if data.content is not None:
        order.content = data.content
        order.modified_by_doctor = True  # 医生已修改AI生成的医嘱
    if data.order_type is not None:
        order.order_type = data.order_type
    if data.doctor_notes is not None:
        order.doctor_notes = data.doctor_notes
    db.commit()
    db.refresh(order)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
    )


@router.get("/templates")
def get_order_templates(current_user: TokenPayload = Depends(get_current_user)):
    """获取医嘱模板列表"""
    return {"templates": order_service.get_all_templates()}


@router.post("/{order_id}/explain", response_model=OrderExplainResponse)
async def explain_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """用LLM将医嘱翻译成孕妇易懂的通俗语言"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")

    original_content = order.content

    # 尝试用LLM翻译
    try:
        system_prompt = {
            "role": "system",
            "content": (
                "你是一位专业的产科健康教育师。请将医生的医嘱翻译成孕妇能理解的通俗语言。\n"
                "要求：\n"
                "1. plain_language: 用日常口语将医嘱内容翻译成通俗易懂的话\n"
                "2. precautions: 列出孕妇需要注意的3-5条事项\n"
                "3. 保持医学准确性，不要添加或删除医疗建议\n"
                "请按以下JSON格式输出（不要输出其他内容）：\n"
                '{"plain_language": "...", "precautions": "..."}'
            )
        }
        user_msg = {
            "role": "user",
            "content": f"请解释以下医嘱：\n{original_content}"
        }
        response = await llm.chat([system_prompt, user_msg], max_tokens=1024)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(response[json_start:json_end])
                plain_language = parsed.get("plain_language", "")
                precautions = parsed.get("precautions", "")
            else:
                plain_language = response
                precautions = ""
        except (json.JSONDecodeError, KeyError):
            plain_language = response
            precautions = ""
    except Exception:
        plain_language = f"以下是您需要注意的医嘱内容（通俗版）：\n{original_content}\n\n如果有不明白的地方，请咨询您的产检医生。"
        precautions = "如有任何不适，请及时联系您的主治医生。"

    return OrderExplainResponse(
        order_id=order_id,
        original_content=original_content,
        plain_language=plain_language,
        precautions=precautions,
        source="AI_CARE"
    )


@router.get("/{order_id}/document", response_model=OrderDocumentResponse)
def get_order_document(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """获取医嘱归档文档（含签名）

    返回：order_snapshot（结构化快照）+ order_text（纯文本）+ signature_data（签名）
    """
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    return OrderDocumentResponse(
        order_id=str(order.id),
        patient_name=pregnant.display_name if pregnant else "未知",
        snapshot=order.order_snapshot or {},
        text=order.order_text or "",
        signature=order.signature_data or {},
        has_document=bool(order.order_snapshot),
    )


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """删除医嘱（软删除：将状态设为 cancelled）

    权限：仅医生/管理员可删除。
    可删除状态：draft（草稿）、cancelled（已取消）。
    已签署/已执行的医嘱不可删除，确保医疗记录完整性。
    """
    if current_user.role not in _SIGN_ALLOWED_ROLES:
        raise HTTPException(403, "仅医生或管理员可以删除医嘱")

    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")

    if order.status not in ("draft", "cancelled"):
        raise HTTPException(
            400,
            f"当前状态 '{order.status}' 不允许删除，仅 'draft' 或 'cancelled' 状态可删除。"
            "已签署或已执行的医嘱不可删除以保障医疗记录完整性。",
        )

    order.status = "cancelled"
    db.commit()
    return {"success": True, "message": "医嘱已取消"}
