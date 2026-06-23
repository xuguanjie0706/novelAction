"""大白文限知视角前置门禁。

导演单负责区分「物理在场」与「幕后相关」，分场在写正文前验证每一场都贴住
主角。这样 POV 硬伤在昂贵正文生成前失败，而不是写完后再被质检封顶 40 分。
"""
from __future__ import annotations

import re
from typing import Any


_OFFSTAGE_REASON_MARKERS = (
    "通过法镜", "远程观察", "暗中观察", "幕后", "不在现场", "另一处",
)
_REMOTE_CUT_RE = re.compile(
    r"(?:与此同时|同时|另一边|画面(?:切到|转到)|视角(?:切到|转到))"
    r"[^。！？\n]{0,36}(?:阁|殿|房|堂|府|院|洞)(?:内|中|深处)"
)
_INNER_STATE_MARKERS = ("心想", "暗想", "确信", "断定", "意识到", "认为", "觉得")


def _named_items(raw: Any) -> list[dict[str, Any]]:
    """把人物数组收敛为带 name 的新 dict，避免原地修改 LLM 结果。"""
    items: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return items
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                items.append({**item, "name": name})
        elif str(item or "").strip():
            items.append({"name": str(item).strip(), "reason": ""})
    return items


def _is_offstage_reason(text: str) -> bool:
    return any(marker in text for marker in _OFFSTAGE_REASON_MARKERS)


def _first_hand_channel(text: str, protagonist: str) -> bool:
    if not protagonist:
        return False
    return any(
        marker in text
        for marker in (
            f"{protagonist}通过", f"{protagonist}从", f"{protagonist}听",
            f"{protagonist}看", f"{protagonist}察觉", f"{protagonist}判断",
        )
    )


def normalize_prewarn_pov(result: dict, *, protagonist: str) -> dict:
    """分离导演单的在场人物与幕后人物，并确保主角属于物理在场名单。

    显式 ``offstage_involved`` 优先；兼容旧导演单时，也会根据 cast.reason 中
    「通过法镜/幕后/远程观察」等标记识别幕后人物。
    """
    if not isinstance(result, dict):
        return result
    cast = _named_items(result.get("cast"))
    offstage = _named_items(result.get("offstage_involved"))
    offstage_names = {item["name"] for item in offstage}

    kept_cast: list[dict[str, Any]] = []
    for item in cast:
        reason = str(item.get("reason") or "").strip()
        if item["name"] in offstage_names or _is_offstage_reason(reason):
            if item["name"] not in offstage_names:
                offstage.append({
                    "name": item["name"],
                    "reason": reason or "幕后相关人物",
                    "information_channel": reason,
                })
                offstage_names.add(item["name"])
            continue
        kept_cast.append(dict(item))

    if protagonist and protagonist not in {item["name"] for item in kept_cast}:
        kept_cast.insert(0, {"name": protagonist, "reason": "限知 POV 主角，全程在场"})

    fact = dict(result.get("fact_lock") or {})
    on_stage = [
        str(name).strip() for name in (fact.get("on_stage") or [])
        if str(name).strip() and str(name).strip() not in offstage_names
    ]
    if protagonist and protagonist not in on_stage:
        on_stage.insert(0, protagonist)
    fact["on_stage"] = list(dict.fromkeys(on_stage))

    reminders = [str(item).strip() for item in (result.get("reminders") or []) if str(item).strip()]
    pov_reminder = "全章限知视角贴住主角；幕后人物只能经主角可见、可听的信息渠道呈现"
    if pov_reminder not in reminders:
        reminders.append(pov_reminder)

    return {
        **result,
        "cast": kept_cast,
        "offstage_involved": offstage,
        "fact_lock": fact,
        "reminders": reminders[:4],
    }


def _remote_cutaway_issue(text: str, protagonist: str) -> bool:
    return bool(_REMOTE_CUT_RE.search(text)) and not _first_hand_channel(text, protagonist)


def prewarn_pov_issues(result: dict | None, *, protagonist: str) -> list[str]:
    """返回导演单 POV 结构问题；空数组表示可进入分场。"""
    if not isinstance(result, dict):
        return ["导演单为空或结构无效"]
    issues: list[str] = []
    cast = _named_items(result.get("cast"))
    cast_names = {item["name"] for item in cast}
    fact = result.get("fact_lock") if isinstance(result.get("fact_lock"), dict) else {}
    on_stage = {str(name).strip() for name in (fact.get("on_stage") or []) if str(name).strip()}
    if protagonist and protagonist not in cast_names:
        issues.append(f"导演单 cast 缺少主角「{protagonist}」")
    if protagonist and protagonist not in on_stage:
        issues.append(f"导演单 on_stage 缺少主角「{protagonist}」")

    beats = result.get("beat_execution") if isinstance(result.get("beat_execution"), dict) else {}
    for key, raw in beats.items():
        text = str(raw or "")
        if _remote_cutaway_issue(text, protagonist):
            issues.append(f"导演单 {key} 含远程切镜，须改为主角可感知的信息渠道")
        for item in cast:
            name = item["name"]
            if name == protagonist or name not in text:
                continue
            start = text.find(name)
            window = text[start:start + 120]
            if any(marker in window for marker in _INNER_STATE_MARKERS) \
                    and not _first_hand_channel(text, protagonist):
                issues.append(f"导演单 {key} 直接断言「{name}」内心状态")
                break
    return list(dict.fromkeys(issues))


def scene_plan_pov_issues(result: dict | None, *, protagonist: str) -> list[str]:
    """验证分场是否可由限知第三人称安全执行。"""
    if not isinstance(result, dict):
        return ["分场为空或结构无效"]
    scenes = result.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ["分场 scenes 为空"]
    issues: list[str] = []
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            issues.append(f"场{index}结构无效")
            continue
        order = scene.get("order") or index
        cast = {str(name).strip() for name in (scene.get("characters_on_stage") or []) if str(name).strip()}
        if protagonist and protagonist not in cast:
            issues.append(f"场{order}缺少主角「{protagonist}」")
        pov = str(scene.get("pov_character") or "").strip()
        if pov and protagonist and pov != protagonist:
            issues.append(f"场{order} POV角色「{pov}」不是主角「{protagonist}」")
        text = "\n".join(str(scene.get(key) or "") for key in ("event", "end_turn"))
        if _remote_cutaway_issue(text, protagonist):
            issues.append(f"场{order}含远程切镜；幕后反应必须通过主角可见/可听渠道呈现")
    return list(dict.fromkeys(issues))

