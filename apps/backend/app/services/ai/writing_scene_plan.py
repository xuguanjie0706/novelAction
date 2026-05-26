"""分场计划 Mixin — 根据章纲生成结构化 4-8 场分场计划。"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.services.bootstrap.parse import parse_json

logger = logging.getLogger(__name__)


class ScenePlanMixin:
    async def scene_plan(
        self,
        chapter_title: str,
        chapter_summary: str,
        genre: str = "",
        positioning: Optional[dict] = None,
        existing_characters: List[dict] = None,
        prev_directives: str = "",
        model_profile: str = "local",
        word_target: int = 2200,
        character_states: Optional[List[dict]] = None,
        open_foreshadows: Optional[List[dict]] = None,
        open_reader_promises: Optional[List[dict]] = None,
        known_locations: Optional[List[dict]] = None,
        constraints_block: Optional[str] = None,
    ) -> dict:
        """根据章纲生成结构化分场计划（4-8 场）。

        每场包含：POV、时间、地点、在场角色、目标、冲突、转折、钩子、字数预算、感官焦点、节奏。

        Args:
            chapter_title: 章节标题。
            chapter_summary: 章节摘要（≤800 字）。
            genre: 类型标签，用于 genre_kit guardrail。
            positioning: 立项定位 dict（取 selling_point/taboo_lines）。
            existing_characters: 角色列表 [{"id":..., "name":...}]，仅用于 prompt 展示。
            prev_directives: 上一章复盘指令（最高优先级约束）。
            model_profile: "local" / "gemini"。
            word_target: 全章目标字数，分配各场预算基准。
            character_states: 关键角色当前状态列表，每条含 name/current_realm/
                              current_status/current_location（可选字段）。有数据时注入约束块。
            open_foreshadows: 未闭合伏笔列表，每条含 title/description/priority。
                              高优先级（priority≥4）在场景安排时需有意识回收或推进。
            open_reader_promises: 未兑现读者承诺列表，每条含 promise_text/promise_type/priority。
                                  高优先级在本章分场中必须有至少一场回应或推进。
            known_locations: 项目已建库地点列表（最多 10 条），每条含 name/aliases/sensory_signature。
            constraints_block: ChapterIngredients 投料约束块（最高写作优先级）。

        Returns:
            dict with key "scenes": List[dict]，每条含 order/title/time/location_name/
            pov_character_name/characters_on_stage/goal/conflict/turn/hook/hook_strength/
            word_budget/pacing/sensory_focus。
        """
        system = (
            "你是资深网文分镜师。严格返回 JSON，不要任何额外文字。"
            "必须严格遵守 genre_kit 的 pacing_guide 和 side_character_quota。"
            "每章 4-8 场，字数总和接近 word_target。"
            "每场必须有明确的 POV（禁止全知），在场角色不得超过 genre_kit quota。"
        )

        kit_block = ""
        if genre:
            from app.services.genre_kit import get_genre_guardrail
            kit_block = "\n" + get_genre_guardrail(genre) + "\n"

        positioning_block = ""
        if positioning:
            positioning_block = "\n【立项定位】\n" + json.dumps(positioning, ensure_ascii=False) + "\n"

        prev_block = ""
        if prev_directives.strip():
            prev_block = "\n【上一章复盘指令（最高优先级）】\n" + prev_directives.strip() + "\n"

        char_block = ""
        if existing_characters:
            char_lines = [f"- {c.get('name','')}（id:{c.get('id','')}）" for c in existing_characters[:8]]
            char_block = "\n当前主要角色：\n" + "\n".join(char_lines)

        # ── 约束注入块 ──────────────────────────────────────────────────────────
        state_block = ""
        if character_states:
            lines = []
            for cs in character_states[:6]:
                parts = [cs.get("name", "?")]
                if cs.get("current_realm"):
                    parts.append(f"境界:{cs['current_realm']}")
                if cs.get("current_status") and cs["current_status"] != "alive":
                    parts.append(f"状态:{cs['current_status']}")
                if cs.get("current_location"):
                    parts.append(f"位置:{cs['current_location']}")
                lines.append("  " + " | ".join(parts))
            state_block = "\n【当前角色状态（分场须保持一致）】\n" + "\n".join(lines) + "\n"

        foreshadow_block = ""
        if open_foreshadows:
            sorted_fw = sorted(open_foreshadows, key=lambda x: -(x.get("priority") or 3))
            lines = []
            for fw in sorted_fw[:4]:
                pri = fw.get("priority") or 3
                marker = "⚡" if pri >= 4 else "·"
                desc = (fw.get("description") or "")[:60]
                lines.append(f"  {marker} {fw.get('title','?')}：{desc}")
            foreshadow_block = (
                "\n【未闭合伏笔（⚡=高优先，本章宜推进或回收）】\n"
                + "\n".join(lines) + "\n"
            )

        promise_block = ""
        if open_reader_promises:
            sorted_rp = sorted(open_reader_promises, key=lambda x: -(x.get("priority") or 3))
            lines = []
            for rp in sorted_rp[:3]:
                pri = rp.get("priority") or 3
                marker = "⚡" if pri >= 4 else "·"
                ptype = rp.get("promise_type") or ""
                text = (rp.get("promise_text") or "")[:80]
                lines.append(f"  {marker} [{ptype}] {text}")
            promise_block = (
                "\n【未兑现读者承诺（⚡=高优先，本章至少一场须回应或推进）】\n"
                + "\n".join(lines) + "\n"
            )

        location_lib_block = ""
        if known_locations:
            loc_lines: list[str] = []
            for loc in known_locations[:10]:
                name = loc.get("name", "")
                aliases = loc.get("aliases") or []
                sig = (loc.get("sensory_signature") or "")[:50]
                alias_str = f"（别名：{'、'.join(aliases[:3])}）" if aliases else ""
                sig_str = f" 【感官：{sig}…】" if sig else ""
                loc_lines.append(f"  - {name}{alias_str}{sig_str}")
            location_lib_block = (
                "\n【已知地点库（location_name 请优先从此列表精确选取）】\n"
                + "\n".join(loc_lines) + "\n"
            )

        ingredients_block = ""
        if constraints_block and constraints_block.strip():
            ingredients_block = "\n" + constraints_block.strip() + "\n"

        prompt = f"""{kit_block}{positioning_block}{prev_block}{ingredients_block}{state_block}{foreshadow_block}{promise_block}{location_lib_block}
