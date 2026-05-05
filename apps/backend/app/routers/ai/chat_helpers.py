from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AiChatMessage, Chapter


def chat_context_label(context_type: str, chapter: Optional[Chapter] = None) -> str:
    if context_type == "outline":
        return "大纲"
    if context_type == "writing":
        return f"当前章节正文：{chapter.title if chapter else '未选择章节'}"
    return "项目"


def query_chat_messages(
    db: Session,
    *,
    project_id: str,
    context_type: str,
    chapter_id: Optional[UUID],
):
    query = db.query(AiChatMessage).filter(
        AiChatMessage.project_id == project_id,
        AiChatMessage.context_type == context_type,
    )
    if chapter_id:
        query = query.filter(AiChatMessage.chapter_id == chapter_id)
    else:
        query = query.filter(AiChatMessage.chapter_id.is_(None))
    return query
