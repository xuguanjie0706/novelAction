"""写前预警 Mixin — 写章前主编级风险扫描与写作简报生成。"""
from __future__ import annotations

from typing import List

from app.services.ai.pre_write_warn_parse import (
    empty_pre_write_warning_error,
    looks_truncated_json,
    parse_pre_write_warning_text,
)
from app.services.llm_token_budgets import max_tokens_pre_write_warning

_COMPACT_JSON_HINT = (
    "【输出格式硬约束】只输出一个合法 JSON 对象，禁止 markdown 代码块外的说明；"
    "禁止在冒号与 [ 或 { 之间换行；不要输出推理过程，直接给出完整 JSON。"
)


class PreWriteWarnMixin:
    async def pre_write_warning(
        self,
        project_title: str,
        genre: str,
        chapter_plan_summary: str,
        memory_chunks: list[dict],
        continuity_state: str = "",
        foreshadow_ledger: str = "",
        character_states: str = "",
        power_systems_summary: str = "",
        outline_context: str = "",
        phase: str = "",
        transition_menu: str = "",
        chapter_lock_table_block: str = "",
        foreshadow_schedule_block: str = "",
    ) -> dict:
        """写前预警：像三十年主编在落笔前把本章的「坑、约束、写法」全交代清楚。

        不仅排雷（连续性/伏笔/设定/OOC/节奏），还输出：
        - protagonist_fact_sheet：主角此刻的精确状态锁定（境界/位置/技能/道具），防止幻觉
        - writing_brief：本章应该怎么写（开篇策略/冲突结构/章末钩子）
        - must_events：本章必须发生的事件（剧情硬约束）
        - hallucination_traps：写这类章节时 AI 最容易犯的错误清单

        Args:
            project_title: 书名。
            genre: 类型标签。
            chapter_plan_summary: 本章计划摘要（五要素或简述）。
            memory_chunks: MemoryChunk 列表，每条含 title/content/memory_type。
            continuity_state: 滚动连续性账本。
            foreshadow_ledger: 伏笔台账。
            character_states: 主要角色当前状态快照。
            power_systems_summary: 境界体系摘要（含各阶名称与规则）。
            outline_context: 本章大纲五要素（hook/summary/conflict/highlight/milestone）。
            phase: 章节所在阶段（opening/rising/turning/dark_hour/climax/ending）。
            transition_menu: 开篇衔接技法菜单（由 transition_advisor 生成，注入衔接决策）。

        Returns:
            dict with keys: ok, risk_count, risks, reminders,
                            protagonist_fact_sheet, writing_brief,
                            must_events, hallucination_traps, transition_directive
        """
        mem_lines: list[str] = []
        for chunk in memory_chunks[:40]:
            mt = chunk.get("memory_type", "event")
            title = (chunk.get("title") or "").strip()
            content = (chunk.get("content") or "").strip()[:200]
            mem_lines.append(f"[{mt}] {title}：{content}")
        mem_block = "\n".join(mem_lines) if mem_lines else "（无记忆条目）"

        phase_hint = {
            "opening":   "开局期：爽点密集，钩子3章一次，字数偏短，不要铺垫过重",
            "rising":    "起飞期：势力扩张，感情线接入，可以开始拉长单章字数",
            "turning":   "转折期：矛盾升级，代价兑现，节奏可稍微放缓以铺陈",
            "dark_hour": "至暗期：允许「虐」，允许主角吃亏，节奏放慢，心理戏加重",
            "climax":    "高潮期：伏笔回收，爆点拉满，爽感最大化，章末钩子必须炸裂",
            "ending":    "收束期：留悬念种子，给读者追读下一卷的理由",
        }.get((phase or "").lower().strip(), "")

        system = (
            "你是拥有三十年经验的网络小说主编，精通玄幻、修仙、都市等各类型。"
            "你的职责是在作者落笔前，像老编辑审稿一样，把这一章的「坑、约束、写法」全部交代清楚，"
            "让写正文的 AI 无法出现幻觉和逻辑错误。严格返回 JSON，不要任何额外文字。"
        )

        lock_part = (
            self._clip_context(chapter_lock_table_block, 2000, None, field_name="chapter_lock_table")
            if chapter_lock_table_block and chapter_lock_table_block.strip()
            else "（第一章或无上章成稿，无情节锁定表）"
        )
        fs_schedule_part = (
            self._clip_context(foreshadow_schedule_block, 2000, None, field_name="foreshadow_schedule")
            if foreshadow_schedule_block and foreshadow_schedule_block.strip()
            else "（无核心谜题日程表）"
        )

        prompt = f"""小说：《{project_title}》（{genre}）
{f'当前阶段：{phase_hint}' if phase_hint else ''}

══════════════════════════════════════
【情节锁定表（程序生成，硬事实，优先级高于本章章纲字面）】
{lock_part}

══════════════════════════════════════
【伏笔日程锁定表（程序生成，硬事实，优先级高于本章章纲 foreshadow 与 must_events）】
{fs_schedule_part}

══════════════════════════════════════
【本章计划（大纲五要素）】
{self._clip_context(outline_context or chapter_plan_summary, 1500, None, field_name="outline")}

══════════════════════════════════════
【主要角色当前状态（精确到境界/位置/技能/持有物）】
{self._clip_context(character_states, 1200, None, field_name="char_states") or "（未提供）"}

【境界体系规则（防止境界幻觉）】
{self._clip_context(power_systems_summary, 2400, None, field_name="power_systems") or "（未提供）"}

【滚动连续性账本（最近章节状态）】
{self._clip_context(continuity_state, 2000, None, field_name="continuity") or "（未提供）"}

【伏笔台账（含未收束条目与逾期警告）】
{self._clip_context(foreshadow_ledger, 1500, None, field_name="foreshadow_ledger") or "（无伏笔记录）"}

【历史记忆库（事件/状态/冲突）】
{self._clip_context(mem_block, 2500, None, field_name="memory_chunks")}
{self._clip_context(transition_menu, 1200, None, field_name="transition_menu") if transition_menu else ""}

══════════════════════════════════════
请以「三十年主编」的视角完成以下六件事，**全部输出到 JSON**：

⓪ 你必须以【情节锁定表】与【伏笔日程锁定表】为准：
   - 情节锁定表：若与【本章计划】矛盾，risks 须含 critical 级 continuity，不得倒带重播上章已完成节拍。
   - 伏笔日程表：禁止提前完整埋设「未到埋设章」的核心谜题；must_events 不得违背「禁止提前完整埋设」清单；
     开局承诺允许的「预告/钩子」除外（仅一声滴答、模糊异象等，不得写尽 lay_method 细节）。

① 主角状态锁定（protagonist_fact_sheet）
   核对上述资料，锁定本章开笔时主角的精确状态，AI 写正文必须严格遵守这份清单：
   - realm：当前境界名称（精确，不可升级或缩写）
   - location：当前所在位置
   - key_skills：本章可以合理使用的技能/功法（各1句话说明来源）
   - key_items：当前持有的关键道具/法宝（各1句话）
   - forbidden：本章绝对不能出现的能力/道具/状态（还未习得/已损毁/不在身边）

② 本章写作简报（writing_brief）
   给写章 AI 的具体写法指导，像导演给演员的场景说明：
   - opening_strategy：开篇第一段应该怎么切入（人物/动作/对话/环境？为什么？）
   - conflict_structure：本章冲突如何分层递进（给出2-3个节拍）
   - closing_hook：最后一段的钩子设计（悬念/爽感/伏笔引爆？具体怎么收？）
   - word_rhythm：字数与节奏建议（哪些场景应该详写/略写）

③ 本章必发事件（must_events）
   根据大纲计划，列出本章必须在正文中落地的关键事件（2-4条，每条一句话）。
   不在大纲里但记忆库/伏笔台账要求必须处理的，也列进来。

④ 幻觉预防清单（hallucination_traps）
   针对这一章的具体内容，列出写 AI 最容易犯的错误（3-5条），格式：「陷阱描述 → 正确做法」

⑤ 风险扫描（risks）
   逐条对照资料，发现以下类型的潜在问题：
   - continuity：连续性矛盾（人物状态/位置/事件顺序）
   - foreshadow：伏笔违约（漏收/误收）
   - setting：设定违规（境界/势力/道具与世界观矛盾）
   - ooc：人物OOC（行为与性格/价值观/创伤明显冲突）
   - pacing：节奏预警（与前章钩子期望落差）

⑥ 开篇衔接策略（transition_directive）—— 仅当上方提供了「开篇衔接需求分析」时填写
   根据提供的衔接技法菜单和本章实际情况，为写章 AI 给出可执行的转场/破境指令：
   - spatial_bridge：空间衔接（若本章起点≠记录位置，或新章需要明确交代空间）
   - realm_bridge：破境衔接（仅当本章有实力里程碑时填，否则 needed=false）
   每个指令必须包含：needed(bool)、technique_id、technique_name、instruction（一到两句可执行指令）

返回 JSON（所有字段必须存在，无内容填空数组/空字符串）：
{{
  "ok": true,
  "risk_count": 0,
  "protagonist_fact_sheet": {{
    "realm": "精确境界名",
    "location": "当前位置",
    "key_skills": ["技能A（来源/原因）", "技能B（来源/原因）"],
    "key_items": ["道具A（来源/当前状态）"],
    "forbidden": ["不能使用X（原因）", "不能出现Y（原因）"]
  }},
  "writing_brief": {{
    "opening_strategy": "具体的开篇切入建议（若有衔接需求，请直接引用所选技法名并说明起手方式）",
    "conflict_structure": "节拍1 → 节拍2 → 节拍3（每个节拍一句话描述）",
    "closing_hook": "章末钩子的具体设计，一到两句话",
    "word_rhythm": "哪段详写、哪段略写的建议"
  }},
  "must_events": [
    "本章必须发生的事件1",
    "本章必须发生的事件2"
  ],
  "hallucination_traps": [
    "陷阱：AI 容易写出X → 正确做法：应该Y",
    "陷阱：AI 容易忽略Z → 正确做法：需要W"
  ],
  "risks": [
    {{
      "type": "continuity/foreshadow/setting/ooc/pacing",
      "severity": "low/medium/high/critical",
      "description": "具体矛盾点，精确到涉及条目和章节",
      "suggested_fix": "建议解决方案"
    }}
  ],
  "reminders": [
    "一句话写作提醒（如：本章主角境界是X，不能使用Y技能）"
  ],
  "transition_directive": {{
    "spatial_bridge": {{
      "needed": true,
      "technique_id": "time_stamp",
      "technique_name": "时间标注法",
      "instruction": "本章开篇第一句：「三日后，绝命谷底——」，随后用感官细节锚定场景"
    }},
    "realm_bridge": {{
      "needed": false,
      "technique_id": "none",
      "technique_name": "无需破境",
      "instruction": ""
    }}
  }}
}}
若无风险则 risks 为空数组，ok=true；有 high/critical 风险则 ok=false。
若未提供衔接需求分析，transition_directive 两个 needed 均填 false，instruction 填空字符串。"""

        max_tok = max_tokens_pre_write_warning(self.profile)
        last_exc: Exception | None = None
        last_response = ""
        for attempt in range(2):
            sys = system if attempt == 0 else f"{system}\n\n{_COMPACT_JSON_HINT}"
            last_response = await self._call_ai(
                sys,
                prompt,
                max_tokens=max_tok,
                context={
                    "operation": "pre_write_warning",
                    "chapter_plan": chapter_plan_summary[:80],
                    "attempt": attempt + 1,
                },
                task="quality.pre_write_warning",
            )
            try:
                if looks_truncated_json(last_response):
                    raise ValueError("模型输出 JSON 不完整（可能顶满 max_tokens，推理占满预算）")
                return parse_pre_write_warning_text(last_response)
            except Exception as e:
                last_exc = e
                continue
        return empty_pre_write_warning_error(
            last_exc or RuntimeError("pre_write_warning 解析失败"),
            last_response,
        )