本章标题：《{chapter_title}》
本章摘要：{chapter_summary[:800]}
{char_block}

请为本章拆分 4-8 场（scene），返回 JSON：
{{
  "scenes": [
    {{
      "order": 1,
      "title": "场标题",
      "time": "第X日·夜",
      "location_name": "地点",
      "pov_character_name": "POV 角色名（必须是现有角色之一）",
      "characters_on_stage": ["角色名列表"],
      "goal": "本场角色想要什么",
      "conflict": "冲突/障碍",
      "turn": "本场关键转折",
      "hook": "场末钩子（留给下一场）",
      "hook_strength": 3,
      "word_budget": 350,
      "pacing": "fast/mid/slow",
      "sensory_focus": "sight/sound/mixed"
    }}
  ],
  "total_word_budget": {word_target},
  "notes": "分场说明（可选）"
}}
只返回 JSON。"""

        raw = await self._call_ai(
            system,
            prompt,
            max_tokens=2000,
            task="draft.scene_plan",
        )
        try:
            data = parse_json(raw)
            if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
                raise ValueError("scene_plan JSON 缺少 scenes 数组")
        except Exception as exc:
            logger.warning("scene_plan JSON 解析失败: %s; raw=%s", exc, (raw or "")[:400])
            _default_char = (existing_characters[0]["name"] if existing_characters else "主角")
            data = {
                "scenes": [
                    {"order": i, "title": t, "time": "同日", "location_name": "未知",
                     "pov_character_name": _default_char, "characters_on_stage": [],
                     "goal": chapter_summary[:60] if i == 1 else "", "conflict": "",
                     "turn": "", "hook": "章末钩子待定" if i == 4 else "",
                     "hook_strength": 5 if i == 4 else 3,
                     "word_budget": 600 if i >= 3 else 500,
                     "pacing": "fast" if i == 3 else "mid",
                     "sensory_focus": "mixed"}
                    for i, t in enumerate(["开场", "冲突升级", "转折", "收束与钩子"], start=1)
                ],
                "total_word_budget": word_target,
                "notes": "兜底分场（LLM 解析失败）"
            }
        return data
