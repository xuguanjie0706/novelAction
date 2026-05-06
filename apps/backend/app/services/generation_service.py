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
import json
import re
from typing import AsyncGenerator, Literal, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_service import AIService
from app.services.genre_kit import get_genre_kit, normalize_genre, render_kit_for_prompt
from app.utils.chapter_numbering import normalize_chapter_plan_title
from app.models import (
    Project, WorldSetting, Character, CharacterRelationship,
    OutlineNode, MemoryChunk, PowerSystem, StoryLine,
    Faction, Skill, Item, ReaderPromise, Scene
)


# ─────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────

def _parse_json(text: str):
    """容错 JSON 解析：去 markdown fence、去 think 标签、strip 空白"""
    # 去掉 <think>...</think>（部分兼容端点会输出 think 块）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    # 去掉 ```json ... ``` 或 ``` ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        text = fence.group(1).strip()
    # 找第一个 { 或 [ 开始截取
    start = min(
        (text.find("{") if text.find("{") != -1 else len(text)),
        (text.find("[") if text.find("[") != -1 else len(text)),
    )
    text = text[start:]
    return json.loads(text)


def _get_genre_kit_block(ctx: dict) -> str:
    """返回 genre_kit 的 prompt 注入块，若 ctx 中已有则直接使用"""
    kit_prompt = ctx.get("genre_kit_prompt")
    if kit_prompt:
        return f"\n{kit_prompt}\n"
    # 兜底：如果 ctx 里还没有（早期步骤），尝试从 genre 生成
    genre = ctx.get("genre")
    if genre:
        from app.services.genre_kit import get_genre_guardrail
        return "\n" + get_genre_guardrail(genre) + "\n"
    return ""


def _coerce_power_system_rank(value, levels: list, default: int | None) -> int | None:
    """
    DB 列 protagonist_*_rank 为 Integer，须对应 levels[].rank。
    LLM 常误填境界中文名；此处尽量解析为整数，失败则回退 default。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            pass
        norm_levels = [lv for lv in (levels or []) if isinstance(lv, dict)]
        for lv in norm_levels:
            name = (lv.get("name") or "").strip()
            if not name:
                continue
            if s == name or name in s or s in name:
                r = lv.get("rank")
                if isinstance(r, int):
                    return r
                try:
                    return int(r)
                except (TypeError, ValueError):
                    continue
    return default


def _safe_int(
    value,
    default: int | None = None,
    *,
    min_v: int | None = None,
    max_v: int | None = None,
) -> int | None:
    """
    单次生成 JSON 里 Integer 字段常被写成字符串或非数字文案；
    尽量解析为 int，失败则 default；可选 min/max 裁剪。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        out = value
    elif isinstance(value, float) and value == int(value):
        out = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            out = int(s)
        except ValueError:
            m = re.search(r"-?\d+", s)
            if not m:
                return default
            out = int(m.group(0))
    else:
        return default
    if min_v is not None:
        out = max(min_v, out)
    if max_v is not None:
        out = min(max_v, out)
    return out


