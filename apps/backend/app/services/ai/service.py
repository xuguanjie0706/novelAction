"""AIService 类定义：Mixin 组合 + ``__init__``。"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection

from app.services.ai.chat import ChatMixin
from app.services.ai.client import ClientMixin
from app.services.ai.coherence import CoherenceMixin
from app.services.ai.debrief import DebriefMixin
from app.services.ai.draft_stream import DraftStreamMixin
from app.services.ai.memory_ai import MemoryMixin
from app.services.ai.outline_ai import OutlineMixin
from app.services.ai.quality import QualityMixin
from app.services.ai.sampling import SamplingMixin
from app.services.ai.writing_tools import WritingToolsMixin


class AIService(
    ClientMixin,
    QualityMixin,
    CoherenceMixin,
    ChatMixin,
    MemoryMixin,
    OutlineMixin,
    DraftStreamMixin,
    DebriefMixin,
    WritingToolsMixin,
    SamplingMixin,
):
    """统一使用 OpenAI 兼容协议（任意 base_url + api_key）。"""

    def __init__(
        self,
        profile: str = "default",
        db: Optional[Session] = None,
        llm_provider_id: Optional[UUID] = None,
    ):
        self.profile = profile
        self._db = db
        self.model = (settings.AI_MODEL or "").strip()
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self._gemini_unconfigured = False
        if profile == "gemini":
            conn = resolve_gemini_connection(db, llm_provider_id)
            if conn:
                self.base_url = normalize_openai_base_url(conn[0])
                self.model = conn[1]
                self.api_key = (conn[2] or "").strip() or "not-required"
            else:
                self._gemini_unconfigured = True
        self._client = None
        self._truncation_warnings: list[str] = []
