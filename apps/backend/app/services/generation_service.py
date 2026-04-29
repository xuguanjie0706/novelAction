"""
Generation Service — 一句话创意 → 全量小说初始化

方案 A (sequential): 串行6步，每步独立 prompt，适合 qwen3:8b 等小模型
方案 B (single_shot): 单次全量生成，适合 Gemini / GPT-4o 等大 context 模型

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

from app.services.ai_service import AIService
from app.models import (
    Project, WorldSetting, Character, CharacterRelationship,
    OutlineNode, MemoryChunk, PowerSystem, StoryLine,
    Faction, Skill, Item
)


# ─────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────

def _parse_json(text: str):
    """容错 JSON 解析：去 markdown fence、去 think 标签、strip 空白"""
    # 去掉 <think>...</think>（qwen3 thinking mode）
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
GEMINI_SINGLE_SHOT_MAX_TOKENS = 32768
GEMINI_SETTING_COMPLETION_MAX_TOKENS = 16384


def _setting_blueprints_for_prompt() -> str:
    return json.dumps(GEMINI_SETTING_BLUEPRINTS, ensure_ascii=False, indent=2)


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
    return extra


def _single_shot_prompt(logline: str, premise: str = "") -> str:
    setting_blueprints = _setting_blueprints_for_prompt()
    return f"""根据以下创意，生成完整的小说初始化数据：

