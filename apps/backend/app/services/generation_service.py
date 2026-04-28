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
from typing import AsyncGenerator, Literal
from sqlalchemy.orm import Session

from app.services.ai_service import AIService
from app.models import (
    Project, WorldSetting, Character, CharacterRelationship,
    OutlineNode, MemoryChunk
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


def _normalize_outline(data: list) -> list:
    """
    容错归并，统一强制 卷 → 篇 → 章 三层结构：
    1. 卷下无篇但有章 → 自动补插一个篇节点，把章节包进去
    2. 卷下多篇 → 合并所有章节到第一篇下
    3. 修正每级子节点的 sort_order，保证从 0 连续递增
    """
    for vol in data:
        if vol.get("node_type") != "volume":
            continue
        children = vol.get("children", [])
        arcs = [c for c in children if c.get("node_type") == "arc"]
        loose_chapters = [c for c in children if c.get("node_type") == "chapter_plan"]

        if not arcs and loose_chapters:
            # 无篇但有章 → 补插一个篇，把散落章节包进去
            vol_title = vol.get("title", "")
            arc_title = vol_title.split("：", 1)[1] if "：" in vol_title else vol_title
            for i, ch in enumerate(loose_chapters):
                ch["sort_order"] = i
            synthetic_arc = {
                "node_type": "arc",
                "title": f"第一篇：{arc_title}",
                "sort_order": 0,
                "children": loose_chapters,
            }
            # 保留非章节的其他子节点（如有），再加合成篇
            other_children = [c for c in children if c.get("node_type") not in ("arc", "chapter_plan")]
            vol["children"] = [synthetic_arc] + other_children

        elif len(arcs) > 1:
            # 多篇 → 合并所有章节到第一篇下
            merged_chapters: list = []
            for arc in arcs:
                merged_chapters.extend(arc.get("children", []))
            for i, ch in enumerate(merged_chapters):
                ch["sort_order"] = i
            first_arc = dict(arcs[0])
            first_arc["children"] = merged_chapters
            non_arcs = [c for c in children if c.get("node_type") != "arc"]
            vol["children"] = [first_arc] + non_arcs

        else:
            # 单篇：只修正篇下章节的 sort_order
            for arc in arcs:
                for i, ch in enumerate(arc.get("children", [])):
                    ch["sort_order"] = i

        # 修正当前层子节点 sort_order
        for i, child in enumerate(vol.get("children", [])):
            child["sort_order"] = i

    return data


# ─────────────────────────────────────────────────────────────
#  主服务类
# ─────────────────────────────────────────────────────────────

class GenerationService:
    def __init__(self, db: Session):
        self.db = db
        self.ai = AIService(db=db)
        self.ai_gemini = AIService(profile="gemini", db=db)

    # ══════════════════════════════════════════════════════════
    #  入口：根据 mode 分发
    # ══════════════════════════════════════════════════════════

    async def bootstrap(
        self,
        logline: str,
        mode: Literal["sequential", "single_shot"] = "sequential",
    ) -> AsyncGenerator[str, None]:
        if mode == "single_shot":
            async for chunk in self._single_shot(logline):
                yield chunk
        else:
            async for chunk in self._sequential(logline):
                yield chunk

    # ══════════════════════════════════════════════════════════
    #  方案 A：串行步进
    # ══════════════════════════════════════════════════════════

    async def _sequential(self, logline: str) -> AsyncGenerator[str, None]:
        ctx = {"logline": logline}   # 上下文在步骤间传递

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

            # Step 3 — 人物
            yield _sse("step_start", step="characters", label="生成人物库...")
            chars = await self._gen_characters(project, ctx)
            yield _sse("step_done", step="characters", count=len(chars),
                       preview="、".join(c.name for c in chars[:3]))

            # Step 4 — 大纲
            yield _sse("step_start", step="outline", label="生成大纲树（3卷+前10章）...")
            nodes = await self._gen_outline(project, ctx)
            yield _sse("step_done", step="outline", count=len(nodes))

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

    async def _single_shot(self, logline: str) -> AsyncGenerator[str, None]:
        yield _sse("step_start", step="all", label="AI 全量生成中（单次调用）...")

        system = """你是专业的网络小说策划，根据一句话创意生成完整的小说初始化数据。
严格返回 JSON，不要任何额外文字。"""

        prompt = f"""根据以下创意，生成完整的小说初始化数据：

创意：{logline}

返回以下 JSON 结构（严格遵守字段名）：
{{
  "project": {{
    "title": "小说名称",
    "genre": "玄幻",
    "logline": "{logline}",
    "world_overview": "世界观简述（200字）",
    "story_core": {{
      "drive": "复仇",
      "conflict": "主角 vs 宗门",
      "theme": "逆境成长",
      "differentiation": "区别于同类的独特点"
    }}
  }},
  "settings": [
    {{"title": "修炼体系", "content": "详细描述", "tags": ["境界", "突破"]}},
    {{"title": "主要势力", "content": "详细描述", "tags": ["宗门"]}},
    {{"title": "世界规则", "content": "详细描述", "tags": ["法则"]}},
    {{"title": "特殊道具/资源", "content": "详细描述", "tags": ["道具"]}}
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
      "node_type": "volume", "title": "第一卷：标题", "sort_order": 0,
      "summary": "本卷概述",
      "children": [
        {{
          "node_type": "arc", "title": "第一篇：标题", "sort_order": 0,
          "children": [
            {{"node_type": "chapter_plan", "title": "第1章：标题", "sort_order": 0,
              "hook": "钩子", "highlight": "燃点", "conflict": "冲突", "summary": "章节摘要"}},
            ...共10个chapter_plan
          ]
        }}
      ]
    }},
    {{"node_type": "volume", "title": "第二卷：标题", "sort_order": 1, "summary": "...", "children": []}},
    {{"node_type": "volume", "title": "第三卷：标题", "sort_order": 2, "summary": "...", "children": []}}
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
            raw = await self.ai_gemini._call_ai(system, prompt)
            data = _parse_json(raw)
            yield _sse("step_done", step="all", count=1)

            yield _sse("step_start", step="saving", label="写入数据库...")
            project = await self._save_all(data, logline)
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

返回JSON：
{{
  "title": "小说名（2~6个汉字，有冲击力）",
  "genre": "玄幻",
  "world_overview": "世界观简述，200字以内",
  "story_core": {{
    "drive": "故事驱动力（成长/复仇/守护等）",
    "conflict": "核心矛盾",
    "theme": "主题",
    "differentiation": "与同类小说的差异化"
  }}
}}"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)

        project = Project(
            title=data["title"],
            genre=data.get("genre", "玄幻"),
            logline=ctx["logline"],
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

        return project, ctx

    # ══════════════════════════════════════════════════════════
    #  Step 2 — 世界观设定卡
    # ══════════════════════════════════════════════════════════

    async def _gen_settings(self, project: Project, ctx: dict):
        system = "你是网络小说世界观设计专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
世界观：{ctx['world_overview'][:300]}

生成4张世界观设定卡，返回JSON数组：
[
  {{"title": "修炼体系", "content": "详细说明境界、突破条件、上限", "tags": ["境界", "修炼"]}},
  {{"title": "主要势力", "content": "3个主要势力的名称、特色、立场", "tags": ["势力", "宗门"]}},
  {{"title": "世界规则", "content": "2~3条最重要的世界底层规则", "tags": ["规则", "法则"]}},
  {{"title": "特殊资源", "content": "本世界独特的修炼资源或道具", "tags": ["资源", "道具"]}}
]"""

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
        ctx["settings_summary"] = " | ".join(s.title for s in results)
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 3 — 人物库
    # ══════════════════════════════════════════════════════════

    async def _gen_characters(self, project: Project, ctx: dict):
        system = "你是网络小说人物设计专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》({ctx['genre']})
创意：{ctx['logline']}
故事核：冲突={ctx['story_core'].get('conflict','')}，主题={ctx['story_core'].get('theme','')}

生成5个人物（1主角+2配角+1反派+1导师/长辈），返回JSON数组：
[
  {{
    "name": "姓名", "role": "protagonist",
    "gender": "男", "age": "17", "faction": "所属势力",
    "personality": "性格（2句话）",
    "background": "背景经历（3句话）",
    "motivation": "核心动机",
    "arc": "人物弧线（从X到Y的成长）",
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
                strengths=item.get("strengths", []),
                weaknesses=item.get("weaknesses", []),
                special_traits=item.get("special_traits", []),
            )
            self.db.add(c)
            results.append(c)

        self.db.commit()
        ctx["char_names"] = [c.name for c in results]
        ctx["protagonist"] = next((c.name for c in results if c.role == "protagonist"), "主角")
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 4 — 大纲树
    # ══════════════════════════════════════════════════════════

    async def _gen_outline(self, project: Project, ctx: dict):
        system = "你是网络小说结构策划专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》主角：{ctx['protagonist']}
创意：{ctx['logline']}
设定：{ctx['settings_summary']}

生成大纲树，返回JSON数组。结构严格为：卷→篇→章（三层）。
第一卷下有且仅有一篇，篇下展开前10个章节计划；其余两卷只写卷标题和概述（children为空）。

[
  {{
    "node_type": "volume", "title": "第一卷：起点（示例）", "sort_order": 0,
    "summary": "本卷核心事件概述",
    "children": [
      {{
        "node_type": "arc", "title": "第一篇：篇名（示例）", "sort_order": 0,
        "summary": "本篇概述",
        "children": [
          {{
            "node_type": "chapter_plan", "title": "第1章：章节标题", "sort_order": 0,
            "summary": "本章发生什么",
            "hook": "开头的悬念/钩子",
            "highlight": "本章最高燃点",
            "conflict": "核心冲突"
          }},
          {{
            "node_type": "chapter_plan", "title": "第2章：章节标题", "sort_order": 1,
            "summary": "...", "hook": "...", "highlight": "...", "conflict": "..."
          }}
        ]
      }}
    ]
  }},
  {{"node_type": "volume", "title": "第二卷：标题", "sort_order": 1, "summary": "...", "children": []}},
  {{"node_type": "volume", "title": "第三卷：标题", "sort_order": 2, "summary": "...", "children": []}}
]
注意：只返回JSON数组，不要任何说明文字。"""

        raw = await self._call_with_retry(system, prompt)
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("outline", [])

        # 归并 AI 可能生成的重复篇节点，并修正 sort_order
        data = _normalize_outline(data)

        results = []

        def save_node(item, parent_id=None):
            node = OutlineNode(
                project_id=project.id,
                parent_id=parent_id,
                node_type=item.get("node_type", "arc"),
                title=item.get("title", "未命名"),
                summary=item.get("summary"),
                hook=item.get("hook"),
                highlight=item.get("highlight"),
                conflict=item.get("conflict"),
                sort_order=item.get("sort_order", 0),
            )
            self.db.add(node)
            self.db.flush()  # 获取 id，供子节点用
            results.append(node)
            for child in item.get("children", []):
                save_node(child, parent_id=node.id)

        for vol in data:
            save_node(vol)

        self.db.commit()
        return results

    # ══════════════════════════════════════════════════════════
    #  Step 5 — 记忆库种子
    # ══════════════════════════════════════════════════════════

    async def _gen_memory(self, project: Project, ctx: dict):
        system = "你是小说设定记忆管理专家。只返回JSON数组。"
        prompt = f"""小说：《{ctx['project_title']}》主角：{ctx['protagonist']}
设定：{ctx['settings_summary']}

生成8条初始记忆库种子（作为后续写作的设定锚点，防止前后矛盾），返回JSON数组：
[
  {{
    "memory_type": "setting",
    "title": "修炼体系最低境界",
    "content": "具体内容，清晰可查阅",
    "tags": ["修炼体系", "锚点"]
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

    async def _save_all(self, data: dict, logline: str) -> Project:
        """把方案B生成的完整 JSON 一次性存库"""
        p = data["project"]
        project = Project(
            title=p["title"],
            genre=p.get("genre", "玄幻"),
            logline=logline,
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
                strengths=c.get("strengths", []),
                weaknesses=c.get("weaknesses", []),
                special_traits=c.get("special_traits", []),
            )
            self.db.add(char)
            self.db.flush()
            char_map[char.name] = char

        def save_node(item, parent_id=None):
            node = OutlineNode(
                project_id=project.id,
                parent_id=parent_id,
                node_type=item.get("node_type", "arc"),
                title=item.get("title", ""),
                summary=item.get("summary"),
                hook=item.get("hook"),
                highlight=item.get("highlight"),
                conflict=item.get("conflict"),
                sort_order=item.get("sort_order", 0),
            )
            self.db.add(node)
            self.db.flush()
            for child in item.get("children", []):
                save_node(child, parent_id=node.id)

        outline_data = _normalize_outline(data.get("outline", []))
        for vol in outline_data:
            save_node(vol)

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
