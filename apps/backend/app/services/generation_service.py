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
    OutlineNode, MemoryChunk, PowerSystem, StoryLine
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

            # Step 2 — 世界观设定
            yield _sse("step_start", step="settings", label="生成世界观设定卡...")
            settings = await self._gen_settings(project, ctx)
            yield _sse("step_done", step="settings", count=len(settings))

            # Step 3 — 境界体系（先于人物，供角色 current_realm 引用真实境界名）
            yield _sse("step_start", step="power_systems", label="生成境界体系...")
            power_systems = await self._gen_power_systems(project, ctx)
            yield _sse("step_done", step="power_systems", count=len(power_systems),
                       preview=power_systems[0].name if power_systems else "")

            # Step 4 — 故事线（先于人物和大纲，供 storyline_ids 引用真实 UUID）
            yield _sse("step_start", step="storylines", label="生成故事线...")
            storylines = await self._gen_storylines(project, ctx)
            yield _sse("step_done", step="storylines", count=len(storylines))

            # Step 5 — 人物
            yield _sse("step_start", step="characters", label="生成人物库...")
            chars = await self._gen_characters(project, ctx)
            yield _sse("step_done", step="characters", count=len(chars),
                       preview="、".join(c.name for c in chars[:3]))

            # Step 6 — 卷级骨架（章节大纲由作者按卷触发生成）
            yield _sse("step_start", step="volumes", label="规划卷级结构...")
            nodes = await self._gen_volumes(project, ctx)
            yield _sse("step_done", step="volumes", count=len(nodes),
                       preview=f"共{len(nodes)}卷")

            # Step 5 — 记忆库种子
            yield _sse("step_start", step="memory", label="生成记忆库种子...")
            mems = await self._gen_memory(project, ctx)
            yield _sse("step_done", step="memory", count=len(mems))

            # Step 6 — 人物关系
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

        prompt = f"""根据以下创意，生成完整的小说初始化数据：

创意：{logline}
立意与类型（作品基本面）：{premise[:2000] or '（未填写，请根据创意自动提炼作品定位、主题命题、核心矛盾与禁忌边界）'}

返回以下 JSON 结构（严格遵守字段名）：
{{
  "project": {{
    "title": "小说名称",
    "genre": "玄幻",
    "logline": "{logline}",
    "premise": "立意与类型：作品定位、核心一句话、类型篇幅、主题命题、核心矛盾、结局倾向、禁忌边界等",
    "world_overview": "世界观简述（200字）",
    "story_core": {{
      "drive": "复仇",
      "conflict": "主角 vs 宗门",
      "theme": "逆境成长",
      "differentiation": "区别于同类的独特点"
    }}
  }},
  "settings": [
    {{"title": "作品立意", "content": "作品定位、主题命题、核心矛盾、情感基调、禁忌边界", "tags": ["立意", "主题"]}},
    {{"title": "主要势力", "content": "详细描述", "tags": ["宗门"]}},
    {{"title": "世界规则", "content": "详细描述", "tags": ["法则"]}},
    {{"title": "特殊道具/资源", "content": "详细描述", "tags": ["道具"]}}
  ],
  "power_systems": [
    {{
      "name": "体系名称", "system_type": "cultivation",
      "description": "体系简介（50字）",
      "cultivation_method": "修炼方式",
      "breakthrough_condition": "突破通用条件",
      "special_rules": "特殊规则",
      "protagonist_start_rank": 1, "protagonist_end_rank": 9,
      "levels": [
        {{"rank": 1, "name": "境界名", "description": "简述", "abilities": ["能力"]}},
        {{"rank": 2, "name": "境界名", "description": "简述", "abilities": ["能力"]}}
      ]
    }}
  ],
  "storylines": [
    {{"name": "主线：线名", "line_type": "main", "description": "简述", "core_conflict": "核心矛盾", "resolution_direction": "收束方向", "status": "active", "start_chapter": 1}},
    {{"name": "支线：线名", "line_type": "sub", "description": "简述", "core_conflict": "核心矛盾", "resolution_direction": "收束方向", "status": "planned", "start_chapter": 10}}
  ],
  "characters": [
    {{
      "name": "主角名", "role": "protagonist", "gender": "男", "age": "17",
      "faction": "青云宗", "personality": "性格描述", "background": "背景",
      "motivation": "动机", "arc": "成长弧线",
      "strengths": ["特质1"], "weaknesses": ["弱点1"], "special_traits": ["特殊能力"]
    }},
    {{"name": "配角1", "role": "supporting", ...}},
    {{"name": "反派1", "role": "antagonist", ...}}
  ],
  "outline": [
    {{
      "title": "第一卷：卷标题（有画面感，带悬念）", "sort_order": 0,
      "summary": "本卷核心剧情概述，60字内",
      "hook": "本卷核心悬念：读者最想知道的问题",
      "conflict": "本卷主要矛盾冲突",
      "planned_chapters": 60
    }}
  ],
  "memory": [
    {{"memory_type": "setting", "title": "修炼体系锚点", "content": "...", "tags": ["设定"]}},
    ...共8条
  ],
  "relations": [
    {{"from_name": "主角名", "to_name": "配角名", "relation_type": "师徒", "description": "...", "intensity": 8}}
  ]
}}"""

        try:
            raw = await self.ai._call_ai(system, prompt)
            data = _parse_json(raw)
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

        raw = await self._call_with_retry(system, prompt)
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
    #  Step 2 — 世界观设定卡
    # ══════════════════════════════════════════════════════════

    async def _gen_settings(self, project: Project, ctx: dict):
        system = "你是网络小说世界观设计专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:1000] or '（未填写）'}