创意：{logline}
立意与类型（作品基本面）：{premise[:2000] or '（未填写，请根据创意自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}

返回一个 JSON 对象，顶层字段固定为：
project, power_systems, factions, storylines, skills, items, characters, settings, outline, memory, relations。

下面是字段结构说明，不代表数组数量；数组数量必须遵守后面的硬性数量规则。

project 字段结构：
{{
  "title": "小说名称",
  "genre": "玄幻",
  "logline": "{logline}",
  "premise": "立意与类型（含作品定位、主题命题、核心矛盾、禁忌边界，可落地，至少200字）",
  "world_overview": "世界观简述（300~500字）",
  "story_core": {{"drive": "故事驱动力", "conflict": "核心矛盾", "theme": "主题", "differentiation": "差异化"}}
}}

power_systems 每个元素字段：
name, system_type, description, cultivation_method, breakthrough_condition, special_rules,
protagonist_start_rank, protagonist_end_rank, levels。
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
name, role, gender, age, faction, personality, background, motivation, arc, current_realm,
speech_style, values, fear, secrets, strengths, weaknesses, special_traits。

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
- outline 必须生成 4~8 卷。
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
    ) -> AsyncGenerator[str, None]:
        if mode == "single_shot":
            async for chunk in self._single_shot(logline, premise):
                yield chunk
        else:
            async for chunk in self._sequential(logline, premise):
                yield chunk

    # ══════════════════════════════════════════════════════════
    #  方案 A：串行步进
    # ══════════════════════════════════════════════════════════

    async def _sequential(self, logline: str, premise: str = "") -> AsyncGenerator[str, None]:
        ctx = {"logline": logline, "premise": premise}   # 上下文在步骤间传递

        try:
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

            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            yield _sse("error", step="unknown", message=str(e))

    # ══════════════════════════════════════════════════════════
    #  方案 B：单次全量（适合 Gemini）
    # ══════════════════════════════════════════════════════════

    async def _single_shot(self, logline: str, premise: str = "") -> AsyncGenerator[str, None]:
        yield _sse("step_start", step="all", label="AI 全量生成中（单次调用）...")

        system = """你是专业的网络小说策划，根据一句话创意生成完整的小说初始化数据。
严格返回 JSON，不要任何额外文字。"""
        prompt = _single_shot_prompt(logline, premise)

        try:
            raw = await self.ai._call_ai(
                system,
                prompt,
                max_tokens=GEMINI_SINGLE_SHOT_MAX_TOKENS,
                context={"operation": "bootstrap_single_shot"},
            )
            data = _parse_json(raw)
            data = await self._complete_single_shot_data(data, logline, premise)
            yield _sse("step_done", step="all", count=1)

            yield _sse("step_start", step="saving", label="写入数据库...")
            project = await self._save_all(data, logline, premise)
            yield _sse("step_done", step="saving", count=1)
            yield _sse("complete", project_id=str(project.id))

        except Exception as e:
            yield _sse("error", step="all", message=str(e))

    # ══════════════════════════════════════════════════════════
    #  Step 1 — 项目基础信息
    # ══════════════════════════════════════════════════════════

    async def _gen_project(self, ctx: dict):
        system = "你是网络小说策划专家。根据创意生成项目基础信息，只返回JSON。"
        prompt = f"""创意：{ctx['logline']}
立意与类型：{ctx.get('premise')[:1500] if ctx.get('premise') else '（未填写，请自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}

返回JSON：
{{
  "title": "小说名（2~6个汉字，有冲击力）",
  "genre": "玄幻",
  "premise": "使用 markdown 二级标题输出完整《立意与类型（PREMISE）》，必须包含：作品定位、核心一句话、类型与篇幅、主题与命题、核心矛盾、主角概况、结局倾向、最坏会怎样（收束边界）、希望读者记住的一个画面、叙事视角与禁忌",
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
2) premise 中必须给出清晰的目标读者、篇幅规模、禁忌边界
3) theme / conflict 要与 premise 一致
4) 只返回 JSON，不要解释文字。"""

        raw = await self._call_with_retry(
            system,
            prompt,
            max_tokens=GEMINI_SETTING_COMPLETION_MAX_TOKENS,
        )
        data = _parse_json(raw)

        project = Project(
            title=data["title"],
            genre=data.get("genre", "玄幻"),
            logline=ctx["logline"],
            premise=data.get("premise") or ctx.get("premise") or "",
            world_overview=data.get("world_overview", ""),
            story_core=data.get("story_core", {}),
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        ctx["project_title"] = project.title
        ctx["genre"] = project.genre
        ctx["world_overview"] = project.world_overview
        ctx["story_core"] = data.get("story_core", {})
        ctx["premise"] = project.premise or ctx.get("premise") or ""

        return project, ctx

    # ══════════════════════════════════════════════════════════
    #  Step 3 — 势力体系（结构化 Faction 记录）
    # ══════════════════════════════════════════════════════════

    async def _gen_factions(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}
境界体系：{ctx.get('power_summary', '（未设定）')}

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
    "attitude_to_protagonist": "hostile"
  }}
]
faction_type 只能是: sect / kingdom / family / guild / evil / race / other
alignment 只能是: protagonist / neutral / antagonist / unknown
active_period 只能是: early / mid / late / full
attitude_to_protagonist 只能是: friendly / hostile / neutral / subordinate / superior
必须涵盖主角阵营势力、核心反派势力、中立势力各至少1个。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt)
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
                extra={"active_period": item.get("active_period", "")},
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
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 6 — 核心功法技能（结构化 Skill 记录）
    # ══════════════════════════════════════════════════════════

    async def _gen_key_skills(self, project: Project, ctx: dict):
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
主要人物：{', '.join(ctx.get('char_names', [])[:6])}

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
    "mastered_by": ["掌握此技能的人物名（从上面人物列表选）"]
  }}
]
skill_type 只能是: combat / defense / movement / support / bloodline / special
grade 只能是: mortal / earth / sky / profound / saint / divine / supreme
选择对故事最重要的技能，包含主角核心战技和1~2个反派标志性技能。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("skills", [])

        char_name_map = {c: c for c in ctx.get("char_names", [])}
        results = []
        for i, item in enumerate(data):
            mastered = [n for n in item.get("mastered_by", []) if n in char_name_map]
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
                mastered_by_character_ids=mastered,
                sort_order=i,
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
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
主要人物：{', '.join(ctx.get('char_names', [])[:6])}
主要势力：{', '.join(ctx.get('faction_names', [])[:4])}

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
    "status": "intact"
  }}
]
item_type 只能是: weapon / armor / pill / artifact / material / scroll / beast / other
rarity 只能是: common / uncommon / rare / epic / legendary / mythic / unique
status 只能是: intact / damaged / destroyed / lost / unknown
选择对主线剧情影响最大的道具，包含主角核心战力道具和1~2个关键麦高芬道具。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("items", [])

        results = []
        for i, item in enumerate(data):
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
                sort_order=i,
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

        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:1000] or '（未填写，请自动提炼）'}
