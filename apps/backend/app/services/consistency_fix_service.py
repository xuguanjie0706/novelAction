"""一致性问题 AI 修复：prompt 脱敏与分批重试。

远程 Gemini 等对中文网文专有名词、势力/境界描述易触发安全过滤。
本模块将实体映射为中性代号（C0/F0/S0），用户向 prompt 使用英文结构化描述，
并在批量调用被 block 时自动降为单条重试。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.models import Character, Faction, Skill
from app.services.ai_service import AIService
from app.services.bootstrap.parse import parse_json

logger = logging.getLogger(__name__)

# issue type → 英文修复意图（不含剧情原文，降低安全过滤误杀）
_ISSUE_TYPE_HINTS: dict[str, str] = {
    "faction_mismatch": "align faction labels with protagonist family naming in records",
    "realm_mismatch": "adjust character realm field to match outline power curve",
    "character_status_conflict": "remove dead/missing character from chapter plan references",
    "skill_realm_conflict": "defer skill mastery or raise character realm rank",
    "volume_order_gap": "fix volume sort_order continuity (may need manual outline edit)",
    "villain_alignment": "raise antagonist realm to match planned arc scale",
    "storyline_gap": "add missing storyline beat in volume summary (often manual)",
    "item_timeline_conflict": "align item first-appearance chapter with outline",
}

_BLOCKED_MARKERS = ("blocked", "safety", "permissiondenied")


class EntityCodebook:
    """实体名 ↔ 中性代号双向表。"""

    def __init__(
        self,
        characters: list[Character],
        factions: list[Faction],
        skills: list[Skill],
    ) -> None:
        self.char_by_code: dict[str, Character] = {}
        self.char_code_by_name: dict[str, str] = {}
        for i, c in enumerate(characters):
            code = f"C{i}"
            self.char_by_code[code] = c
            if c.name:
                self.char_code_by_name[c.name] = code

        self.faction_by_code: dict[str, Faction] = {}
        self.faction_code_by_name: dict[str, str] = {}
        for i, f in enumerate(factions):
            code = f"F{i}"
            self.faction_by_code[code] = f
            if f.name:
                self.faction_code_by_name[f.name] = code

        self.skill_by_code: dict[str, Skill] = {}
        self.skill_code_by_name: dict[str, str] = {}
        for i, s in enumerate(skills):
            code = f"S{i}"
            self.skill_by_code[code] = s
            if s.name:
                self.skill_code_by_name[s.name] = code

    def char_lines(self) -> list[str]:
        return [
            f"{code}: faction={c.faction or ''}, current_realm={c.current_realm or ''}"
            for code, c in self.char_by_code.items()
        ]

    def faction_lines(self) -> list[str]:
        return [f"{code}: name={f.name or ''}" for code, f in self.faction_by_code.items()]

    def skill_lines(self) -> list[str]:
        return [
            f"{code}: mastered_by={getattr(s, 'mastered_by', '') or ''}"
            for code, s in self.skill_by_code.items()
        ]

    def resolve_entity_name(self, entity_type: str, raw_name: str) -> str | None:
        """将 patch 中的 entity_name（代号或真名）解析为数据库真名。"""
        name = (raw_name or "").strip()
        if not name:
            return None
        if entity_type == "character":
            if name in self.char_by_code:
                return self.char_by_code[name].name
            return name if name in self.char_code_by_name else None
        if entity_type == "faction":
            if name in self.faction_by_code:
                return self.faction_by_code[name].name
            return name if name in self.faction_code_by_name else None
        if entity_type == "skill":
            if name in self.skill_by_code:
                return self.skill_by_code[name].name
            return name if name in self.skill_code_by_name else None
        return None


def _is_blocked_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _BLOCKED_MARKERS)


def _issue_hint(issue: dict) -> str:
    t = str(issue.get("type") or "unknown")
    return _ISSUE_TYPE_HINTS.get(t, "resolve structured data inconsistency")


def build_fix_prompt(
    selected_pairs: list[tuple[int, dict]],
    codebook: EntityCodebook,
    user_prompt: str = "",
) -> tuple[str, str]:
    """构建脱敏后的 system + user prompt（英文）。"""
    issues_block = "\n".join(
        f"[seq={seq}] severity={iss.get('severity', '')} type={iss.get('type', '')} "
        f"fix_hint={_issue_hint(iss)}"
        for seq, (_, iss) in enumerate(selected_pairs)
    )
    user_note = ""
    if user_prompt.strip():
        user_note = f"\nAuthor note (apply if compatible): {user_prompt.strip()[:200]}"

    system = (
        "You are a JSON-only structured database patch generator. "
        "Fiction project records use opaque entity codes (C*=character, F*=faction, S*=skill). "
        "Output a JSON array of patch objects. No markdown, no explanation."
    )
    prompt = f"""Task: produce field-level patches for the selected consistency issues.

