"""
AI Service — 统一使用 OpenAI 兼容协议
支持本地 Ollama (qwen3:8b) 及任意自定义 base_url + api_key 的端点
"""
import json
from typing import List, AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection


class AIService:
    def __init__(
        self,
        profile: str = "default",
        db: Optional[Session] = None,
        llm_provider_id: Optional[UUID] = None,
    ):
        self.profile = profile
        self._db = db
        self.model = settings.AI_MODEL
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

    def _get_client(self):
        """
        始终使用 AsyncOpenAI，通过 base_url + api_key 指向任意 OpenAI 兼容服务：
          - 本地 Ollama:   base_url=http://localhost:11434/v1  api_key=ollama
          - 远程代理/云服务: 在 .env 中填写真实 LLM_BASE_URL / LLM_API_KEY
        """
        if self._gemini_unconfigured:
            raise RuntimeError(
                "未配置远程大模型：请在管理后台「大模型」中新增并启用/设为默认，"
                "或设置环境变量 GEMINI_BASE_URL 与 GEMINI_MODEL"
            )
        if self._client:
            return self._client
        import openai
        self._client = openai.AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )
        return self._client

    # ── 质检 ──────────────────────────────────────────
    async def quality_check(
        self,
        chapter_content: str,
        chapter_title: str,
        memories: List[str],
        settings_summary: List[str],
        check_types: List[str],
        # 新增：人物当前状态、故事线、大纲节点上下文
        character_states: List[str] = None,
        storylines_context: List[str] = None,
        power_systems_summary: List[str] = None,
        outline_context: str = "",
    ) -> dict:
        memory_text = "\n".join(f"- {m}" for m in memories[:20]) if memories else "暂无记忆条目"
        settings_text = "\n".join(f"- {s}" for s in settings_summary[:8]) if settings_summary else "暂无设定"

        # 人物当前状态（用于一致性检查的核心）
        char_state_text = ""
        if character_states:
            char_state_text = "\n人物当前状态（一致性检查关键依据）：\n"
            char_state_text += "\n".join(f"- {c}" for c in character_states[:10])

        # 故事线进展
        storyline_text = ""
        if storylines_context:
            storyline_text = "\n当前活跃故事线：\n"
            storyline_text += "\n".join(f"- {s}" for s in storylines_context[:5])

        # 本章大纲计划
        outline_text = f"\n本章大纲计划：{outline_context}" if outline_context else ""

        system = """你是专业的网络小说编辑，负责对章节内容进行质量检查。
请严格按照 JSON 格式返回结果，不要有任何额外文字。

特别关注以下一致性问题：
1. 人物使用了超出其当前境界的技能/能力
2. 人物出现在与记录不符的位置
3. 已死亡/封印的人物突然出现
4. 人物行为违背其价值观和动机
5. 使用了尚未习得的技能或尚未获得的道具"""

        prompt = f"""请对以下章节进行质检，返回 JSON 格式。

章节标题：{chapter_title}
章节正文（前2000字）：
{chapter_content[:2000]}
{char_state_text}
{storyline_text}
{outline_text}

近期记忆条目（供参考）：
{memory_text}

世界观设定：
{settings_text}

检查维度：{", ".join(check_types)}

返回格式（字段名固定）：
{{
  "overall_score": 8.5,
  "dimensions": {{
    "plot": {{"score": 9, "status": "pass", "comment": "情节推进是否有效"}},
    "character": {{"score": 8, "status": "pass", "comment": "人物行为是否符合设定"}},
    "consistency": {{"score": 7, "status": "warning", "comment": "境界/技能/位置是否前后一致"}},
    "pacing": {{"score": 8, "status": "pass", "comment": "节奏是否合适"}},
    "hooks": {{"score": 9, "status": "excellent", "comment": "钩子和悬念是否到位"}}
  }},
  "issues": [{{"type": "warning", "description": "具体问题描述，如：林默在第X章记录位置为青云城，本章却出现在远水城"}}],
  "suggestions": ["具体可操作的修改建议"],
  "summary": "整体评价一句话"
}}"""

        response = await self._call_ai(system, prompt)
        try:
            import re
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            return json.loads(text)
        except Exception:
            return {
                "overall_score": 0,
                "raw_response": response,
                "error": "Failed to parse AI response"
            }

    # ── 多章节连贯性检测 ────────────────────────────────
    async def chapter_coherence_check(
        self,
        project_title: str,
        chapters: List[dict],
    ) -> dict:
        """
        对多章进行连贯性检查：
        1) 标题与内容是否匹配
        2) 章节间剧情推进是否连贯
        """
        chapter_blocks = []
        for idx, chapter in enumerate(chapters, start=1):
            title = chapter.get("title", "未命名章节")
            content = (chapter.get("content") or "").strip()
            content_preview = content[:1800] if content else "（正文为空）"
            chapter_blocks.append(
                f"[样本{idx}] 章节ID={chapter.get('id')} | 顺序={chapter.get('sort_order', idx - 1)}\n"
                f"标题：{title}\n"
                f"正文（截断）：\n{content_preview}"
            )
        chapters_text = "\n\n".join(chapter_blocks)

        system = """你是资深网文编辑，擅长检查章节标题与剧情的一致性，以及多章连续阅读时的剧情连贯性。
必须严格返回 JSON，不要输出任何解释性文字。"""

        prompt = f"""小说：{project_title}

下面是按章节顺序选出的正文样本，请做连贯性检测：
{chapters_text}

请重点检查：
1. 每章“标题-正文”是否匹配（是否标题党、偏题、内容兑现不足）
2. 章节之间剧情推进是否自然（动机、冲突、信息承接、时间线）
3. 是否存在明显断层（人物状态突变、因果缺失、场景跳跃）

返回 JSON（字段名固定）：
{{
  "title_match_score": 8.2,
  "continuity_score": 7.6,
  "overall_score": 7.9,
  "chapter_evaluations": [
    {{
      "chapter_id": "uuid",
      "chapter_title": "第12章 ...",
      "title_match_score": 8,
      "title_match_comment": "标题与正文主事件基本一致",
      "risk_level": "low"
    }}
  ],
  "cross_chapter_issues": [
    {{
      "type": "continuity_gap",
      "severity": "warning",
      "description": "第12章结尾主角重伤，第13章开头直接满状态出战，缺少恢复或解释"
    }}
  ],
  "suggestions": [
    "按章节顺序给出可执行修改建议"
  ],
  "summary": "一句话总评"
}}"""

        response = await self._call_ai(system, prompt, max_tokens=2200)
        try:
            import re

            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            return json.loads(text)
        except Exception:
            return {
                "title_match_score": 0,
                "continuity_score": 0,
                "overall_score": 0,
                "chapter_evaluations": [],
                "cross_chapter_issues": [],
                "suggestions": [],
                "summary": "",
                "error": "Failed to parse AI response",
                "raw_response": response,
            }

    # ── 流式建议 ──────────────────────────────────────
    async def suggest_stream(
        self,
        chapter_content: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        system = "你是经验丰富的网络小说写作顾问，帮助作者优化章节内容。"
        prompt = f"""当前章节内容（前1500字）：
{chapter_content[:1500]}

作者问题：{user_prompt}

请给出具体的修改建议和示例。"""

        async for chunk in self._stream_ai(system, prompt):
            yield chunk

    # ── 记忆提取 ──────────────────────────────────────
    async def extract_memory(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
    ) -> List[dict]:
        system = """你是小说记忆提取助手。从章节中提取关键记忆条目，严格返回 JSON 数组。"""
        prompt = f"""从以下章节提取关键记忆条目（最多8条），返回 JSON 数组：

章节{chapter_number}《{chapter_title}》正文：
{chapter_content[:3000]}

返回格式：
[
  {{
    "memory_type": "event",
    "title": "林默获得古传承",
    "content": "林默在鬼门关意外触发古老传承，获得...",
    "tags": ["林默", "传承", "关键事件"]
  }},
  ...
]

memory_type 只能是: event / character_state / foreshadow / setting / conflict"""

        response = await self._call_ai(system, prompt)
        try:
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return []

    # ── 大纲展开（五要素卡片）─────────────────────────
    async def expand_outline(
        self,
        node_title: str,
        node_type: str,              # volume / legacy arc
        node_summary: str,
        project_title: str,
        genre: str,
        world_summary: str,
        character_summary: str,
        theme_statement: str = "",
        existing_chapters: int = 0,  # 已有章节数，用于章节编号连续
        chapter_count: int = 10,     # 生成几章
    ) -> dict:
        """
        为选定的大纲节点（卷或旧篇）生成详细的子章节计划。
        返回「五要素」格式：开篇钩子/核心事件/人物变化/伏笔管理/章末钩子。
        """
        system = """你是拥有30年经验的网络小说策划，深刻理解网文追读机制。
你的大纲必须让每一章都有存在的理由，特别是「章末钩子」——
那是让读者无法放下手机的最后一句话的设计意图。
严格返回 JSON，不要任何额外文字。"""

        start_num = existing_chapters + 1
        prompt = f"""小说：《{project_title}》（{genre}）
当前节点：{node_type == 'volume' and '卷' or '旧篇'}《{node_title}》
节点概述：{node_summary or '（未填写）'}

世界观摘要：{world_summary[:400]}
主要人物：{character_summary[:300]}
全书立意：{theme_statement[:300] or '（未填写；请从创意和人物中提炼一条贯穿全书的价值命题）'}

请为本{node_type == 'volume' and '卷' or '旧篇'}生成 {chapter_count} 个章节计划，章节编号从第{start_num}章开始。

每章使用「作家五要素」格式，返回 JSON：
{{
  "volume_analysis": {{
    "emotional_arc": "情绪弧线，如：压迫→绝境→逆转→升华",
    "core_question": "本卷核心悬念（读者最想知道的答案）",
    "pacing_rhythm": "节奏说明，如：前3章快节奏建立冲突，中间4章展开，末3章爆发"
  }},
  "chapters": [
    {{
      "number": {start_num},
      "title": "章节标题（有冲击力，可带悬念）",
      "opening_hook": "开篇钩子：前500字的核心手段。例：用主角被宣判死刑的场面倒叙开篇",
      "core_event": "核心事件：这章存在的理由，删掉会损失什么",
      "character_change": "人物变化：谁的认知/处境/关系发生了不可逆变化",
      "foreshadow": "伏笔管理：本章新埋的伏笔 / 回收的旧伏笔（格式：埋[xxx] 收[xxx]）",
      "end_hook": "章末钩子：读者读完最后一句停不下来的原因，要具体到手法",
      "pacing": "fast/medium/slow",
      "word_estimate": 2300
    }}
  ]
}}

重点要求：
1. 每章「章末钩子」必须具体，不能只写"留下悬念"，要说清楚「悬念的具体内容」
2. 每章字数预估控制在 2200-2400 字，默认 2300 字
3. 每章核心事件必须同时服务于情节推进、人物变化和全书立意，不要只堆事件
4. 前3章追读钩子要特别强
5. 伏笔要有连续性，本卷内至少有2条贯穿始终的伏笔线"""

        # gemini 有大 context，可以给更多 token；小模型控制在 4096 防止 OOM
        max_tok = 8192 if self.profile == "gemini" else 4096
        response = await self._call_ai(system, prompt, max_tokens=max_tok)
        try:
            import re
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = min(
                (text.find("{") if text.find("{") != -1 else len(text)),
                (text.find("[") if text.find("[") != -1 else len(text)),
            )
            return json.loads(text[start:])
        except Exception as e:
            return {"error": str(e), "raw": response[:500]}

    # ── 全量大纲：第一步生成卷级结构 ──────────────────
    async def plan_full_structure(
        self,
        project_title: str,
        genre: str,
        logline: str,
        world_summary: str,
        character_summary: str,
        theme_statement: str = "",
        scale_hint: str = "auto",   # auto / short / medium / long
    ) -> dict:
        """
        全量大纲规划：AI 规划卷结构，后端会按每卷约 60 章校准章节数。
        返回: { "volumes": [{ title, summary, hook, conflict, planned_chapters: int }] }
        """
        scale_desc = {
            "auto":   "默认约 540 章、约 124 万字，拆成 9 个 60 章左右的卷",
            "short":  "短篇长篇化，约 360 章、约 80 万字，拆成 6 个 60 章左右的卷",
            "medium": "标准长篇，约 540 章、约 124 万字，拆成 9 个 60 章左右的卷",
            "long":   "超长篇，约 660 章、约 152 万字，拆成 11 个 60 章左右的卷",
        }.get(scale_hint, "根据故事自由决定")

        system = "你是资深网络小说策划，擅长根据故事特质规划最合适的卷章结构。严格返回JSON，不要任何额外文字。"
        prompt = f"""小说：《{project_title}》（{genre}）
一句话创意：{logline or '（未填写）'}
全书立意：{theme_statement[:500] or '（未填写；请从创意和人物中提炼一条贯穿全书的价值命题）'}
世界观：{world_summary[:300] or '（未填写）'}
主要人物：{character_summary[:200] or '（未填写）'}

篇幅倾向：{scale_desc}

请根据这个故事的特质规划卷级结构。
章节数必须服务于「每卷约 60 章、每章 2200-2400 字」的长篇目录结构：planned_chapters 优先使用 60，必要时允许 30，不要使用篇/arc结构。
每卷必须围绕全书立意形成一个阶段性证明：人物选择如何变化，价值冲突如何升级，不能只做事件堆叠。

返回JSON：
{{
  "volumes": [
    {{
      "title": "卷标题（简洁有力，带悬念感，不要用"第X卷"）",
      "summary": "本卷核心情节摘要，60字内",
      "theme_stage": "本卷如何推进/反证/深化全书立意",
      "character_arc": "本卷关键人物的欲望、选择和代价",
      "hook": "本卷核心悬念：读者最想知道答案的问题",
      "conflict": "本卷主要矛盾冲突",
      "planned_chapters": 60
    }}
  ]
}}

规划原则：
1. 不再使用“篇”的概念；直接规划“卷 → 章”
2. 每卷优先 60 章，少数过渡卷可以 30 章；不要随意给 10、15、20、40 这类杂乱数量
3. 每章按 2200-2400 字设计，优先按 2300 字估算
4. 整体弧线完整，起承转合清晰，收尾不要仓促
5. 人物弧线、剧情主线、世界观秘密都要受全书立意统领
6. 悬念递进，每卷末尾都要有足够的钩子让读者追下一卷
7. 标题要有画面感，能让读者一眼感受到本卷的核心氛围"""

        response = await self._call_ai(system, prompt)
        import re
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start == -1:
                raise ValueError("No JSON object found")
            return json.loads(text[start:])
        except Exception as e:
            return {"error": str(e), "raw": response[:500]}

    # ── AI 辅助写作（流式）────────────────────────────
    async def draft_assist_stream(
        self,
        chapter_title: str,
        outline_hook: str,
        outline_summary: str,
        outline_conflict: str,
        outline_highlight: str,
        outline_foreshadow: str,
        prev_chapter_tail: str,
        world_summary: str,
        character_summary: str,
        memory_summary: str,
        existing_content: str,
        user_prompt: str = "",
        replace_existing: bool = False,
        # 新增：故事线、实力里程碑、情感基调
        storyline_summary: str = "",
        outline_power_milestone: str = "",
        outline_emotional_tone: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        根据大纲计划 + 完整故事上下文，流式生成本章起笔或续写建议。
        像一位有30年经验的作家，把世界观、人物弧、伏笔、故事线进展自然织入文字。
        """
        has_content = bool(
            not replace_existing and existing_content and len(existing_content.strip()) > 50
        )

        system = """你是拥有30年经验的网络小说作家，文笔老练，深谙追读节奏。
你的任务是根据章节计划和故事背景，为作者提供一段高质量的正文文字。

写作原则：
1. 严格遵循「开篇钩子」意图，第一句话就要抓人
2. 世界观、人物当前境界和状态要自然融入，不要与已知人物设定矛盾
3. 人物的行动和心理要符合其弧线和动机
4. 注意上一章结尾的衔接，保持情感和节奏的连续性
5. 如果本章有实力里程碑（如突破境界），要让这一刻有分量
6. 故事线进展要顺势推进，切勿无视当前活跃的冲突线
7. 直接给出正文，不要解释、不要旁白、不要说"好的"之类的废话"""

        if replace_existing:
            task_line = (
                "【整章重写】请根据本章大纲与故事背景，写出全新正文约 800 字，"
                "不要复述或抄袭旧稿套话；若旧稿与大纲冲突，以大纲为准。"
            )
        elif has_content:
            task_line = f"当前已写内容（最后500字供衔接参考）：\n{existing_content[-500:]}\n\n请根据章节计划，续写接下来约600字的正文："
        else:
            task_line = "请根据章节计划，写出本章开篇约600字，第一句话必须立刻抓住读者："

        # 控制 prompt 总长度（8b 模型 context 约 8k，每段严格限字）
        world_part = world_summary[:200] if world_summary else "（未设定）"
        char_part = character_summary[:300] if character_summary else "（未设定）"
        mem_part = f"\n近期关键事件：{memory_summary[:150]}" if memory_summary else ""
        prev_part = prev_chapter_tail[-300:] if prev_chapter_tail else "（这是第一章，无前情）"

        # 故事线与本章特殊目标
        storyline_part = f"\n当前活跃故事线：{storyline_summary[:200]}" if storyline_summary else ""
        milestone_part = f"\n本章实力里程碑：{outline_power_milestone}" if outline_power_milestone else ""
        tone_part = f"\n情感基调：{outline_emotional_tone}" if outline_emotional_tone else ""

        extra = ""
        if user_prompt and user_prompt.strip():
            extra = f"\n\n【作者补充要求】\n{user_prompt.strip()[:800]}"

        prompt = f"""【故事背景】
世界观：{world_part}
主要人物（含境界/位置/技能）：{char_part}{mem_part}{storyline_part}

【上章结尾】
{prev_part}

【本章大纲计划】
标题：{chapter_title}
开篇钩子：{outline_hook or "（未填写）"}
核心事件：{outline_summary or "（未填写）"}
人物变化：{outline_conflict or "（未填写）"}
章末方向：{outline_highlight or "（未填写）"}{milestone_part}{tone_part}
{f"伏笔管理：{outline_foreshadow}" if outline_foreshadow else ""}

{task_line}{extra}"""

        async for chunk in self._stream_ai(system, prompt):
            yield chunk

    # ── 自动复盘提取 ──────────────────────────────────
    async def auto_extract_debrief(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
        character_states: List[dict],    # [{"id":…,"name":…,"current_realm":…,"current_location":…,"current_status":…}]
        storylines: List[dict],          # [{"id":…,"name":…,"line_type":…,"status":…,"core_conflict":…}]
    ) -> dict:
        """
        AI 读取章节正文，对照人物当前状态和故事线，
        自动提取本章发生的状态变化和故事节拍。
        返回结构化建议供前端预填复盘表单。
        """
        # 精简人物列表（token 控制）
        char_lines = []
        for c in character_states[:10]:
            parts = [f"- {c['name']}（id:{c['id']}）"]
            if c.get("current_realm"):
                parts.append(f"境界:{c['current_realm']}")
            if c.get("current_location"):
                parts.append(f"位置:{c['current_location']}")
            if c.get("current_status"):
                parts.append(f"状态:{c['current_status']}")
            char_lines.append("".join(parts))
        chars_text = "\n".join(char_lines) or "（无人物数据）"

        sl_lines = [
            f"- {s['name']}（id:{s['id']}，{s['line_type']}，当前:{s['status']}）：{(s.get('core_conflict') or '')[:60]}"
            for s in storylines[:8]
        ]
        sl_text = "\n".join(sl_lines) or "（无故事线数据）"

        system = "你是网络小说助手，从章节内容中提取人物状态变化和故事线推进，只返回JSON，不要任何解释。"

        prompt = f"""章节{chapter_number}《{chapter_title}》正文（前2500字）：
{chapter_content[:2500]}

当前人物状态（对照基准）：
{chars_text}

当前故事线（对照基准）：
{sl_text}

请分析本章内容，提取：
1. 哪些人物的境界/位置/状态发生了变化
2. 哪些人物习得了新技能
3. 哪些故事线有了推进（节拍）

只提取文中明确发生的变化，不要推断或猜测。
如果某字段没有变化，不要包含它。

返回JSON（严格遵守字段名）：
{{
  "character_updates": [
    {{
      "character_id": "人物id",
      "character_name": "人物名称（供显示）",
      "current_realm": "新境界（如有变化）",
      "current_location": "新位置（如有变化）",
      "current_status": "新状态 alive/dead/missing/sealed（如有变化）",
      "add_skill_name": "习得的技能名（如有）",
      "add_skill_mastery": "掌握程度，如：初学/熟练/精通"
    }}
  ],
  "storyline_updates": [
    {{
      "storyline_id": "故事线id",
      "storyline_name": "故事线名称（供显示）",
      "status": "新状态 planned/active/climax/resolved/dropped（如有变化）",
      "beat": "本章该故事线发生了什么（一句话）"
    }}
  ],
  "summary": "本章整体复盘总结（一句话）"
}}"""

        response = await self._call_ai(system, prompt, max_tokens=1500)
        try:
            import re as _re
            text = response.strip()
            text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
            if "```" in text:
                fence = _re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            data = json.loads(text)
            # 清理空字段
            char_updates = []
            for cu in data.get("character_updates", []):
                cleaned = {k: v for k, v in cu.items() if v and k not in ("character_name",)}
                if len(cleaned) > 1:  # 除 character_id 外还有其他字段
                    cleaned["character_name"] = cu.get("character_name", "")
                    char_updates.append(cleaned)
            sl_updates = []
            for su in data.get("storyline_updates", []):
                cleaned = {k: v for k, v in su.items() if v and k not in ("storyline_name",)}
                if len(cleaned) > 1:
                    cleaned["storyline_name"] = su.get("storyline_name", "")
                    sl_updates.append(cleaned)
            return {
                "character_updates": char_updates,
                "storyline_updates": sl_updates,
                "summary": data.get("summary", ""),
            }
        except Exception as e:
            return {
                "character_updates": [],
                "storyline_updates": [],
                "summary": "",
                "error": f"解析失败: {e}",
                "raw": response[:300],
            }

    # ── 底层调用 ──────────────────────────────────────
    async def _call_ai(self, system: str, prompt: str, max_tokens: int = 2048) -> str:
        client = self._get_client()
        resp = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def _stream_ai(self, system: str, prompt: str) -> AsyncGenerator[str, None]:
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
