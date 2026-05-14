# 医嘱与随访数据打通设计文档

## 概述

本设计旨在打通医生端医嘱和孕妇端数据的连接，实现核心功能：

**孕妇端已读确认**：孕妇查看医嘱后可以确认阅读，医生端可看到阅读状态

## 背景

### 当前状态分析

**已打通的数据：**
- 随访中的量化数据（体重、血压、胎动、血糖等）已通过 `_save_health_data_point()` 同步写入 HealthDataPoint
- 医生 AI 分析时已能获取这些量化数据（通过 `_collect_doctor_analysis_context()` 查询 health_data_summary）

**未打通的数据：**
- 孕妇端查看医嘱后没有反馈机制，医生不知道孕妇是否已阅读

### 设计目标

- 形成医嘱 → 阅读确认的闭环
- 让医生知道孕妇是否已阅读医嘱

## 功能设计

### 功能：孕妇端已读确认

#### 数据模型改动

**文件：** `backend/app/models/models.py`

MedicalOrder 类新增字段：

```python
class MedicalOrder(Base):
    # ... 现有字段 ...
    acknowledged_at = Column(DateTime, nullable=True, comment="孕妇确认阅读时间")
```

#### 后端 API

**文件：** `backend/app/routers/orders.py`

新增 API 端点：

```python
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
```

修改现有 API 返回已读状态：

```python
# OrderResponse schema 增加 acknowledged_at 字段
class OrderResponse(BaseModel):
    # ... 现有字段 ...
    acknowledged_at: Optional[datetime] = None
```

#### 前端改动

**文件：** `frontend/src/api/endpoints.ts`

```typescript
export const orderApi = {
  // ... 现有 API ...
  acknowledge: (orderId: string) =>
    client.put(`/orders/${orderId}/acknowledge`),
}
```

**孕妇端医嘱详情页：**
- 显示医嘱内容
- 增加"已读"按钮
- 点击后调用 acknowledge API
- 已读状态本地更新

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                        医生端                                │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ AI 分析请求  │───▶│ 收集分析上下文   │───▶│ LLM 综合分析│ │
│  └─────────────┘    │ - 健康数据 ✓    │    └──────┬──────┘ │
│                     │ - 预警历史 ✓    │           │        │
│                     │ - 随访记录 ✓    │           ▼        │
│                     └─────────────────┘    ┌─────────────┐ │
│                                            │ 分析结果展示 │ │
│                                            └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 医嘱生成/签署
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        孕妇端                                │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ 医嘱通知    │───▶│ 医嘱详情页      │───▶│ 确认阅读    │ │
│  └─────────────┘    └─────────────────┘    └──────┬──────┘ │
│                                                   │        │
│                                                   ▼        │
│                                            ┌─────────────┐ │
│                                            │ acknowledged │ │
│                                            │ _at 更新     │ │
│                                            └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 实施计划

### 阶段 1：后端改动
1. MedicalOrder 模型增加 acknowledged_at 字段
2. 数据库迁移（alembic migration）
3. orders.py 增加 acknowledge API
4. OrderResponse schema 增加 acknowledged_at 字段

### 阶段 2：前端改动
1. endpoints.ts 增加 acknowledge API
2. 孕妇端医嘱详情页增加已读按钮
3. 医生端医嘱列表显示已读状态（可选）

## 测试要点

1. **孕妇端已读确认**：确认点击已读后 acknowledged_at 正确更新
2. **幂等性**：重复点击已读按钮不会报错
3. **数据一致性**：确认 acknowledged_at 字段正确持久化