def _sse(event: str, **kwargs) -> str:
    payload = {"event": event, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


GEMINI_SETTING_BLUEPRINTS = [
    {"title": "作品立意", "category": "世界背景", "tags": ["立意", "主题"], "importance": "core", "stage": "full", "section": "core", "purpose": "锁定作品承诺、核心矛盾、读者钩子和禁忌边界。"},
    {"title": "世界底层规则", "category": "规则法则", "tags": ["规则", "法则"], "importance": "core", "stage": "full", "section": "focus", "purpose": "定义所有角色必须遵守的硬规则、代价和例外。"},
    {"title": "时代格局与阶层结构", "category": "世界背景", "tags": ["时代", "阶层"], "importance": "core", "stage": "full", "section": "focus", "purpose": "说明世界为什么不公平，主角从哪里被压迫。"},
    {"title": "主角起点生存环境", "category": "世界背景", "tags": ["起点", "生存"], "importance": "core", "stage": "early", "section": "focus", "purpose": "提供开篇十章可直接使用的生活压力、羞辱和资源限制。"},
    {"title": "大陆地图与地缘格局", "category": "地理场景", "tags": ["地图", "地理"], "importance": "core", "stage": "full", "section": "focus", "purpose": "给出大地图、路线方向、资源分布和势力边界。"},
    {"title": "开篇城镇与日常空间", "category": "地理场景", "tags": ["城镇", "开篇"], "importance": "major", "stage": "early", "section": "focus", "purpose": "沉淀主角开局活动区、街巷、家族/宗门/市集场景。"},
    {"title": "核心宗门或学院地貌", "category": "地理场景", "tags": ["宗门", "学院"], "importance": "major", "stage": "early", "section": "focus", "purpose": "给修炼、考核、冲突和师承关系提供稳定舞台。"},
    {"title": "禁地与高危秘境", "category": "地理场景", "tags": ["禁地", "秘境"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "准备升级副本、伏笔揭示和关键资源争夺。"},
    {"title": "交通路径与边境关卡", "category": "地理场景", "tags": ["交通", "边境"], "importance": "major", "stage": "full", "section": "focus", "purpose": "约束角色移动速度、追杀路线和跨区域代价。"},
    {"title": "远古战争与失落真相", "category": "历史传说", "tags": ["远古", "战争"], "importance": "core", "stage": "full", "section": "focus", "purpose": "埋下全书级谜团、反派根源和世界现状成因。"},
    {"title": "被篡改的官方历史", "category": "历史传说", "tags": ["历史", "谎言"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "制造信息差，让读者持续追问真相。"},
    {"title": "民间传说与危险谣言", "category": "历史传说", "tags": ["传说", "谣言"], "importance": "flavor", "stage": "early", "section": "focus", "purpose": "给路人谈资、地方恐惧和小伏笔提供素材。"},
    {"title": "禁忌人物或失踪先贤", "category": "历史传说", "tags": ["先贤", "禁忌"], "importance": "major", "stage": "full", "section": "focus", "purpose": "连接主角传承、反派阴影和后期真相。"},
    {"title": "宗门礼法与等级称谓", "category": "文化风俗", "tags": ["礼法", "称谓"], "importance": "major", "stage": "early", "section": "focus", "purpose": "让对话、羞辱、拜师和处罚有具体制度感。"},
    {"title": "民俗节庆与公共仪式", "category": "文化风俗", "tags": ["节庆", "仪式"], "importance": "flavor", "stage": "full", "section": "focus", "purpose": "提供大型场景、社交冲突和视觉记忆点。"},
    {"title": "交易习惯与黑市规矩", "category": "文化风俗", "tags": ["交易", "黑市"], "importance": "major", "stage": "full", "section": "focus", "purpose": "支撑拍卖、情报、赃物、资源兑换和风险。"},
    {"title": "婚盟血誓与家族规训", "category": "文化风俗", "tags": ["家族", "誓约"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "制造人物选择、亲情束缚和势力联姻矛盾。"},
    {"title": "资源经济与稀缺机制", "category": "规则法则", "tags": ["资源", "经济"], "importance": "core", "stage": "full", "section": "focus", "purpose": "解释修炼资源如何流通、垄断和剥削。"},
    {"title": "誓约契约与违约反噬", "category": "规则法则", "tags": ["誓约", "契约"], "importance": "major", "stage": "full", "section": "focus", "purpose": "给承诺、背叛、交易和审判提供硬约束。"},
    {"title": "突破副作用与失败代价", "category": "规则法则", "tags": ["突破", "代价"], "importance": "core", "stage": "full", "section": "focus", "purpose": "防止升级廉价化，让每次变强有代价。"},
    {"title": "信息禁区与知识垄断", "category": "规则法则", "tags": ["禁区", "知识"], "importance": "major", "stage": "mid", "section": "focus", "purpose": "解释秘密为何难以公开，制造调查阻力。"},
    {"title": "妖兽生态与危险等级", "category": "其他", "tags": ["妖兽", "生态"], "importance": "major", "stage": "full", "section": "focus", "purpose": "提供野外战斗、材料来源和环境压迫。"},
    {"title": "职业体系与底层营生", "category": "其他", "tags": ["职业", "民生"], "importance": "flavor", "stage": "full", "section": "focus", "purpose": "让世界不只围着修炼者转，补足普通人的生活。"},
    {"title": "终局神话与世界边界", "category": "其他", "tags": ["终局", "边界"], "importance": "core", "stage": "late", "section": "focus", "purpose": "预埋后期地图扩展、终极敌人和结局余味。"},
]

CHARACTER_TARGET = 8
FACTION_MIN_TARGET = 4
FACTION_MAX_TARGET = 6
SKILL_MIN_TARGET = 5
SKILL_MAX_TARGET = 8
ITEM_MIN_TARGET = 5
ITEM_MAX_TARGET = 8
def _setting_blueprints_for_prompt() -> str:
    return json.dumps(GEMINI_SETTING_BLUEPRINTS, ensure_ascii=False, indent=2)


def _book_length_constraints_for_prompt(target_words: int) -> str:
    """写入 LLM：premise「类型与篇幅」必须与项目 target_words 一致，避免默认套用网文超长篇区间。"""
    from app.services.outline_planning import words_to_plan

    tw = max(1, int(target_words or 1_200_000))
    plan = words_to_plan(tw)
    approx_wan = round(tw / 10_000)
    return (
        f"【全书字数目标（硬性约束）】全书计划总字数为 {tw:,} 字（约 {approx_wan} 万字），"
        f"按当前规划约 {plan['total_chapters']} 章、{plan['total_volumes']} 卷。\n"
        "premise 中的「类型与篇幅」必须与上述总字数一致：用该字数规模（或与之等价的单一区间，且上下限均不得偏离该目标一个数量级）描述篇幅，"
        "禁止写「三百万—五百万字」「数百万字」「千万字级」等与上述目标明显矛盾的常见超长篇口径；"
        "若题材常见于超长篇，仍须按本项目既定总字数收敛叙事尺度（地图换代、支线数量与之匹配），不得暗示必须写到更高字数才能讲完。"
    )


def _setting_extra_with_defaults(item: dict) -> dict:
    extra = item.get("extra", {})
    if not isinstance(extra, dict):
        extra = {}
    matching = next(
        (bp for bp in GEMINI_SETTING_BLUEPRINTS if bp["title"] == item.get("title")),
        None,
    )
    if matching:
        extra = {
            "schema_version": 2,
            **extra,
            "category": matching["category"],
            "importance": matching["importance"],
            "stage": matching["stage"],
        }
    else:
        extra = {"schema_version": 2, **extra}
    # 揭示节奏字段（v3，若 AI 生成时填写则保留，否则给空字符串占位）
    extra.setdefault("reveal_timing", "")      # 本设定何时/以何种情节方式向读者/主角揭示
    extra.setdefault("who_knows_now", "")      # 故事开篇时哪些角色/势力知道这一设定
    return extra


def _single_shot_prompt(logline: str, premise: str = "", target_words: int = 1_200_000) -> str:
    from app.services.outline_planning import words_to_plan
    plan = words_to_plan(target_words)
    n_volumes = plan["total_volumes"]
    total_chapters_hint = plan["total_chapters"]
    setting_blueprints = _setting_blueprints_for_prompt()
    return f"""根据以下创意，生成完整的小说初始化数据：

创意：{logline}
立意与类型（作品基本面）：{premise[:2000] or '（未填写，请根据创意自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}
【全书字数目标】{target_words:,}字，折合约{total_chapters_hint}章
{_book_length_constraints_for_prompt(target_words)}

返回一个 JSON 对象，顶层字段固定为：
project, power_systems, factions, storylines, skills, items, characters, settings, outline, memory, relations。

下面是字段结构说明，不代表数组数量；数组数量必须遵守后面的硬性数量规则。

project 字段结构：
{{
  "title": "小说名称",
  "genre": "玄幻",
  "logline": "{logline}",
  "premise": "立意与类型（含作品定位、主题命题、核心矛盾、禁忌边界，可落地，至少200字）；其中「类型与篇幅」必须严格服从上方【全书字数目标（硬性约束）】",
  "world_overview": "世界观简述（300~500字）",
  "story_core": {{"drive": "故事驱动力", "conflict": "核心矛盾", "theme": "主题", "differentiation": "差异化"}}
}}

power_systems 每个元素字段：
name, system_type, description, cultivation_method, breakthrough_condition, special_rules,
protagonist_start_rank, protagonist_end_rank, levels。
protagonist_start_rank 与 protagonist_end_rank 必须是整数（与 levels 中某一层的 rank 一致），禁止写境界中文名。
levels 至少 6 个层级，每层包含 rank, name, description, requirements, abilities, sub_level_count。

factions 每个元素字段：
name, faction_type, alignment, active_period, description, territory, strength_level,
member_count, top_power, goals, resources, history, secrets, rivals, allies, attitude_to_protagonist。

storylines 每个元素字段：
name, line_type, description, core_conflict, resolution_direction, status, start_chapter。

skills 每个元素字段：
name, skill_type, grade, source, level_required, prerequisites, description, effects, limitations, mastered_by。

items 每个元素字段：
name, item_type, rarity, description, origin, effects, limitations, story_significance, current_owner, status。

characters 每个元素字段：
name, role, character_tier, gender, age, faction, personality, background, motivation, arc, current_realm,
speech_style, values, fear, secrets, strengths, weaknesses, special_traits。
role 只能是: protagonist / supporting / antagonist
character_tier 代表该人物在全书中的叙事层级，只能是以下4个值之一：
core=核心长线（贯穿全书，驱动主线，如主角/主反派/固定伙伴）；
arc=弧线支柱（某卷/某段主导剧情，随弧线结束淡出）；
plot=剧情推手（短期推进特定情节后退场）；
background=背景填充（丰富世界氛围，无强情节绑定）。
请根据每个人物实际定位严格判断，不要全部填 core。

settings 每个元素字段：
title, content, tags, extra。
"作品立意" 必须填写 extra.core 全字段；其他设定卡必须填写 extra.focus 全字段。
所有 settings 都必须写入 extra.schema_version=2、extra.category、extra.importance、extra.stage。

outline 每个元素字段：
title, sort_order, summary, hook, conflict, planned_chapters。planned_chapters 只能是 30 或 60。

memory 每个元素字段：
memory_type, title, content, tags。

relations 每个元素字段：
from_name, to_name, relation_type, description, intensity。

硬性数量规则：
- factions 必须生成 {FACTION_MIN_TARGET}~{FACTION_MAX_TARGET} 个，涵盖主角阵营、反派阵营、中立阵营；active_period 只能是 early/mid/late/full。
- storylines 必须生成 3~5 条，必须有且只有 1 条 main。
- skills 必须生成 {SKILL_MIN_TARGET}~{SKILL_MAX_TARGET} 个关键技能。
- items 必须生成 {ITEM_MIN_TARGET}~{ITEM_MAX_TARGET} 个关键道具。
- characters 必须生成 {CHARACTER_TARGET} 个：1 主角、3 核心配角、2 反派、2 师长/势力角色。
- settings 必须生成 {len(GEMINI_SETTING_BLUEPRINTS)} 张，严格按以下【世界设定蓝图】顺序生成，不要少卡，不要合并卡。
- outline 必须恰好生成 {n_volumes} 卷（由目标字数推算，不得增减），所有卷 planned_chapters 之和须尽量接近{total_chapters_hint}章。
- memory 必须生成 10 条初始记忆库种子。

世界设定蓝图：
{setting_blueprints}

settings 规则：
1) 每张卡 title/category/tags/importance/stage 必须与蓝图一致，写入 extra。
2) 每张卡 content 至少180字，要有可写进正文的名词、地点、制度、代价、例外或冲突。
3) WorldSetting 只写没有专属表承载的叙事世界圣经；不要把势力档案、功法、道具整段重复进 settings。

只返回 JSON，不要解释，不要 markdown fence。"""




# ─────────────────────────────────────────────────────────────
#  主服务类
# ─────────────────────────────────────────────────────────────

class GenerationService:
    def __init__(
        self,
        db: Session,
        model_profile: Literal["local", "gemini"] = "local",
        llm_provider_id: Optional[UUID] = None,
    ):
        self.db = db
        ai_profile = "default" if model_profile == "local" else "gemini"
        self.ai = AIService(profile=ai_profile, db=db, llm_provider_id=llm_provider_id)

    # ══════════════════════════════════════════════════════════
    #  入口：根据 mode 分发
    # ══════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════
    #  方案 A：串行步进
    # ══════════════════════════════════════════════════════════

    async def _sequential(self, logline: str, premise: str = "", target_words: int = 1_200_000) -> AsyncGenerator[str, None]:
        ctx = {"logline": logline, "premise": premise, "target_words": target_words}   # 上下文在步骤间传递

        try:
            # Step 0 — 立项会议（题材定位 / 受众画像 / 爽点节奏）
            # 必须放在所有设定生成之前：让"目标读者→爽点类型→打脸频率→情感线占比→节奏类型"
            # 作为后续 11 步的全局约束，避免每步独立猜定位导致题材漂移。
            yield _sse("step_start", step="positioning", label="召开立项会议（题材定位）...")
            positioning = await self._gen_positioning(ctx)
            ctx["positioning"] = positioning
            yield _sse(
                "step_done",
                step="positioning",
                count=1,
                preview=positioning.get("selling_point", "")[:30] if positioning else "",
            )

            # Step 1 — 项目基础
            yield _sse("step_start", step="project", label="生成项目基础信息...")
            project, ctx = await self._gen_project(ctx)
            yield _sse("step_done", step="project", count=1,
                       preview=f"《{project.title}》{project.genre}")

            # Step 2 — 境界体系（先生成，后续步骤都要引用境界名）
            yield _sse("step_start", step="power_systems", label="生成境界体系...")
            power_systems = await self._gen_power_systems(project, ctx)
            yield _sse("step_done", step="power_systems", count=len(power_systems),
                       preview=power_systems[0].name if power_systems else "")

            # Step 3 — 势力（结构化，供人物 faction_id 引用）
            yield _sse("step_start", step="factions", label="生成势力体系...")
            factions = await self._gen_factions(project, ctx)
            yield _sse("step_done", step="factions", count=len(factions),
                       preview="、".join(f.name for f in factions[:3]))

            # Step 4 — 故事线（先于人物和大纲，供 storyline_ids 引用真实 UUID）
            yield _sse("step_start", step="storylines", label="生成故事线...")
            storylines = await self._gen_storylines(project, ctx)
            yield _sse("step_done", step="storylines", count=len(storylines))

            # Step 5 — 人物
            yield _sse("step_start", step="characters", label="生成人物库...")
            chars = await self._gen_characters(project, ctx)
            yield _sse("step_done", step="characters", count=len(chars),
                       preview="、".join(c.name for c in chars[:3]))

            # Step 6 — 核心技能/功法
            yield _sse("step_start", step="skills", label="生成核心功法技能...")
            skills = await self._gen_key_skills(project, ctx)
            yield _sse("step_done", step="skills", count=len(skills))

            # Step 7 — 关键道具/法宝
            yield _sse("step_start", step="items", label="生成关键道具法宝...")
            items = await self._gen_key_items(project, ctx)
            yield _sse("step_done", step="items", count=len(items))

            # Step 8 — 世界观设定卡（纯叙事类，无专属表的内容）
            yield _sse("step_start", step="settings", label="生成世界观设定卡...")
            settings = await self._gen_settings(project, ctx)
            yield _sse("step_done", step="settings", count=len(settings))

            # Step 9 — 卷级骨架
            yield _sse("step_start", step="volumes", label="规划卷级结构...")
            nodes = await self._gen_volumes(project, ctx)
            yield _sse("step_done", step="volumes", count=len(nodes),
                       preview=f"共{len(nodes)}卷")

            # Step 10 — 记忆库种子
            yield _sse("step_start", step="memory", label="生成记忆库种子...")
            mems = await self._gen_memory(project, ctx)
            yield _sse("step_done", step="memory", count=len(mems))

            # Step 11 — 人物关系
            yield _sse("step_start", step="relations", label="建立人物关系...")
            rels = await self._gen_relations(project, chars, ctx)
            yield _sse("step_done", step="relations", count=len(rels))

            # Step 12 — 开局前十章追读承诺清单
            # ⚠️ 必须在 vol1_chapters（Step 12.5）之前运行：chapter_plan 生成需要读取承诺节点
            yield _sse("step_start", step="opening_contract", label="规划开局追读承诺...")
            opening_contract = await self._gen_opening_contract(project, ctx)
            yield _sse(
                "step_done",
                step="opening_contract",
                count=1,
                preview=opening_contract.get("chapter1_hook", "")[:30] if opening_contract else "",
            )

            # Step 12.5 — 第一卷章级大纲（chapter_plan OutlineNode）
            # 位于关系生成（relation_triggers）和承诺清单（opening_contract）之后，
            # 两者都已写入 ctx，chapter_plan 可以按章号精确锚定冲突节点和钩子要求
            yield _sse("step_start", step="vol1_chapters", label="生成第一卷章级大纲...")
            vol1_plans = await self._gen_vol1_chapter_plans(project, nodes, ctx)
            yield _sse(
                "step_done",
                step="vol1_chapters",
                count=len(vol1_plans),
                preview=f"第一卷共{len(vol1_plans)}章蓝图" if vol1_plans else "生成失败",
            )

            # Step 13 — 第1章场景蓝图（Scene records）
            # 依赖 vol1_plans[0]（第1章 OutlineNode）；chapter_id=null，写章时再绑定
            yield _sse("step_start", step="ch1_scenes", label="生成第1章场景蓝图...")
            ch1_scenes = await self._gen_ch1_scenes(project, vol1_plans, ctx)
            yield _sse(
                "step_done",
                step="ch1_scenes",
                count=len(ch1_scenes),
                preview=f"第1章共{len(ch1_scenes)}场" if ch1_scenes else "生成失败",
            )

            # Step 14 — 全局一致性扫描（交叉核验所有生成物的关键字段）
            yield _sse("step_start", step="consistency", label="全局一致性扫描...")
            consistency_issues = await self._gen_consistency_scan(project, ctx)
            yield _sse(
                "step_done",
                step="consistency",
                count=len(consistency_issues),
                preview=f"发现{len(consistency_issues)}处需确认项" if consistency_issues else "无明显矛盾",
            )

            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            # 不传 step：前端对 unknown 等未映射 step 曾静默丢弃错误
            yield _sse("error", message=str(e))

    # ══════════════════════════════════════════════════════════
    #  方案 B：单次全量（适合 Gemini）
    # ══════════════════════════════════════════════════════════

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
            data = await self._complete_single_shot_data(data, logline, premise)
            yield _sse("step_done", step="all", count=1)

            yield _sse("step_start", step="saving", label="写入数据库...")
            project = await self._save_all(data, logline, premise, target_words=target_words)
            yield _sse("step_done", step="saving", count=1)
            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            yield _sse("error", step="all", message=str(e))

    # ══════════════════════════════════════════════════════════
    #  Step 0 — 立项会议（题材定位）
    # ══════════════════════════════════════════════════════════

    async def _gen_positioning(self, ctx: dict) -> dict:
        """召开立项会议：从 logline 推出读者画像 / 爽点类型 / 打脸频率 / 情感线占比 / 节奏。

        本步骤的产物 (``ctx['positioning']``) 必须在后续所有 Bootstrap 步骤的 prompt 中
        作为全局约束注入，并在写章节 prompt 中作为「作品基本面」每章贯彻——这是网文
        系统区别于"AI 自由发挥"的关键。

        Returns:
            dict 包含字段：
              target_audience, tropes, reference_works, selling_point,
              face_slap_pattern, emotional_arc, pace_type, taboo_lines,
              market_risk, differentiation_durability, hook_test（v3.1 新增，市场可行性评估）。
            字段缺失或解析失败时回退为空 dict（写章节路径会优雅降级）。
        """
        system = (
            "你是有30年经验的网络小说总编辑。从一句话创意推导出可执行的题材定位，"
            "只返回 JSON，不要任何解释文字。"
        )
        prompt = f"""创意：{ctx['logline']}
作者补充：{(ctx.get('premise') or '')[:600] or '（未填写，请独立推导）'}

请基于以上创意，做一次「立项会议」决策，返回 JSON：
{{
  "target_audience": "目标读者画像（性别/年龄段/平台调性，例：男频 18-30 岁起点向）",
  "tropes": ["核心爽点类型 3-5 个，从：重生/系统/苟道/扮猪吃虎/无敌流/种田流/红尘炼心/打脸装x/团宠/收徒养崽/复仇/逆袭 等中筛选最契合的"],
  "reference_works": ["3 部参照作品（同流派代表作，仅作基调参考，禁止抄袭）"],
  "selling_point": "一句话卖点钩子（30 字内，必须能贴在书籍封面）",
  "face_slap_pattern": "打脸节奏（例：每 3 章一小、每 10 章一中、每卷一大）",
  "emotional_arc": "情感线占比（none/low/medium/high，对应 0%/10%/25%/40%）",
  "pace_type": "节奏类型（fast=番茄式爽快 / medium=起点中速 / slow=猫腻式文笔）",
  "taboo_lines": ["禁忌边界 2-4 条（禁止涉及的题材/主题）"],
  "market_risk": "市场风险评估（同质化程度/受众规模/题材饱和度，各一句，合计50字内）",
  "differentiation_durability": "差异化持续性：你的核心差异化能撑几卷？第几卷之后最可能暴露同质化？建议提前布局什么钩子来对冲？（60字内）",
  "hook_test": "封面50字钩子：用50字以内写出这本书的书架推荐语，然后自评'一个从未看过此类书的28岁男/女读者，看到这50字的点击意愿（1-10分）'，格式：推荐语｜自评分:X｜理由（30字）"
}}

要求：
1. tropes 必须互相协调，禁止"种田流+无敌流"这类自相矛盾组合
2. reference_works 必须是同流派作品（不要跨流派类比）
3. 若 logline 暗示女频题材，target_audience 不要硬扭成男频
4. market_risk 必须诚实评估，不要只说好话——若同质化风险高，直接指出
5. hook_test 的自评分要实事求是，6分以下要给出"如何提升钩子吸引力"的建议
6. 严禁返回任何解释，仅返回 JSON。"""

        raw = await self._call_with_retry(
            system,
            prompt,
            max_tokens=2560,
            task="bootstrap.positioning",
        )
        try:
            data = _parse_json(raw)
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        # 字段兜底：缺失字段不丢，仅做最小清洗
        for k in (
            "target_audience", "selling_point", "face_slap_pattern",
            "emotional_arc", "pace_type",
            "market_risk", "differentiation_durability", "hook_test",
        ):
            v = data.get(k)
            if not isinstance(v, str):
                data[k] = ""
        for k in ("tropes", "reference_works", "taboo_lines"):
            v = data.get(k)
            if not isinstance(v, list):
                data[k] = []
            else:
                data[k] = [str(x).strip() for x in v if x and isinstance(x, (str, int, float))]
        return data

    # ══════════════════════════════════════════════════════════
    #  Step 1 — 项目基础信息
    # ══════════════════════════════════════════════════════════

    async def _gen_project(self, ctx: dict):
        system = "你是网络小说策划专家。根据创意生成项目基础信息，只返回JSON。"
        tw = int(ctx.get("target_words") or 1_200_000)
        length_block = _book_length_constraints_for_prompt(tw)
        # Step 0 立项定位作为全局约束注入：让 title/genre/premise 都贴合定位
        positioning_block = ""
        positioning = ctx.get("positioning") or {}
        if isinstance(positioning, dict) and positioning:
            positioning_block = (
                "\n【立项定位（必须严格遵守）】\n"
                + json.dumps(positioning, ensure_ascii=False, indent=2)
                + "\n"
            )
        prompt = f"""创意：{ctx['logline']}
立意与类型：{ctx.get('premise')[:1500] if ctx.get('premise') else '（未填写，请自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}
{positioning_block}
{length_block}

返回JSON：
{{
  "title": "小说名（2~6个汉字，有冲击力）",
  "genre": "玄幻",
  "premise": "使用 markdown 二级标题输出完整《立意与类型（PREMISE）》，必须包含：作品定位、核心一句话、类型与篇幅、主题与命题、核心矛盾、主角概况、结局倾向、最坏会怎样（收束边界）、希望读者记住的一个画面、叙事视角与禁忌；其中「类型与篇幅」必须严格服从上方【全书字数目标（硬性约束）】",
  "world_overview": "世界观简述，300~500字，包含力量体系、势力格局、社会规则",
  "story_core": {{
    "drive": "故事驱动力（成长/复仇/守护等）",
    "conflict": "核心矛盾",
    "theme": "主题",
    "differentiation": "与同类小说的差异化"
  }}
}}
要求：
1) premise 不要空话，必须可直接作为作者创作基线
2) premise 中必须给出清晰的目标读者、禁忌边界；「类型与篇幅」仅允许使用与【全书字数目标（硬性约束）】一致的规模表述
3) theme / conflict 要与 premise 一致
4) 只返回 JSON，不要解释文字。"""

        raw = await self._call_with_retry(
            system,
            prompt,
            max_tokens=settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS,
            task="bootstrap.project",
        )
        data = _parse_json(raw)

        # Step 0 立项定位写进 story_core.positioning，并把作品基本面 mirror 到
        # Project.extra.positioning（如该列已迁移），写章节路径优先读后者。
        story_core = data.get("story_core", {}) or {}
        positioning = ctx.get("positioning") or {}
        if isinstance(story_core, dict) and positioning:
            story_core["positioning"] = positioning

        project_kwargs = dict(
            title=data["title"],
            genre=data.get("genre", "玄幻"),
            logline=ctx["logline"],
            premise=data.get("premise") or ctx.get("premise") or "",
            world_overview=data.get("world_overview", ""),
            story_core=story_core,
            target_words=int(ctx.get("target_words") or 1_200_000),
        )
        # Project.extra 列在 main.py 的兼容迁移里新增；旧库未迁移时跳过赋值
        if hasattr(Project, "extra") and positioning:
            project_kwargs["extra"] = {"positioning": positioning}
        project = Project(**project_kwargs)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        ctx["project_title"] = project.title
        ctx["genre"] = project.genre
        ctx["world_overview"] = project.world_overview
        ctx["story_core"] = story_core
        ctx["premise"] = project.premise or ctx.get("premise") or ""
        # 流派分流：加载 genre_kit 作为全局约束，后续所有步骤都读它
        ctx["genre_kit"] = get_genre_kit(project.genre)
        ctx["genre_kit_prompt"] = render_kit_for_prompt(ctx["genre_kit"])

        return project, ctx

    # ══════════════════════════════════════════════════════════
    #  Step 3 — 势力体系（结构化 Faction 记录）
    # ══════════════════════════════════════════════════════════

    async def _gen_factions(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}
境界体系：{ctx.get('power_summary', '（未设定）')}

【流派编辑手册约束】
- 势力定位与冲突必须符合 genre_kit 的 satisfaction_tropes（玄幻多宗门/打脸、悬疑多嫌疑人互咬、言情多家族/情敌）

生成本小说的主要势力/组织（4~6个），返回JSON数组：
[
  {{
    "name": "势力名称",
    "faction_type": "sect",
    "alignment": "antagonist",
    "active_period": "early",
    "description": "势力特色与定位（60字内）",
    "territory": "领地/活动范围",
    "strength_level": "实力级别（如：顶级宗门，坐镇一名斗宗）",
    "member_count": "成员规模",
    "top_power": "最强战力描述",
    "goals": "势力目标与图谋",
    "resources": "势力核心资源/特产",
    "history": "势力历史背景（30字）",
    "secrets": "势力不为人知的秘密/隐藏阴谋（供作者参考）",
    "rivals": ["竞争势力名"],
    "allies": ["盟友势力名"],
    "attitude_to_protagonist": "hostile",
    "internal_factions": "势力内部的派系博弈（至少2派，各有代表人物与目标差异，50字内；protagonist阵营与neutral阵营也必须填写，写'改革派vs保守派'等内部张力）",
    "villain_timeline": "【仅 antagonist 阵营填写，其余填空字符串】若主角什么都不做，这股势力会在第几卷完成什么阴谋？被主角打断后的应对策略是什么？（70字内，具体到卷号）"
  }}
]
faction_type 只能是: sect / kingdom / family / guild / evil / race / other
alignment 只能是: protagonist / neutral / antagonist / unknown
active_period 只能是: early / mid / late / full
attitude_to_protagonist 只能是: friendly / hostile / neutral / subordinate / superior
必须涵盖主角阵营势力、核心反派势力、中立势力各至少1个。
villain_timeline 对 antagonist 类势力为必填，要求具体到"第X卷前完成xxx，主角若干预则转为yyy策略"。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.factions")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("factions", [])

        results = []
        for i, item in enumerate(data):
            f = Faction(
                project_id=project.id,
                name=item.get("name", f"势力{i+1}"),
                faction_type=item.get("faction_type", "sect"),
                alignment=item.get("alignment", "neutral"),
                description=item.get("description"),
                territory=item.get("territory"),
                strength_level=item.get("strength_level"),
                member_count=item.get("member_count"),
                top_power=item.get("top_power"),
                goals=item.get("goals"),
                resources=item.get("resources"),
                history=item.get("history"),
                secrets=item.get("secrets"),
                rivals=item.get("rivals", []),
                allies=item.get("allies", []),
                attitude_to_protagonist=item.get("attitude_to_protagonist", "neutral"),
                sort_order=i,
                extra={
                    "active_period": item.get("active_period", ""),
                    "internal_factions": item.get("internal_factions", ""),
                    "villain_timeline": item.get("villain_timeline", ""),
                },
            )
            self.db.add(f)
            results.append(f)

        self.db.commit()

        # 压入 ctx：供人物 faction 字段、设定卡去重引用
        ctx["faction_summary"] = "、".join(
            f"{f.name}（{f.alignment}，{f.extra.get('active_period','')}期）"
            for f in results
        )
        ctx["faction_names"] = [f.name for f in results]
        # 压入 villain_timeline 汇总，供 expand_outline 注入反派行动线约束
        villain_timelines = [
            f"{f.name}：{f.extra.get('villain_timeline', '')}"
            for f in results
            if f.alignment == "antagonist" and f.extra.get("villain_timeline", "").strip()
        ]
        ctx["villain_timelines"] = villain_timelines
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 6 — 核心功法技能（结构化 Skill 记录）
    # ══════════════════════════════════════════════════════════

    async def _gen_key_skills(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
主要人物：{', '.join(ctx.get('char_names', [])[:6])}

【流派编辑手册约束】
- 技能效果与获取方式必须符合 genre_kit 的 satisfaction_tropes（玄幻强调金手指新用法，仙侠强调心魔/渡劫相关）

生成本小说最关键的5~8个功法/技能，返回JSON数组：
[
  {{
    "name": "功法/技能名称",
    "skill_type": "combat",
    "grade": "earth",
    "source": "来源（如：上古秘典、宗门传承）",
    "level_required": "修炼要求（境界，如：斗者三星以上）",
    "description": "功法/技能描述（40字内）",
    "effects": "使用效果",
    "limitations": "使用限制或副作用",
    "mastered_by": ["掌握此技能的人物名（从上面人物列表选）"],
    "plot_hook": "这个技能/功法在故事中的剧情钩子：何时会被损毁/被夺走/被超越/失效/揭露禁忌代价？用一句话指明触发章节范围（如：「第2卷高潮时主角核心功法被反派破解，被迫觉醒隐藏传承」）"
  }}
]
skill_type 只能是: combat / defense / movement / support / bloodline / special
grade 只能是: mortal / earth / sky / profound / saint / divine / supreme
选择对故事最重要的技能，包含主角核心战技和1~2个反派标志性技能。
每个技能必须填写 plot_hook，不得留空。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.skills")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("skills", [])

        # ★ 修复：用名字→UUID 映射，mastered_by_character_ids 存真实 UUID
        char_name_to_id: dict = ctx.get("char_name_to_id", {})
        results = []
        for i, item in enumerate(data):
            # 将 AI 返回的人物名转换为对应的 character UUID 列表
            mastered_ids = [
                char_name_to_id[name]
                for name in item.get("mastered_by", [])
                if name in char_name_to_id
            ]
            skill_extra = {}
            if item.get("plot_hook"):
                skill_extra["plot_hook"] = str(item["plot_hook"])[:300]
            sk = Skill(
                project_id=project.id,
                name=item.get("name", f"功法{i+1}"),
                skill_type=item.get("skill_type", "combat"),
                grade=item.get("grade", "earth"),
                source=item.get("source"),
                level_required=item.get("level_required"),
                description=item.get("description"),
                effects=item.get("effects"),
                limitations=item.get("limitations"),
                mastered_by_character_ids=mastered_ids,
                sort_order=i,
                extra=skill_extra,
            )
            self.db.add(sk)
            results.append(sk)

        self.db.commit()
        ctx["skill_names"] = [sk.name for sk in results]
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 7 — 关键道具法宝（结构化 Item 记录）
    # ══════════════════════════════════════════════════════════

    async def _gen_key_items(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
主要人物：{', '.join(ctx.get('char_names', [])[:6])}
主要势力：{', '.join(ctx.get('faction_names', [])[:4])}

【流派编辑手册约束】
- 道具效果与获取必须符合 genre_kit 的 satisfaction_tropes（玄幻强调升级/打脸相关法宝）

生成本小说最重要的5~8件道具/法宝，返回JSON数组：
[
  {{
    "name": "道具/法宝名称",
    "item_type": "artifact",
    "rarity": "legendary",
    "description": "外观与特征描述（30字内）",
    "origin": "来历（上古遗留、宗门镇宝等）",
    "effects": "核心能力效果",
    "limitations": "使用限制（境界要求、次数、副作用）",
    "story_significance": "在故事中的重要性/象征意义",
    "current_owner": "当前持有人名（从人物列表选，或留空）",
    "status": "intact",
    "plot_hook": "这件道具在故事中的剧情钩子：何时会被损毁/被夺走/持有者死亡/揭露隐藏能力/成为争夺焦点？用一句话指明触发章节范围（如：「第1卷末法宝被反派势力强夺，主角踏上复夺之路」）"
  }}
]
item_type 只能是: weapon / armor / pill / artifact / material / scroll / beast / other
rarity 只能是: common / uncommon / rare / epic / legendary / mythic / unique
status 只能是: intact / damaged / destroyed / lost / unknown
选择对主线剧情影响最大的道具，包含主角核心战力道具和1~2个关键麦高芬道具。
每件道具必须填写 plot_hook，不得留空。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.items")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("items", [])

        char_name_to_id: dict = ctx.get("char_name_to_id", {})
        results = []
        for i, item in enumerate(data):
            owner_name = item.get("current_owner", "") or ""
            owner_uuid_str = char_name_to_id.get(owner_name) if owner_name else None
            item_extra = {}
            if item.get("plot_hook"):
                item_extra["plot_hook"] = str(item["plot_hook"])[:300]
            it = Item(
                project_id=project.id,
                name=item.get("name", f"道具{i+1}"),
                item_type=item.get("item_type", "artifact"),
                rarity=item.get("rarity", "rare"),
                description=item.get("description"),
                origin=item.get("origin"),
                effects=item.get("effects"),
                limitations=item.get("limitations"),
                story_significance=item.get("story_significance"),
                status=item.get("status", "intact"),
                current_owner_id=UUID(owner_uuid_str) if owner_uuid_str else None,
                sort_order=i,
                extra=item_extra,
            )
            self.db.add(it)
            results.append(it)

        self.db.commit()
        ctx["item_names"] = [it.name for it in results]
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 8 — 世界观设定卡（纯叙事，无专属表的内容）
    # ══════════════════════════════════════════════════════════

    async def _gen_settings(self, project: Project, ctx: dict):
        """
        只生成无专属结构化表的纯叙事设定卡。
        ❌ 不再生成：修炼体系（→ PowerSystem）、主要势力（→ Faction）、
                    功法技能（→ Skill）、道具法宝（→ Item）
        ✅ 生成：作品立意、世界规则、历史谜团、地图/地理、文化风俗
        """
        system = "你是网络小说世界观设计专家。只返回JSON数组。"

        # 汇总已生成的结构化数据，让设定卡内容不重复
        faction_brief = ctx.get("faction_summary", "（已独立生成势力档案）")
        power_brief   = ctx.get("power_summary",   "（已独立生成境界体系）")
        setting_blueprints = _setting_blueprints_for_prompt()

        # 把人物名与势力名注入设定 prompt，强制 who_knows_now 引用真实命名
        char_names_hint = "、".join(ctx.get("char_names", []))
        faction_names_hint = "、".join(ctx.get("faction_names", []))

        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:1000] or '（未填写，请自动提炼）'}
世界观：{ctx['world_overview'][:300]}

【流派编辑手册约束】
- 世界观必须体现流派特有的力量体系、势力格局、社会规则和读者期待（例：玄幻要强调金手指代价与升级仪式，悬疑要强调信息差与嫌疑人布局）
- 禁忌边界必须参考 genre_kit 的 forbidden_examples

已独立生成的结构化数据（设定卡不要重复这些内容）：
- 境界体系：{power_brief}
- 势力档案：{faction_brief}
- 已确定人物（写 who_knows_now 时必须从此列表选名字）：{char_names_hint or '（尚未生成）'}
- 已确定势力（写 who_knows_now 时可引用）：{faction_names_hint or '（尚未生成）'}

请严格按【世界设定蓝图】生成完整的【纯叙事型】世界观设定卡，不要少卡、不要合并卡。
世界设定蓝图：
{setting_blueprints}

返回JSON数组，单条结构参考如下（不要只生成示例）：
[
  {{
    "title": "作品立意",
    "content": "作品定位、目标读者、类型与篇幅、主题命题、核心矛盾、情感基调、结局倾向、禁忌边界（至少200字，可落地执行）",
    "tags": ["立意", "主题"],
    "extra": {{
      "category": "世界背景",
      "core": {{
        "core_concept": "一句话讲清这本书：谁在什么压迫下，通过什么方式完成什么逆转",
        "genre_position": "题材、目标读者、篇幅规模、同类差异化",
        "protagonist_drive": "主角为什么必须行动，停下来会失去什么",
        "core_conflict": "贯穿全书的核心对抗/价值冲突/压迫结构",
        "reader_hook": "读者每十章愿意追下去的疑问、爽点和承诺",
        "emotional_tone": "热血、压抑、克制、复仇、成长等主要味道",
        "boundaries": "不能写偏的禁忌边界，尤其避免人物工具化和主题漂移",
        "ending_direction": "最终收束方向、胜利形态、代价或余味"
      }}
    }}
  }},
  {{
    "title": "世界底层规则",
    "content": "2~3条最重要的世界法则，含违反代价与例外情况",
    "tags": ["规则", "法则"],
    "extra": {{
      "category": "规则法则",
      "focus": {{
        "summary": "最重要的世界规则一句话",
        "story_function": "它如何制造成长压力、阶层压迫或剧情限制",
        "conflict_seed": "这条规则会引发的核心冲突",
        "cost_or_risk": "违反规则或钻漏洞的代价",
        "affected_people": "受影响的阶层、势力或角色",
        "exception_or_loophole": "例外情况、漏洞或禁区",
        "visual_anchor": "能写进正文的规则呈现场景"
      }}
    }}
  }},
  {{
    "title": "历史谜团与禁忌",
    "content": "驱动长线追读的历史真相、远古秘密与禁忌边界",
    "tags": ["历史", "谜团"],
    "extra": {{
      "category": "历史传说",
      "focus": {{
        "summary": "历史谜团一句话",
        "story_function": "它如何推动长线主线或反派计划",
        "conflict_seed": "揭开它会撕裂哪些人物/势力关系",
        "cost_or_risk": "追查或公开真相的代价",
        "affected_people": "被历史真相影响的人群或势力",
        "exception_or_loophole": "被篡改、封印或误读的关键处",
        "visual_anchor": "遗迹、碑文、禁书、仪式等画面锚点"
      }}
    }}
  }},
  {{
    "title": "大陆地图与地缘格局",
    "content": "主要地区、关键地点、资源分布与地缘政治态势",
    "tags": ["地图", "地理"],
    "extra": {{
      "category": "地理场景",
      "focus": {{
        "summary": "世界空间格局一句话",
        "story_function": "地图如何决定主角路线、升级节奏和冲突升级",
        "conflict_seed": "资源/边界/禁地引发的地缘冲突",
        "cost_or_risk": "穿越、占领或进入关键地区的代价",
        "affected_people": "受地理格局影响的势力和民众",
        "exception_or_loophole": "隐秘通道、失落区域、禁区漏洞",
        "visual_anchor": "最有画面感的地标或危险区域"
      }}
    }}
  }},
  {{
    "title": "文化与民俗",
    "content": "主要文化圈、礼仪习俗、宗教信仰与日常生活质感",
    "tags": ["文化", "风俗"],
    "extra": {{
      "category": "文化风俗",
      "focus": {{
        "summary": "文化气质一句话",
        "story_function": "它如何影响人物选择、羞耻感、荣誉感或社会秩序",
        "conflict_seed": "传统与主角目标之间的矛盾",
        "cost_or_risk": "违背习俗、誓言或信仰的后果",
        "affected_people": "最受文化规训的人群",
        "exception_or_loophole": "被少数人利用或反叛的习俗漏洞",
        "visual_anchor": "节庆、仪式、服饰、称谓或日常场景"
      }}
    }}
  }},
  {{
    "title": "稀缺资源与经济体系",
    "content": "修炼资源稀缺性与流通规则、阶层分化来源，不重复境界体系内容",
    "tags": ["资源", "经济"],
    "extra": {{
      "category": "规则法则",
      "focus": {{
        "summary": "资源分配机制一句话",
        "story_function": "它如何支撑爽点、压迫感和升级门槛",
        "conflict_seed": "围绕资源发生的争夺、垄断或黑市冲突",
        "cost_or_risk": "获取、吞服、交易或透支资源的代价",
        "affected_people": "资源体系下的受益者与被剥削者",
        "exception_or_loophole": "主角可利用但必须付代价的破局点",
        "visual_anchor": "拍卖、矿脉、丹市、贡赋、秘境采集等画面"
      }}
    }}
  }}
]
要求：
1) 必须生成蓝图中的全部 {len(GEMINI_SETTING_BLUEPRINTS)} 张设定卡，顺序与蓝图一致
2) 每张卡 title/category/tags/importance/stage 必须与蓝图一致，写入 extra
3) "作品立意"必须填写 extra.core 的全部字段，每个字段一句短句，不要空泛
4) 其他卡必须填写 extra.focus 的全部字段，每个字段一句短句，先给作者可扫读抓手
5) 每张卡 content 至少180字，有可落地的名词、规则、代价、例外和冲突
6) 不要重复已有的境界体系或势力信息
7) 每张卡必须在 extra 中填写两个揭示节奏字段：
   - reveal_timing：本设定何时、通过什么情节方式揭示给读者/主角（例：「第3卷主角发现禁忌遗迹时逐步揭示」）
   - who_knows_now：故事开篇时已知晓这一设定的角色与势力，**必须从上方"已确定人物"和"已确定势力"列表中选取真实名字**，禁止使用"反派首领""主角"等泛称；格式示例：「李长清、玄天宗知晓内情；叶凡完全不知」