世界观：{ctx['world_overview'][:300]}

生成8张设定卡，返回JSON数组（第一张必须是"作品立意"）：
[
  {{"title": "作品立意", "content": "提炼作品定位、主题命题、核心矛盾、情感基调与禁忌边界", "tags": ["立意", "主题"]}},
  {{"title": "修炼体系", "content": "详细说明境界、突破条件、上限", "tags": ["境界", "修炼"]}},
  {{"title": "主要势力", "content": "3个主要势力的名称、特色、立场", "tags": ["势力", "宗门"]}},
  {{"title": "世界规则", "content": "2~3条最重要的世界底层规则", "tags": ["规则", "法则"]}},
  {{"title": "特殊资源", "content": "本世界独特的修炼资源或道具", "tags": ["资源", "道具"]}},
  {{"title": "丹药/功法体系", "content": "关键丹药线与功法成长路径", "tags": ["丹药", "功法"]}},
  {{"title": "地图与区域风险", "content": "关键地点、资源点、禁地与风险层级", "tags": ["地图", "风险"]}},
  {{"title": "历史谜团与禁忌", "content": "驱动长线追读的历史真相与禁忌边界", "tags": ["谜团", "禁忌"]}}
]
要求：
1) 第一张卡标题固定为"作品立意"
2) 若用户未提供立意，由你根据创意自动提炼
3) "作品立意"聚焦作品基本面，不写世界规则细节
4) 其余卡片聚焦可执行设定，避免空话
5) 每张卡 content 至少120字，且要有可落地细节（名词、规则、代价、限制）
只返回JSON，不要解释。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("settings", [])

        results = []
        for item in data:
            s = WorldSetting(
                project_id=project.id,
                title=item.get("title", "设定"),
                content=item.get("content", ""),
                tags=item.get("tags", []),
            )
            self.db.add(s)
            results.append(s)

        self.db.commit()
        # 包含内容摘要（截取前80字），让后续步骤能真正用到设定细节
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

        for s in data.get("settings", []):
            self.db.add(WorldSetting(
                project_id=project.id,
                title=s.get("title", "设定"),
                content=s.get("content", ""),
                tags=s.get("tags", []),
            ))

        for ps in data.get("power_systems", []):
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
                sort_order=ps.get("sort_order", 0),
            ))

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

    # ══════════════════════════════════════════════════════════
    #  带重试的 AI 调用
    # ══════════════════════════════════════════════════════════

    async def _call_with_retry(self, system: str, prompt: str, max_retries: int = 2) -> str:
        """调用 AI，失败时最多重试 max_retries 次"""
        last_err = None
        for attempt in range(max_retries):
            try:
                return await self.ai._call_ai(system, prompt)
            except Exception as e:
                last_err = e
                continue
        raise last_err
