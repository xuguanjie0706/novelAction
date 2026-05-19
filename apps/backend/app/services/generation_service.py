"""
Generation Service — 一句话创意 → 全量小说初始化

方案 A (sequential): 多步串行，每步独立 prompt；线路由 AIService(model_profile, llm_provider_id) 决定
方案 B (single_shot): 单次全量生成，默认推荐；线路同上

SSE 事件格式:
  {"event": "step_start", "step": "project",  "label": "生成项目基础信息..."}
  {"event": "step_done",  "step": "project",  "count": 1, "preview": "《书名》玄幻"}
  {"event": "complete",   "project_id": "uuid"}
  {"event": "error",      "step": "characters", "message": "..."}
"""
import asyncio
from typing import AsyncGenerator, Literal, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_service import AIService
from app.models import Project, WorldSetting

# ── Bootstrap 子包：解析 / SSE / Prompt / 上下文 ────────────────────
from app.services.bootstrap.parse import (
    parse_json as _parse_json,
    coerce_power_system_rank as _coerce_power_system_rank,
    safe_int as _safe_int,
)
from app.services.bootstrap.sse import sse as _sse
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
    single_shot_prompt as _single_shot_prompt,
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

    async def bootstrap(
        self,
        logline: str,
        premise: str = "",
        mode: Literal["sequential", "single_shot"] = "sequential",
        target_words: int = 1_200_000,
    ) -> AsyncGenerator[str, None]:
        if mode == "single_shot":
            async for chunk in self._single_shot(logline, premise, target_words=target_words):
                yield chunk
        else:
            async for chunk in self._sequential(logline, premise, target_words=target_words):
                yield chunk

    async def _sequential(self, logline: str, premise: str = "", target_words: int = 1_200_000) -> AsyncGenerator[str, None]:
        ctx = {"logline": logline, "premise": premise, "target_words": target_words}
        project = None

        try:
            yield _sse("step_start", step="positioning", label="召开立项会议（题材定位）...")
            positioning = await self._gen_positioning(ctx)
            ctx["positioning"] = positioning
            yield _sse(
                "step_done",
                step="positioning",
                count=1,
                preview=positioning.get("selling_point", "")[:30] if positioning else "",
            )

            yield _sse("step_start", step="project", label="生成项目基础信息...")
            project, ctx = await self._gen_project(ctx)
            yield _sse("step_done", step="project", count=1,
                       preview=f"《{project.title}》{project.genre}")

            yield _sse("step_start", step="power_systems", label="生成境界体系...")
            try:
                power_systems = await asyncio.wait_for(
                    self._gen_power_systems(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="power_systems", message="境界体系生成超时（3分钟），已跳过")
                power_systems = []
            except Exception as e:
                yield _sse("error", step="power_systems", message=f"境界体系生成失败：{e}")
                power_systems = []
            yield _sse("step_done", step="power_systems", count=len(power_systems),
                       preview=power_systems[0].name if power_systems else "（跳过）")

            yield _sse("step_start", step="factions", label="生成势力体系...")
            try:
                factions = await asyncio.wait_for(
                    self._gen_factions(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="factions", message="势力生成超时（3分钟），已跳过")
                factions = []
            except Exception as e:
                yield _sse("error", step="factions", message=f"势力生成失败：{e}")
                factions = []
            yield _sse("step_done", step="factions", count=len(factions),
                       preview="、".join(f.name for f in factions[:3]) if factions else "（跳过）")

            yield _sse("step_start", step="storylines", label="生成故事线...")
            try:
                storylines = await asyncio.wait_for(
                    self._gen_storylines(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="storylines", message="故事线生成超时（3分钟），已跳过")
                storylines = []
            except Exception as e:
                yield _sse("error", step="storylines", message=f"故事线生成失败：{e}")
                storylines = []
            yield _sse("step_done", step="storylines", count=len(storylines))

            yield _sse("step_start", step="characters", label="生成人物库...")
            try:
                chars = await asyncio.wait_for(
                    self._gen_characters(project, ctx),
                    timeout=240.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="characters", message="人物生成超时（4分钟），已跳过")
                chars = []
            except Exception as e:
                yield _sse("error", step="characters", message=f"人物生成失败：{e}")
                chars = []
            ctx.setdefault("protagonist", "主角")
            yield _sse("step_done", step="characters", count=len(chars),
                       preview="、".join(c.name for c in chars[:3]) if chars else "（跳过）")

            yield _sse("step_start", step="skills", label="生成核心功法技能...")
            yield _sse("step_start", step="items", label="生成关键道具法宝...")
            try:
                si_results = await asyncio.wait_for(
                    asyncio.gather(
                        self._gen_key_skills(project, ctx),
                        self._gen_key_items(project, ctx),
                        return_exceptions=True,
                    ),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                for step_name in ("skills", "items"):
                    yield _sse("error", step=step_name, message="并行生成超时（3分钟），已跳过")
                si_results = [[], []]
            skills = si_results[0] if not isinstance(si_results[0], BaseException) else []
            items = si_results[1] if not isinstance(si_results[1], BaseException) else []
            for step_name, result in zip(("skills", "items"), si_results):
                if isinstance(result, BaseException):
                    yield _sse("error", step=step_name, message=f"生成失败：{result}")
            yield _sse("step_done", step="skills", count=len(skills))
            yield _sse("step_done", step="items", count=len(items))

            yield _sse("step_start", step="settings", label="生成世界观设定卡...")
            try:
                settings_rows = await asyncio.wait_for(
                    self._gen_settings(project, ctx),
                    timeout=270.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="settings", message="世界观设定生成超时（4.5分钟），已跳过")
                settings_rows = []
            except Exception as e:
                yield _sse("error", step="settings", message=f"世界观设定生成失败：{e}")
                settings_rows = []
            if not ctx.get("settings_summary"):
                ctx["settings_summary"] = "（世界观设定生成失败）"
            yield _sse("step_done", step="settings", count=len(settings_rows))

            yield _sse("step_start", step="volumes", label="规划卷级结构...")
            try:
                nodes = await asyncio.wait_for(
                    self._gen_volumes(project, ctx),
                    timeout=240.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="volumes", message="卷级结构生成超时（4分钟），已跳过")
                nodes = []
            except Exception as e:
                yield _sse("error", step="volumes", message=f"卷级结构生成失败：{e}")
                nodes = []
            yield _sse("step_done", step="volumes", count=len(nodes),
                       preview=f"共{len(nodes)}卷" if nodes else "（跳过）")

            yield _sse("step_start", step="memory", label="生成记忆库种子...")
            try:
                mems = await asyncio.wait_for(
                    self._gen_memory(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="memory", message="记忆库生成超时（3分钟），已跳过")
                mems = []
            except Exception as e:
                yield _sse("error", step="memory", message=f"记忆库生成失败：{e}")
                mems = []
            yield _sse("step_done", step="memory", count=len(mems))

            yield _sse("step_start", step="relations", label="建立人物关系...")
            try:
                rels = await asyncio.wait_for(
                    self._gen_relations(project, chars, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="relations", message="人物关系生成超时（3分钟），已跳过")
                rels = []
            except Exception as e:
                yield _sse("error", step="relations", message=f"人物关系生成失败：{e}")
                rels = []
            yield _sse("step_done", step="relations", count=len(rels))

            yield _sse("step_start", step="opening_contract", label="规划开局追读承诺...")
            try:
                opening_contract = await asyncio.wait_for(
                    self._gen_opening_contract(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="opening_contract", message="开局承诺生成超时（3分钟），已跳过")
                opening_contract = {}
            except Exception as e:
                yield _sse("error", step="opening_contract", message=f"开局承诺生成失败：{e}")
                opening_contract = {}
            yield _sse(
                "step_done",
                step="opening_contract",
                count=1 if opening_contract else 0,
                preview=opening_contract.get("chapter1_hook", "")[:30] if opening_contract else "（跳过）",
            )

            yield _sse("step_start", step="vol1_chapters", label="生成第一卷章级大纲...")
            try:
                vol1_plans = await asyncio.wait_for(
                    self._gen_vol1_chapter_plans(project, nodes, ctx),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="vol1_chapters", message="章级大纲生成超时（5分钟），已跳过")
                vol1_plans = []
            except Exception as e:
                yield _sse("error", step="vol1_chapters", message=f"章级大纲生成失败：{e}")
                vol1_plans = []
            yield _sse(
                "step_done",
                step="vol1_chapters",
                count=len(vol1_plans),
                preview=f"第一卷共{len(vol1_plans)}章蓝图" if vol1_plans else "（跳过）",
            )

            yield _sse("step_start", step="ch1_scenes", label="生成第1章场景蓝图...")
            try:
                ch1_scenes = await asyncio.wait_for(
                    self._gen_ch1_scenes(project, vol1_plans, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="ch1_scenes", message="场景蓝图生成超时（3分钟），已跳过")
                ch1_scenes = []
            except Exception as e:
                yield _sse("error", step="ch1_scenes", message=f"场景蓝图生成失败：{e}")
                ch1_scenes = []
            yield _sse(
                "step_done",
                step="ch1_scenes",
                count=len(ch1_scenes),
                preview=f"第1章共{len(ch1_scenes)}场" if ch1_scenes else "（跳过）",
            )

            yield _sse("step_start", step="consistency", label="全局一致性扫描...")
            try:
                consistency_issues = await asyncio.wait_for(
                    self._gen_consistency_scan(project, ctx),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse("error", step="consistency", message="一致性扫描超时（3分钟），已跳过")
                consistency_issues = []
            except Exception as e:
                yield _sse("error", step="consistency", message=f"一致性扫描失败：{e}")
                consistency_issues = []
            yield _sse(
                "step_done",
                step="consistency",
                count=len(consistency_issues),
                preview=f"发现{len(consistency_issues)}处需确认项" if consistency_issues else "无明显矛盾",
            )

            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            if project is not None:
                yield _sse("error", message=f"生成中断（{e}），已完成部分内容已保存", partial=True)
                yield _sse("complete", project_id=str(project.id), partial=True)
            else:
                yield _sse("error", message=str(e))

    async def _single_shot(self, logline: str, premise: str = "", target_words: int = 1_200_000) -> AsyncGenerator[str, None]:
        yield _sse("step_start", step="all", label="AI 全量生成中（单次调用）...")

        system = """你是专业的网络小说策划，根据一句话创意生成完整的小说初始化数据。
严格返回 JSON，不要任何额外文字。"""
        prompt = _single_shot_prompt(logline, premise, target_words=target_words)

        try:
            raw = await self.ai._call_ai(
                system,
                prompt,
                max_tokens=settings.GEMINI_SINGLE_SHOT_MAX_TOKENS,
                context={"operation": "bootstrap_single_shot"},
                task="bootstrap.single_shot",
            )
            data = _parse_json(raw)
            from app.services.bootstrap import completion
            data = await completion.complete_single_shot_data(self.ai, data, logline, premise)
            yield _sse("step_done", step="all", count=1)

            yield _sse("step_start", step="saving", label="写入数据库...")
            from app.services.bootstrap import save_all
            project = await save_all.save_all(self, data, logline, premise, target_words=target_words)
            yield _sse("step_done", step="saving", count=1)
            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            yield _sse("error", step="all", message=str(e))

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

    async def _gen_volumes(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.volumes import gen_volumes
        return await gen_volumes(self, project, ctx)

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

    async def _gen_emotion_arc(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.emotion_arc import gen_emotion_arc
        return await gen_emotion_arc(self, project, ctx)

    async def _gen_villain_arc(self, project: Project, ctx: dict):
        from app.services.bootstrap.steps.villain_arc import gen_villain_arc
        return await gen_villain_arc(self, project, ctx)

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
    """兼容旧代码对 GEMINI_*_MAX_TOKENS 的模块级访问（值来自 Settings / 环境变量）。"""
    if name == "GEMINI_SINGLE_SHOT_MAX_TOKENS":
        return settings.GEMINI_SINGLE_SHOT_MAX_TOKENS
    if name == "GEMINI_SETTING_COMPLETION_MAX_TOKENS":
        return settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
