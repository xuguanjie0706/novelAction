"""创作端只读：当前可用的大模型 / 智能体信息（不含密钥）。"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.llm_config import pick_active_provider, resolve_gemini_connection

router = APIRouter(prefix="/llm", tags=["llm-public"])


class RemoteAgentBrief(BaseModel):
    id: UUID
    name: str
    model_name: str


class LlmOverviewOut(BaseModel):
    """大纲 / 写作页展示「当前对接哪套模型」。"""
    local_model_name: str
    remote_ready: bool
    effective_remote_model: Optional[str] = None
    remote_agent: Optional[RemoteAgentBrief] = None
    remote_source: str = "none"  # database | env | none


@router.get("/overview", response_model=LlmOverviewOut)
def llm_overview(db: Session = Depends(get_db)):
    conn = resolve_gemini_connection(db)
    row = pick_active_provider(db)

    remote_agent = None
    source = "none"
    if row:
        remote_agent = RemoteAgentBrief(id=row.id, name=row.name, model_name=row.model_name)
        source = "database"
    elif conn and settings.GEMINI_BASE_URL and settings.GEMINI_MODEL:
        source = "env"

    eff_model = conn[1] if conn else None

    return LlmOverviewOut(
        local_model_name=settings.AI_MODEL,
        remote_ready=conn is not None,
        effective_remote_model=eff_model,
        remote_agent=remote_agent,
        remote_source=source,
    )
