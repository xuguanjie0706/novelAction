"""
debrief_extract.py — 章节自动复盘提取 Mixin

职责：
  DebriefMixin.auto_extract_debrief → AI 读取章节正文，提取人物状态/故事线/伏笔/资产变化，
                                       返回结构化建议供前端预填复盘表单。
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

from app.services.ai.character_resolve import resolve_character_updates_from_states
from app.services.ai.debrief_helpers import (
    _clean_fulfilled_promise_texts,
    _clean_new_reader_promises,
    split_foreshadow_updates,
)
from app.services.bootstrap.prompts.character_naming import character_naming_constraints_for_prompt
from app.services.llm_token_budgets import max_tokens_auto_debrief

logger = logging.getLogger(__name__)


class DebriefMixin:
    async def auto_extract_debrief(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
        character_states: List[dict],    # [{"id":…,"name":…,"current_realm":…,"current_location":…,"current_status":…}]
        storylines: List[dict],          # [{"id":…,"name":…,"line_type":…,"status":…,"core_conflict":…}]
        open_promises: List[dict] = [],  # [{"id":…,"promise_text":…,"promise_type":…,"source_chapter_number":…,"priority":…}]
        genre: str | None = None,
    ) -> dict:
        """
        AI 读取章节正文，对照人物当前状态和故事线，
        自动提取本章发生的状态变化和故事节拍。
        open_promises：当前项目所有 status=open 的读者承诺，供 AI 判断本章是否兑现。
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

        # 读者承诺台账注入：按优先级降序，最多 20 条，供 AI 判断本章是否兑现
        promise_lines = []
        for p in (open_promises or [])[:20]:
            pid = p.get("id", "")
            text = (p.get("promise_text") or "").strip()
            if not text:
                continue
            src = p.get("source_chapter_number") or "?"
            prio = p.get("priority") or 3
            ptype = p.get("promise_type") or "chapter_ending"
            promise_lines.append(f"- [id:{pid}] 【{ptype}·优先级{prio}】第{src}章埋：{text}")
        open_promises_text = (
            "当前开放读者承诺（status=open，对照正文判断本章是否已兑现）：\n"
            + "\n".join(promise_lines)
            if promise_lines
            else ""
        )

        system = (
            "你是网络小说助手，从章节内容中提取人物状态、故事线、伏笔、信息来源和结构化资产变化，只返回JSON，不要任何解释。"
            "语言：除 JSON 键名、以及各字段说明中要求使用的英文枚举值（如 alive/dead、open、planned/active/climax/resolved/dropped、"
            "low/medium/high、item_type/rarity 等）外，所有人类可读的自然语言字符串必须使用简体中文——含 memory_updates 的 title/content/tags、"
            "storyline_updates.beat、chapter_index 全部文案（含 story_day）、asset_updates 与 new_characters 中的描述字段、summary 等。"
            "不得用英文撰写剧情摘要、伏笔说明或章末钩子；专有名词（人名、功法、法宝、地名）与正文用字保持一致。"
        )

        narrative_body = self._clip_context(
            (chapter_content or "").strip(),
            12000,
            120000,
        )

        naming_block = character_naming_constraints_for_prompt(genre)

        prompt = f"""章节{chapter_number}《{chapter_title}》

【叙事正文】（业务库仅存叙事；须通读下列全文以提取人物、故事线、资产与记忆；稿末模板仅保留在模型调用记录中供对账）
{narrative_body}

当前人物状态（对照基准）：
{chars_text}

当前故事线（对照基准）：
{sl_text}
{f"{chr(10)}{open_promises_text}{chr(10)}" if open_promises_text else ""}
请分析本章内容，提取：
1. 哪些人物的境界/位置/状态发生了变化
2. 哪些人物习得了新技能
3. 哪些故事线有了推进（节拍）
4. 哪些信息来源需要记录，避免后文凭空知道信息
5. 哪些伏笔被埋下、推进或回收，避免后文突然出现无前因的设定（在 chapter_index.foreshadow_updates 中用显式 "code" 字段标注全局伏笔编号，回收/推进条目必须填 code，新埋伏笔 code 可为 null 由系统分配）
6. 哪些新道具/法宝、功法/技能、势力需要收入系统，或已有资产状态发生变化
7. 生成章节索引（chapter_index）：完全依据上方叙事正文归纳；须与正文事实一致
8. 本章是否出现了不在现有角色库中、且值得长期追踪的新角色（new_characters）
   判断标准：正文中有名有姓、有台词或行动、且 arc_scope 为 mini_arc 或以上；纯工具性一次性路人不需要入库

只提取文中明确发生的变化，不要推断或猜测。
如果某字段没有变化，不要包含它。
realm_rank 若填写必须与上方人物列表所属力量体系 levels 的 rank 一致；不确定请省略该字段（系统会按 current_realm 文本解析），禁止自创 11、99 等随意整数。
资产表只记录 A/B 级耐久实体：会再次出现、影响人物能力/势力关系/主线伏笔/后续冲突的道具、技能、势力。
C级临时资产（一次性丹药、普通符箓、无名小队、普通招式）不要放进 asset_updates，只可在正文或 memory_updates 中作为事件细节出现。
记忆库记录"第几章发生了什么、信息来源是什么、为何获得/使用/暴露该资产"；资产表记录"这个实体现在是什么、谁持有/掌握、能力/限制/状态是什么"。两者不要互相替代。
{naming_block}
`character_updates.current_status` 只能填写以下枚举之一：
- alive
- dead
- missing
- sealed
- transformed
禁止输出任何附加说明，例如 "alive（受伤）"、"dead-被刺杀"、"active"。
再次强调：除上述英文枚举与 JSON 键名外，一律简体中文；story_day 用中文表述故事内时间（如「第8日」「首日·夜至晨」），勿用 Day 1 式英文。

返回JSON（严格遵守字段名）：
{{
  "character_updates": [
    {{
      "character_id": "必须从上方「当前人物状态」列表原样复制 id（UUID 格式）；禁止 su_chen_id、protagonist_xxx 等自创 slug",
      "character_name": "必填，与列表中姓名完全一致",
      "current_realm": "新境界名称（如有变化，须与境界体系设定完全一致）",
      "realm_rank": null,
      "current_location": "新位置（如有变化）",
      "current_status": "新状态（仅允许 alive/dead/missing/sealed/transformed 之一）",
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
  "memory_updates": [
    {{
      "memory_type": "event / character_state / foreshadow / setting / conflict 之一",
      "title": "短标题",
      "content": "可供后续生成使用的事实，必须写清信息来源、伏笔前因或状态变化",
      "tags": ["人物名", "关键词"],
      "importance_score": 0.7
    }}
  ],
  "asset_updates": {{
    "new_items": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新道具/法宝/材料名",
        "item_type": "weapon/armor/pill/artifact/material/scroll/beast/other",
        "rarity": "common/uncommon/rare/epic/legendary/mythic/unique",
        "description": "外观与性质",
        "origin": "来历（如正文明确）",
        "effects": "能力效果",
        "limitations": "限制/代价",
        "current_owner_id": "持有人物id（如能对应）",
        "current_owner_name": "持有人名（如正文明确）",
        "story_significance": "为什么值得入库",
        "status": "intact/damaged/destroyed/lost/unknown",
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "item_updates": [
      {{
        "item_id": "已有道具id（如知道）",
        "item_name": "已有道具名",
        "status": "新状态（如有）",
        "current_owner_id": "新持有人id（如有）",
        "current_owner_name": "新持有人名（如有）",
        "effects": "新增/暴露的效果（如正文明确）",
        "limitations": "新增/暴露的限制（如正文明确）",
        "story_significance": "意义变化（如有）",
        "event_note": "本章发生的资产事件"
      }}
    ],
    "new_skills": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新功法/技能名",
        "skill_type": "combat/defense/movement/support/bloodline/special",
        "grade": "mortal/earth/sky/profound/saint/divine/supreme",
        "source": "来源",
        "level_required": "境界要求",
        "prerequisites": "前置条件",
        "description": "技能描述",
        "effects": "效果",
        "limitations": "限制/代价",
        "mastered_by_character_ids": ["掌握者id"],
        "mastered_by_character_names": ["掌握者姓名"],
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "skill_updates": [
      {{
        "skill_id": "已有技能id（如知道）",
        "skill_name": "已有技能名",
        "effects": "新增/暴露的效果（如正文明确）",
        "limitations": "新增/暴露的限制（如正文明确）",
        "add_mastered_by_character_id": "新掌握者id（如有）",
        "add_mastered_by_character_name": "新掌握者姓名（如有）",
        "mastery": "掌握程度",
        "event_note": "本章发生的技能事件"
      }}
    ],
    "new_factions": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新势力名",
        "faction_type": "sect/kingdom/family/guild/evil/race/other",
        "alignment": "protagonist/neutral/antagonist/unknown",
        "description": "势力描述",
        "territory": "活动范围",
        "strength_level": "实力层级",
        "goals": "目标",
        "resources": "资源",
        "attitude_to_protagonist": "friendly/hostile/neutral/subordinate/superior",
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "faction_updates": [
      {{
        "faction_id": "已有势力id（如知道）",
        "faction_name": "已有势力名",
        "alignment": "新阵营（如有）",
        "goals": "目标变化（如有）",
        "resources": "资源变化（如有）",
        "attitude_to_protagonist": "对主角态度变化（如有）",
        "event_note": "本章发生的势力事件"
      }}
    ]
  }},
  "new_characters": [
    {{
      "name": "正名（姓+名，2~4字；禁止老铁/小X/称呼词作正名）",
      "alias": ["可选外号/乳名/道号"],
      "role": "supporting",
      "character_tier": "arc",
      "gender": "男/女",
      "age": "年龄或模糊描述",
      "faction": "所属势力或机构",
      "personality": "性格（1句话）",
      "motivation": "本章/本卷的行为动机",
      "background": "背景（1句话）",
      "current_realm": "境界或能力层级",
      "current_status": "alive",
      "current_location": "本章末位置",
      "arc_scope": "single_chapter / mini_arc / long_arc",
      "author_notes": "给作者的提醒：此角色应如何使用、何时退出、是否有伏笔价值"
    }}
  ],
  "chapter_index": {{
    "story_day": "故事内时间（简体中文），如「第8日」「首日（夜→晨）」；未知则为空字符串",
    "core_events": ["本章实际发生的核心事件1", "核心事件2"],
    "first_appearances": [{{"character_id": "可为空", "name": "首次出场人物名"}}],
    "foreshadow_updates": [
      {{
        "action": "lay",
        "code": null,
        "title": "简短标题（5字以内）",
        "description": "伏笔内容",
        "deadline_chapter": 5
      }},
      {{
        "action": "develop",
        "code": "F-007",
        "title": "简短标题",
        "description": "本章如何进一步铺垫/加深的"
      }},
      {{
        "action": "resolve",
        "code": "F-003",
        "title": "简短标题",
        "description": "本章以何种方式完整回收的"
      }}
    ],
    "ending_hook": "章末钩子描述",
    "hook_strength": 1,
    "continuity_notes": [{{"severity": "low/medium/high", "note": "生成或正文中发现的连续性风险"}}]
  }},
  "highlight_quote": "本章最有截图/转发价值的1句原文；全章无亮句则填空字符串",
  "subscribe_intent_score": 8,
  "summary": "本章整体复盘总结（一句话）",
  "speech_kit_updates": [
    {{
      "character_id": "人物id",
      "character_name": "人物名",
      "new_signature_words": ["本章新出现的标志性词语"],
      "new_sample_dialogues": ["本章新出现的典型台词（1-3句）"],
      "evolution_note": "本章人物说话风格/心理有何细微演变"
    }}
  ],
  "new_reader_promises": [
    {{
      "promise_text": "对读者的承诺原文或提炼",
      "promise_type": "chapter_ending / volume_ending / name_implication / chapter_comment_consensus",
      "expected_within_chapters": 1,
      "priority": 5,
      "audience_aware": 4
    }}
  ],
  "fulfilled_promise_texts": [
    "已兑现承诺的原文（从上方「当前开放读者承诺」中选取，复制 promise_text 原文）"
  ],
  "next_chapter_directives": [
    {{
      "outline_node_id": "目标下一章 OutlineNode 的 id（若已知则填，否则留空字符串）",
      "patch": {{
        "add_foreshadow": "建议在下一章回收或发展的伏笔描述",
        "force_pov": "下一章建议强制使用哪位角色 POV",
        "increase_screen_time_for": ["角色id列表"],
        "must_resolve_promise_in_next_N_chapters": 2,
        "adjust_pacing": "fast / normal / slow",
        "reader_expectation_note": "读者当前最期待/最怕看到什么"
      }},
      "reason": "为什么要做这个 patch 的编辑逻辑（简短一句）"
    }}
  ]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_auto_debrief(self.profile),
            context={"operation": "auto_extract_debrief", "chapter_title": chapter_title},
            task="debrief.auto",
        )
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
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
                # realm_rank 为 0 时 v=0 被过滤，需单独保留
                if "realm_rank" in cu and cu["realm_rank"] is not None:
                    try:
                        cleaned["realm_rank"] = int(cu["realm_rank"])
                    except (ValueError, TypeError):
                        pass
                if len(cleaned) > 1:  # 除 character_id 外还有其他字段
                    cleaned["character_name"] = cu.get("character_name", "")
                    char_updates.append(cleaned)
            sl_updates = []
            for su in data.get("storyline_updates", []):
                cleaned = {k: v for k, v in su.items() if v and k not in ("storyline_name",)}
                if len(cleaned) > 1:
                    cleaned["storyline_name"] = su.get("storyline_name", "")
                    sl_updates.append(cleaned)
            memory_updates = []
            valid_memory_types = {"event", "character_state", "foreshadow", "setting", "conflict"}
            for mu in data.get("memory_updates", []):
                if not isinstance(mu, dict):
                    continue
                memory_type = mu.get("memory_type") or "event"
                if memory_type not in valid_memory_types:
                    memory_type = "event"
                content = (mu.get("content") or "").strip()
                if not content:
                    continue
                tags = mu.get("tags") if isinstance(mu.get("tags"), list) else []
                try:
                    imp = float(mu.get("importance_score") or 0.5)
                    imp = max(0.0, min(1.0, imp))
                except (ValueError, TypeError):
                    imp = 0.5
                memory_updates.append({
                    "memory_type": memory_type,
                    "title": (mu.get("title") or memory_type).strip()[:120],
                    "content": content,
                    "tags": [str(t) for t in tags[:8] if str(t).strip()],
                    "importance_score": imp,
                })
            raw_assets = data.get("asset_updates") if isinstance(data.get("asset_updates"), dict) else {}

            def _clean_asset_items(key: str, limit: int = 8) -> list:
                return [
                    item for item in (raw_assets.get(key) or [])[:limit]
                    if isinstance(item, dict) and (
                        item.get("name") or item.get("item_name")
                        or item.get("skill_name") or item.get("faction_name")
                    )
                ]

            asset_updates = {
                "new_items": [
                    item for item in _clean_asset_items("new_items")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "item_updates": _clean_asset_items("item_updates"),
                "new_skills": [
                    item for item in _clean_asset_items("new_skills")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "skill_updates": _clean_asset_items("skill_updates"),
                "new_factions": [
                    item for item in _clean_asset_items("new_factions")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "faction_updates": _clean_asset_items("faction_updates"),
            }
            chapter_index = data.get("chapter_index") if isinstance(data.get("chapter_index"), dict) else {}
            hook_strength = chapter_index.get("hook_strength", 1)
            try:
                hook_strength = max(1, min(5, int(hook_strength)))
            except Exception:
                hook_strength = 1
            cleaned_index = {
                "story_day": (chapter_index.get("story_day") or "").strip(),
                "core_events": [
                    item for item in (chapter_index.get("core_events") or [])[:5]
                    if isinstance(item, (str, dict)) and item
                ],
                "first_appearances": [
                    item for item in (chapter_index.get("first_appearances") or [])[:8]
                    if isinstance(item, dict) and (item.get("name") or item.get("character_id"))
                ],
                **split_foreshadow_updates(chapter_index),
                "ending_hook": (chapter_index.get("ending_hook") or "").strip(),
                "hook_strength": hook_strength,
                "continuity_notes": [
                    item for item in (chapter_index.get("continuity_notes") or [])[:10]
                    if isinstance(item, (str, dict)) and item
                ],
            }
            # 提取 new_characters，过滤无效项；兼容 AI 把多人写进单个 description 字段的错误格式
            raw_new_chars = data.get("new_characters") or []
            new_characters = []
            for item in raw_new_chars:
                if not isinstance(item, dict):
                    continue
                if item.get("name"):
                    new_characters.append(item)
                elif item.get("description") and not item.get("name"):
                    desc = str(item["description"])
                    parts = re.split(r"[、，,；;\n]+", desc)
                    for part in parts:
                        name = re.split(r"[（(【]", part.strip())[0].strip()
                        if name and 1 <= len(name) <= 10:
                            new_characters.append({"name": name, "role": "supporting", "current_status": "alive"})
            new_characters = new_characters[:6]  # 单章最多6个新配角

            new_reader_promises = _clean_new_reader_promises(data.get("new_reader_promises"))
            fulfilled_promise_texts = _clean_fulfilled_promise_texts(
                data.get("fulfilled_promise_texts")
            )
            char_updates = resolve_character_updates_from_states(char_updates, character_states)

            return {
                "character_updates": char_updates,
                "storyline_updates": sl_updates,
                "memory_updates": memory_updates,
                "asset_updates": asset_updates,
                "new_characters": new_characters,
                "chapter_index": cleaned_index,
                "new_reader_promises": new_reader_promises,
                "fulfilled_promise_texts": fulfilled_promise_texts,
                "summary": data.get("summary", ""),
            }
        except Exception as e:
            return {
                "character_updates": [],
                "storyline_updates": [],
                "memory_updates": [],
                "asset_updates": {
                    "new_items": [], "item_updates": [],
                    "new_skills": [], "skill_updates": [],
                    "new_factions": [], "faction_updates": [],
                },
                "new_characters": [],
                "chapter_index": {},
                "new_reader_promises": [],
                "fulfilled_promise_texts": [],
                "summary": "",
                "error": f"解析失败: {e}",
                "raw": response[:300],
            }
