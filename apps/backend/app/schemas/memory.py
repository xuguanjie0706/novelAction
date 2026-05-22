from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class MemoryChunkCreate(BaseModel):
    chapter_id: Optional[uuid.UUID] = None
    memory_type: str = "event"
    title: Optional[str] = None
    content: str
    chapter_number: Optional[int] = None
    tags: List[str] = []
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryChunkOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: Optional[uuid.UUID]
    memory_type: str
    title: Optional[str]
    content: str
    chapter_number: Optional[int]
    tags: List[str]
    # 重要度 / 访问统计（时效衰减检索用）
    importance_score: float = 0.5
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MemoryConflictItem(BaseModel):
    """单条记忆冲突描述。"""
    conflict_type: str              # character_state / timeline / attribute / foreshadow
    severity: str                   # low / medium / high
    description: str                # 人可读的冲突说明
    chunk_ids: List[uuid.UUID]      # 涉及的 MemoryChunk ID
    chapter_refs: List[int]         # 涉及的章节编号


class MemoryConflictReport(BaseModel):
    """记忆冲突检测结果报告。"""
    project_id: uuid.UUID
    total_chunks_scanned: int
    conflicts: List[MemoryConflictItem]
    detected_at: datetime


class MemoryConflictDetectLogOut(BaseModel):
    """单次记忆冲突检测运行日志。"""
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: Optional[uuid.UUID]
    trigger: str
    status: str
    duration_ms: int
    total_chunks_scanned: int
    conflict_count: int
    llm_call_log_id: Optional[uuid.UUID]
    error: Optional[str]
    output_payload: dict
    created_at: datetime

    class Config:
        from_attributes = True
