"""角色生命周期事件时间轴（确定性抽取，linter 的"单一事实源"）。

设计动机
--------
番茄/修仙大纲常出现"低级逻辑硬伤"——人物第 32 章被格杀、第 55 章再次被
"彻底轰碎"、第 58 章又活着当大将。根因是章纲懒展开按卷生成，缺少一张跨卷的
"谁在第几章死/活/翻阵营"的结构化事实表；质检只能事后读叙述找矛盾。

本模块从**已落库章纲文本**里确定性地抽取角色的死亡 / 复活 / 阵营翻转事件，
按全书章号排成时间轴，供 ``rules_lifecycle`` 做跨卷硬校验。它**不调用 LLM**、
核心抽取函数**不依赖 DB**（接收纯数据，便于单测）。

施害者 / 受害者区分
------------------
"苏云斩杀陆长歌"中，苏云是施害者、陆长歌才是死亡受害者。朴素的"名字 + 死亡词
共现"会把施害者也误判为死者。本模块用**有向匹配**只在三种语法位置认定受害者：
1. 被动："N 被/遭 …… <死亡词>"（如"陆大虎被彻底轰碎"）
2. 自动词死亡："N …… <自动词死亡>"（如"陆长歌身亡"、"陆大虎陨落"）
3. 及物宾语："<及物杀戮词>…… N"（N 紧跟在动词之后，如"斩杀陆长歌"）

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ── 词典（动词 / 状态词）────────────────────────────────────────────────────

# 自动词死亡：名字作主语自己死，无需宾语
_INTRANS_DEATH = (
    "陨落|身亡|身死道消|身死|死亡|殒命|丧命|命丧|气绝|毙命|横死|暴毙|惨死|战死"
    "|魂飞魄散|魂飞湮灭|形神俱灭|香消玉殒|命殒|授首|死于"
)
# 及物杀戮：动词后接受害者宾语
_TRANS_KILL = (
    "斩杀|击杀|格杀|杀死|杀掉|灭杀|诛杀|斩落|斩于|枭首|轰碎|轰杀|轰成|碾杀|碾碎"
    "|绞杀|射杀|刺杀|抹杀|炼化|吞噬|打死|打爆|镇杀|屠"
)
# 被动死亡（被/遭 之后可接的所有致死词，含及物与"重创致死"类）
_PASSIVE_DEATH = _TRANS_KILL + "|" + _INTRANS_DEATH + "|彻底轰碎|轰成齑粉|斩成两段|当场击毙"

# 复活 / 未死（仅显式"起死回生"类词；"归来/再次出现"过于泛化，故剔除——
# 死者再次现身改由 LIFE-01 重复死亡 / LIFE-02 死后出场捕获，避免误判为合法复活）
_REVIVE = (
    "复活|重生|转世|复苏|苏醒|借尸还魂|死而复生|起死回生|诈死|假死|未死|并未真死"
    "|重塑肉身|夺舍|死而不僵"
)

# 阵营 → 倒向主角 / 我方
_ALIGN_ALLY = (
    "反水|倒戈|反正|投靠|归顺|投诚|投奔|归附|弃暗投明|阵前倒戈|临阵反水"
    "|舍命相救|出手相救|拼死护"
)
# 阵营 → 再度敌对 / 翻脸（用于判断盟友是否经过"再叛"过渡）
_ALIGN_ENEMY = (
    "叛变|背叛|反目|反咬|倒打一耙|倒戈相向|再度为敌|重新与.{0,6}?为敌"
    "|与.{0,6}?反目|恩断义绝|彻底决裂|反水投敌"
)

_SENT_STOP = "，。；！？\n、：…—"  # 句内窗口边界（避免跨句误配）


def _seg(window: int) -> str:
    return f"[^{re.escape(_SENT_STOP)}]{{0,{window}}}?"


# 预编译模板需按名字动态拼接，故此处只存动词组字符串，匹配时构造正则。
EVENT_DEATH = "death"
EVENT_REVIVE = "revive"
EVENT_ALLY = "align_ally"
EVENT_ENEMY = "align_enemy"


@dataclass(frozen=True)
class CharacterRef:
    """角色引用（用于在文本中识别该角色的别名）。"""

    id: str
    name: str
    aliases: tuple[str, ...] = ()

    def all_names(self) -> list[str]:
        names = [self.name, *self.aliases]
        # 去空、去重、长名优先（避免"陆大"先于"陆大虎"命中导致截断）
        seen: set[str] = set()
        out: list[str] = []
        for n in sorted((x.strip() for x in names if x and x.strip()), key=len, reverse=True):
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out


@dataclass
class LifecycleEvent:
    """一条角色生命周期事件。"""

    char_id: str
    char_name: str
    global_chapter: int
    event_type: str  # death | revive | align_ally | align_enemy
    evidence: str
    node_id: str | None = None
    volume_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "char_id": self.char_id,
            "char_name": self.char_name,
            "global_chapter": self.global_chapter,
            "event_type": self.event_type,
            "evidence": self.evidence,
            "node_id": self.node_id,
            "volume_index": self.volume_index,
        }


@dataclass
class ChapterTextRow:
    """供抽取器消费的章纲文本行（DB 无关，便于单测）。

    ``declared_deaths`` / ``declared_revives`` 为章纲结构化「生死声明」字段（角色名），
    由作者/AI 显式填写。它们是**精确主信号**（无施害者/受害者歧义），与正文正则抽取
    取**并集**——声明覆盖"明说了的"，正则兜底"写进正文却漏声明的"。
    """

    global_chapter: int
    text: str
    node_id: str | None = None
    volume_index: int | None = None
    involved_character_ids: list[str] = field(default_factory=list)
    declared_deaths: list[str] = field(default_factory=list)
    declared_revives: list[str] = field(default_factory=list)


def _evidence(text: str, start: int, end: int, pad: int = 8) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].strip()


_HARD_STOP = "。；！？\n"  # 句子终结边界：受害者归属不得跨越（主语会换）
_BACK_MAX = 12            # 被动死亡向前找受害者的最大字距
# 及物杀戮：动词与受害者名之间仅允许轻量助词（「斩杀陆长歌」），禁止跨名词（「轰碎界碑，陆沉」）
_TRANS_OBJECT_GAP = re.compile(r"^[了吗掉将于并]?$")


def _inside_square_brackets(text: str, pos: int) -> bool:
    """pos 是否落在未闭合的 ``[...]`` 技能标签内（章纲 ``因[技能]→[结果]`` 格式）。"""
    depth = 0
    for ch in text[:pos]:
        if ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
    return depth > 0


def _is_negated_passive(text: str, bei_start: int) -> bool:
    """「没被/未遭/并非被」等否定被动，不算死亡。"""
    if bei_start <= 0:
        return False
    if text[bei_start - 1] in "没未":
        return True
    if bei_start >= 2 and text[bei_start - 2 : bei_start] in ("并未", "不曾", "未曾", "并非"):
        return True
    return False


def _name_occurrences(
    text: str, refs: list[CharacterRef]
) -> list[tuple[int, int, str]]:
    """文本中所有受跟踪角色名出现位置：[(start, end, char_id)]。"""
    occ: list[tuple[int, int, str]] = []
    for ref in refs:
        for nm in ref.all_names():
            for m in re.finditer(re.escape(nm), text):
                occ.append((m.start(), m.end(), ref.id))
    return occ


def _detect_deaths(text: str, refs: list[CharacterRef]) -> dict[str, str]:
    """检出死亡受害者：char_id → 证据片段。

    采用"锚点 + 就近归属"，正确区分施害者与受害者：
    - 被动："被/遭 …… 致死词"，受害者 = 该"被"字前最近的角色名（允许跨逗号、
      但不得跨句号/分号，也不得越过另一个角色名）。
    - 自动词死亡："N …… 自动词死亡"（同小句，名字作主语）。
    - 及物："杀戮词 …… N"（N 紧跟动词作宾语）。
    """
    occ = _name_occurrences(text, refs)
    deaths: dict[str, str] = {}

    def _add(cid: str, s: int, e: int) -> None:
        deaths.setdefault(cid, _evidence(text, s, e))

    soft_seg = r"[^" + re.escape(_HARD_STOP) + r"]{0,8}?"

    # 被动：锚定"被/遭…死亡词"，向前就近找受害者
    for m in re.finditer(r"(?:被|遭)" + soft_seg + f"(?:{_PASSIVE_DEATH})", text):
        bei = m.start()
        if _is_negated_passive(text, bei):
            continue
        best: tuple[int, str, int] | None = None  # (name_end, cid, name_start)
        for s, e, cid in occ:
            if e > bei or bei - e > _BACK_MAX:
                continue
            gap = text[e:bei]
            if any(c in gap for c in _HARD_STOP):
                continue
            if best is None or e > best[0]:
                best = (e, cid, s)
        if best:
            _add(best[1], best[2], m.end())

    # 自动词死亡：名字作主语，同小句（不跨任何停顿）
    intrans_re = re.compile(r"[^" + re.escape(_HARD_STOP + "，、：") + r"]{0,6}?(?:" + _INTRANS_DEATH + r")")
    for s, e, cid in occ:
        mm = intrans_re.match(text, e)
        if mm:
            _add(cid, s, mm.end())

    # 及物宾语：杀戮词后紧跟受害者宾语（排除方括号技能名、→ 结果段、主语在前结构）
    for m in re.finditer(r"(?:" + _TRANS_KILL + r")", text):
        if _inside_square_brackets(text, m.start()):
            continue
        vend = m.end()
        for s, e, cid in occ:
            if s < vend:
                continue
            gap = text[vend:s]
            if s - vend > 2 or not _TRANS_OBJECT_GAP.fullmatch(gap):
                continue
            if any(c in gap for c in _HARD_STOP + "，、→]"):
                continue
            _add(cid, m.start(), e)
            break

    return deaths


def _classify_nondeath_for_name(text: str, name: str) -> list[tuple[str, str]]:
    """单角色名的非死亡事件（复活 / 阵营翻转），每类至多一条。"""
    esc = re.escape(name)
    found: dict[str, str] = {}

    def _try(event_type: str, pattern: str) -> None:
        if event_type in found:
            return
        m = re.search(pattern, text)
        if m:
            found[event_type] = _evidence(text, m.start(), m.end())

    # 复活 / 重现（双向窗口）
    _try(EVENT_REVIVE, esc + _seg(8) + f"(?:{_REVIVE})")
    _try(EVENT_REVIVE, f"(?:{_REVIVE})" + _seg(6) + esc)

    # 阵营→我方：仅"名字在前作主语"方向（"陆大虎反水"），
    # 避免把被救/被投靠的对象（"反水救苏云"里的苏云）误判为反水者。
    _try(EVENT_ALLY, esc + _seg(8) + f"(?:{_ALIGN_ALLY})")

    # 阵营→再叛 / 翻脸：同样仅主语方向。
    _try(EVENT_ENEMY, esc + _seg(8) + f"(?:{_ALIGN_ENEMY})")

    return list(found.items())


def extract_events_from_text(
    text: str,
    characters: Iterable[CharacterRef],
) -> list[tuple[str, str, str, str]]:
    """从一段文本抽取事件：返回 [(char_id, char_name, event_type, evidence)]。"""
    out: list[tuple[str, str, str, str]] = []
    if not text:
        return out
    refs = list(characters)
    name_by_id = {r.id: r.name for r in refs}

    # 死亡：锚点 + 就近归属（跨小句、区分施害者/受害者）
    for cid, evidence in _detect_deaths(text, refs).items():
        out.append((cid, name_by_id.get(cid, cid), EVENT_DEATH, evidence))

    # 非死亡事件：逐角色逐别名分类后按 (char, type) 去重
    for ch in refs:
        per_char: dict[str, str] = {}
        for nm in ch.all_names():
            if nm not in text:
                continue
            for etype, evidence in _classify_nondeath_for_name(text, nm):
                per_char.setdefault(etype, evidence)
        for etype, evidence in per_char.items():
            out.append((ch.id, ch.name, etype, evidence))
    return out


def _resolve_declared(
    names: list[str] | None,
    refs: list[CharacterRef],
    event_type: str,
) -> list[tuple[str, str, str, str]]:
    """生死声明名单 → [(char_id, char_name, event_type, evidence)]（按角色名/别名匹配）。"""
    if not names:
        return []
    by_name: dict[str, CharacterRef] = {}
    for r in refs:
        for nm in r.all_names():
            by_name.setdefault(nm, r)
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for raw in names:
        nm = (raw or "").strip()
        if not nm:
            continue
        ref = by_name.get(nm)
        if ref is None:  # 宽松包含匹配（声明名含已知名或反之）
            for cand_nm, cand_ref in by_name.items():
                if cand_nm in nm or nm in cand_nm:
                    ref = cand_ref
                    break
        if ref is None or ref.id in seen:
            continue
        seen.add(ref.id)
        out.append((ref.id, ref.name, event_type, f"声明:{nm}"))
    return out


def resolve_declared_events(
    declared_deaths: list[str] | None,
    declared_revives: list[str] | None,
    characters: Iterable[CharacterRef],
) -> list[tuple[str, str, str, str]]:
    """把一章的结构化生死声明解析为事件元组（死亡 + 复活）。"""
    refs = list(characters)
    return (
        _resolve_declared(declared_deaths, refs, EVENT_DEATH)
        + _resolve_declared(declared_revives, refs, EVENT_REVIVE)
    )


def declared_from_extra(extra: Any) -> tuple[list[str], list[str]]:
    """从 OutlineNode.extra 读出生死声明名单 (deaths_declared, revives_declared)。"""
    e = extra if isinstance(extra, dict) else {}
    deaths = [str(x).strip() for x in (e.get("deaths_declared") or []) if str(x).strip()]
    revives = [str(x).strip() for x in (e.get("revives_declared") or []) if str(x).strip()]
    return deaths, revives


def build_timeline(
    characters: Iterable[CharacterRef],
    rows: Iterable[ChapterTextRow],
) -> dict[str, list[LifecycleEvent]]:
    """构建 char_id → 按全书章号升序的事件列表。

    每章事件 = 正文正则抽取 ∪ 结构化生死声明，按 (char_id, event_type) 去重。
    """
    chars = list(characters)
    timeline: dict[str, list[LifecycleEvent]] = {}
    for row in sorted(rows, key=lambda r: r.global_chapter):
        events = list(extract_events_from_text(row.text, chars))
        events.extend(
            resolve_declared_events(row.declared_deaths, row.declared_revives, chars)
        )
        seen_pair: set[tuple[str, str]] = set()
        for char_id, char_name, etype, evidence in events:
            if (char_id, etype) in seen_pair:
                continue
            seen_pair.add((char_id, etype))
            timeline.setdefault(char_id, []).append(
                LifecycleEvent(
                    char_id=char_id,
                    char_name=char_name,
                    global_chapter=row.global_chapter,
                    event_type=etype,
                    evidence=evidence,
                    node_id=row.node_id,
                    volume_index=row.volume_index,
                )
            )
    for events in timeline.values():
        events.sort(key=lambda e: (e.global_chapter, e.event_type))
    return timeline


# ── DB 适配层（把 OutlineNode / Character 转成纯数据行）──────────────────────

# 章纲里参与事件判定的文本字段（结构化 extra + 列）
_EXTRA_TEXT_KEYS = (
    "choice_cost",
    "villain_action",
    "end_hook",
    "protagonist_choice",
    "core_event",
    "character_change",
    "satisfaction_payoff",
    "supporting_spotlight",
)


def node_event_text(node) -> str:
    """拼接一个 chapter_plan 节点里参与生命周期判定的全部文本。"""
    extra = node.extra if isinstance(getattr(node, "extra", None), dict) else {}
    parts = [
        node.title or "",
        node.summary or "",
        node.conflict or "",
        node.highlight or "",
        node.power_milestone or "",
    ]
    for key in _EXTRA_TEXT_KEYS:
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    return " ".join(p for p in parts if p)


def load_character_refs(db, project_id) -> list[CharacterRef]:
    """从 Character 表构建角色引用（含 alias）。"""
    from app.models import Character

    refs: list[CharacterRef] = []
    for c in db.query(Character).filter(Character.project_id == project_id).all():
        aliases: list[str] = []
        raw_alias = getattr(c, "alias", None)
        if isinstance(raw_alias, str) and raw_alias.strip():
            # alias 可能是"号A、号B"或"号A/号B"形式
            aliases = [a.strip() for a in re.split(r"[、，,/|；;]", raw_alias) if a.strip()]
        name = (c.name or "").strip()
        if not name:
            continue
        # 过滤过短/泛化名（≥2 字才参与，避免单字误配）
        names = [name, *aliases]
        names = [n for n in names if len(n) >= 2]
        if not names:
            continue
        refs.append(CharacterRef(id=str(c.id), name=name, aliases=tuple(names[1:])))
    return refs


def load_chapter_rows(db, project_id) -> list[ChapterTextRow]:
    """从全书 chapter_plan 构建文本行（带全书章号、卷号）。"""
    from app.models import OutlineNode
    from app.services.outline_linter.chapter_index import build_global_chapter_index

    node_to_global, _ = build_global_chapter_index(db, project_id)

    # 卷号映射：parent_id -> volume.sort_order
    vol_sort: dict[str, int] = {
        str(v.id): int(v.sort_order or 0)
        for v in db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id, OutlineNode.node_type == "volume")
        .all()
    }

    rows: list[ChapterTextRow] = []
    plans = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )
    for node in plans:
        g = node_to_global.get(str(node.id))
        if g is None:
            continue
        decl_deaths, decl_revives = declared_from_extra(getattr(node, "extra", None))
        rows.append(
            ChapterTextRow(
                global_chapter=g,
                text=node_event_text(node),
                node_id=str(node.id),
                volume_index=vol_sort.get(str(node.parent_id)),
                involved_character_ids=[str(x) for x in (node.involved_character_ids or [])],
                declared_deaths=decl_deaths,
                declared_revives=decl_revives,
            )
        )
    return rows


def build_project_timeline(db, project_id) -> tuple[
    dict[str, list[LifecycleEvent]], list[ChapterTextRow], dict[str, CharacterRef]
]:
    """工程入口：返回 (时间轴, 章纲文本行, char_id→CharacterRef)。"""
    refs = load_character_refs(db, project_id)
    rows = load_chapter_rows(db, project_id)
    timeline = build_timeline(refs, rows)
    ref_map = {r.id: r for r in refs}
    return timeline, rows, ref_map
