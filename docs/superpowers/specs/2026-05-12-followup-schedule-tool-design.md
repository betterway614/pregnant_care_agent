# 小Hu随访排期推荐工具设计

## 目标

为护士AI（小Hu）新增排期推荐能力：根据历史随访记录、数据上报情况、风险标签和活跃预警，自动生成随访排期推荐列表，护士可一键触发随访。

## 使用场景

1. **分析时自动推荐**：护士点击"AI分析"，分析结果末尾附带排期推荐列表
2. **独立查询**：护士在Dashboard主动调用 `GET /api/v1/nurse/schedule-recommend/{pregnant_id}`

## 工具接口

### 函数签名

```python
def tool_recommend_followup_schedule(db, pregnant_id: str) -> dict:
```

### 输出结构

```json
{
  "pregnant_id": "PT_XXX",
  "current_gestational_week": "28+3",
  "recommendations": [
    {
      "recommended_date": "immediate",
      "gestational_week": "28+3",
      "template_id": "fgr_high_risk",
      "reason": "存在2条高级别预警需立即处理：[RED] 血压异常升高；[ORANGE] 胎动减少",
      "priority": "high",
      "is_overdue": false,
      "suggested_actions": ["立即联系孕妇进行随访", "确认预警详情并处理"]
    },
    {
      "recommended_date": "2026-05-22",
      "gestational_week": "30+0",
      "template_id": "fgr_high_risk",
      "reason": "高危孕妇需加密随访",
      "priority": "medium",
      "is_overdue": false,
      "suggested_actions": ["确认随访时间并通知孕妇", "提醒携带最近B超报告"]
    }
  ],
  "context_summary": {
    "days_since_last_followup": 15,
    "last_followup_date": "2026-04-27",
    "last_followup_status": "confirmed",
    "health_data_frequency": "inactive",
    "health_data_count_14d": 2,
    "active_alert_count": 2,
    "has_critical_alerts": true,
    "risk_tags": ["FGR高危"]
  }
}
```

## 排期规则

### 基础间隔

| 条件 | 间隔（天） |
|------|-----------|
| 有RED/ORANGE预警 | 0（立即） |
| ≥36周 | 7 |
| FGR高危 或 高血压 | 10 |
| GDM | 14 |
| 正常孕妇 | 21 |

### 推荐生成逻辑（按优先级排序）

1. **立即随访（高危预警）**：有RED/ORANGE PENDING预警 → `recommended_date="immediate"`, `priority="high"`
2. **逾期检查**：距上次随访天数 > 间隔×1.5 → `recommended_date="immediate"`, `priority="high"`, `is_overdue=true`；无随访记录且≥12周 → 同上
3. **数据督促**：14天内健康数据<3条 且 有风险标签 → 附加建议"督促孕妇加强健康数据上报"
4. **未来排期**：按间隔生成未来2-3个日期，根据到达该日期时的孕周分配priority：
   - ≥36周 → high
   - FGR/高血压 → medium
   - 数据不活跃且有风险标签 → 优先级提升一级
   - 其他 → low

### 模板选择

| 条件 | 模板 |
|------|------|
| FGR高危 或 高血压 | `fgr_high_risk` |
| ≥37周 | `post_discharge` |
| 其他 | `standard` |

### 辅助建议动作

| 条件 | 建议 |
|------|------|
| FGR高危 | 提醒携带最近B超报告 |
| 高血压 | 提醒携带血压监测记录 |
| GDM | 提醒携带血糖监测记录 |
| 数据不活跃 | 督促孕妇加强健康数据上报 |
| ≥36周 | 确认分娩准备情况 |

### 边界情况

| 场景 | 处理 |
|------|------|
| 孕妇不存在 | 返回 `{"error": "孕妇不存在"}` |
| 无随访记录 | ≥12周标记逾期，<12周只生成未来排期 |
| 孕周>42 | 停止生成未来日期 |
| 风险标签为空 | 使用标准间隔21天+standard模板 |

## 一键触发

护士选择推荐后，前端调用现有 `tool_generate_followup_record(db, pregnant_id, template_id, chief_complaint)` 创建随访草稿。不新增模型字段，不新增数据库表。

## 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/routers/nurse_ai.py` | 新增 `tool_recommend_followup_schedule` + 3个辅助函数 + GET端点 + nurse_analyze集成 |
| `backend/app/schemas/schemas.py` | 新增 `FollowupScheduleRecommendation`, `FollowupScheduleContext`, `FollowupScheduleResponse`；`NurseAnalyzeResponse` 增加 `followup_schedule` 字段 |
| `backend/app/schemas/__init__.py` | 导出新模型 |

## 不改的部分

- 不改 FollowUpRecord 模型（不加 next_followup_date）
- 不加数据库表
- 不涉及前端改动（本次只做后端工具+API）
- 不涉及LLM调用