只返回JSON数组，不要解释。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.settings")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("settings", [])

        results = []
        for item in data:
            extra = _setting_extra_with_defaults(item)
            s = WorldSetting(
                project_id=project.id,
                title=item.get("title", "设定"),
                content=item.get("content", ""),
                tags=item.get("tags", []),
                extra=extra,
            )
            self.db.add(s)
            results.append(s)

        self.db.commit()
        ctx["settings_summary"] = " | ".join(
            f"{s.title}：{(s.content or '')[:80]}" for s in results
        )
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 3 — 境界体系
    # ══════════════════════════════════════════════════════════

    async def _gen_power_systems(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}

【流派编辑手册约束】
- 境界体系必须符合 genre_kit 的 pacing_guide（玄幻要强调升级仪式与金手指代价，仙侠要强调心魔与渡劫）

生成本小说的力量/境界体系，返回JSON数组（通常1~2套）：
[
  {{
    "name": "体系名称，如「修炼境界」",
    "system_type": "cultivation",
    "description": "体系在世界观中的地位与简介（50字内）",
    "cultivation_method": "修炼方式（如：吸纳天地灵气，淬炼丹田）",
    "breakthrough_condition": "突破通用条件（如：灵气积累满溢+感悟）",
    "special_rules": "特殊规则（如：天才/废柴判定，天花板原因）",
    "protagonist_start_rank": 1,
    "protagonist_end_rank": 9,
    "levels": [
      {{
        "rank": 1,
        "name": "境界名",
        "description": "简述",
        "abilities": ["能力1"],
        "chapter_budget": 20,
        "gatekeeper": "守在这一境界卡点的核心障碍（强敌名/事件类型/资源缺口，10字内）"
      }},
      {{
        "rank": 2,
        "name": "境界名",
        "description": "简述",
        "abilities": ["能力1"],
        "chapter_budget": 30,
        "gatekeeper": "守在这一境界卡点的核心障碍"
      }}
    ]
  }}
]
system_type 只能是: cultivation / magic / ability / tech / hybrid
levels 至少包含 6 个境界，按强弱从低到高排列。
protagonist_start_rank、protagonist_end_rank 必须是整数，且等于 levels 中某一层的 rank，禁止填境界中文名。
chapter_budget 为主角在该境界停留的预计章数（整数）；所有境界 chapter_budget 之和建议在目标总章数 70% 左右（其余 30% 用于横向扩展剧情）。
gatekeeper 必须具体（如"宗门首席×××"或"突破所需天材地宝被反派势力垄断"），不要空泛写"强敌"。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.power_systems")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("power_systems", [])

        results = []
        for i, item in enumerate(data):
            levels = item.get("levels", [])
            start_raw = item.get("protagonist_start_rank")
            if start_raw is None:
                start_raw = item.get("protagonist_current_rank")
            end_raw = item.get("protagonist_end_rank")
            ps = PowerSystem(
                project_id=project.id,
                name=item.get("name", "修炼体系"),
                system_type=item.get("system_type", "cultivation"),
                description=item.get("description"),
                cultivation_method=item.get("cultivation_method"),
                breakthrough_condition=item.get("breakthrough_condition"),
                special_rules=item.get("special_rules"),
                levels=levels,
                protagonist_current_rank=_coerce_power_system_rank(start_raw, levels, 1),
                protagonist_end_rank=_coerce_power_system_rank(end_raw, levels, None),
                sort_order=i,
            )
            self.db.add(ps)
            results.append(ps)

        self.db.commit()

        # 把境界名列表压入 ctx，供人物 current_realm 和大纲 power_milestone 引用
        if results:
            main_ps = results[0]
            level_names = [lv.get("name", "") for lv in (main_ps.levels or []) if lv.get("name")]
            ctx["power_level_names"] = level_names
            ctx["power_system_name"] = main_ps.name
            ctx["power_summary"] = (
                f"{main_ps.name}：" + " → ".join(level_names[:8])
            )
        else:
            ctx["power_level_names"] = []
            ctx["power_system_name"] = ""
            ctx["power_summary"] = ""

        return results

    # ══════════════════════════════════════════════════════════
    #  Step 4 — 故事线
    # ══════════════════════════════════════════════════════════

    async def _gen_storylines(self, project: Project, ctx: dict):
        system = "你是网络小说叙事结构专家。只返回JSON数组。"
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
故事核：{ctx['story_core'].get('conflict', '')} | 主题：{ctx['story_core'].get('theme', '')}
境界体系：{ctx.get('power_summary', '（未设定）')}

