"""
scene_draft.py — 三层调度：逐场正文生成 Mixin（第二层）

公共接口：
  ``scene_draft_stream`` — 为单个 Scene 流式生成正文；
      调用方负责将完整文本写回 ``scene.content``、更新 ``status=written``。

设计约束：
  - 严格限制在本场 POV，禁止全知视角；
  - 结尾句必须埋入 ``hook_to_plant``；
  - 字数不超过 ``word_budget ± 10%``；
  - 通过 ``task="draft.chapter"`` 采样档位获得高温创作参数。
"""

from __future__ import annotations

from typing import AsyncGenerator, List, Optional


class SceneDraftMixin:
    """逐场正文生成能力；由 AIService 通过多重继承混入。"""

    async def scene_draft_stream(
        self,
        *,
        scene_order: int,
        scene_title: Optional[str],
        time: Optional[str],
        location_name: Optional[str],
        pov_character: str,
        characters_on_stage: List[str],
        goal: str,
        conflict: str,
        turn: str,
        hook_to_plant: str,
        word_budget: int,
        pacing: str,
        sensory_focus: str,
        prev_hook: str = "",
        chapter_title: str = "",
        chapter_summary: str = "",
        genre: str = "玄幻",
        positioning: Optional[dict] = None,
        memory_snippets: Optional[List[str]] = None,
        location_context: str = "",
        scene_constraint_block: str = "",
        power_systems_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        为单个 Scene 流式生成正文。

        Args:
            scene_order: 场次号（第几场，用于标注上下文）。
            scene_title: 场标题（可选，不写入正文）。
            time: 故事内时间描述（如"第3日·夜"）。
            location_name: 地点名称。
            pov_character: POV 角色名；全场固定此视角。
            characters_on_stage: 在场角色名列表（含 POV）。
            goal: 本场角色想达成的目标。
            conflict: 阻碍目标的冲突或对立。
            turn: 本场的关键转折事件。
            hook_to_plant: 场末必须埋入的钩子/悬念。
            word_budget: 预算字数；实际输出允许 ±10%。
            pacing: "fast"/"mid"/"slow"，决定句式密度。
            sensory_focus: 感官焦点（sight/sound/smell/touch/mixed）。
            prev_hook: 上一场结尾钩子；非空时本场必须顺接。
            chapter_title: 所属章节标题（提供上下文）。
            chapter_summary: 章节摘要（限 300 字）。
            genre: 类型标签，用于加载 genre_kit guardrail。
            positioning: 立项定位 dict（取 selling_point/taboo_lines）。
            memory_snippets: 相关记忆片段（最多 6 条）。
            location_context: 由 _build_single_location_block 生成的感官基准约束块；
                              非空时注入 prompt，强制 AI 遵守地点感官一致性。

        Yields:
            逐 token 文本块（与 ``_stream_ai`` 返回格式一致）。
        """
        from app.services.genre_kit import get_genre_guardrail
        from app.services.llm_token_budgets import max_tokens_scene_draft

        kit_block = get_genre_guardrail(genre) if genre else ""

        pos_block = ""
        if positioning:
            selling = (positioning.get("selling_point") or "").strip()
            taboo = (positioning.get("taboo_lines") or "").strip()
            if selling or taboo:
                pos_block = f"\n【卖点】{selling}\n【禁忌线】{taboo}\n"

        mem_block = ""
        if memory_snippets:
            mem_block = "\n【相关记忆（禁止照抄，仅供一致性参考）】\n" + "\n".join(
                f"- {m[:120]}" for m in memory_snippets[:6]
            )

        prev_block = (
            f"\n【上一场结尾钩子（本场开头必须顺接或回应）】：{prev_hook.strip()}"
            if prev_hook.strip() else ""
        )

        on_stage = "、".join(characters_on_stage) if characters_on_stage else pov_character

        pacing_guide = {
            "fast": "紧绷节奏：短句为主，每段≤60字，动作/对话交替",
            "slow": "舒缓节奏：允许长句与内心独白，细节丰富",
            "mid": "均衡节奏：动静结合，段落长短错落",
        }
        sensory_guide = {
            "sight": "以视觉画面为主导",
            "sound": "以声音细节为主导",
            "smell": "以气味/嗅觉为主导",
            "touch": "以触觉/体感为主导",
            "mixed": "多感官综合",
        }

        system = (
            "你是专业网络小说作家。严格按分场设定写正文，"
            "禁止自行发明新剧情、跳跃场景或改变 POV。"
            "只写本场正文，不写场标题、旁白说明、章节编号，直接从第一句开始。"
            f"{kit_block}"
        )

        loc_context_block = (
            f"\n{location_context}\n" if location_context else ""
        )

        constraint_block = (
            f"\n{scene_constraint_block}\n" if scene_constraint_block else ""
        )

        power_block = ""
        if power_systems_context and power_systems_context.strip():
            power_block = (
                "\n【力量体系（多轴，禁止自创未登记境界/道途/法宝阶）】\n"
                + power_systems_context.strip()[:2400]
                + "\n"
            )

        prompt = f"""章节：《{chapter_title}》
章节摘要：{chapter_summary[:300]}
{pos_block}{prev_block}{power_block}{constraint_block}{mem_block}{loc_context_block}
---
【第 {scene_order} 场】{('  ' + scene_title) if scene_title else ''}
时间：{time or '同日'}　　地点：{location_name or '未知'}
POV：{pov_character}（全场保持此 POV，禁止全知视角插入）
在场角色：{on_stage}

本场任务：
- 目标：{goal}
- 冲突：{conflict}
- 转折：{turn}
- 场末必须埋下钩子：{hook_to_plant}

写作约束：
- 字数：{word_budget} 字（允许 ±10%，不得大幅超出）
- 节奏：{pacing}（{pacing_guide.get(pacing, '均衡节奏')}）
- 感官焦点：{sensory_guide.get(sensory_focus, '多感官综合')}
- 禁用词：「突然」「忽然」「不禁」「只见」「顿时」「心中一震」
- 结尾：最后一句必须植入悬念或张力，呼应「场末必须埋下钩子」

请直接输出本场正文："""

        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tokens_scene_draft(),
            task="draft.chapter",
        ):
            yield chunk