世界观：{ctx['world_overview'][:300]}

已独立生成的结构化数据（设定卡不要重复这些内容）：
- 境界体系：{power_brief}
- 势力档案：{faction_brief}

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
只返回JSON数组，不要解释。"""

        raw = await self._call_with_retry(system, prompt)
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
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}

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
      {{"rank": 1, "name": "境界名", "description": "简述", "abilities": ["能力1"]}},
      {{"rank": 2, "name": "境界名", "description": "简述", "abilities": ["能力1"]}}
    ]
  }}
]
system_type 只能是: cultivation / magic / ability / tech / hybrid
levels 至少包含 6 个境界，按强弱从低到高排列。
只返回JSON数组，不要说明文字。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("power_systems", [])

        results = []
        for i, item in enumerate(data):
            ps = PowerSystem(
                project_id=project.id,
                name=item.get("name", "修炼体系"),
                system_type=item.get("system_type", "cultivation"),
                description=item.get("description"),
                cultivation_method=item.get("cultivation_method"),
                breakthrough_condition=item.get("breakthrough_condition"),
                special_rules=item.get("special_rules"),
                levels=item.get("levels", []),
                protagonist_current_rank=item.get("protagonist_start_rank", 1),
                protagonist_end_rank=item.get("protagonist_end_rank"),
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
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
故事核：{ctx['story_core'].get('conflict', '')} | 主题：{ctx['story_core'].get('theme', '')}
境界体系：{ctx.get('power_summary', '（未设定）')}

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

        raw = await self._call_with_retry(system, prompt)
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
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:800] or '（未填写）'}
故事核：冲突={ctx['story_core'].get('conflict','')}，主题={ctx['story_core'].get('theme','')}{power_hint}

生成8个人物（至少：1主角+3核心配角+2反派+2师长/势力角色），返回JSON数组：
[
  {{
    "name": "姓名", "role": "protagonist",
    "gender": "男", "age": "17", "faction": "所属势力",
    "personality": "性格（2句话）",
    "background": "背景经历（3句话）",
    "motivation": "核心动机",
    "arc": "人物弧线（从X到Y的成长）",
    "current_realm": "当前境界（或能力层级）",
    "speech_style": "说话风格",
    "values": "价值观",
    "fear": "最恐惧的东西",
    "secrets": "不愿公开的秘密",
    "strengths": ["特质1", "特质2"],
    "weaknesses": ["弱点1"],
    "special_traits": ["特殊能力或标志性特征"]
  }}
]
role 只能是: protagonist / supporting / antagonist"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("characters", [])

        results = []
        for item in data:
            c = Character(
                project_id=project.id,
                name=item.get("name", "未命名"),
                role=item.get("role", "supporting"),
                gender=item.get("gender"),
                age=item.get("age"),
                faction=item.get("faction"),
                personality=item.get("personality"),
                background=item.get("background"),
                motivation=item.get("motivation"),
                arc=item.get("arc"),
                current_realm=item.get("current_realm"),
                speech_style=item.get("speech_style"),
                values=item.get("values"),
                fear=item.get("fear"),
                secrets=item.get("secrets"),
                strengths=item.get("strengths", []),
                weaknesses=item.get("weaknesses", []),
                special_traits=item.get("special_traits", []),
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
        prompt = f"""小说：《{ctx['project_title']}》主角：{ctx['protagonist']}
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:700] or '（未填写）'}
设定摘要：{ctx['settings_summary']}{storyline_hint}

根据故事规模规划卷级结构，返回JSON数组。
卷数建议4~8卷（最少3卷），每卷约60章（过渡卷可30章）。