【流派编辑手册约束】
- 每条故事线的 core_conflict 和 resolution_direction 必须符合 genre_kit 的 satisfaction_tropes 和 pacing_guide
- 主线冲突类型必须贴合流派（玄幻打脸/升级、悬疑信息差/嫌疑人、言情误会/追妻等）

生成3~5条主要故事线，返回JSON数组：
[
  {{
    "name": "主线：（简短有力的线名）",
    "line_type": "main",
    "description": "故事线简述（40字内）",
    "core_conflict": "这条线的核心矛盾是什么",
    "resolution_direction": "预计如何收束",
    "status": "active",
    "start_chapter": 1
  }}
]
line_type 只能是: main / sub / romance / growth / mystery / faction / antagonist
status 只能是: planned / active
必须有且只有1条 main，其余为其他类型。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.storylines")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("storylines", [])

        results = []
        for i, item in enumerate(data):
            sl = StoryLine(
                project_id=project.id,
                name=item.get("name", f"故事线{i+1}"),
                line_type=item.get("line_type", "sub"),
                description=item.get("description"),
                core_conflict=item.get("core_conflict"),
                resolution_direction=item.get("resolution_direction"),
                status=item.get("status", "planned"),
                start_chapter=item.get("start_chapter"),
                sort_order=i,
            )
            self.db.add(sl)
            results.append(sl)

        self.db.commit()

        # 压入 ctx，供大纲生成时引用
        ctx["storyline_summary"] = " | ".join(
            f"{sl.name}（{sl.line_type}）" for sl in results
        )
        ctx["storyline_ids"] = {sl.name: str(sl.id) for sl in results}

        return results

    # ══════════════════════════════════════════════════════════
    #  Step 5 — 人物库
    # ══════════════════════════════════════════════════════════

    async def _gen_characters(self, project: Project, ctx: dict):
        system = "你是网络小说人物设计专家。只返回JSON数组。"
        power_hint = (
            f"\n境界体系（current_realm 必须从此列表选择）：{ctx.get('power_summary', '')}"
            if ctx.get('power_level_names') else ""
        )
        kit_block = _get_genre_kit_block(ctx)
        prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:800] or '（未填写）'}
