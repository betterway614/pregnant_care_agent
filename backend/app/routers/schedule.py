"""排期管理 API"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from ..models import Pregnant, ScheduleNode
from ..schemas import ScheduleNodeCreate, ScheduleNodeResponse, ScheduleNodeUpdate
from ..services import schedule_engine
from ..core.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/schedule", tags=["排期管理"])


@router.get("/{pregnant_id}", response_model=list[ScheduleNodeResponse])
def get_schedule(pregnant_id: str, db: Session = Depends(get_db),
                 current_user: TokenPayload = Depends(get_current_user)):
    """获取孕妇排期"""
    nodes = db.query(ScheduleNode).filter(
        ScheduleNode.pregnant_id == pregnant_id
    ).order_by(ScheduleNode.scheduled_date).all()
    return nodes


@router.post("/generate/{pregnant_id}")
def generate_schedule(pregnant_id: str, db: Session = Depends(get_db),
                      current_user: TokenPayload = Depends(get_current_user)):
    """自动生成全孕周排期"""
    pregnant = db.query(Pregnant).filter(Pregnant.pregnant_id == pregnant_id).first()
    if not pregnant:
        raise HTTPException(status_code=404, detail="孕妇不存在")

    if not pregnant.lmp_date:
        raise HTTPException(status_code=400, detail="孕妇缺少末次月经日期")

    # 使用排期引擎生成
    current_week = pregnant.gestational_age_days // 7 if pregnant.gestational_age_days else None
    nodes = schedule_engine.generate(
        lmp_date=pregnant.lmp_date,
        risk_tags=pregnant.risk_tags or [],
        current_gest_week=current_week,
    )

    # 删除旧排期
    db.query(ScheduleNode).filter(ScheduleNode.pregnant_id == pregnant_id).delete()

    # 插入新排期
    created = []
    for node in nodes:
        db_node = ScheduleNode(
            pregnant_id=pregnant_id,
            gest_week=node["gest_week"],
            scheduled_date=date.fromisoformat(node["scheduled_date"]),
            item=node["item"],
            node_type=node.get("node_type", "routine"),
        )
        db.add(db_node)
        created.append(db_node)

    db.commit()
    return {"message": f"已生成 {len(created)} 个排期节点", "count": len(created)}


@router.put("/{pregnant_id}/publish")
def publish_schedule(pregnant_id: str, db: Session = Depends(get_db),
                     current_user: TokenPayload = Depends(get_current_user)):
    """发布排期 — 将该孕妇所有排期节点标记为已发布"""
    nodes = db.query(ScheduleNode).filter(
        ScheduleNode.pregnant_id == pregnant_id,
    ).all()
    for node in nodes:
        node.status = "published"
        node.is_published = 1
    db.commit()
    return {"message": f"已发布 {len(nodes)} 个排期节点", "count": len(nodes)}


@router.put("/node/{node_id}", response_model=ScheduleNodeResponse)
def update_node(node_id: str, update: ScheduleNodeUpdate, db: Session = Depends(get_db),
                current_user: TokenPayload = Depends(get_current_user)):
    """更新排期节点"""
    from uuid import UUID
    node = db.query(ScheduleNode).filter(ScheduleNode.id == UUID(node_id)).first()
    if not node:
        raise HTTPException(404, "节点不存在")
    if update.scheduled_date:
        node.scheduled_date = update.scheduled_date
    if update.item:
        node.item = update.item
    if update.node_type:
        node.node_type = update.node_type
    db.commit()
    db.refresh(node)
    return node
