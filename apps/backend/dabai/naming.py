"""大白文人物正名约束与占位名检测。

Bootstrap 阵营卡司、章纲 witnesses/involved_characters 共用，避免
「执法堂甲」「天剑宗弟子A」「外门弟子众」类描述性占位进入档案。
"""

from __future__ import annotations

import re

# 组织/场景词 + 甲乙丙丁 → 群演序号占位（执法堂甲、刑堂乙）
_ORG_SUFFIX_RE = re.compile(
    r"^[一-龥]{2,12}(?:执法堂|刑堂|外门|内门|长老院|执事堂|"
    r"堂|殿|阁|院|府|峰|谷|寨|帮|族|家|楼|营|队|卫|宗|门|派)"
    r"[甲乙丙丁戊己]$"
)
# 势力前缀 + 弟子 + 字母/甲乙（天剑宗弟子A）
_SECT_DISCIPLE_RE = re.compile(
    r"^[一-龥]{2,12}弟子[ABCDEFGHIJKLMN甲乙丙丁]$", re.IGNORECASE
)
# 纯序号占位
_LETTER_SUFFIX_RE = re.compile(r"^[一-龥]+[ABCDEFGHIJKLMN]$", re.IGNORECASE)
_AB_SUFFIX_ONLY_RE = re.compile(r"^[甲乙丙丁戊己庚辛]$")

_FORBIDDEN_EXACT = frozenset({
    "路人", "路人甲", "路人乙", "路人丙", "路人丁",
    "群众", "众人", "围观群众", "围观众人", "外门弟子", "内门弟子",
    "执法弟子", "执法堂弟子", "弟子甲", "弟子乙", "弟子A", "弟子B",
    "某长老", "某弟子", "某管事", "某执事", "某掌柜", "某师姐", "某师兄",
    "未命名", "无名氏", "主角", "反派", "女主", "BOSS", "Boss",
})

_ORG_HINTS = (
    "执法", "刑堂", "外门", "内门", "长老", "执事", "宗", "门", "派",
    "堂", "殿", "阁", "院", "府", "峰", "谷", "寨", "帮", "族", "家",
    "楼", "营", "队", "卫", "天剑", "玄阳", "青云", "紫霄",
)


def _base_name(name: str) -> str:
    """去掉括号备注，取用于校验的主名。"""
    return re.sub(r"[（(][^）)]*[）)]", "", (name or "").strip()).strip()


def is_placeholder_character_name(name: str) -> str | None:
    """检测占位/描述性人名；合法则返回 None。"""
    base = _base_name(name)
    if not base:
        return "姓名为空"
    if base in _FORBIDDEN_EXACT:
        return f"禁止占位名「{base}」"
    if _AB_SUFFIX_ONLY_RE.match(base):
        return "单字序号不宜作姓名"
    if base.startswith(("路人", "某长", "某弟", "某管", "某执", "某掌")):
        return "「某/路人」类占位称呼"
    if base.endswith("众") and len(base) >= 3:
        return "群体名（XX众）不能当作具体人物"
    if base.endswith("等人"):
        return "群体名（XX等人）不能当作具体人物"
    if re.search(r"(的爪牙|的狗腿子|跟班|手下|护卫|家丁|家奴)$", base):
        return "描述性附属称呼不能当作正名"
    if _SECT_DISCIPLE_RE.match(base):
        return "「宗门+弟子+序号」类占位"
    if _ORG_SUFFIX_RE.match(base):
        return "「组织+甲乙」类占位"
    if _LETTER_SUFFIX_RE.match(base) and any(h in base for h in _ORG_HINTS):
        return "组织名+字母序号占位"
    # 执法堂甲、天剑宗甲 — 末字甲乙且前缀含组织词
    if base[-1] in "甲乙丙丁戊己" and len(base) >= 3:
        prefix = base[:-1]
        if any(h in prefix for h in _ORG_HINTS):
            return "组织/身份+序号占位"
    if re.search(r"弟子[ABCDEFGHIJKLMN]$", base, re.IGNORECASE):
        return "弟子+字母序号占位"
    if re.search(r"弟子[甲乙丙丁]$", base):
        return "弟子+甲乙序号占位"
    return None


