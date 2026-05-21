from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QualityCheckRequest(BaseModel):
    chapter_id: str
    check_types: List[str] = ["plot", "character", "setting_consistency", "pacing", "hooks", "outline_alignment"]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SuggestRequest(BaseModel):
    chapter_id: str
    prompt: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChatMessageOut(BaseModel):
    id: UUID
    project_id: UUID
    chapter_id: Optional[UUID]
    context_type: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatStreamRequest(BaseModel):
    prompt: str
    context_type: Literal["outline", "writing", "general"] = "general"
    chapter_id: Optional[UUID] = None
    """写作对话：将其他章节正文一并并入模型上下文（须属本书；当前章不必重复勾选，最多 8 章）。"""
    additional_chapter_ids: Optional[List[UUID]] = Field(default=None, max_length=8)
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChapterCoherenceCheckRequest(BaseModel):
    chapter_ids: List[str]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SaveChapterCoherenceReportRequest(BaseModel):
    name: Optional[str] = None
    model_profile: Literal["local", "gemini"] = "local"
    selected_chapter_ids: List[str]
    result: dict


class CoherenceApplyFocusSelection(BaseModel):
    """与报告内数组下标对应；提供时仅将这些条目并入改正文提示（scores/summary 仍用完整报告）。"""

    cross_chapter_issue_indices: List[int] = Field(default_factory=list)
    suggestion_indices: List[int] = Field(default_factory=list)
    chapter_evaluation_indices: List[int] = Field(default_factory=list)


class ChapterCoherenceApplyPreviewRequest(BaseModel):
    report_id: UUID
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    focus_keywords: Optional[List[str]] = Field(default=None, description="定向修订关键词，并入模型提示")
    revision_note: Optional[str] = Field(default=None, description="作者补充说明")
    focus_selection: Optional[CoherenceApplyFocusSelection] = Field(
        default=None,
        description="勾选子集；不传则使用报告内全部跨章问题、建议、章节点评",
    )


class CoherenceApplyRevisionItem(BaseModel):
    chapter_id: UUID
    revised_content: str


class ChapterCoherenceApplyCommitRequest(BaseModel):
    report_id: UUID
    revisions: List[CoherenceApplyRevisionItem]


class DraftAssistRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    """作者补充说明：风格、禁忌、情节走向等，会并入提示词"""
    user_prompt: Optional[str] = None
    """为 True 时按「整章重写」生成，不把长正文当作续写衔接"""
    replace_existing: bool = False
    """若指定，则在 user_prompt 中注入该条待处理质量债务的定向修复指令（须与 chapter_id 对应章一致）"""
    focus_quality_debt_id: Optional[UUID] = None
    consistency_issue_ack: Optional[List[str]] = Field(
        default=None,
        description=(
            "当 ``writing_config.block_on_consistency_issues`` 为真且存在未处理的高优先级矛盾时，"
            "传入待放行条目的 fingerprint 列表（与 409 响应 ``issues[].fingerprint`` 一致）。"
        ),
    )


class GatedDraftRequest(BaseModel):
    """
    质量门控写作请求。

    后端会执行「起笔 → 自动质检 → 未达标则重写」循环，直至通过或达到
    最大尝试次数。循环配置优先读 project.extra.writing_config，可在此
    处传 override_config 临时覆盖（A/B 测试或单次调整用）。
    """
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    """作者补充说明：写作风格、情节走向等，注入每次起笔提示"""
    user_prompt: Optional[str] = None
    """是否整章重写；False 时若已有正文则追加，True 时清空重写"""
    replace_existing: bool = True
    """可选：临时覆盖项目级 writing_config 的部分字段"""
    override_config: Optional[dict] = None
    consistency_issue_ack: Optional[List[str]] = Field(
        default=None,
        description="阻塞起笔时与 ``DraftAssistRequest.consistency_issue_ack`` 语义相同。",
    )


class CharacterUpdate(BaseModel):
    character_id: str
    current_realm: Optional[str] = None
    realm_rank: Optional[int] = None
    current_location: Optional[str] = None
    current_status: Optional[str] = None
    add_skill: Optional[dict] = None      # {"skill_id": "...", "skill_name": "...", "mastery": "初学"}
    add_item: Optional[dict] = None       # {"item_id": "...", "item_name": "...", "acquired_chapter": 5}
    remove_item_id: Optional[str] = None  # 失去道具时传 item_id


class StoryLineUpdate(BaseModel):
    storyline_id: Optional[str] = None
    storyline_name: Optional[str] = None
    status: Optional[str] = None          # planned/active/climax/resolved/dropped
    append_beat: Optional[str] = None     # 追加到 key_beats 的新节点描述


class MemoryUpdate(BaseModel):
    memory_type: Literal["event", "character_state", "foreshadow", "setting", "conflict"] = "event"
    title: Optional[str] = None
    content: str
    tags: List[str] = []
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    """记忆重要度（0-1）。AI 复盘时可按情节权重赋值（如主角突破 → 0.9，路人出场 → 0.3）；
    不传则默认 0.5，影响 RAG 召回优先级与时效衰减排序。"""


class NewItemAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    item_type: str = "artifact"
    rarity: str = "rare"
    description: Optional[str] = None
    origin: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    current_owner_id: Optional[str] = None
    current_owner_name: Optional[str] = None
    story_significance: Optional[str] = None
    status: str = "intact"
    reason_to_store: Optional[str] = None


