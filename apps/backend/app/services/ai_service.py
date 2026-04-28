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
    ) -> dict:
        memory_text = "\n".join(f"- {m}" for m in memories[:30]) if memories else "暂无记忆条目"
        settings_text = "\n".join(f"- {s}" for s in settings_summary[:10]) if settings_summary else "暂无设定"

        system = """你是专业的网络小说编辑，负责对章节内容进行质量检查。
请严格按照 JSON 格式返回结果，不要有任何额外文字。"""

        prompt = f"""请对以下章节进行质检，返回 JSON 格式。

章节标题：{chapter_title}
章节正文（前2000字）：
{chapter_content[:2000]}

已有记忆条目（供一致性参考）：
{memory_text}

世界观设定摘要：
{settings_text}

检查维度：{", ".join(check_types)}

返回格式：
{{
  "overall_score": 8.5,
  "dimensions": {{
    "plot": {{"score": 9, "status": "pass", "comment": "..."}},
    "character": {{"score": 8, "status": "pass", "comment": "..."}},
    "setting_consistency": {{"score": 7, "status": "warning", "comment": "..."}},
    "pacing": {{"score": 8, "status": "pass", "comment": "..."}},
    "hooks": {{"score": 9, "status": "excellent", "comment": "..."}}
  }},
  "issues": [{{"type": "warning", "description": "..."}}],
  "suggestions": ["...", "..."],
  "summary": "整体评价一句话"
}}"""

        response = await self._call_ai(system, prompt)
        try:
            # 提取 JSON
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return {
                "overall_score": 0,
                "raw_response": response,
                "error": "Failed to parse AI response"
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
        node_type: str,              # volume / arc
        node_summary: str,
        project_title: str,
        genre: str,
        world_summary: str,
        character_summary: str,
        existing_chapters: int = 0,  # 已有章节数，用于章节编号连续
        chapter_count: int = 10,     # 生成几章
    ) -> dict:
        """
        为选定的大纲节点（卷/篇）生成详细的子章节计划。
        返回「五要素」格式：开篇钩子/核心事件/人物变化/伏笔管理/章末钩子。
        """
        system = """你是拥有30年经验的网络小说策划，深刻理解网文追读机制。
你的大纲必须让每一章都有存在的理由，特别是「章末钩子」——
那是让读者无法放下手机的最后一句话的设计意图。
严格返回 JSON，不要任何额外文字。"""

        start_num = existing_chapters + 1
        prompt = f"""小说：《{project_title}》（{genre}）
当前节点：{node_type == 'volume' and '卷' or '篇'}《{node_title}》
节点概述：{node_summary or '（未填写）'}

世界观摘要：{world_summary[:400]}
主要人物：{character_summary[:300]}

请为本{node_type == 'volume' and '卷' or '篇'}生成 {chapter_count} 个章节计划，章节编号从第{start_num}章开始。

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
      "word_estimate": 3000
    }}
  ]
}}

重点要求：
1. 每章「章末钩子」必须具体，不能只写"留下悬念"，要说清楚「悬念的具体内容」
2. 前3章追读钩子要特别强
3. 伏笔要有连续性，本卷内至少有2条贯穿始终的伏笔线"""

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
        scale_hint: str = "auto",   # auto / short / medium / long
    ) -> dict:
        """
        全量大纲规划：AI 自主决定卷数和每卷章节数，无需用户指定。
        scale_hint 只是量级参考，AI 根据故事内容自行判断最合适的结构。
        返回: { "volumes": [{ title, summary, hook, conflict, planned_chapters: int }] }
        """
        scale_desc = {
            "auto":   "根据故事复杂度自由决定（通常 2-8 卷）",
            "short":  "轻量短篇风格，约 30-50 章（2-3 卷）",
            "medium": "标准中篇，约 60-120 章（3-5 卷）",
            "long":   "长篇连载，约 150 章以上（5-10 卷）",
        }.get(scale_hint, "根据故事自由决定")

        system = "你是资深网络小说策划，擅长根据故事特质规划最合适的卷章结构。严格返回JSON，不要任何额外文字。"
        prompt = f"""小说：《{project_title}》（{genre}）
一句话创意：{logline or '（未填写）'}
世界观：{world_summary[:300] or '（未填写）'}
主要人物：{character_summary[:200] or '（未填写）'}

篇幅倾向：{scale_desc}

请根据这个故事的特质，自主规划最适合的卷级结构。
每卷给出你认为最合适的章节数（planned_chapters），而不是固定值。

返回JSON：
{{
  "volumes": [
    {{
      "title": "卷标题（简洁有力，带悬念感，不要用"第X卷"）",
      "summary": "本卷核心情节摘要，60字内",
      "hook": "本卷核心悬念：读者最想知道答案的问题",
      "conflict": "本卷主要矛盾冲突",
      "planned_chapters": 15
    }}
  ]
}}

规划原则：
1. 章节数要符合本卷的情节密度——信息量大、转折多的卷章节数可以多一些
2. 整体弧线完整，起承转合清晰，收尾不要仓促
3. 悬念递进，每卷末尾都要有足够的钩子让读者追下一卷
4. 标题要有画面感，能让读者一眼感受到本卷的核心氛围"""

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
    ) -> AsyncGenerator[str, None]:
        """
        根据大纲计划 + 完整故事上下文，流式生成本章起笔或续写建议。
        像一位有30年经验的作家，把世界观、人物弧、伏笔自然织入文字。
        """
        has_content = bool(
            not replace_existing and existing_content and len(existing_content.strip()) > 50
        )

        system = """你是拥有30年经验的网络小说作家，文笔老练，深谙追读节奏。
你的任务是根据章节计划和故事背景，为作者提供一段高质量的正文文字。

写作原则：
1. 严格遵循「开篇钩子」意图，第一句话就要抓人
2. 世界观和人物设定要自然融入场景，不要生硬介绍背景
3. 人物的行动和心理要符合其弧线和动机
4. 注意上一章结尾的衔接，保持情感和节奏的连续性
5. 伏笔要埋得不着痕迹
6. 直接给出正文，不要解释、不要旁白、不要说"好的"之类的废话"""

        if replace_existing:
            task_line = (
                "【整章重写】请根据本章大纲与故事背景，写出全新正文约 800 字，"
                "不要复述或抄袭旧稿套话；若旧稿与大纲冲突，以大纲为准。"
            )
        elif has_content:
            task_line = f"当前已写内容（最后500字供衔接参考）：\n{existing_content[-500:]}\n\n请根据章节计划，续写接下来约600字的正文："
        else:
            task_line = "请根据章节计划，写出本章开篇约600字，第一句话必须立刻抓住读者："

        # 控制 prompt 总长度（8b 模型 context 约 8k）
        world_part = world_summary[:250] if world_summary else "（未设定）"
        char_part = character_summary[:200] if character_summary else "（未设定）"
        mem_part = f"\n近期关键事件：{memory_summary[:200]}" if memory_summary else ""
        prev_part = prev_chapter_tail[-300:] if prev_chapter_tail else "（这是第一章，无前情）"

        extra = ""
        if user_prompt and user_prompt.strip():
            extra = f"\n\n【作者补充要求】\n{user_prompt.strip()[:1200]}"

        prompt = f"""【故事背景】
世界观：{world_part}
主要人物：{char_part}{mem_part}

【上章结尾】
{prev_part}

【本章大纲计划】
标题：{chapter_title}
开篇钩子：{outline_hook or "（未填写）"}
核心事件（删掉会损失什么）：{outline_summary or "（未填写）"}
人物变化：{outline_conflict or "（未填写）"}
章末方向：{outline_highlight or "（未填写）"}
{f"伏笔管理：{outline_foreshadow}" if outline_foreshadow else ""}

{task_line}{extra}"""

        async for chunk in self._stream_ai(system, prompt):
            yield chunk

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
