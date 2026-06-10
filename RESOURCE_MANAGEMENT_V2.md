# 资源管理系统 V2 - 完整实现

## 新增功能

### 1. 功率监测 ✅

| 指标 | 说明 | 来源 |
|------|------|------|
| `gpu_power_w` | GPU 当前功率 (W) | rocm-smi |
| `gpu_power_cap_w` | GPU 功率上限 (W) | rocm-smi |
| `cpu_power_w` | CPU 当前功率 (W) | RAPL/sys |
| `package_power_w` | 整机功率 (W) | 估算 |
| `gpu_temp_c` | GPU 温度 (°C) | rocm-smi |
| `cpu_temp_c` | CPU 温度 (°C) | psutil |

### 2. 异常/预警数据库记录 ✅

**新增数据表:**

| 表名 | 说明 |
|------|------|
| `resource_alerts` | 资源预警记录 |
| `resource_metrics` | 资源指标历史 |

**预警类型:**

| 类型 | 触发条件 | 严重程度 |
|------|----------|----------|
| `vram_high` | VRAM ≥ 85% / 95% | warning / critical |
| `gpu_high` | GPU ≥ 95% | critical |
| `cpu_high` | CPU ≥ 90% | warning |
| `temp_high` | GPU ≥ 80°C / 90°C | warning / critical |
| `power_high` | GPU 功率 ≥ 95% 上限 | warning |
| `npu_offline` | NPU 设备不可用 | info |

### 3. 预警管理 API ✅

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/resource/alerts` | 获取预警列表 |
| PUT | `/api/v1/admin/resource/alerts/{id}/acknowledge` | 确认预警 |
| PUT | `/api/v1/admin/resource/alerts/{id}/resolve` | 解决预警 |
| GET | `/api/v1/admin/resource/alerts/stats` | 预警统计 |

---

## 完整 API 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/resource/status` | 系统资源状态 (含功率/温度) |
| GET | `/api/v1/admin/resource/services` | 服务配置 |
| PUT | `/api/v1/admin/resource/services/{name}` | 更新服务配置 |
| GET | `/api/v1/admin/resource/policy` | 当前策略 |
| PUT | `/api/v1/admin/resource/policy` | 切换策略 |
| GET | `/api/v1/admin/resource/adjustments` | 优化建议 |
| GET | `/api/v1/admin/resource/history` | 历史数据 |
| POST | `/api/v1/admin/resource/monitoring/start` | 启动监控 |
| POST | `/api/v1/admin/resource/monitoring/stop` | 停止监控 |
| GET | `/api/v1/admin/resource/llm-analysis` | LLM 分析 |
| GET | `/api/v1/admin/resource/alerts` | 预警列表 |
| PUT | `/api/v1/admin/resource/alerts/{id}/acknowledge` | 确认预警 |
| PUT | `/api/v1/admin/resource/alerts/{id}/resolve` | 解决预警 |
| GET | `/api/v1/admin/resource/alerts/stats` | 预警统计 |

---

## 前端访问地址

| 页面 | 地址 |
|------|------|
| 资源监控 | `http://localhost:3000/admin/resource-monitor` |
| 资源配置 | `http://localhost:3000/admin/resource-config` |

---

## 数据库表结构

### resource_alerts

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| alert_type | VARCHAR(32) | 预警类型 |
| severity | VARCHAR(16) | 严重程度 |
| title | VARCHAR(128) | 预警标题 |
| message | TEXT | 预警详情 |
| vram_percent | FLOAT | VRAM 使用率 |
| gpu_percent | FLOAT | GPU 使用率 |
| cpu_percent | FLOAT | CPU 使用率 |
| gpu_power_w | FLOAT | GPU 功率 |
| gpu_temp_c | FLOAT | GPU 温度 |
| cpu_temp_c | FLOAT | CPU 温度 |
| status | VARCHAR(16) | 状态 |
| acknowledged_by | VARCHAR(64) | 确认人 |
| acknowledged_at | DATETIME | 确认时间 |
| resolved_at | DATETIME | 解决时间 |
| resolution | TEXT | 解决方案 |
| policy_name | VARCHAR(32) | 当前策略 |
| auto_action | VARCHAR(64) | 自动动作 |
| created_at | DATETIME | 创建时间 |

### resource_metrics

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| vram_percent | FLOAT | VRAM 使用率 |
| gpu_percent | FLOAT | GPU 使用率 |
| cpu_percent | FLOAT | CPU 使用率 |
| ram_percent | FLOAT | RAM 使用率 |
| gpu_power_w | FLOAT | GPU 功率 |
| gpu_power_cap_w | FLOAT | GPU 功率上限 |
| cpu_power_w | FLOAT | CPU 功率 |
| package_power_w | FLOAT | 整机功率 |
| gpu_temp_c | FLOAT | GPU 温度 |
| cpu_temp_c | FLOAT | CPU 温度 |
| load_level | VARCHAR(16) | 负载级别 |
| policy_name | VARCHAR(32) | 当前策略 |
| created_at | DATETIME | 采样时间 |

---

## 测试命令

```bash
# 测试资源监控
curl http://localhost:9999/api/v1/admin/resource/status \
  -H "Authorization: Bearer <token>"

# 测试预警列表
curl http://localhost:9999/api/v1/admin/resource/alerts \
  -H "Authorization: Bearer <token>"

# 测试预警统计
curl http://localhost:9999/api/v1/admin/resource/alerts/stats \
  -H "Authorization: Bearer <token>"
```
