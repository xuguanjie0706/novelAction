"""
Generation Service — 小说 AI 生成服务容器

Bootstrap 串行步进流程的 SSE 编排已迁移到 services/bootstrap/graph.py（LangGraph）。
本服务类作为步骤调用的容器（svc）持续使用：graph_nodes.py 通过 _make_svc() 构造实例，
再调用 svc._gen_* 代理方法（每个代理指向 steps/ 子包对应函数）。

向后兼容导出：旧代码通过 `generation_service._parse_json` 等模块属性访问的符号
由 __getattr__ 和顶层 import 维持。
"""
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_service import AIService
from app.models import Project, WorldSetting

# ── Bootstrap 子包：解析 / Prompt / 上下文（向后兼容 re-export）──────
from app.services.bootstrap.parse import (
    parse_json as _parse_json,
    coerce_power_system_rank as _coerce_power_system_rank,
    safe_int as _safe_int,
)
from app.services.bootstrap.prompts import (
    GEMINI_SETTING_BLUEPRINTS,
    SETTING_CARD_SCHEMA_BRIEF as _SETTING_CARD_SCHEMA_BRIEF,
    CHARACTER_TARGET,
    FACTION_MIN_TARGET,
    FACTION_MAX_TARGET,
    SKILL_MIN_TARGET,
    SKILL_MAX_TARGET,
    ITEM_MIN_TARGET,
    ITEM_MAX_TARGET,
    setting_blueprints_for_prompt as _setting_blueprints_for_prompt,
    setting_extra_with_defaults as _setting_extra_with_defaults,
    book_length_constraints_for_prompt as _book_length_constraints_for_prompt,
)
from app.services.bootstrap.context import (
    get_genre_kit_block as _get_genre_kit_block,
    hydrate_ctx_from_project as _hydrate_ctx_from_project_impl,
)


