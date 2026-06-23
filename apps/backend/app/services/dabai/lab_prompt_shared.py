"""dabai 实验书架 prompt 共享块 — 境界体系 / 人物称谓锁定 / 导演单后处理。"""
from __future__ import annotations

import re

from app.models.dabai import DabaiChapterOutline, DabaiProject

# 常见外来修仙体系用语（本书 power_ladder 未收录时才视为禁用）
_FOREIGN_REALM_TERMS = (
    "练气", "练体", "淬体", "后天", "先天", "开光", "心动", "元婴", "化神",
)

# 限知视角硬约束（读者反馈：正文常有上帝视角旁白/分析，新事物主角却不懵）。
# 由 dabai_write 正文 prompt 注入 system，lab_qc_prompt 据此同向验收，避免「写—检—改」拉锯。
POV_LIMITED_RULES = (
    "\n★叙事视角硬约束（限知第三人称，全程贴住主角）★：\n"
    "- 只写主角此刻能看到、听到、感觉到、合理推断到的；禁止上帝视角旁白——"
    "不写主角不可能知道的他人内心活动、幕后真相、未来结果、设定的来历与全貌；\n"
    "- 禁止作者下场分析点评（如『其实这是…』『殊不知…』『所有人都没料到…』"
    "『这正是…的奥妙』式句子）；信息只能借主角的观察、疑问、试探，"
    "或他人的台词/动作自然带出；\n"
    "- 出现主角尚不了解的新事物（新道具/法宝/金手指/能力/境界/规则/陌生人）时，"
    "主角第一反应必须是懵/疑/不解：先写他的困惑、追问或试探，再由懂行的人开口解释、"
    "或主角自己摸索验证后才逐步弄懂；★严禁主角或旁白一上来就准确报出其名称、来历、"
    "用法、数值★；\n"
    "- ★全员信息可得性★：不止主角——任何配角/反派/路人也只能基于他「合理能知道」的信息"
    "行动与开口。禁止反派无来由地知道主角的金手指/底牌/秘密身份并据此针对，"
    "禁止配角凭空知道未公开的真相或主角的隐藏实力。某角色要表现出「知情」，"
    "必须先在正文交代他从何得知（亲眼见、听人说、查到、套话、本就在场）。\n"
)

_BRIDGE_GOAL_MARKERS = ("位移", "过渡", "承接", "转场", "赶路", "回途")

_CONTINUITY_STOP = frozenset({
    "什么", "已经", "一个", "这种", "那里", "此时", "感觉", "体内", "自己",
    "不是", "可以", "没有", "就是", "这一", "那一", "只见", "突然",
})

# 勿含「看向/目光」等日常描写词——会误判内省镜头为「下一瞬间续写」而吞掉位移场。
_IMMEDIATE_CONTINUATION_MARKERS = (
    "踏出", "走出", "刚踏", "刚走", "迎向", "封住", "对峙",
    "尚未", "还没", "正待", "刹那", "瞬间", "下一刻", "紧接着",
)

_EN_ROUTE_VERBS = (
    "走去", "赶往", "奔赴", "疾驰", "飞奔", "踏上", "步入", "闯入",
    "朝", "向", "赶往", "直奔",
)


def location_key(location: str) -> str:
    """取场景载体主地点前缀用于粗比对（与 DLB-03 质检一致）。"""
    text = (location or "").strip()
    if not text:
        return ""
    return text.split("·")[0][:6]


def has_location_gap(prev_loc: str, curr_loc: str) -> bool:
    """上章与本章纲 location 是否跨场景（需开篇位移交代）。"""
    prev = (prev_loc or "").strip()
    curr = (curr_loc or "").strip()
    if not prev or not curr:
        return False
    prev_key = location_key(prev)
    curr_key = location_key(curr)
    if not prev_key or not curr_key:
        return False
    if prev_key == curr_key or prev_key in curr or curr_key in prev:
        return False
    return True


def _prev_content_tail(prev_ch: DabaiChapterOutline, prev_tail: str = "") -> str:
    """上章正文末段（优先调用方已截好的 prev_tail）。"""
    tail = (prev_tail or "").strip()
    if tail:
        return tail[-600:]
    content = (prev_ch.content or "").strip()
    return content[-600:] if content else ""


def _continuity_tokens(text: str) -> set[str]:
    """从正文片段提取 2～4 字词块，用于衔接重叠判定。"""
    return {
        t for t in re.findall(r"[\u4e00-\u9fff]{2,4}", text or "")
        if t not in _CONTINUITY_STOP
    }


