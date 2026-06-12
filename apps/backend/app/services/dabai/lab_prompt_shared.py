"""dabai 实验书架 prompt 共享块 — 境界体系 / 人物称谓锁定 / 导演单后处理。"""
from __future__ import annotations

import re

from app.models.dabai import DabaiChapterOutline, DabaiProject

# 常见外来修仙体系用语（本书 power_ladder 未收录时才视为禁用）
_FOREIGN_REALM_TERMS = (
    "练气", "练体", "淬体", "后天", "先天", "开光", "心动", "元婴", "化神",
)

_BRIDGE_GOAL_MARKERS = ("位移", "过渡", "承接", "转场", "赶路", "回途")

_CONTINUITY_STOP = frozenset({
    "什么", "已经", "一个", "这种", "那里", "此时", "感觉", "体内", "自己",
    "不是", "可以", "没有", "就是", "这一", "那一", "只见", "突然",
})

_IMMEDIATE_CONTINUATION_MARKERS = (
    "踏出", "走出", "刚踏", "刚走", "迎向", "封住", "对峙", "看向", "目光",
    "尚未", "还没", "正待", "这时", "刹那", "瞬间", "下一刻", "紧接着",
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
    tail = (prev_tail or "").strip()[-220:]
    return any(m in tail for m in _IMMEDIATE_CONTINUATION_MARKERS)


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
        f"  最低档（开书默认）：{first}\n"
        f"  全书档位：{chain}\n"
        f"  ★有【系统面板】时开笔境界须与面板完全一致；无面板时用「{first}」起步。"
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


def sanitize_prewarn_result(result: dict, project: DabaiProject) -> dict:
    """修正导演单 JSON 中 fact_lock.realm 的外来体系用语。"""
    if not isinstance(result, dict):
        return result
    fact = dict(result.get("fact_lock") or {})
    if fact.get("realm"):
        fact["realm"] = fix_realm_string(str(fact["realm"]), project)
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
    if directive[:12] in cur:
        return cur
    return f"{directive}｜{cur}" if cur else directive


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
