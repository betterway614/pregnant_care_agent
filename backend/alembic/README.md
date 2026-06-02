# Alembic 数据库迁移

## 常用命令

```bash
# 生成新迁移（自动检测模型变更）
cd backend
alembic revision --autogenerate -m "描述信息"

# 执行迁移（升级到最新）
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history --verbose

# 降级到指定版本
alembic downgrade <revision_id>
```

## 注意事项

1. **SQLite 兼容**：已配置 `render_as_batch=True`，SQLite 的 ALTER TABLE 限制通过 batch 模式处理
2. **数据库 URL**：从 `app.config.settings.database_url` 自动读取，无需手动配置 alembic.ini
3. **模型导入**：`env.py` 已配置自动导入 `app.models.models`，新增模型无需修改 env.py
4. **生产部署**：建议在部署脚本中加入 `alembic upgrade head` 步骤

## 从手写迁移迁移到 Alembic

旧的 `_ensure_*` 函数（在 `main.py` 中）已被 Alembic 替代。新列的添加应通过迁移脚本完成：

```bash
# 修改模型后生成迁移
alembic revision --autogenerate -m "add new column to xxx"

# 检查生成的迁移脚本，确认无误后执行
alembic upgrade head
```