def _substring_continuity_hits(tail: str, head: str, *, min_len: int = 2) -> int:
    """上章末与开篇共享的非泛化子串数量（弥补固定窗 token 切分漏检）。"""
    tail_slice = (tail or "")[-180:]
    head_text = (head or "")[:220]
    hits: set[str] = set()
    for length in (4, 3, 2):
        for i in range(max(0, len(tail_slice) - length + 1)):
            frag = tail_slice[i:i + length]
            if frag in _CONTINUITY_STOP or frag in hits:
                continue
            if frag in head_text:
                hits.add(frag)
    return len(hits)


def opening_continues_prev_tail(
    prev_tail: str,
    opening: str,
    *,
    min_shared: int = 2,
) -> bool:
    """开篇是否紧接上章末句同一瞬间（即便章纲 location 不同）。"""
    tail = (prev_tail or "").strip()[-400:]
    head = (opening or "").strip()[:450]
    if not tail or not head:
        return False
    for m in _IMMEDIATE_CONTINUATION_MARKERS:
        if m in tail[-250:] and m in head:
            return True
    if _substring_continuity_hits(tail, head) >= min_shared:
        return True
    if prev_tail_implies_immediate_continuation(tail):
        if _substring_continuity_hits(tail[-220:], head, min_len=2) >= 1:
            return True
    shared = _continuity_tokens(tail) & _continuity_tokens(head)
    end_anchors = _continuity_tokens(tail[-150:])
    anchor_hits = shared & end_anchors
    if anchor_hits and len(shared) >= min_shared:
        return True
    return len(shared) >= min_shared + 1


def prev_tail_implies_immediate_continuation(prev_tail: str) -> bool:
    """上章末是否停在「下一瞬间续写」边界（写前勿注入章纲级位移块）。"""
    tail = (prev_tail or "").strip()[-120:]
    return any(m in tail for m in _IMMEDIATE_CONTINUATION_MARKERS)


def _destination_name_tokens(curr_loc: str) -> list[str]:
    """从章纲 location 提取可用于末段比对的地点词（主场景 + · 后事件锚点）。"""
    loc = (curr_loc or "").strip()
    if not loc:
        return []
    root, _, suffix = loc.partition("·")
    tokens: list[str] = []
    for part in (root, suffix):
        part = part.strip()
        if len(part) >= 2 and part not in tokens:
            tokens.append(part)
        for i in range(max(0, len(part) - 2)):
            frag = part[i:i + 3]
            if len(frag) >= 3 and frag not in tokens:
                tokens.append(frag)
    key = location_key(loc)
    if key and key not in tokens:
        tokens.append(key)
    return tokens


def _places_overlap(a: str, b: str, *, min_len: int = 2) -> bool:
    """粗比对两处地名是否指同一方向（容忍「青云宗演武场」vs「青云演武大场」）。"""
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    for size in range(min(len(left), len(right), 4), min_len - 1, -1):
        for i in range(len(left) - size + 1):
            if left[i:i + size] in right:
                return True
    return False


def prev_tail_en_route_to_destination(prev_tail: str, curr_loc: str) -> bool:
    """上章末是否已在向本章主场景移动（勿再插位移分场）。"""
    tail = (prev_tail or "").strip()[-280:]
    if not tail:
        return False
    curr_root = (curr_loc or "").split("·")[0].strip()
    if not curr_root:
        return False
    move_match = re.search(
        r"[朝向往到]([^，。！？\s]{2,14}?)(?:走去|赶往|飞奔|疾驰|而去|奔去)",
        tail,
    )
    if move_match:
        dest_phrase = move_match.group(1).strip()
        if _places_overlap(dest_phrase, curr_root):
            return True
    tokens = _destination_name_tokens(curr_loc)
    for token in tokens:
        if len(token) < 3 or token not in tail:
            continue
        idx = tail.rfind(token)
        window = tail[max(0, idx - 24): min(len(tail), idx + len(token) + 20)]
        if any(v in window for v in _EN_ROUTE_VERBS):
            return True
    return False


def needs_location_bridge(
    prev_ch: DabaiChapterOutline | None,
    ch: DabaiChapterOutline,
    prev_tail: str = "",
) -> bool:
    """是否需注入「章纲级」位移硬约束。

    上章已有正文时，章纲 ``location`` 可能滞后（单章内已位移到下一地点）。
    若正文末段已出现本章场景前缀，则不再要求「从章纲 location 再走一遍」。
    """
    if not prev_ch:
        return False
    prev_loc = (prev_ch.location or "").strip()
    curr_loc = (ch.location or "").strip()
    if not has_location_gap(prev_loc, curr_loc):
        return False
    tail = _prev_content_tail(prev_ch, prev_tail)
    if not tail:
        return True
    curr_key = location_key(curr_loc)
    if curr_key and curr_key in tail:
        return False
    curr_root = curr_loc.split("·")[0].strip()
    if curr_root and curr_root in tail:
        return False
    if prev_tail_en_route_to_destination(tail, curr_loc):
        return False
    if prev_tail_implies_immediate_continuation(tail):
        return False
    return True


