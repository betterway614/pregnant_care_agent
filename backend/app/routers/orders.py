"""医嘱管理 API"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime
from ..database import get_db, SessionLocal
from ..models import MedicalOrder, Pregnant, Alert
from ..schemas import OrderGenerateRequest, OrderResponse, OrderSignRequest, OrderExplainResponse
from ..services import order_service
from ..core import get_llm_client

router = APIRouter(prefix="/api/v1/orders", tags=["医嘱管理"])
llm = get_llm_client()


@router.post("/generate")
async def generate_order(req: OrderGenerateRequest, db: Session = Depends(get_db)):
    """生成医嘱建议（LLM增强版）"""
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
            "content": f"{patient_context}\n\n原始医嘱模板：{recommendation['content']}\n\n请优化上述医嘱内容，使其更加个性化和孕妇友好。"
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
def get_orders(status: Optional[str] = None,
                pregnant_id: Optional[str] = None,
                db: Session = Depends(get_db)):
    """获取医嘱列表"""
    query = db.query(MedicalOrder)
    if status:
        query = query.filter(MedicalOrder.status == status)
    if pregnant_id:
        query = query.filter(MedicalOrder.pregnant_id == pregnant_id)
    orders = query.order_by(MedicalOrder.created_at.desc()).limit(50).all()

    result = []
    for o in orders:
        pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == o.pregnant_id).first()
        result.append(OrderResponse(
            **{c.name: getattr(o, c.name) for c in o.__table__.columns},
            patient_name=pregnant.display_name if pregnant else "未知",
        ))
    return result


@router.get("/pregnant/{pregnant_id}", response_model=list[OrderResponse])
def get_pregnant_orders(pregnant_id: str, db: Session = Depends(get_db)):
    """获取孕妇的医嘱列表（用于孕妇端展示）"""
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


@router.put("/{order_id}/sign", response_model=OrderResponse)
def sign_order(order_id: str, req: OrderSignRequest, db: Session = Depends(get_db)):
    """签署发布医嘱"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")

    order.status = "signed"
    order.created_by = req.doctor_id
    order.signed_at = datetime.utcnow()
    db.commit()
    db.refresh(order)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
    )


@router.put("/{order_id}/acknowledge")
def acknowledge_order(order_id: str, db: Session = Depends(get_db)):
    """孕妇确认阅读医嘱"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    if order.acknowledged_at:
        return {"success": True, "message": "已确认阅读"}
    order.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "已确认阅读"}


@router.put("/{order_id}", response_model=OrderResponse)
def update_order(order_id: str, data: dict, db: Session = Depends(get_db)):
    """更新医嘱"""
    order = db.query(MedicalOrder).filter(MedicalOrder.id == UUID(order_id)).first()
    if not order:
        raise HTTPException(404, "医嘱不存在")
    if "content" in data:
        order.content = data["content"]
    if "order_type" in data:
        order.order_type = data["order_type"]
    db.commit()
    db.refresh(order)

    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == order.pregnant_id).first()
    return OrderResponse(
        **{c.name: getattr(order, c.name) for c in order.__table__.columns},
        patient_name=pregnant.display_name if pregnant else "未知",
    )


@router.get("/templates")
def get_order_templates():
    """获取医嘱模板列表"""
    return {"templates": order_service.get_all_templates()}


@router.post("/{order_id}/explain", response_model=OrderExplainResponse)
async def explain_order(order_id: str):
    """用LLM将医嘱翻译成孕妇易懂的通俗语言"""
    db = SessionLocal()
    try:
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
                # 尝试提取JSON
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
            # LLM不可用时生成兜底解释
            plain_language = f"以下是您需要注意的医嘱内容（通俗版）：\n{original_content}\n\n如果有不明白的地方，请咨询您的产检医生。"
            precautions = "如有任何不适，请及时联系您的主治医生。"

        return OrderExplainResponse(
            order_id=order_id,
            original_content=original_content,
            plain_language=plain_language,
            precautions=precautions,
            source="AI_CARE"
        )
    finally:
        db.close()
