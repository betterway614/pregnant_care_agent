"""对话消息持久化存储 - 支持异步/同步双模式"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import desc
from ..database import SessionLocal
from ..models import ConversationMessage


class ConversationStore:
    """基于数据库的对话历史存储

    提供同步方法（`load_history` 等）供同步端点使用，
    和对应的 `async_` 异步方法（`async_load_history` 等）供 async 端点使用，
    异步方法通过 `asyncio.to_thread` 将同步 DB 操作委托到线程池，避免阻塞事件循环。
    """

    def __init__(self, max_history: int = 20):
        self.max_history = max_history

    # ==================== 同步方法（供同步端点使用） ====================

    def load_history(self, session_id: str, pregnant_id: str) -> list[dict]:
        """加载指定会话的历史消息（最近 N 条）"""
        db = SessionLocal()
        try:
            messages = db.query(ConversationMessage).filter(
                ConversationMessage.session_id == session_id,
                ConversationMessage.pregnant_id == pregnant_id,
            ).order_by(desc(ConversationMessage.created_at)).limit(self.max_history).all()

            # 反转为时间正序
            messages.reverse()
            return [
                {"role": m.role, "content": m.content}
                for m in messages
            ]
        finally:
            db.close()

    def save_messages(self, session_id: str, pregnant_id: str,
                      messages: list[dict], metadata: dict | None = None):
        """批量保存消息到数据库"""
        db = SessionLocal()
        try:
            for msg in messages:
                if msg.get("role") in ("system", "tool"):
                    continue  # 跳过系统消息和工具消息
                record = ConversationMessage(
                    session_id=session_id,
                    pregnant_id=pregnant_id,
                    role=msg["role"],
                    content=msg["content"],
                    extra_data=metadata or {},
                )
                db.add(record)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def save_single(self, session_id: str, pregnant_id: str,
                    role: str, content: str, metadata: dict | None = None):
        """保存单条消息"""
        db = SessionLocal()
        try:
            record = ConversationMessage(
                session_id=session_id,
                pregnant_id=pregnant_id,
                role=role,
                content=content,
                extra_data=metadata or {},
            )
            db.add(record)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def clear_session(self, session_id: str, pregnant_id: str):
        """清除指定会话的历史"""
        db = SessionLocal()
        try:
            db.query(ConversationMessage).filter(
                ConversationMessage.session_id == session_id,
                ConversationMessage.pregnant_id == pregnant_id,
            ).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def cleanup_old(self, days: int = 30):
        """清理超过指定天数的旧消息"""
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            db.query(ConversationMessage).filter(
                ConversationMessage.created_at < cutoff
            ).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    # ==================== 异步方法（供 async 端点使用） ====================

    async def async_load_history(self, session_id: str, pregnant_id: str) -> list[dict]:
        """异步加载对话历史（在线程池中执行）"""
        return await asyncio.to_thread(self.load_history, session_id, pregnant_id)

    async def async_save_messages(self, session_id: str, pregnant_id: str,
                                  messages: list[dict], metadata: dict | None = None):
        """异步批量保存消息"""
        return await asyncio.to_thread(self.save_messages, session_id, pregnant_id, messages, metadata)

    async def async_save_single(self, session_id: str, pregnant_id: str,
                                role: str, content: str, metadata: dict | None = None):
        """异步保存单条消息"""
        return await asyncio.to_thread(self.save_single, session_id, pregnant_id, role, content, metadata)

    async def async_clear_session(self, session_id: str, pregnant_id: str):
        """异步清除会话历史"""
        return await asyncio.to_thread(self.clear_session, session_id, pregnant_id)

    async def async_cleanup_old(self, days: int = 30):
        """异步清理旧消息"""
        return await asyncio.to_thread(self.cleanup_old, days)


# 全局单例
conversation_store = ConversationStore()