def build_location_bridge_block(
    prev_ch: DabaiChapterOutline,
    ch: DabaiChapterOutline,
    prev_tail: str = "",
) -> str:
    """规则层位移硬约束块 — 不依赖导演单 LLM，写前/重写均注入。"""
    if not needs_location_bridge(prev_ch, ch, prev_tail):
        return ""
    prev_loc = (prev_ch.location or "").strip()
    curr_loc = (ch.location or "").strip()
    return (
        "【⚠️ 空间衔接硬约束（必须遵守，否则 DLB-03 质检不通过）】\n"
        f"- 上章场景载体：{prev_loc}\n"
        f"- 本章场景载体：{curr_loc}\n"
        f"- 开篇前 450 字必须先写从「{prev_loc}」到「{curr_loc}」的位移/转场："
        "怎么离开、经什么路径、怎么抵达（走/回/潜/踏入/折返/穿行/摸黑等），"
        "写清楚动机与过程；禁止开篇直接站在本章冲突现场而无交代。\n"
        "- 若有分场调度，scenes[0] 必须是位移承接场，冲突从 scenes[1] 开始。"
    )


def ladder_level_names(project: DabaiProject) -> list[str]:
    """本书境界名列表（按 rank 升序）。"""
    levels = (project.power_ladder or {}).get("levels") or []
    return [str(lv.get("name") or "").strip() for lv in levels if str(lv.get("name") or "").strip()]


def build_power_ladder_block(project: DabaiProject) -> str:
    """注入导演单/分场：强制 fact_lock.realm 使用本书境界名。"""
    names = ladder_level_names(project)
    if not names:
        return ""
    chain = " → ".join(names[:8])
    first = names[0]
    forbidden = [t for t in _FOREIGN_REALM_TERMS if not any(t in n for n in names)]
    forbid_str = "、".join(forbidden[:6]) if forbidden else "外来体系用语"
    return (
        f"【本书境界体系（fact_lock.realm 必须只用下列名称，禁止 {forbid_str}）】\n"
        f"  最低档（无面板时的开书默认）：{first}\n"
        f"  全书档位：{chain}\n"
        f"  ★有【系统面板】或【开笔境界基准】时，开笔/章末须与已写情节一致；"
        f"无面板时再参考「{first}」起步。★"
    )


def build_witness_lock_block(ch: DabaiChapterOutline) -> str:
    """锁定章纲见证者/出场人物称谓，禁止正文另起代名。"""
    witnesses = [str(w).strip() for w in (ch.witnesses or []) if str(w).strip()]
    involved = [str(c).strip() for c in (ch.involved_characters or []) if str(c).strip()]
    names = list(dict.fromkeys(witnesses + involved))
    if not names:
        return ""
    lines = "\n".join(f"  - {n}" for n in names[:12])
    return (
        "【人物称谓锁定（正文/导演单/分场须使用下列名字，禁止另起代称）】\n"
        f"{lines}\n"
        "  ★同一角色不得改叫其他名字（如「狗腿子甲/乙」不可改成「张三/李四」）。"
    )


_CN_LAYER = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}


def _extract_layer_suffix(text: str) -> str | None:
    """从境界字符串提取层数（阿拉伯或中文）。"""
    m = re.search(r"第?\s*(\d+)\s*层", text)
    if m:
        return m.group(1)
    m = re.search(r"([一二三四五六七八九十]+)层", text)
    if m:
        return _CN_LAYER.get(m.group(1), m.group(1))
    return None


def fix_realm_string(realm: str, project: DabaiProject) -> str:
    """导演单后处理：外来境界用语替换为本书最低档或已匹配档名。"""
    text = (realm or "").strip()
    if not text:
        return text
    names = ladder_level_names(project)
    if not names:
        return text
    forbidden = [t for t in _FOREIGN_REALM_TERMS if not any(t in n for n in names)]
    if not any(t in text for t in forbidden):
        return text
    matched = next((n for n in names if n in text), "")
    base = matched or names[0]
    layer = _extract_layer_suffix(text)
    if layer:
        return f"{base}·第{layer}层"
    return base


def sanitize_prewarn_result(
    result: dict,
    project: DabaiProject,
    *,
    prev_location: str = "",
    outline_location: str = "",
) -> dict:
    """修正导演单 JSON 中 fact_lock.realm / location 的外来体系用语与台账坐标。"""
    if not isinstance(result, dict):
        return result
    fact = dict(result.get("fact_lock") or {})
    if fact.get("realm"):
        fact["realm"] = fix_realm_string(str(fact["realm"]), project)
    if fact.get("location"):
        from app.services.dabai.lab_location_coords import normalize_ledger_location
        fact["location"] = normalize_ledger_location(
            str(fact["location"]),
            prev_location=prev_location,
            outline_location=outline_location,
        )
    if fact:
        result["fact_lock"] = fact
    return result