[
  {{
    "title": "第一卷：卷标题（有画面感，带悬念）",
    "sort_order": 0,
    "summary": "本卷核心剧情概述，60字内",
    "hook": "本卷核心悬念：读者最想知道的问题",
    "conflict": "本卷主要矛盾冲突",
    "planned_chapters": 60
  }}
]
planned_chapters 只能填 30 或 60，不要其他数字。
只返回JSON数组，不要任何说明文字。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("outline", data.get("volumes", []))

        results = []
        for i, vol in enumerate(data):
            planned = vol.get("planned_chapters", 60)
            if planned not in (30, 60):
                planned = 60
            node = OutlineNode(
                project_id=project.id,
                parent_id=None,
                node_type="volume",
                title=vol.get("title", f"第{i+1}卷"),
                summary=vol.get("summary"),
                hook=vol.get("hook"),
                conflict=vol.get("conflict"),
                sort_order=vol.get("sort_order", i),
                extra={"planned_chapters": planned},
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

        raw = await self._call_with_retry(system, prompt)
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

        name_map = {c.name: c for c in chars}
        system = "你是人物关系设计专家。只返回JSON数组。"
        prompt = f"""人物列表：{', '.join(ctx['char_names'])}
创意：{ctx['logline']}

生成人物关系，返回JSON数组：
[
  {{
    "from_name": "人物A", "to_name": "人物B",
    "relation_type": "师徒",
    "description": "关系描述",
    "intensity": 8
  }}
]
intensity 为 1~10 的整数，只能使用上面列出的人物名"""

        try:
            raw = await self._call_with_retry(system, prompt)
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
            rel = CharacterRelationship(
                project_id=project.id,
                from_character_id=from_char.id,
                to_character_id=to_char.id,
                relation_type=item.get("relation_type", "认识"),
                description=item.get("description"),
                intensity=int(item.get("intensity", 5)),
            )
            self.db.add(rel)
            results.append(rel)

        self.db.commit()
        return results

    # ══════════════════════════════════════════════════════════
    #  单次全量保存（方案B）
    # ══════════════════════════════════════════════════════════

    async def _save_all(self, data: dict, logline: str, premise: str = "") -> Project:
        """把方案B生成的完整 JSON 一次性存库"""
        p = data["project"]
        project = Project(
            title=p["title"],
            genre=p.get("genre", "玄幻"),
            logline=logline,
            premise=p.get("premise") or premise or "",
            world_overview=p.get("world_overview", ""),
            story_core=p.get("story_core", {}),
        )
        self.db.add(project)
        self.db.flush()

        # 境界体系
        for i, ps in enumerate(data.get("power_systems", [])):
            self.db.add(PowerSystem(
                project_id=project.id,
                name=ps.get("name", "修炼体系"),
                system_type=ps.get("system_type", "cultivation"),
                description=ps.get("description"),
                cultivation_method=ps.get("cultivation_method"),
                breakthrough_condition=ps.get("breakthrough_condition"),
                special_rules=ps.get("special_rules"),
                levels=ps.get("levels", []),
                protagonist_current_rank=ps.get("protagonist_start_rank", 1),
                protagonist_end_rank=ps.get("protagonist_end_rank"),
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
                start_chapter=sl.get("start_chapter"),
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

        char_map = {}
        for c in data.get("characters", []):
            char = Character(
                project_id=project.id,
                name=c.get("name", "未命名"),
                role=c.get("role", "supporting"),
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
            planned = item.get("planned_chapters", 60)
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
                sort_order=item.get("sort_order", idx),
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
                    intensity=int(r.get("intensity", 5)),
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
            max_tokens=GEMINI_SETTING_COMPLETION_MAX_TOKENS,
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
            max_tokens=6000,
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
    ) -> str:
        """调用 AI，失败时最多重试 max_retries 次"""
        last_err = None
        for attempt in range(max_retries):
            try:
                return await self.ai._call_ai(system, prompt, max_tokens=max_tokens)
            except Exception as e:
                last_err = e
                continue
        raise last_err