Selected issues (issue_seq indexes the list below):
{issues_block}{user_note}

Character records (code: faction, current_realm):
{chr(10).join(codebook.char_lines()) or '(none)'}

Faction records (code: name):
{chr(10).join(codebook.faction_lines()) or '(none)'}

Skill records (code: mastered_by):
{chr(10).join(codebook.skill_lines()) or '(none)'}

Return JSON array only:
[
  {{
    "issue_seq": 0,
    "entity_type": "character|faction|skill",
    "entity_name": "C0 or F1 or S2 (must match codes above)",
    "field": "current_realm|faction|name|description|mastered_by",
    "new_value": "...",
    "reason": "short reason under 20 chars"
  }}
]

Rules:
- entity_name MUST be an existing code from the lists above
- field whitelist: character → current_realm,faction; faction → name,description; skill → mastered_by
- Skip issues that cannot be fixed via these fields
- Do not invent new codes"""
    return system, prompt


def _rule_realm_patches(
    selected_pairs: list[tuple[int, dict]],
    characters: list[Character],
) -> list[dict]:
    """从 suggestion 解析目标境界，对 description 中出现的人物更新 current_realm。"""
    realm_patterns = (
        re.compile(
            r"(?:提升至|调整为|改为)\s*[\u201c\u300c\"']?"
            r"([^」\u201d\u300d\"'\s（(]{2,10})"
        ),
        re.compile(r"境界至\s*([^，。\s（(]{2,10})"),
        re.compile(r"(?:境界)?设为\s*([\u4e00-\u9fff]{2,10})"),
        re.compile(r"标注为\s*([\u4e00-\u9fff]{2,10})"),
        re.compile(
            r"统一标注为\s*([\u4e00-\u9fff]{2,10})"
        ),
    )
    patches: list[dict] = []
    for seq, (real_idx, iss) in enumerate(selected_pairs):
        if iss.get("type") not in ("realm_mismatch", "villain_alignment"):
            continue
        suggestion = str(iss.get("suggestion") or "")
        m = None
        for realm_re in realm_patterns:
            m = realm_re.search(suggestion)
            if m:
                break
        if not m:
            continue
        target_realm = m.group(1).strip()
        desc = str(iss.get("description") or "")
        matched_any = False
        for c in characters:
            if not c.name or c.name not in desc:
                continue
            matched_any = True
            patches.append({
                "issue_seq": seq,
                "entity_type": "character",
                "entity_name": c.name,
                "field": "current_realm",
                "new_value": target_realm,
                "reason": "rule:realm_update",
                "_real_idx": real_idx,
            })
        if not matched_any:
            continue
    return patches


def _rule_faction_rename_patches(
    selected_pairs: list[tuple[int, dict]],
    factions: list[Faction],
) -> list[dict]:
    """从 suggestion 中解析「A 更正为 B」类势力更名，无需调用模型。"""
    patches: list[dict] = []
    rename_patterns = (
        re.compile(
            r"「([^」]{1,12})」[^「]*(?:统一)?(?:更正|改为|修改为|替换为)[^「]*「([^」]{1,20})」"
        ),
        re.compile(
            r"[\u201c\"]([^\u201d\"]{1,12})[\u201d\"]"
            r"[^\u201c\u201d\"]*(?:统一)?(?:更正|改为|修改为|替换为)"
            r"[^\u201c\u201d\"]*[\u201c\"]([^\u201d\"]{1,20})[\u201d\"]"
        ),
    )
    for seq, (real_idx, iss) in enumerate(selected_pairs):
        if iss.get("type") != "faction_mismatch":
            continue
        suggestion = str(iss.get("suggestion") or "")
        m = None
        for rename_re in rename_patterns:
            m = rename_re.search(suggestion)
            if m:
                break
        if not m:
            continue
        old_frag, new_frag = m.group(1), m.group(2)
        for f in factions:
            if not f.name or old_frag not in f.name:
                continue
            new_name = f.name.replace(old_frag, new_frag, 1)
            if new_name == f.name:
                continue
            patches.append({
                "issue_seq": seq,
                "entity_type": "faction",
                "entity_name": f.name,
                "field": "name",
                "new_value": new_name,
                "reason": "rule:faction_rename",
                "_real_idx": real_idx,
            })
            break
    return patches


async def _call_ai_patches(
    ai_svc: AIService,
    system: str,
    prompt: str,
) -> list[dict]:
    raw = await ai_svc._call_ai(system, prompt, max_tokens=2048, task="quality.check")
    parsed = parse_json(raw)
    return parsed if isinstance(parsed, list) else []


async def _ai_patches_with_fallback(
    ai_svc: AIService,
    pairs: list[tuple[int, dict]],
    characters: list[Character],
    factions: list[Faction],
    skills: list[Skill],
    user_prompt: str,
) -> list[dict]:
    """对给定 issue 子集调用 AI；批量 block 时降为单条重试。"""
    if not pairs:
        return []

    codebook = EntityCodebook(characters, factions, skills)
    system, prompt = build_fix_prompt(pairs, codebook, user_prompt)

    try:
        return await _call_ai_patches(ai_svc, system, prompt)
    except Exception as exc:
        if not _is_blocked_error(exc) or len(pairs) <= 1:
            raise
        logger.warning(
            "consistency_fix 批量请求被安全过滤，降为单条重试（共 %d 条）",
            len(pairs),
        )

    merged: list[dict] = []
    for pair in pairs:
        single_book = EntityCodebook(characters, factions, skills)
        s_sys, s_prompt = build_fix_prompt([pair], single_book, user_prompt)
        try:
            merged.extend(await _call_ai_patches(ai_svc, s_sys, s_prompt))
        except Exception as single_exc:
            if _is_blocked_error(single_exc):
                logger.warning("consistency_fix 单条仍被过滤 issue_idx=%s", pair[0])
                continue
            raise
    if not merged:
        raise RuntimeError("blocked")
    return merged


async def generate_fix_patches(
    ai_svc: AIService,
    selected_pairs: list[tuple[int, dict]],
    characters: list[Character],
    factions: list[Faction],
    skills: list[Skill],
    user_prompt: str = "",
) -> list[dict]:
    """生成修复 patch 列表：规则补丁 + AI（未覆盖条目）；block 时降为单条重试。"""
    rule_patches = (
        _rule_faction_rename_patches(selected_pairs, factions)
        + _rule_realm_patches(selected_pairs, characters)
    )
    covered_seq: set[int] = {
        p["issue_seq"] for p in rule_patches if isinstance(p.get("issue_seq"), int)
    }
    ai_pairs = [
        pair for seq, pair in enumerate(selected_pairs) if seq not in covered_seq
    ]

    ai_patches: list[dict] = []
    if ai_pairs:
        try:
            ai_patches = await _ai_patches_with_fallback(
                ai_svc, ai_pairs, characters, factions, skills, user_prompt
            )
        except Exception as exc:
            if rule_patches:
                logger.warning("consistency_fix AI 失败但已有规则补丁: %s", exc)
            else:
                raise

    if not rule_patches and not ai_patches:
        raise RuntimeError("blocked")

    if rule_patches:
        logger.info(
            "consistency_fix 规则补丁 %d 条，AI 补丁 %d 条",
            len(rule_patches),
            len(ai_patches),
        )
    return rule_patches + ai_patches