def is_bridge_scene(sc: dict) -> bool:
    """分场是否为位移/承接场。"""
    goal = str(sc.get("goal") or "")
    name = str(sc.get("name") or "")
    return any(m in goal or m in name for m in _BRIDGE_GOAL_MARKERS)


def merge_opening_directive(opening_line: str, opening_directive: str) -> str:
    """分场 opening_line 必须体现导演单 opening_directive。"""
    cur = (opening_line or "").strip()
    directive = (opening_directive or "").strip()
    if not directive:
        return cur
    if not cur:
        return directive
    if directive in cur or cur in directive:
        return cur if len(cur) >= len(directive) else directive
    if directive[:12] in cur or cur[:12] in directive:
        return cur if len(cur) >= len(directive) else directive
    return f"{directive}；{cur}"


def _prepend_bridge_scene(
    result: dict,
    *,
    event: str,
    ch: DabaiChapterOutline,
    pre_warn: dict | None,
    from_loc: str,
) -> dict:
    """在分场 scenes 头部插入位移承接场。"""
    out = dict(result)
    scenes = [s for s in (out.get("scenes") or []) if isinstance(s, dict)]
    if not scenes or is_bridge_scene(scenes[0]):
        out["scenes"] = scenes
        return out
    fact = (pre_warn or {}).get("fact_lock") or {}
    loc = str(fact.get("location") or ch.location or "途中").strip()
    on_stage = fact.get("on_stage") or []
    cast = [str(c) for c in on_stage[:4] if str(c).strip()] or ["主角"]
    budget = max(250, (ch.expected_words or 2000) // 10)
    bridge_scene = {
        "order": 1,
        "name": "位移承接",
        "location": from_loc.split("·")[0] if from_loc else "途中",
        "characters_on_stage": cast,
        "goal": "位移/承接上章",
        "event": event,
        "dialogue_ammo": [],
        "sensory_anchor": "脚步、风声或通道里的潮腐气",
        "end_turn": f"抵达{loc.split('·')[0] if loc else '本章主场景'}，冲突即将爆发",
        "word_budget": budget,
    }
    for i, sc in enumerate(scenes):
        sc["order"] = i + 2
    out["scenes"] = [bridge_scene] + scenes
    return out


def inject_prewarn_into_scene_plan(
    result: dict,
    pre_warn: dict | None,
    ch: DabaiChapterOutline,
    prev_ch: DabaiChapterOutline | None = None,
    prev_tail: str = "",
) -> dict:
    """分场后处理：合并 opening_directive；跨场景时补位移承接场。"""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if pre_warn:
        out["opening_line"] = merge_opening_directive(
            str(out.get("opening_line") or ""),
            str(pre_warn.get("opening_directive") or ""),
        )
    bridges = [
        str(b).strip()
        for b in ((pre_warn or {}).get("bridge_directives") or [])
        if str(b).strip()
    ]
    prev_loc = (prev_ch.location or "").strip() if prev_ch else ""
    curr_loc = (ch.location or "").strip()
    if bridges:
        event = bridges[0]
        out = _prepend_bridge_scene(
            out, event=event, ch=ch, pre_warn=pre_warn, from_loc=prev_loc or "上章末",
        )
    elif prev_ch and needs_location_bridge(prev_ch, ch, prev_tail):
        event = f"从{prev_loc}离开，经合理路径抵达{curr_loc.split('·')[0]}"
        out = _prepend_bridge_scene(
            out, event=event, ch=ch, pre_warn=pre_warn, from_loc=prev_loc or "上章末",
        )
    else:
        out["scenes"] = [s for s in (out.get("scenes") or []) if isinstance(s, dict)]
    if prev_ch and not needs_location_bridge(prev_ch, ch, prev_tail):
        scenes = [s for s in (out.get("scenes") or []) if isinstance(s, dict)]
        while scenes and is_bridge_scene(scenes[0]):
            scenes.pop(0)
        for i, sc in enumerate(scenes):
            sc["order"] = i + 1
        out["scenes"] = scenes
    return out


def prewarn_cast_names(result: dict | None) -> list[str]:
    """导演单确认的本章出场人物名：优先 cast[].name，回退 fact_lock.on_stage。"""
    if not isinstance(result, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for c in result.get("cast") or []:
        nm = str((c.get("name") if isinstance(c, dict) else c) or "").strip()
        if nm and nm not in seen:
            names.append(nm)
            seen.add(nm)
    if names:
        return names
    fact = result.get("fact_lock") or {}
    for raw in fact.get("on_stage") or []:
        s = str(raw or "").strip()
        if s and s not in seen:
            names.append(s)
            seen.add(s)
    return names