class GenerationService:
    def __init__(
        self,
        db: Session,
        model_profile: Literal["local", "gemini"] = "gemini",
        llm_provider_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ):
        """
        Args:
            db: SQLAlchemy Session
            model_profile: ``gemini``=远程（管理后台 provider 或 GEMINI_*）；``local``=可选本地兼容端点
            llm_provider_id: 远程 provider 行 id；与 model_profile 解耦
            user_id: 项目归属用户 id；多用户隔离的核心字段。新建 Project 时强制写入。
                兼容老流程允许传 None，但生产路径（/bootstrap/stream）必传。
        """
        self.db = db
        self.user_id = user_id
        ai_profile = "default" if model_profile == "local" else "gemini"
        self.ai = AIService(
            profile=ai_profile,
            db=db,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
        )

    def hydrate_ctx_from_project(self, project: Project) -> dict:
        """从已落库项目拼装 ctx，供「补生成设定卡」类接口复用。"""
        return _hydrate_ctx_from_project_impl(self.db, project)

    async def regenerate_world_settings(
        self,
        project: Project,
        *,
        mode: Literal["blueprint_replace", "blueprint_fill_missing", "append"],
        user_hint: str = "",
        append_count: int = 6,
    ) -> dict:
        """针对已有项目补写世界观设定卡（不落 Bootstrap SSE，仅单次写库）。"""
        ctx = self.hydrate_ctx_from_project(project)
        addon = (user_hint or "").strip()
        prompt_addon = f"【作者/测试附加说明】\n{addon}\n" if addon else ""

        from app.services.bootstrap.steps.settings import gen_settings, gen_settings_append

        if mode == "blueprint_replace":
            self.db.query(WorldSetting).filter(WorldSetting.project_id == project.id).delete(
                synchronize_session=False
            )
            self.db.commit()
            rows = await gen_settings(self, project, ctx, prompt_addon=prompt_addon)
            return {"mode": mode, "created_count": len(rows), "settings": rows}

        if mode == "blueprint_fill_missing":
            existing = {
                (s.title or "").strip()
                for s in self.db.query(WorldSetting).filter(WorldSetting.project_id == project.id).all()
            }
            missing = [bp for bp in GEMINI_SETTING_BLUEPRINTS if bp["title"] not in existing]
            if not missing:
                return {
                    "mode": mode,
                    "created_count": 0,
                    "message": "蓝图内标题均已存在，未生成新卡",
                    "settings": [],
                }
            rows = await gen_settings(
                self, project, ctx, blueprints=missing, prompt_addon=prompt_addon
            )
            return {"mode": mode, "created_count": len(rows), "settings": rows}

        n = max(3, min(12, int(append_count or 6)))
        hint = (user_hint or "").strip() or "补全世界观中尚未覆盖的细节，可与现有卡互补但不要逐句复述。"
        rows = await gen_settings_append(self, project, ctx, user_hint=hint, count=n)
        return {"mode": mode, "created_count": len(rows), "settings": rows}

    # ── Bootstrap SSE 编排已迁移到 services/bootstrap/graph.py ──────
    # 入口：POST /api/v1/bootstrap/runs（bootstrap_graph.py 路由）。
    # 本类保留作为 svc 容器：graph_nodes.py 通过 _make_svc() 构造后
    # 调用下方 _gen_* 代理方法，各方法再委托 steps/ 子包对应函数。
    # ────────────────────────────────────────────────────────────────

    async def _gen_positioning(self, ctx: dict):
        from app.services.bootstrap.steps.positioning import gen_positioning
        return await gen_positioning(self, ctx)

    async def _gen_project(self, ctx: dict):
        from app.services.bootstrap.steps.project import gen_project
        return await gen_project(self, ctx)

    async def _gen_power_systems(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.power_systems import gen_power_systems
        return await gen_power_systems(self, project, ctx)

    async def _gen_factions(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.factions import gen_factions
        return await gen_factions(self, project, ctx)

    async def _gen_storylines(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.storylines import gen_storylines
        return await gen_storylines(self, project, ctx)

    async def _gen_antagonist_ladder(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.antagonist_ladder import gen_antagonist_ladder
        return await gen_antagonist_ladder(self, project, ctx)

    async def _gen_characters(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.characters import gen_characters
        return await gen_characters(self, project, ctx)

    async def _gen_key_skills(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.skills import gen_key_skills
        return await gen_key_skills(self, project, ctx)

    async def _gen_key_items(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.items import gen_key_items
        return await gen_key_items(self, project, ctx)

    async def _gen_settings(self, project: Project, ctx: dict, **kwargs):
        from app.services.bootstrap.steps.settings import gen_settings
        return await gen_settings(self, project, ctx, **kwargs)

    async def _gen_settings_append(self, project: Project, ctx: dict, **kwargs):
        from app.services.bootstrap.steps.settings import gen_settings_append
        return await gen_settings_append(self, project, ctx, **kwargs)

    async def _gen_volumes(self, project: Project, ctx: dict, **kwargs):
        from app.services.bootstrap.steps.volumes import gen_volumes
        return await gen_volumes(self, project, ctx, **kwargs)

    async def _gen_memory(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.memory import gen_memory
        return await gen_memory(self, project, ctx)

    async def _gen_relations(self, project: Project, chars: list, ctx: dict):
        from app.services.bootstrap.steps.relations import gen_relations
        return await gen_relations(self, project, chars, ctx)

    async def _gen_opening_contract(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.opening_contract import gen_opening_contract
        return await gen_opening_contract(self, project, ctx)

    async def _gen_vol1_chapter_plans(self, project: Project, volumes: list, ctx: dict):
        from app.services.bootstrap.steps.vol1_chapter_plans import gen_vol1_chapter_plans
        return await gen_vol1_chapter_plans(self, project, volumes, ctx)

    async def _gen_ch1_scenes(self, project: Project, vol1_plans: list, ctx: dict):
        from app.services.bootstrap.steps.ch1_scenes import gen_ch1_scenes
        return await gen_ch1_scenes(self, project, vol1_plans, ctx)

    async def _gen_consistency_scan(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.consistency_scan import gen_consistency_scan
        return await gen_consistency_scan(self, project, ctx)

    async def _gen_emotion_arc(self, project: Project, ctx: dict, *, persist: bool = True):
        from app.services.bootstrap.steps.emotion_arc import gen_emotion_arc
        return await gen_emotion_arc(self, project, ctx, persist=persist)

    async def _gen_villain_arc(self, project: Project, ctx: dict, *, persist: bool = True):
        from app.services.bootstrap.steps.villain_arc import gen_villain_arc
        return await gen_villain_arc(self, project, ctx, persist=persist)

    async def _gen_core_mysteries(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.core_mysteries import gen_core_mysteries
        return await gen_core_mysteries(self, project, ctx)

    async def _call_with_retry(
        self,
        system: str,
        prompt: str,
        max_retries: int = 2,
        max_tokens: int = 2048,
        *,
        task: Optional[str] = None,
    ) -> str:
        """调用 AI，外层失败时做一次补偿重试（详见 ``bootstrap.retry``）。"""
        from app.services.bootstrap.retry import call_with_retry
        return await call_with_retry(self.ai, system, prompt, max_tokens=max_tokens, task=task)


def __getattr__(name: str):
    """兼容旧代码对 GEMINI_SETTING_COMPLETION_MAX_TOKENS 的模块级访问。"""
    if name == "GEMINI_SETTING_COMPLETION_MAX_TOKENS":
        return settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