故事核：冲突={ctx['story_core'].get('conflict','')}，主题={ctx['story_core'].get('theme','')}{power_hint}

【流派编辑手册约束（必须严格遵守）】
- 角色配额必须符合 genre_kit 的 side_character_quota
- 说话风格必须符合 dialogue_tone 和 forbidden_examples（严禁出现本流派禁忌的开局/对白方式）
- speech_kit 中的 signature_words / sample_dialogues 必须体现流派特有的咬字习惯和禁忌词

⚠️ 你正在生成"主线核心卡司（Core Cast）"——这8人是全书贯穿的主线角色，不是全书所有人物。
后续章节写作时会按剧情需要动态补充配角，这里只需确定主线固定角色。

生成8个人物（至少：1主角+3核心配角+2反派+2师长/势力角色），返回JSON数组：
[
  {{
    "name": "姓名", "role": "protagonist",
    "character_tier": "core",
    "gender": "男", "age": "17", "faction": "所属势力",
    "personality": "性格（2句话）",
    "background": "背景经历（3句话）",
    "motivation": "核心动机",
    "arc": "人物弧线（从X到Y的成长）",
    "current_realm": "当前境界（或能力层级）",
    "speech_style": "说话风格（自由文本，一句话）",
    "speech_kit": {{
      "signature_words": ["最常说的1-3个标志性词语/口头禅"],
      "sentence_length_pref": "短句/中句/长句偏好",
      "taboo_words": ["绝对不会说的词或句式"],
      "sample_dialogues": ["5-8句典型台词，体现说话习惯"],
      "inner_monologue_style": "内心独白风格（克制/细腻/直白/诗化等）"
    }},
    "values": "价值观",
    "fear": "最恐惧的东西——必须具体，且这个恐惧在故事中会被迫直面",
    "secrets": "不愿公开的秘密——必须具体，且这个秘密暴露后会引发实质性后果",
    "strengths": ["特质1", "特质2"],
    "weaknesses": ["弱点1"],
    "special_traits": ["特殊能力或标志性特征"],
    "debt_to": "对哪个角色（用名字）有未还的恩情/仇怨/承诺？欠了什么？（15字内；若无则填空）",
    "detonation_vol": "上述欠债预计在第几卷被引爆或清偿？（填卷号整数，如2；若无欠债填0）"
  }}
]
role 只能是: protagonist / supporting / antagonist
character_tier 代表该人物在全书中的叙事层级，只能是以下4个值之一：
- core       = 核心长线：贯穿全书始终，长期驱动主线或重要支线（主角、主要反派、全书固定伙伴）
- arc        = 弧线支柱：在某卷或某段剧情中主导走向，随该弧线完结后淡出或阵亡
- plot       = 剧情推手：短期出现以推进特定情节节点，之后退场
- background = 背景填充：丰富世界厚度与氛围，无强情节绑定
请根据每个人物在故事中的实际定位严格判断，不要全部填 core。
debt_to 要求：主角必须对至少1个人有欠债；主要反派必须对主角或某配角有欠债（仇怨或嫉妒型）；这些欠债要分散在不同卷引爆，制造持续的人物动力。

---
【第二部分】再追加生成5个「开局配角」（仅第一卷活跃，character_tier 固定为 "plot"）：
这些人物丰富开局前30章的世界厚度，无需长线设计，但每人在卷一必须有具体的情节功能。
典型角色类型（按需选用）：反派爪牙/小Boss、同辈竞争者/欺凌者、商人/情报贩子、门派长老/考官、普通市民/路人甲（提供信息或见证主角爆发）。