class ItemAssetUpdate(BaseModel):
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    status: Optional[str] = None
    current_owner_id: Optional[str] = None
    current_owner_name: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    story_significance: Optional[str] = None
    event_note: Optional[str] = None


class NewSkillAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    skill_type: str = "combat"
    grade: str = "earth"
    source: Optional[str] = None
    level_required: Optional[str] = None
    prerequisites: Optional[str] = None
    description: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    mastered_by_character_ids: List[str] = Field(default_factory=list)
    mastered_by_character_names: List[str] = Field(default_factory=list)
    reason_to_store: Optional[str] = None


class SkillAssetUpdate(BaseModel):
    skill_id: Optional[str] = None
    skill_name: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    add_mastered_by_character_id: Optional[str] = None
    add_mastered_by_character_name: Optional[str] = None
    mastery: Optional[str] = None
    event_note: Optional[str] = None


class NewFactionAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    faction_type: str = "other"
    alignment: str = "neutral"
    description: Optional[str] = None
    territory: Optional[str] = None
    strength_level: Optional[str] = None
    goals: Optional[str] = None
    resources: Optional[str] = None
    attitude_to_protagonist: str = "neutral"
    reason_to_store: Optional[str] = None


class FactionAssetUpdate(BaseModel):
    faction_id: Optional[str] = None
    faction_name: Optional[str] = None
    alignment: Optional[str] = None
    goals: Optional[str] = None
    resources: Optional[str] = None
    attitude_to_protagonist: Optional[str] = None
    event_note: Optional[str] = None


class AssetUpdates(BaseModel):
    new_items: List[NewItemAsset] = Field(default_factory=list)
    item_updates: List[ItemAssetUpdate] = Field(default_factory=list)
    new_skills: List[NewSkillAsset] = Field(default_factory=list)
    skill_updates: List[SkillAssetUpdate] = Field(default_factory=list)
    new_factions: List[NewFactionAsset] = Field(default_factory=list)
    faction_updates: List[FactionAssetUpdate] = Field(default_factory=list)


class ChapterIndexPayload(BaseModel):
    story_day: Optional[str] = None
    core_events: List[dict | str] = []
    first_appearances: List[dict] = []
    # 新格式：AI 输出统一数组，后端解析层按 action 拆分后填入下方两字段
    foreshadow_updates: List[dict] = []
    # 下游消费字段（由 _split_foreshadow_updates 填充，或前端直接提交时使用）
    actual_foreshadows_laid: List[dict] = []
    actual_foreshadows_resolved: List[dict] = []
    ending_hook: Optional[str] = None
    hook_strength: int = 1
    continuity_notes: List[dict | str] = []


class NewCharacterPayload(BaseModel):
    """auto_debrief 从正文识别出的新配角，由 chapter_debrief 写入 DB。"""
    name: str
    role: str = "supporting"
    # 叙事层级：core=核心长线 / arc=弧线支柱 / plot=剧情推手 / background=背景填充
    character_tier: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    faction: Optional[str] = None
    personality: Optional[str] = None
    motivation: Optional[str] = None
    background: Optional[str] = None
    current_realm: Optional[str] = None
    current_status: Optional[str] = "alive"
    current_location: Optional[str] = None
    arc_scope: Optional[str] = "mini_arc"   # single_chapter / mini_arc / long_arc（兼容旧字段，tier 优先）
    author_notes: Optional[str] = None


class ChapterDebriefRequest(BaseModel):
    chapter_id: str
    character_updates: List[CharacterUpdate] = []
    storyline_updates: List[StoryLineUpdate] = []
    memory_updates: List[MemoryUpdate] = []
    asset_updates: AssetUpdates = Field(default_factory=AssetUpdates)
    new_characters: List[NewCharacterPayload] = []   # 本章新出场、值得入库的配角
    chapter_index: Optional[ChapterIndexPayload] = None
    notes: Optional[str] = None           # 作者备注，存到 chapter
    #: 落库审计：队列自动复盘 / Tab 手动提交（缺省按 manual_tab 记）
    apply_source: Optional[Literal["queue_auto", "manual_tab"]] = None
    #: 复盘闭环：下一章要做的 patch 指令（由 auto_debrief 建议，前端可编辑后提交）
    next_chapter_directives: List[dict] = []  # [{outline_node_id, patch: {...}, reason}]
    #: 人物语风指纹沉淀：本章新出现的口头禅/台词样本，合并进 Character.speech_kit
    speech_kit_updates: List[dict] = []  # [{character_id, new_signature_words, new_sample_dialogues, evolution_note}]
    #: 读者期待管理：本章新做出的承诺（章末预告、卷末预告、名字暗示等）
    new_reader_promises: List[dict] = []  # [{promise_text, promise_type, expected_within_chapters, priority}]
    #: 承诺兑现闭环：本章已兑现的承诺原文（由 auto_debrief 提取，经前端确认后提交）
    #: apply_debrief 将对 open ReaderPromise 做模糊匹配并标记 fulfilled。
    fulfilled_promise_texts: List[str] = []
    #: auto_debrief 服务端将 fulfilled_promise_texts 解析为精确 ID 后写入缓存，
    #: 前端提交时带上 ID 可跳过二次模糊匹配，直接按主键更新，优先级高于文本匹配。
    fulfilled_promise_ids: List[str] = []


class AutoDebriefRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    force_refresh: bool = False
    #: 仅读 ChapterDebriefCache，不调用 LLM；用于写作页打开复盘 Tab 时恢复上次分析结果
    cache_only: bool = False
