"""一次性修复数据库中 schedule_nodes 的 status 与 is_published 不一致问题"""
from app.database import SessionLocal
from app.models import ScheduleNode


def fix_schedule_consistency():
    db = SessionLocal()
    try:
        # 1. status=published 但 is_published=0 → 修正 is_published=1
        inconsistent1 = (
            db.query(ScheduleNode)
            .filter(ScheduleNode.status == "published", ScheduleNode.is_published == 0)
            .count()
        )
        db.query(ScheduleNode).filter(
            ScheduleNode.status == "published", ScheduleNode.is_published == 0
        ).update({"is_published": 1}, synchronize_session=False)

        # 2. status=pending 但 is_published=1 → 修正 is_published=0
        inconsistent2 = (
            db.query(ScheduleNode)
            .filter(ScheduleNode.status == "pending", ScheduleNode.is_published == 1)
            .count()
        )
        db.query(ScheduleNode).filter(
            ScheduleNode.status == "pending", ScheduleNode.is_published == 1
        ).update({"is_published": 0}, synchronize_session=False)

        db.commit()
        print(f"修复完成: {inconsistent1} 条 published/is_published=0, {inconsistent2} 条 pending/is_published=1")
    finally:
        db.close()


if __name__ == "__main__":
    fix_schedule_consistency()