每个配角只需填写精简字段：
{{
  "name": "姓名",
  "role": "supporting 或 antagonist",
  "character_tier": "plot",
  "gender": "性别",
  "age": "年龄",
  "faction": "所属势力（已有势力名或留空）",
  "personality": "性格一句话",
  "motivation": "在卷一的行为动机（一句话）",
  "current_realm": "当前境界（与已有境界体系一致）",
  "vol1_function": "在第一卷30章内的具体剧情功能（必须具体：如'第5章欺凌主角引发第一次反击'、'第12章提供关键情报后消失'）",
  "debt_to": "",
  "detonation_vol": 0,
  "speech_kit": {{"signature_words": [], "sentence_length_pref": "短句", "taboo_words": [], "sample_dialogues": [], "inner_monologue_style": "直白"}},
  "values": "", "fear": "", "secrets": "", "strengths": [], "weaknesses": [], "special_traits": []
}}
请将这5个配角追加到同一JSON数组末尾，不要分开返回。"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.characters")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("characters", [])

        _VALID_TIERS = {"core", "arc", "plot", "background"}
        results = []
        for item in data:
            tier = item.get("character_tier", "core")
            if tier not in _VALID_TIERS:
                tier = "core"
            # 欠债字段：存入 extra，供大纲质检和 expand_outline 引用
            char_extra: dict = {}
            debt_to = (item.get("debt_to") or "").strip()
            if debt_to:
                char_extra["debt_to"] = debt_to
            det_vol_raw = item.get("detonation_vol")
            det_vol = _safe_int(det_vol_raw, default=0)
            if det_vol and det_vol > 0:
                char_extra["detonation_vol"] = det_vol
            # plot 档配角：保存卷一功能说明
            vol1_func = (item.get("vol1_function") or "").strip()
            if vol1_func:
                char_extra["vol1_function"] = vol1_func
            c = Character(
                project_id=project.id,
                name=item.get("name", "未命名"),
                role=item.get("role", "supporting"),
                character_tier=tier,
                gender=item.get("gender"),
                age=item.get("age"),
                faction=item.get("faction"),
                personality=item.get("personality"),
                background=item.get("background"),
                motivation=item.get("motivation"),
                arc=item.get("arc"),
                current_realm=item.get("current_realm"),
                speech_style=item.get("speech_style"),
                speech_kit=item.get("speech_kit") or {},
                values=item.get("values"),
                fear=item.get("fear"),
                secrets=item.get("secrets"),
                strengths=item.get("strengths", []),
                weaknesses=item.get("weaknesses", []),
                special_traits=item.get("special_traits", []),
                extra=char_extra if char_extra else None,
            )
            self.db.add(c)
            results.append(c)

        self.db.commit()
        ctx["char_names"] = [c.name for c in results]
        ctx["protagonist"] = next((c.name for c in results if c.role == "protagonist"), "主角")
        # 供 memory 生成用：角色名→当前境界快照
        ctx["char_realms"] = {
            c.name: (c.current_realm or "未知") for c in results
        }
        # ★ 修复：名字→UUID 映射，供 Skill/Item 存真实 character_id
        ctx["char_name_to_id"] = {c.name: str(c.id) for c in results}
        # 仅 core/arc 层级参与关系图（plot 档配角不做全连接，避免组合爆炸）
        ctx["core_char_names"] = [
            c.name for c in results if c.character_tier in ("core", "arc")
        ]
        # plot 档配角摘要：供 vol1_chapter_plans 等步骤引用
        ctx["plot_npc_summary"] = "; ".join(
            f"{c.name}（{c.extra.get('vol1_function', '') if c.extra else ''}）"
            for c in results
            if c.character_tier == "plot" and c.extra and c.extra.get("vol1_function")
        )
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 4 — 大纲树
    # ══════════════════════════════════════════════════════════

    async def _gen_volumes(self, project: Project, ctx: dict):
        """
        Bootstrap 阶段只生成卷级骨架（volume skeleton），不生成 chapter_plan。

        章节级大纲由作者确认设定后按卷触发 expand_outline 生成，
        那时 power_milestone / involved_characters 才有准确上下文。
        """
        system = "你是网络小说结构策划专家。只返回JSON数组。"
        storyline_hint = (
            f"\n故事线（每卷 summary 应说明推进了哪条线）：{ctx.get('storyline_summary', '')}"
            if ctx.get('storyline_summary') else ""
        )
        # 从 target_words 推算卷数区间（单一数据源）
        from app.services.outline_planning import words_to_plan
        tw = int(project.target_words or 1_200_000)
        plan = words_to_plan(tw)
        n_volumes = plan["total_volumes"]
        total_chapters_hint = plan["total_chapters"]

        # Step 0 立项定位塞进卷规划：让卖点钩子 / 节奏类型 / 打脸频率落到卷级
        positioning = ctx.get("positioning") or {}
        positioning_block = ""
        if isinstance(positioning, dict) and positioning:
            positioning_block = (
                "\n【立项定位（每卷必须贯彻）】\n"
                + json.dumps(positioning, ensure_ascii=False)
                + "\n"
            )
        kit_block = _get_genre_kit_block(ctx)

        # 反派时间线摘要 → 卷规划约束：dark_hour / climax 的触发依据
        villain_timelines = ctx.get("villain_timelines", [])
        villain_block = ""
        if villain_timelines:
            villain_block = (
                "\n【反派行动时间线（卷级 phase 必须与之对齐）】\n"
                + "\n".join(f"- {vt}" for vt in villain_timelines)
                + "\n⚠️ 对齐规则：反派明显占优/主角处于劣势的卷 → phase=dark_hour；\n"
                "反派计划被终结/代价完全兑现的卷 → phase=climax。\n"
            )

        prompt = f"""小说：《{ctx['project_title']}》主角：{ctx['protagonist']}
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:700] or '（未填写）'}
设定摘要：{ctx['settings_summary']}{storyline_hint}{villain_block}{positioning_block}{kit_block}

主线核心角色（固定卡司，非全书全部人物）：{', '.join(ctx.get('char_names', []))}
⚠️ 以上只是主线人物。每卷 summary/conflict 允许并鼓励提及未命名配角（如"某城守将""地下情报商""宗门长老"等职能角色），章节细化时会按需正式创建他们。

根据故事规模规划卷级结构，返回JSON数组。
【字数目标】全书目标：{tw:,}字，折合约{total_chapters_hint}章；**必须恰好 {n_volumes} 卷**（由目标字数推算，数组长度必须等于{n_volumes}；不得为多塞 phase 而加卷，卷少时合并阶段）。
每卷 planned_chapters 只能填 30 或 60（过渡/尾卷可填30），不要其他数字。
所有卷的 planned_chapters 之和须尽量接近{total_chapters_hint}章。

【phase 阶段标记（必填，单值）】每卷必须从下列阶段中选一个，全书必须按以下顺序大致单调推进：
  - opening    第一卷固定为开局期（新手村、立金手指、密集爽点）
  - rising     起飞期（势力扩张、感情线接入），通常 1-2 卷
  - turning    转折期（矛盾升级、代价兑现），通常 1 卷
  - dark_hour  至暗期（虐主、节奏放缓），通常 1 卷或与 turning 合并
  - climax     高潮期（伏笔回收、终战），通常 1 卷
  - ending     收束期（最终卷，留下一卷悬念种子）
若总卷数较少，可省略 dark_hour 或合并 turning + dark_hour，但 opening 与 climax 必须存在。

[
  {{
    "title": "第一卷：卷标题（有画面感，带悬念）",
    "sort_order": 0,
    "summary": "本卷核心剧情概述，60字内",
    "hook": "本卷核心悬念：读者最想知道的问题",
    "conflict": "本卷主要矛盾冲突",
    "planned_chapters": 60,
    "phase": "opening"
  }}
]
只返回JSON数组，不要任何说明文字。"""

        raw = await self._call_with_retry(
            system,
            prompt,
            task="bootstrap.volumes",
        )
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("outline", data.get("volumes", []))

        valid_phases = {"opening", "rising", "turning", "dark_hour", "climax", "ending"}
        results = []
        for i, vol in enumerate(data):
            planned = vol.get("planned_chapters", 60)
            if planned not in (30, 60):
                planned = 60
            phase_val = (vol.get("phase") or "").strip().lower() or None
            if phase_val and phase_val not in valid_phases:
                # 兜底：模型偶尔返回中文或其他写法，统一映射到默认轨迹
                phase_val = None
            # 若模型未返回 phase，按位置兜底：第一卷 opening、最后一卷 ending、其余 rising
            if phase_val is None:
                total_hint = max(1, len(data))
                if i == 0:
                    phase_val = "opening"
                elif i == total_hint - 1:
                    phase_val = "ending"
                else:
                    phase_val = "rising"
            node = OutlineNode(
                project_id=project.id,
                parent_id=None,
                node_type="volume",
                title=vol.get("title", f"第{i+1}卷"),
                summary=vol.get("summary"),
                hook=vol.get("hook"),
                conflict=vol.get("conflict"),
                sort_order=vol.get("sort_order", i),
                phase=phase_val,
                extra={"planned_chapters": planned, "phase": phase_val},
            )
            self.db.add(node)
            results.append(node)

        self.db.commit()
        # 供 memory 生成用：卷级摘要
        ctx["volumes_summary"] = " | ".join(
            f"{n.title}：{(n.summary or '')[:40]}" for n in results
        )
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 7 — 记忆库种子
    # ══════════════════════════════════════════════════════════

    async def _gen_memory(self, project: Project, ctx: dict):
        system = "你是小说设定记忆管理专家。只返回JSON数组。"
        # 汇总所有已生成的结构化上下文，让记忆种子真正锚定设定细节
        char_snapshot = "、".join(
            f"{n}（{ctx.get('char_realms', {}).get(n, '未知境界')}）"
            for n in ctx.get("char_names", [])[:6]
        )
        prompt = f"""小说：《{ctx['project_title']}》主角：{ctx['protagonist']}
境界体系：{ctx.get('power_summary', '（未设定）')}
故事线：{ctx.get('storyline_summary', '（未设定）')}
主要人物：{char_snapshot or ctx.get('char_names', [])}
卷级结构：{ctx.get('volumes_summary', '（未设定）')}
设定摘要：{ctx['settings_summary'][:400]}

生成10条初始记忆库种子，覆盖「境界锚点、人物初始状态、故事线起点、关键设定规则、核心伏笔」五类，
作为后续写作的防矛盾基线，返回JSON数组：
[
  {{
    "memory_type": "setting",
    "title": "简短标题（10字内，精准可查）",
    "content": "具体内容，可直接作为写作参考（不少于30字）",
    "tags": ["分类标签"]
  }}
]
memory_type 只能是: event / character_state / foreshadow / setting / conflict"""

        raw = await self._call_with_retry(system, prompt, task="bootstrap.memory")
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("memory", [])

        results = []
        for item in data:
            m = MemoryChunk(
                project_id=project.id,
                memory_type=item.get("memory_type", "setting"),
                title=item.get("title"),
                content=item.get("content", ""),
                tags=item.get("tags", []),
                chapter_number=0,  # 初始种子标记为第0章
            )
            self.db.add(m)
            results.append(m)

        self.db.commit()
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 6 — 人物关系
    # ══════════════════════════════════════════════════════════

    async def _gen_relations(self, project: Project, chars: list, ctx: dict):
        if len(chars) < 2:
            return []

        # 只对 core / arc 层角色做全连接关系图；plot 档配角不参与，避免组合爆炸
        core_names = set(ctx.get("core_char_names", [c.name for c in chars]))
        relation_chars = [c for c in chars if c.name in core_names]
        if len(relation_chars) < 2:
            relation_chars = chars  # 兜底：若过滤后不足2人，仍用全部

        name_map = {c.name: c for c in chars}  # 全量 map 供解析用
        # 把欠债信息汇总给关系生成，让 AI 设计互相呼应的张力
        debt_summary = "; ".join(
            f"{c.name}→欠债:{c.extra.get('debt_to','')}(第{c.extra.get('detonation_vol',0)}卷引爆)"
            for c in relation_chars
            if c.extra and c.extra.get("debt_to", "").strip()
        )
        system = "你是人物关系设计专家。只返回JSON数组。"
        prompt = f"""人物列表：{', '.join(c.name for c in relation_chars)}
创意：{ctx['logline']}
已知欠债关系（请让关系设计与欠债相互呼应）：{debt_summary or '（无）'}

生成人物关系（覆盖所有核心人物，每对关系1条），返回JSON数组：
[
  {{
    "from_name": "人物A", "to_name": "人物B",
    "relation_type": "师徒",
    "description": "关系现状描述（15字内）",
    "intensity": 8,
    "unresolved_tension": "这段关系中悬而未决的张力/恩怨/信息差（20字内；若纯粹积极关系，写潜在的分歧或考验）",
    "trigger_event": "什么事件会让这段关系发生质变？（15字内，要具体）"
  }}
]
intensity 为 1~10 的整数，只能使用上面列出的人物名。
unresolved_tension 和 trigger_event 为必填，不能为空或敷衍。"""

        try:
            raw = await self._call_with_retry(system, prompt, task="bootstrap.relations")
            data = _parse_json(raw)
            if not isinstance(data, list):
                data = data.get("relations", [])
        except Exception:
            return []

        results = []
        for item in data:
            from_char = name_map.get(item.get("from_name", ""))
            to_char = name_map.get(item.get("to_name", ""))
            if not from_char or not to_char:
                continue
            # 将 unresolved_tension / trigger_event 拼入 evolution_note 持久化
            tension = (item.get("unresolved_tension") or "").strip()
            trigger = (item.get("trigger_event") or "").strip()
            evolution_note_parts = []
            if tension:
                evolution_note_parts.append(f"[张力]{tension}")
            if trigger:
                evolution_note_parts.append(f"[引爆事件]{trigger}")
            evolution_note = "；".join(evolution_note_parts) or None
            rel = CharacterRelationship(
                project_id=project.id,
                from_character_id=from_char.id,
                to_character_id=to_char.id,
                relation_type=item.get("relation_type", "认识"),
                description=item.get("description"),
                intensity=int(item.get("intensity", 5)),
                evolution_note=evolution_note,
            )
            self.db.add(rel)
            results.append(rel)

        self.db.commit()

        # 关系张力摘要 → 供 Step 11.5 生成第一卷章级大纲时引用
        ctx["relation_triggers"] = "; ".join(
            f"{item.get('from_name','?')}↔{item.get('to_name','?')}[{item.get('trigger_event','')}]"
            for item in data
            if item.get("trigger_event", "").strip()
        )

        return results

    # ══════════════════════════════════════════════════════════
    #  Step 11.5 — 第一卷章级大纲（OutlineNode chapter_plan）
    # ══════════════════════════════════════════════════════════

    async def _gen_vol1_chapter_plans(self, project: Project, volumes: list, ctx: dict) -> list:
        """利用 Bootstrap 全量上下文为第一卷生成 chapter_plan 级 OutlineNode。

        此步骤在 Step 11（人物关系）之后触发，可以使用全部已积累的：
        人物档案、欠债引爆节点、关系触发事件、反派时间线、故事线、开局承诺、境界体系。

        Args:
            project: 当前项目。
            volumes: Step 9 生成的卷级 OutlineNode 列表（取 sort_order=0 的第一卷）。
            ctx: Bootstrap 上下文字典。

        Returns:
            生成的 OutlineNode（chapter_plan）列表；失败时返回空列表。
        """
        if not volumes:
            return []

        vol1 = next((v for v in volumes if v.sort_order == 0), volumes[0])
        planned = (vol1.extra or {}).get("planned_chapters", 30)
        if planned not in (30, 60):
            planned = 30

        system = "你是网络小说结构策划专家，擅长将宏观设定转化为可执行的章节级写作蓝图。只返回JSON数组。"

        # ── 压缩上下文 ──────────────────────────────────────────
        # 人物摘要：名字 + 层级 + 欠债引爆卷
        char_lines = []
        for name in ctx.get("char_names", []):
            tier = "plot" if name not in ctx.get("core_char_names", []) else "core"
            realm = ctx.get("char_realms", {}).get(name, "")
            char_lines.append(f"{name}({tier},{realm})")
        char_snapshot = "、".join(char_lines)

        # 欠债引爆信息（核心驱动力）
        debt_lines = []
        for name in ctx.get("core_char_names", []):
            pass  # debt is already in char_extra, summarised below via relation_triggers

        # 故事线
        storyline_summary = ctx.get("storyline_summary", "（未设定）")
        # 关系触发事件
        relation_triggers = ctx.get("relation_triggers", "（无）")
        # 反派时间线
        villain_timelines = ctx.get("villain_timelines", [])
        villain_hint = "；".join(villain_timelines) if villain_timelines else "（无）"
        # 开局承诺：优先从 ctx 读（Step 12 已将其写入 ctx['opening_contract']），
        # 兜底再查 project.extra（单步重跑场景下可能没有 ctx）
        opening_contract = ctx.get("opening_contract") or (project.extra or {}).get("opening_contract", {})
        contract_hint = ""
        if opening_contract:
            contract_hint = (
                f"\n【已有开局承诺（章级大纲必须兑现）】\n"
                f"  第1章末钩子：{opening_contract.get('chapter1_hook','')}\n"
                f"  第3章爽点：{opening_contract.get('chapter3_payoff','')}\n"
                f"  第5章伏笔：{opening_contract.get('chapter5_foreshadow','')}\n"
                f"  第10章订阅钩：{opening_contract.get('chapter10_subscribe_reason','')}\n"
                f"  节奏规划：{opening_contract.get('chapter_rhythm','')}\n"
            )

        # plot NPC 简介
        plot_npc_hint = ctx.get("plot_npc_summary", "")

        # 定位爽点
        positioning = ctx.get("positioning") or {}
        tropes = "、".join(positioning.get("tropes", []))
        pace_type = positioning.get("pace_type", "medium")

        # 境界突破预算：第一卷内主角应完成几个境界
        power_level_names = ctx.get("power_level_names", [])
        power_hint = ""
        if power_level_names:
            power_hint = f"\n境界体系层级：{' → '.join(power_level_names[:6])}（如有更多则省略）"

        # opening 期字数标准
        words_per_chapter = 2200  # opening phase 标准字数

        # ── 分批生成（60章拆两批）──────────────────────────────
        all_results: list[OutlineNode] = []

        batch_ranges = [(1, min(30, planned))]
        if planned > 30:
            batch_ranges.append((31, planned))

        for batch_start, batch_end in batch_ranges:
            batch_count = batch_end - batch_start + 1
            prev_summary = ""
            if all_results:
                # 前一批末尾3章摘要作为续写上下文
                prev_summary = "\n【前批末尾3章摘要（续写衔接用）】\n" + "\n".join(
                    f"  第{n.sort_order + 1}章：{n.summary or ''}"
                    for n in all_results[-3:]
                )

            prompt = f"""小说：《{ctx.get('project_title', '')}》  主角：{ctx.get('protagonist', '主角')}
创意：{ctx.get('logline', '')}
{vol1.title}（phase={vol1.phase}，共{planned}章）
卷摘要：{vol1.summary or ''}  核心冲突：{vol1.conflict or ''}

【人物阵容】{char_snapshot}
【开局配角功能】{plot_npc_hint or '（无）'}
【故事线】{storyline_summary}
【关系触发事件（可在对应章节引爆）】{relation_triggers}
【反派时间线】{villain_hint}
【核心爽点类型】{tropes or '（未设定）'}  节奏类型：{pace_type}{power_hint}{contract_hint}{prev_summary}

请为本卷第{batch_start}～{batch_end}章生成{batch_count}个章节计划，返回JSON数组：
[
  {{
    "chapter_number": {batch_start},
    "title": "第X章：章节标题（有画面感，≤12字）",
    "summary": "本章主要情节（≤50字，具体到人物+事件+结果）",
    "conflict": "本章核心矛盾（≤25字）",
    "hook": "章末钩子（≤20字，让读者必须看下一章）",
    "involved_characters": ["人物名1", "人物名2"],
    "storyline_refs": ["故事线名称（从已有故事线中选）"],
    "pacing": "fast/normal/slow/climax（章节节奏）",
    "emotional_tone": "exciting/tense/sad/romantic/mysterious/funny/epic/calm",
    "power_milestone": "若本章有境界突破/技能习得则描述，否则填空字符串",
    "has_face_slap": false,
    "has_emotional_beat": false,
    "expected_words": {words_per_chapter}
  }}
]
⚠️ 强制要求：
1. involved_characters 只能使用上方已知人物名，不要发明新名字
2. 前5章：每章必须有一个具体悬念收尾（hook 不能是"主角沉思"之类的废话）
3. 第1章和第3章必须对应 chapter1_hook / chapter3_payoff 的要求（若有）
4. 若 planned=60，前30章节奏偏快（以爽点和信息密度驱动），后30章可有1-2章慢节奏铺垫
5. opening phase 每3章内至少有1次有感知的主角胜利或资源获取
6. storyline_refs 要交叉出现，不要只推进主线
只返回JSON数组，不要解释。"""

            try:
                raw = await self._call_with_retry(
                    system, prompt, task="bootstrap.vol1_chapters", max_tokens=4096
                )
                batch_data = _parse_json(raw)
                if not isinstance(batch_data, list):
                    batch_data = batch_data.get("chapters", [])
            except Exception:
                continue  # 本批失败不阻断整体

            char_name_to_id = ctx.get("char_name_to_id", {})
            storyline_ids_map = ctx.get("storyline_ids", {})

            for item in batch_data:
                ch_num = item.get("chapter_number", batch_start)
                # involved_characters → UUID 列表
                involved_ids = [
                    char_name_to_id[n]
                    for n in item.get("involved_characters", [])
                    if n in char_name_to_id
                ]
                # storyline_refs → UUID 列表
                sl_ids = [
                    storyline_ids_map[n]
                    for n in item.get("storyline_refs", [])
                    if n in storyline_ids_map
                ]
                node = OutlineNode(
                    project_id=project.id,
                    parent_id=vol1.id,
                    node_type="chapter_plan",
                    title=normalize_chapter_plan_title(ch_num, item.get("title")),
                    summary=item.get("summary"),
                    conflict=item.get("conflict"),
                    hook=item.get("hook"),
                    phase=vol1.phase,
                    pacing=item.get("pacing", "normal"),
                    emotional_tone=item.get("emotional_tone"),
                    power_milestone=item.get("power_milestone") or None,
                    involved_character_ids=involved_ids,
                    storyline_ids=sl_ids,
                    expected_words=item.get("expected_words", words_per_chapter),
                    sort_order=ch_num - 1,
                    extra={
                        "has_face_slap": item.get("has_face_slap", False),
                        "has_emotional_beat": item.get("has_emotional_beat", False),
                        "bootstrap_generated": True,
                    },
                )
                self.db.add(node)
                all_results.append(node)

        if all_results:
            self.db.commit()

        ctx["vol1_chapter_count"] = len(all_results)
        return all_results

    # ══════════════════════════════════════════════════════════
    #  Step 13 — 第1章场景蓝图（Scene records）
    # ══════════════════════════════════════════════════════════

    async def _gen_ch1_scenes(
        self, project: Project, vol1_plans: list, ctx: dict
    ) -> list:
        """为第1章生成 3-5 个 Scene（分场）蓝图，写入数据库。

        依赖 vol1_plans[0]（第1章 chapter_plan OutlineNode）；
        chapter_id=null，写章时再绑定；status="planned"，content=null。

        Args:
            project: 当前项目。
            vol1_plans: Step 12.5 生成的第一卷 chapter_plan 节点列表。
            ctx: Bootstrap 上下文字典。

        Returns:
            生成的 Scene 列表；失败时返回空列表。
        """
        if not vol1_plans:
            return []

        ch1_node = vol1_plans[0]  # 第1章 OutlineNode（sort_order=0）

        system = "你是网络小说分场设计专家。只返回JSON数组。"

        # 读取第1章节点信息
        ch1_summary = ch1_node.summary or ""
        ch1_conflict = ch1_node.conflict or ""
        ch1_hook = ch1_node.hook or ""

        # 开局承诺对第1章的要求
        opening_contract = ctx.get("opening_contract") or {}
        first_200 = opening_contract.get("first_200_words_test", "")
        ch1_hook_req = opening_contract.get("chapter1_hook", "")

        # 主角与世界设定锚点（供场景选择地点和感官焦点）
        protagonist = ctx.get("protagonist", "主角")
        world_hint = ctx.get("world_overview", "")[:200]
        power_hint = ctx.get("power_summary", "")[:100]
        positioning = ctx.get("positioning") or {}
        pace_type = positioning.get("pace_type", "medium")

        # opening phase 字数：第1章约 2200 字，3-4 场每场约 500-700 字
        words_per_scene = 550

        prompt = f"""小说：《{ctx.get('project_title', '')}》  主角：{protagonist}
创意：{ctx.get('logline', '')}
世界背景（供选择地点）：{world_hint}
境界提示：{power_hint}

【第1章节点信息】
摘要：{ch1_summary}
核心冲突：{ch1_conflict}
章末钩子：{ch1_hook}

【开局承诺对第1章的要求】
前200字必须完成：{first_200 or '（未设定）'}
章末必须埋下的钩子：{ch1_hook_req or '（未设定）'}
节奏类型：{pace_type}

请为第1章设计 3-5 个分场（Scene），返回JSON数组：
[
  {{
    "order": 1,
    "title": "场标题（可选，≤10字）",
    "time": "故事内时间（如"第1日·晨"）",
    "location_name": "具体地点（结合世界背景，≤15字）",
    "pov_character": "视点人物名（通常是主角）",
    "characters_on_stage": ["在场人物名1", "在场人物名2"],
    "goal": "本场角色想达成的目标（≤20字）",
    "conflict": "阻碍目标实现的障碍或对立（≤20字）",
    "turn": "本场发生的关键转变（≤20字）",
    "hook": "场末留下的疑问或紧张（≤15字，最后一场写章末大钩）",
    "hook_strength": 4,
    "word_budget": {words_per_scene},
    "pacing": "fast/mid/slow",
    "sensory_focus": "sight/sound/smell/taste/touch/mixed"
  }}
]
⚠️ 要求：
1. 第1场必须在前100字内建立主角处境的压力或不公（不要废话开场）
2. 至少有1场包含主角的主动行动（不能全是被动被安排）
3. 最后一场的 hook 必须对应上方「章末必须埋下的钩子」要求
4. pov_character 和 characters_on_stage 中只能用上方已知的人物名
5. 各场字数预算之和约为 2000-2400 字（opening 期标准）
只返回JSON数组，不要解释。"""

        try:
            raw = await self._call_with_retry(system, prompt, task="bootstrap.ch1_scenes")
            data = _parse_json(raw)
            if not isinstance(data, list):
                data = data.get("scenes", [])
        except Exception:
            return []

        char_name_to_id = ctx.get("char_name_to_id", {})
        results: list = []

        for item in data:
            pov_name = item.get("pov_character", protagonist)
            pov_id = char_name_to_id.get(pov_name)

            on_stage_ids = [
                char_name_to_id[n]
                for n in item.get("characters_on_stage", [])
                if n in char_name_to_id
            ]

            scene = Scene(
                project_id=project.id,
                chapter_id=None,          # 章节未写，待写章时绑定
                outline_node_id=ch1_node.id,
                order=item.get("order", len(results) + 1),
                title=item.get("title") or None,
                time=item.get("time") or None,
                location_name=item.get("location_name") or None,
                pov_character_id=pov_id,
                characters_on_stage=on_stage_ids,
                goal=item.get("goal"),
                conflict=item.get("conflict"),
                turn=item.get("turn"),
                hook=item.get("hook"),
                hook_strength=int(item.get("hook_strength", 3)),
                word_budget=int(item.get("word_budget", words_per_scene)),
                pacing=item.get("pacing", "mid"),
                sensory_focus=item.get("sensory_focus", "mixed"),
                status="planned",
                content=None,
                extra={"bootstrap_generated": True},
            )
            self.db.add(scene)
            results.append(scene)

        if results:
            self.db.commit()

        return results

    # ══════════════════════════════════════════════════════════
    #  Step 14 — 全局一致性扫描
    # ══════════════════════════════════════════════════════════

    async def _gen_consistency_scan(self, project, ctx: dict) -> list:
        """Bootstrap 全部步骤完成后，对所有生成物做一次交叉核验。

        检查常见矛盾：境界数字一致性、人物 faction 与势力档案对齐、
        主角掌握技能是否满足境界要求、故事线与卷骨架是否呼应等。
        结果写入 Project.extra.consistency_issues，供前端展示"X处需确认项"。

        Returns:
            list[dict]：每条 issue 含 severity / type / description / suggestion。
        """
        system = (
            "你是有30年经验的网络小说总编辑，专门做稿件前置审核。"
            "只返回 JSON 数组，不要任何解释文字。"
        )

        # 汇总关键字段摘要（压缩到能交叉对比的程度）
        power_summary = ctx.get("power_summary", "（未设定）")
        faction_summary = ctx.get("faction_summary", "（未设定）")
        char_realms = ctx.get("char_realms", {})
        char_names = ctx.get("char_names", [])
        skill_names = ctx.get("skill_names", [])
        item_names = ctx.get("item_names", [])
        storyline_summary = ctx.get("storyline_summary", "（未设定）")
        volumes_summary = ctx.get("volumes_summary", "（未设定）")
        protagonist = ctx.get("protagonist", "主角")

        char_realm_lines = "\n".join(
            f"- {name}：境界={realm}" for name, realm in char_realms.items()
        )

        prompt = f"""小说：《{ctx.get('project_title', '未命名')}》（{ctx.get('genre', '')}）

【境界体系】
{power_summary}

【势力档案摘要】
{faction_summary}

【人物+当前境界】
{char_realm_lines or '（未设定）'}

【人物列表】{', '.join(char_names)}
主角：{protagonist}
主角起点境界（power_systems 中 protagonist_start_rank 对应名称）：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}

【已生成技能】{', '.join(skill_names) or '（无）'}
【已生成道具】{', '.join(item_names) or '（无）'}

【故事线】
{storyline_summary}

【卷级骨架】
{volumes_summary}

请对以上信息做「交叉核验」，找出所有显著矛盾或风险项，返回JSON数组：
[
  {{
    "severity": "high/medium/low",
    "type": "realm_mismatch/faction_mismatch/skill_requirement/storyline_gap/timeline_conflict/other",
    "description": "具体矛盾描述，举例说明哪里和哪里不一致（30字内）",
    "suggestion": "最简单的修复建议（20字内）"
  }}
]

检查重点：
1. 人物卡中 current_realm 是否在境界体系 levels 的合法名称里？
2. 主角和重要人物的 faction 是否与势力档案中的势力名吻合（允许模糊匹配）？
3. 故事线类型（main/sub/romance等）与卷骨架描述的冲突走向是否吻合？
4. 若有多条故事线，是否都能在卷骨架中找到对应的推进节点？
5. 境界体系 protagonist_start_rank 与主角人物卡 current_realm 是否对应同一境界？
如果没有发现矛盾，返回空数组 []。只返回JSON数组，不要任何解释。"""

        try:
            raw = await self._call_with_retry(
                system, prompt, max_tokens=2048, task="bootstrap.consistency_scan"
            )
            issues = _parse_json(raw)
            if not isinstance(issues, list):
                issues = []
        except Exception:
            issues = []

        # 写入 Project.extra
        try:
            extra = project.extra or {}
            extra["consistency_issues"] = issues
            project.extra = extra
            self.db.commit()
        except Exception:
            pass

        return issues

    # ══════════════════════════════════════════════════════════
    #  Step 12 — 开局前十章追读承诺清单
    # ══════════════════════════════════════════════════════════

    async def _gen_opening_contract(self, project, ctx: dict) -> dict:
        """生成开局前十章的「追读承诺清单」。

        网文能否存活，开局前十章决定 70%。本步骤从全部已生成设定中
        提炼「每章必须兑现的追读钩子」，写入 Project.extra.opening_contract。

        Returns:
            dict：包含 chapter1_hook / chapter3_payoff / chapter5_foreshadow /
                  chapter10_subscribe_reason / first_200_words_test 等字段。
        """
        system = (
            "你是有30年经验的网络小说总编辑，专门做开局追读策划。"
            "只返回 JSON，不要任何解释文字。"
        )

        positioning = ctx.get("positioning") or {}
        tropes = positioning.get("tropes", [])
        pace_type = positioning.get("pace_type", "medium")
        target_audience = positioning.get("target_audience", "")

        prompt = f"""小说：《{ctx.get('project_title', '未命名')}》（{ctx.get('genre', '')}）
主角：{ctx.get('protagonist', '主角')}  起点境界：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}
创意：{ctx.get('logline', '')}
核心爽点：{', '.join(tropes) or '（未设定）'}
节奏类型：{pace_type}
目标读者：{target_audience or '（未设定）'}
世界观：{ctx.get('world_overview', '')[:200]}
卷一概述：{(ctx.get('volumes_summary') or '').split('|')[0][:100]}

请为本书开局前10章制定「追读承诺清单」，这是编辑决定是否签约的核心审核项。
返回JSON：
{{
  "first_200_words_test": "第一章前200字必须完成的3件事：1) xxx 2) xxx 3) xxx（具体到场景/信息/情绪，不要废话）",
  "chapter1_hook": "第1章末尾钩子：读者读完第1章后必须知道答案才肯继续的那个问题（一句话）",
  "chapter3_payoff": "第3章小爽点：主角在前3章内必须获得的第一次具体反转/胜利/资源（要具体，不要'小小展示实力'这种废话）",
  "chapter5_foreshadow": "第5章必须埋下的长线伏笔：能支撑读者追到第30章的那个谜（一句话，具体到人物或秘密）",
  "chapter10_subscribe_reason": "第10章末尾：读者为什么要付费订阅第11章？给出一个让人无法放下的悬念设计（具体手法：强敌登场/秘密揭示/关系逆转/etc）",
  "opening_traps_to_avoid": ["开局必须避免的3个常见坑（针对本书题材和爽点类型的具体风险）"],
  "chapter_rhythm": "前10章节奏设计：哪章快哪章慢，何时第一次打脸，何时第一次建立情感连接（50字内）"
}}
要求：每个字段必须结合本书具体设定给出，禁止使用通用模板语言。"""

        try:
            raw = await self._call_with_retry(
                system, prompt, max_tokens=2048, task="bootstrap.opening_contract"
            )
            contract = _parse_json(raw)
            if not isinstance(contract, dict):
                contract = {}
        except Exception:
            contract = {}

        # 写入 Project.extra（兼容保留，原有读取路径不受影响）
        try:
            extra = project.extra or {}
            extra["opening_contract"] = contract
            project.extra = extra
            self.db.commit()
        except Exception:
            pass

        # 同时写入 ctx，供 Step 12.5（_gen_vol1_chapter_plans）直接读取，
        # 无需再从 project.extra 回查——避免首次运行时时序错位导致联动为空
        ctx["opening_contract"] = contract

        # ── 里程碑字段映射 → ReaderPromise 表 ──────────────────────
        # 将结构化里程碑字段逐条写入 ReaderPromise，供写章 prompt 按章号查询注入，
        # 避免每次都解析 JSON 字段；保留 extra.opening_contract 作为只读原始存档。
        #
        # 映射规则：
        #   chapter1_hook          → source_ch=1,  window=2,  type=chapter_ending   (引导到第3章)
        #   chapter3_payoff        → source_ch=0,  window=3,  type=protagonist_claim (前3章内兑现)
        #   chapter5_foreshadow    → source_ch=5,  window=25, type=chapter_ending   (追到第30章)
        #   chapter10_subscribe    → source_ch=10, window=1,  type=chapter_ending   (钩到第11章)
        #   first_200_words_test   → source_ch=1,  window=0,  type=name_implication (写作指引)
        if contract:
            milestone_map = [
                {
                    "key": "chapter1_hook",
                    "promise_type": "chapter_ending",
                    "source_chapter_number": 1,
                    "expected_chapter_window": 2,
                    "priority": 5,
                    "audience_aware": 4,
                },
                {
                    "key": "chapter3_payoff",
                    "promise_type": "protagonist_claim",
                    "source_chapter_number": 0,
                    "expected_chapter_window": 3,
                    "priority": 4,
                    "audience_aware": 3,
                },
                {
                    "key": "chapter5_foreshadow",
                    "promise_type": "chapter_ending",
                    "source_chapter_number": 5,
                    "expected_chapter_window": 25,
                    "priority": 3,
                    "audience_aware": 2,
                },
                {
                    "key": "chapter10_subscribe_reason",
                    "promise_type": "chapter_ending",
                    "source_chapter_number": 10,
                    "expected_chapter_window": 1,
                    "priority": 5,
                    "audience_aware": 5,
                },
                {
                    "key": "first_200_words_test",
                    "promise_type": "name_implication",
                    "source_chapter_number": 1,
                    "expected_chapter_window": 0,
                    "priority": 2,
                    "audience_aware": 1,
                },
            ]
            try:
                for m in milestone_map:
                    text = contract.get(m["key"])
                    if not text:
                        continue
                    # opening_traps_to_avoid 是数组，跳过（不适合单条 promise）
                    if isinstance(text, list):
                        text = "；".join(str(t) for t in text if t)
                    if not text.strip():
                        continue
                    rp = ReaderPromise(
                        project_id=project.id,
                        promise_text=str(text).strip(),
                        promise_type=m["promise_type"],
                        source_chapter_number=m["source_chapter_number"],
                        expected_chapter_window=m["expected_chapter_window"],
                        priority=m["priority"],
                        audience_aware=m["audience_aware"],
                        status="open",
                        extra={"origin": "bootstrap_opening_contract", "contract_key": m["key"]},
                    )
                    self.db.add(rp)
                self.db.commit()
            except Exception:
                pass  # ReaderPromise 写入失败不阻断主流程

        return contract

    # ══════════════════════════════════════════════════════════
    #  单次全量保存（方案B）
    # ══════════════════════════════════════════════════════════

    async def _save_all(self, data: dict, logline: str, premise: str = "", target_words: int = 1_200_000) -> Project:
        """把方案B生成的完整 JSON 一次性存库"""
        p = data["project"]
        project = Project(
            title=p["title"],
            genre=p.get("genre", "玄幻"),
            logline=logline,
            premise=p.get("premise") or premise or "",
            world_overview=p.get("world_overview", ""),
            story_core=p.get("story_core", {}),
            target_words=target_words,
        )
        self.db.add(project)
        self.db.flush()

        # 境界体系
        for i, ps in enumerate(data.get("power_systems", [])):
            levels = ps.get("levels", [])
            start_raw = ps.get("protagonist_start_rank")
            if start_raw is None:
                start_raw = ps.get("protagonist_current_rank")
            end_raw = ps.get("protagonist_end_rank")
            self.db.add(PowerSystem(
                project_id=project.id,
                name=ps.get("name", "修炼体系"),
                system_type=ps.get("system_type", "cultivation"),
                description=ps.get("description"),
                cultivation_method=ps.get("cultivation_method"),
                breakthrough_condition=ps.get("breakthrough_condition"),
                special_rules=ps.get("special_rules"),
                levels=levels,
                protagonist_current_rank=_coerce_power_system_rank(start_raw, levels, 1),
                protagonist_end_rank=_coerce_power_system_rank(end_raw, levels, None),
                sort_order=i,
            ))

        # 势力
        for i, f in enumerate(data.get("factions", [])):
            self.db.add(Faction(
                project_id=project.id,
                name=f.get("name", f"势力{i+1}"),
                faction_type=f.get("faction_type", "sect"),
                alignment=f.get("alignment", "neutral"),
                description=f.get("description"),
                territory=f.get("territory"),
                strength_level=f.get("strength_level"),
                member_count=f.get("member_count"),
                top_power=f.get("top_power"),
                goals=f.get("goals"),
                resources=f.get("resources"),
                history=f.get("history"),
                secrets=f.get("secrets"),
                rivals=f.get("rivals", []),
                allies=f.get("allies", []),
                attitude_to_protagonist=f.get("attitude_to_protagonist", "neutral"),
                sort_order=i,
                extra={"active_period": f.get("active_period", "")},
            ))

        # 故事线
        for i, sl in enumerate(data.get("storylines", [])):
            self.db.add(StoryLine(
                project_id=project.id,
                name=sl.get("name", f"故事线{i+1}"),
                line_type=sl.get("line_type", "sub"),
                description=sl.get("description"),
                core_conflict=sl.get("core_conflict"),
                resolution_direction=sl.get("resolution_direction"),
                status=sl.get("status", "planned"),
                start_chapter=_safe_int(sl.get("start_chapter"), None),
                sort_order=i,
            ))

        # 技能
        for i, sk in enumerate(data.get("skills", [])):
            self.db.add(Skill(
                project_id=project.id,
                name=sk.get("name", f"功法{i+1}"),
                skill_type=sk.get("skill_type", "combat"),
                grade=sk.get("grade", "earth"),
                source=sk.get("source"),
                level_required=sk.get("level_required"),
                description=sk.get("description"),
                effects=sk.get("effects"),
                limitations=sk.get("limitations"),
                mastered_by_character_ids=sk.get("mastered_by", []),
                sort_order=i,
            ))

        # 道具
        for i, it in enumerate(data.get("items", [])):
            self.db.add(Item(
                project_id=project.id,
                name=it.get("name", f"道具{i+1}"),
                item_type=it.get("item_type", "artifact"),
                rarity=it.get("rarity", "rare"),
                description=it.get("description"),
                origin=it.get("origin"),
                effects=it.get("effects"),
                limitations=it.get("limitations"),
                story_significance=it.get("story_significance"),
                status=it.get("status", "intact"),
                sort_order=i,
            ))

        # 世界观设定卡（纯叙事类）
        for s in data.get("settings", []):
            self.db.add(WorldSetting(
                project_id=project.id,
                title=s.get("title", "设定"),
                content=s.get("content", ""),
                tags=s.get("tags", []),
                extra=_setting_extra_with_defaults(s),
            ))

        _VALID_TIERS = {"core", "arc", "plot", "background"}
        char_map = {}
        for c in data.get("characters", []):
            _tier = c.get("character_tier", "core")
            if _tier not in _VALID_TIERS:
                _tier = "core"
            char = Character(
                project_id=project.id,
                name=c.get("name", "未命名"),
                role=c.get("role", "supporting"),
                character_tier=_tier,
                gender=c.get("gender"),
                age=c.get("age"),
                faction=c.get("faction"),
                personality=c.get("personality"),
                background=c.get("background"),
                motivation=c.get("motivation"),
                arc=c.get("arc"),
                current_realm=c.get("current_realm"),
                speech_style=c.get("speech_style"),
                values=c.get("values"),
                fear=c.get("fear"),
                secrets=c.get("secrets"),
                strengths=c.get("strengths", []),
                weaknesses=c.get("weaknesses", []),
                special_traits=c.get("special_traits", []),
            )
            self.db.add(char)
            self.db.flush()
            char_map[char.name] = char

        def save_node(item, idx=0):
            # bootstrap 阶段只保存卷级节点，忽略 children
            planned = _safe_int(item.get("planned_chapters"), 60)
            if planned not in (30, 60):
                planned = 60
            node = OutlineNode(
                project_id=project.id,
                parent_id=None,
                node_type="volume",
                title=item.get("title", f"第{idx+1}卷"),
                summary=item.get("summary"),
                hook=item.get("hook"),
                conflict=item.get("conflict"),
                sort_order=_safe_int(item.get("sort_order"), idx),
                extra={"planned_chapters": planned},
            )
            self.db.add(node)
            self.db.flush()

        outline_data = data.get("outline", data.get("volumes", []))
        for idx, vol in enumerate(outline_data):
            save_node(vol, idx=idx)

        for m in data.get("memory", []):
            self.db.add(MemoryChunk(
                project_id=project.id,
                memory_type=m.get("memory_type", "setting"),
                title=m.get("title"),
                content=m.get("content", ""),
                tags=m.get("tags", []),
                chapter_number=0,
            ))

        for r in data.get("relations", []):
            fc = char_map.get(r.get("from_name", ""))
            tc = char_map.get(r.get("to_name", ""))
            if fc and tc:
                self.db.add(CharacterRelationship(
                    project_id=project.id,
                    from_character_id=fc.id,
                    to_character_id=tc.id,
                    relation_type=r.get("relation_type", "认识"),
                    description=r.get("description"),
                    intensity=_safe_int(r.get("intensity"), 5, min_v=1, max_v=10) or 5,
                ))

        self.db.commit()
        self.db.refresh(project)
        return project

    async def _complete_single_shot_data(self, data: dict, logline: str, premise: str = "") -> dict:
        """Gemini 单次生成如果少给关键数组，保存前按同一规格补齐。"""
        if not isinstance(data, dict):
            return data

        data.setdefault("settings", [])
        data.setdefault("characters", [])
        data["settings"] = await self._complete_missing_settings(data, logline, premise)
        data["characters"] = await self._complete_missing_characters(data, logline, premise)
        return data

    async def _complete_missing_settings(self, data: dict, logline: str, premise: str = "") -> list:
        existing = data.get("settings") or []
        existing_titles = {
            item.get("title")
            for item in existing
            if isinstance(item, dict) and item.get("title")
        }
        missing_blueprints = [
            bp for bp in GEMINI_SETTING_BLUEPRINTS
            if bp["title"] not in existing_titles
        ]
        if not missing_blueprints:
            return existing

        system = "你是网络小说世界观设计专家。只返回JSON数组。"
        prompt = f"""补齐缺失的世界设定卡。

创意：{logline}
立意与类型：{premise[:2000] or data.get('project', {}).get('premise', '')[:2000]}
项目基础：{json.dumps(data.get('project', {}), ensure_ascii=False)[:4000]}
已有设定标题：{json.dumps(sorted(existing_titles), ensure_ascii=False)}

只生成以下缺失蓝图对应的设定卡：
{json.dumps(missing_blueprints, ensure_ascii=False, indent=2)}

返回JSON数组。每张卡字段：
title, content, tags, extra。
要求：
1) title/category/tags/importance/stage 必须与蓝图一致，写入 extra。
2) "作品立意" 必须填写 extra.core 全字段。
3) 其他卡必须填写 extra.focus 全字段：summary, story_function, conflict_seed, cost_or_risk, affected_people, exception_or_loophole, visual_anchor。
4) content 至少180字，要有名词、地点、制度、代价、例外或冲突。
只返回JSON数组，不要解释。"""
        raw = await self.ai._call_ai(
            system,
            prompt,
            max_tokens=settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS,
            context={"operation": "bootstrap_complete_settings"},
        )
        parsed = _parse_json(raw)
        if not isinstance(parsed, list):
            parsed = parsed.get("settings", [])
        completed = [
            item for item in parsed
            if isinstance(item, dict) and item.get("title") not in existing_titles
        ]
        return [*existing, *completed]

    async def _complete_missing_characters(self, data: dict, logline: str, premise: str = "") -> list:
        existing = data.get("characters") or []
        existing_names = {
            item.get("name")
            for item in existing
            if isinstance(item, dict) and item.get("name")
        }
        missing_count = max(0, CHARACTER_TARGET - len(existing))
        if missing_count <= 0:
            return existing

        system = "你是网络小说人物设计专家。只返回JSON数组。"
        prompt = f"""补齐缺失的人物档案。

创意：{logline}
立意与类型：{premise[:1600] or data.get('project', {}).get('premise', '')[:1600]}
项目基础：{json.dumps(data.get('project', {}), ensure_ascii=False)[:3000]}
已有人物：{json.dumps(existing, ensure_ascii=False)[:6000]}
已有人物名禁止重复：{json.dumps(sorted(existing_names), ensure_ascii=False)}

还需要生成 {missing_count} 个人物，使总人物数达到 {CHARACTER_TARGET} 个。
总阵容目标：1 主角、3 核心配角、2 反派、2 师长/势力角色。

返回JSON数组。每个人物字段：
name, role, gender, age, faction, personality, background, motivation, arc, current_realm,
speech_style, values, fear, secrets, strengths, weaknesses, special_traits。
role 只能是 protagonist / supporting / antagonist。
只返回JSON数组，不要解释。"""
        raw = await self.ai._call_ai(
            system,
            prompt,
            max_tokens=settings.GEMINI_CHARACTER_COMPLETION_MAX_TOKENS,
            context={"operation": "bootstrap_complete_characters"},
        )
        parsed = _parse_json(raw)
        if not isinstance(parsed, list):
            parsed = parsed.get("characters", [])
        completed = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name or name in existing_names:
                continue
            completed.append(item)
            existing_names.add(name)
            if len(existing) + len(completed) >= CHARACTER_TARGET:
                break
        return [*existing, *completed]

    # ══════════════════════════════════════════════════════════
    #  带重试的 AI 调用
    # ══════════════════════════════════════════════════════════

    async def _call_with_retry(
        self,
        system: str,
        prompt: str,
        max_retries: int = 2,
        max_tokens: int = 2048,
        *,
        task: Optional[str] = None,
    ) -> str:
        """调用 AI，失败时最多重试 max_retries 次。

        Args:
            task: 任务名，传给 ``ai._call_ai`` 让其按任务级采样配置发起调用；
                未传入时使用网关默认采样（与历史行为一致）。
        """
        last_err = None
        for attempt in range(max_retries):
            try:
                return await self.ai._call_ai(
                    system,
                    prompt,
                    max_tokens=max_tokens,
                    task=task,
                )
            except Exception as e:
                last_err = e
                continue
        raise last_err


def __getattr__(name: str):
    """兼容旧代码对 GEMINI_*_MAX_TOKENS 的模块级访问（值来自 Settings / 环境变量）。"""
    if name == "GEMINI_SINGLE_SHOT_MAX_TOKENS":
        return settings.GEMINI_SINGLE_SHOT_MAX_TOKENS
    if name == "GEMINI_SETTING_COMPLETION_MAX_TOKENS":
        return settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