def known_character_names(ctx: dict) -> list[str]:
    """从 ctx 提取已建档人物正名列表。"""
    names: list[str] = []
    for c in ctx.get("characters") or []:
        if isinstance(c, dict):
            n = _base_name(str(c.get("name") or ""))
            if n:
                names.append(n)
    ladder = ctx.get("antagonist_ladder") or []
    for row in ladder:
        if isinstance(row, dict):
            n = _base_name(str(row.get("boss_name") or ""))
            if n and not is_placeholder_character_name(n):
                names.append(n)
    return list(dict.fromkeys(names))


def character_naming_prompt_block(
    ctx: dict | None = None,
    *,
    for_chapter: bool = False,
) -> str:
    """注入 LLM 的人物正名硬约束块。"""
    known = known_character_names(ctx or {})
    known_line = ""
    if known:
        sample = "、".join(known[:24])
        if len(known) > 24:
            sample += f" 等共{len(known)}人"
        if for_chapter:
            known_line = (
                f"\n- 已建档人物（witnesses/involved_characters 只能从此列表选人，"
                f"禁止发明新名）：{sample}"
            )
        else:
            known_line = f"\n- 已有人名（禁止重名、禁止仅改一字）：{sample}"

    chapter_extra = ""
    if for_chapter:
        chapter_extra = (
            "\n- witnesses / involved_characters / beat_sequence 的 slap_target "
            "必须是上方已建档的具体人名，禁止用「XX众」「执法堂甲乙」充数"
        )

    return f"""【人物正名规范（硬性，违反即无效）】
- name 必须是姓+名的具体人名，2~4 个汉字（复姓 4 字），如「沈烬」「顾远山」「慕容辞衡」
- 禁止把身份/组织/序号当作姓名：✗ 执法堂甲/乙、✗ 天剑宗弟子A、✗ 外门弟子众、✗ 路人甲、✗ 某长老
- 身份标签写在 role/persona/function，不要塞进 name；执法弟子也要起名（如「钟厉」「方平」）
- 工具人配角池 8-12 人：每人必须有独立正名+一句身份（管事/师兄/执法弟子…），禁止用甲乙丙丁或 A/B/C 编号
- 同批次姓氏重复不超过 2 人；「名」不得重复；核心角色辨识度要高{known_line}{chapter_extra}"""


def lint_names_in_chapter(ch: dict, known: set[str], add_issue) -> None:
    """章纲内 witnesses / involved_characters 占位名与越权新名检查。"""
    from dabai.linter import Issue

    num = ch.get("chapter_number")
    fields = (
        ("witnesses", ch.get("witnesses") or []),
        ("involved_characters", ch.get("involved_characters") or []),
    )
    for field, values in fields:
        if not isinstance(values, list):
            continue
        for raw in values:
            name = _base_name(str(raw))
            if not name:
                continue
            reason = is_placeholder_character_name(name)
            if reason:
                add_issue(Issue(
                    "DB-14", "high", num,
                    f"{field} 含占位人名「{name}」——{reason}",
                    "改为人物档案里已有的具体正名，或为该角色补建档",
                ))
                continue
            if known and name not in known:
                add_issue(Issue(
                    "DB-15", "medium", num,
                    f"{field} 出现未建档人名「{name}」",
                    "优先复用人物档案中的名字；确需新配角须先在 Bootstrap 建档",
                ))


def lint_character_roster(characters: list[dict]) -> list[tuple[str, str]]:
    """Bootstrap 人物列表占位名检查；返回 [(name, reason), ...]。"""
    bad: list[tuple[str, str]] = []
    for c in characters or []:
        if not isinstance(c, dict):
            continue
        name = _base_name(str(c.get("name") or ""))
        reason = is_placeholder_character_name(name)
        if reason:
            bad.append((name or "（空）", reason))
    return bad
