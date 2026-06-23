"""dabai 实验书架写章 —— 本章出场人物「声音档案」注入块。

从 ``lab_draft_context`` 拆出（600 行硬上限治理）。职责单一：把本章出场人物的
性格 / 说话风格 / 功能 / 欲望 / 憋屈来源整理成注入块，让每个人物按自己的腔调
发声，消除对话千人一面。台账（资产 / 与主角态度）另由 ``ledger_block`` 注入，
此处不重复。

无外部依赖（不反向 import lab_draft_context，避免循环）：出场人名由调用方传入。
"""
from __future__ import annotations

from app.models.dabai import DabaiCharacter, DabaiChapterOutline, DabaiProject


def _protagonist_char(project: DabaiProject):
    """主角 DabaiCharacter：role 含『主角』/protagonist 优先，否则第一个核心。"""
    chars = list(project.characters or [])
    for c in chars:
        role = str(c.role or "")
        if "主角" in role or role.lower() == "protagonist":
            return c
    for c in chars:
        if str(c.tier or "") == "核心":
            return c
    return chars[0] if chars else None


def resolve_char_realm(
    c: DabaiCharacter,
    *,
    project: DabaiProject | None = None,
    ch: DabaiChapterOutline | None = None,
) -> str:
    """人物写作期境界：主角走面板/复盘链；配角章纲锁定 > extra > bootstrap。"""
    name = str(c.name or "").strip()
    protag = _protagonist_char(project) if project else None
    protag_name = str(protag.name).strip() if protag and protag.name else ""
    if name and name != protag_name and project is not None and ch is not None:
        from app.services.dabai.lab_prewarn_outline_lock import (
            extract_outline_cast_realms,
            format_locked_realm_label,
        )
        locked = extract_outline_cast_realms(ch)
        if name in locked:
            return format_locked_realm_label(locked[name], project)
    extra = c.extra if isinstance(c.extra, dict) else {}
    current = str(extra.get("current_realm") or "").strip()
    if current:
        if project is not None:
            from app.services.dabai.lab_realm_baseline import (
                ensure_full_realm_label,
                realm_label_has_sub,
            )
            meta = (project.meta or {}) if project else {}
            fallback_sub = getattr(ch, "realm_sub_rank", None) if ch else None
            if name == protag_name and not realm_label_has_sub(current):
                meta_label = str(meta.get("protagonist_realm") or "").strip()
                if realm_label_has_sub(meta_label):
                    return meta_label
            return ensure_full_realm_label(
                current, None, project, fallback_sub=fallback_sub,
            )
        return current
    if name == protag_name and project is not None:
        meta_label = str((project.meta or {}).get("protagonist_realm") or "").strip()
        if meta_label:
            return meta_label
    return str(c.start_realm or "").strip()


def build_cast_realm_lock_block(
    project: DabaiProject,
    stage_names: list[str],
    ch: DabaiChapterOutline | None = None,
) -> str:
    """本章出场非主角境界硬锁（章纲锁定优先于 bootstrap 人物表）。"""
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    if not by_name:
        return ""
    protag = _protagonist_char(project)
    protag_name = str(protag.name).strip() if protag and protag.name else ""
    from app.services.dabai.lab_prewarn_outline_lock import extract_outline_cast_realms

    outline_locked = extract_outline_cast_realms(ch) if ch else {}
    lines: list[str] = []
    for name in stage_names:
        if not name or name == protag_name:
            continue
        c = by_name.get(name)
        if not c:
            continue
        realm = resolve_char_realm(c, project=project, ch=ch)
        if realm:
            src = "章纲锁定" if name in outline_locked else "人物档案"
            lines.append(
                f"- {name}：{realm}（{src}；正文与对话称述须一致，"
                f"禁止无突破描写擅自改层/改境）"
            )
    if not lines:
        return ""
    tail = (
        "- 旁观者（如王铁柱）议论对手境界时，须与上表一致，禁止沿用旧稿/bootstrap 错误层数。"
    )
    if outline_locked:
        tail += (
            "\n- 本章为章纲锁定的同境对决时，禁止把对手写成更高层以凑「越级秒杀」爽感。"
        )
    else:
        tail += (
            "\n- 主角以金手指/奇袭/破绽越级碾压更高境界对手是允许的；"
            "禁止把档案境界更高的配角写成与主角同层或更低，除非五拍明确写其境界变化。"
        )
    return "【出场人物境界锁定（硬约束，章纲锁定 > 人物表）】\n" + "\n".join(lines) + "\n" + tail


def _format_char_voice(
    c: DabaiCharacter,
    *,
    is_protagonist: bool,
    project: DabaiProject | None = None,
    ch: DabaiChapterOutline | None = None,
) -> str:
    """单个人物声音档案行：性格 + 说话风格 + 功能 + 欲望/憋屈。"""
    extra = c.extra if isinstance(c.extra, dict) else {}
    head = f"{c.name}（{c.role or '配角'}"
    if c.tier:
        head += f"/{c.tier}"
    realm = resolve_char_realm(c, project=project, ch=ch)
    if realm:
        head += f"，{realm}"
    debut = extra.get("debut_chapter")
    if debut not in (None, ""):
        head += f"，第{debut}章登场"
    head += "）"
    bits: list[str] = []
    if c.persona:
        bits.append(f"性格:{str(c.persona)[:60]}")
    speech = extra.get("speech_kit") or extra.get("speech_style")
    if speech:
        bits.append(f"说话风格:{str(speech)[:60]}")
    if c.function:
        bits.append(f"功能:{str(c.function)[:50]}")
    if extra.get("desire"):
        bits.append(f"欲望:{str(extra['desire'])[:40]}")
    if extra.get("wound"):
        bits.append(f"憋屈来源:{str(extra['wound'])[:40]}")
    tail = "；".join(bits) if bits else (
        "按主角一贯口吻发声" if is_protagonist else "按其身份口吻发声"
    )
    return f"  - {head}：{tail}"


def build_char_voice_block(
    project: DabaiProject,
    stage_names: list[str],
    ch: DabaiChapterOutline | None = None,
) -> str:
    """本章出场人物声音档案：让每个人按自己的性格/说话风格发声，对话有区分度。"""
    by_name = {str(c.name).strip(): c for c in (project.characters or []) if c.name}
    if not by_name:
        return ""
    protag = _protagonist_char(project)
    ordered: list[tuple] = []
    seen: set[str] = set()
    if protag and protag.name:
        ordered.append((protag, True))
        seen.add(str(protag.name).strip())
    for name in stage_names:
        c = by_name.get(name)
        if c and name not in seen:
            ordered.append((c, False))
            seen.add(name)
        if len(ordered) >= 8:
            break
    if not ordered:
        return ""
    lines = [
        _format_char_voice(c, is_protagonist=p, project=project, ch=ch)
        for c, p in ordered
    ]
    realm_lock = build_cast_realm_lock_block(project, stage_names, ch=ch)
    body = (
        "【本章出场人物声音档案（每人按其性格与说话风格发声，"
        "对话须有区分度，禁止所有人一个腔调）】\n" + "\n".join(lines)
    )
    if realm_lock:
        body += "\n\n" + realm_lock
    return body
