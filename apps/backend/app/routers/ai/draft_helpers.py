"""
draft_helpers.py — 写章上下文组装的轻量辅助函数。

职责范围：
- ``_calc_hook_requirement``：按章节序号 + 卷阶段 + 打脸频率，推算本章是否为爽点结算章，
  返回需注入 prompt 的 MUST 约束文本。
- ``_build_consistency_issues_block``：将 Bootstrap Step 14 遗留的全局一致性矛盾列表，
  过滤出与本章涉及角色相关的条目，格式化为连续性账本追加块。
- ``merge_writing_config``：合并项目级 ``extra.writing_config`` 与请求覆盖，供普通起草与门控起草共用。
- ``prewrite_gate_violation``：写章前硬门（一致性未确认、境界名与体系 levels 不一致），
  返回结构化 detail 供路由层 ``HTTPException(409)``。

设计原则：
- 纯过滤/格式化逻辑保持无副作用；涉及 ORM 的 gate 单独函数并集中在一处。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Character, PowerSystem, Project

# ── 写作门控默认（与 gated_draft_routes 历史默认值对齐，并扩展新键）────────
_WRITING_CONFIG_DEFAULTS: dict[str, Any] = {
    "auto_quality_gate": True,
    "min_overall_score": 6.0,
    "min_subscribe_intent": 6.0,
    "max_rewrite_attempts": 3,
    "pre_write_warning_enabled": False,
    # 新增：Bootstrap Step14 矛盾 — 默认不阻塞（向后兼容）
    "block_on_consistency_issues": False,
    "consistency_block_severities": ["high"],
    # 新增：爽点结算章 — 门控质检是否强制 face_slap_payoff 维度
    "enforce_face_slap_payoff_when_hook_required": False,
    "min_face_slap_payoff_score": 6.0,
    # 新增：人物 current_realm 是否须落在所属 PowerSystem.levels.name
    "block_on_realm_mismatch": False,
}


def merge_writing_config(project: Project, override: dict | None) -> dict:
    """
    合并 ``project.extra.writing_config`` 与请求级 ``override``。

    @param project: 已加载的 Project ORM
    @param override: 仅接受 ``_WRITING_CONFIG_DEFAULTS`` 中已声明的键
    @returns 新 dict（不修改 defaults 常量本体）
    """
    cfg = dict(_WRITING_CONFIG_DEFAULTS)
    project_extra = getattr(project, "extra", None) or {}
    if isinstance(project_extra, dict):
        stored = project_extra.get("writing_config")
        if isinstance(stored, dict):
            cfg.update({k: v for k, v in stored.items() if k in _WRITING_CONFIG_DEFAULTS})
    if override and isinstance(override, dict):
        cfg.update({k: v for k, v in override.items() if k in _WRITING_CONFIG_DEFAULTS})
    # 值域保护（与 gated 路由一致）
    cfg["min_overall_score"] = max(0.0, min(10.0, float(cfg["min_overall_score"])))
    cfg["min_subscribe_intent"] = max(0.0, min(10.0, float(cfg["min_subscribe_intent"])))
    cfg["max_rewrite_attempts"] = max(1, min(5, int(cfg["max_rewrite_attempts"])))
    cfg["pre_write_warning_enabled"] = bool(cfg.get("pre_write_warning_enabled", False))
    cfg["block_on_consistency_issues"] = bool(cfg.get("block_on_consistency_issues", False))
    cfg["block_on_realm_mismatch"] = bool(cfg.get("block_on_realm_mismatch", False))
    cfg["enforce_face_slap_payoff_when_hook_required"] = bool(
        cfg.get("enforce_face_slap_payoff_when_hook_required", False)
    )
    cfg["min_face_slap_payoff_score"] = max(0.0, min(10.0, float(cfg.get("min_face_slap_payoff_score", 6.0))))
    sev = cfg.get("consistency_block_severities") or ["high"]
    if isinstance(sev, list):
        cfg["consistency_block_severities"] = [str(s).strip().lower() for s in sev if str(s).strip()]
    else:
        cfg["consistency_block_severities"] = ["high"]
    return cfg


def _normalize_severity(raw: Any) -> str:
    s = (str(raw) if raw is not None else "").strip().lower()
    if s in ("high", "critical", "严重"):
        return "high"
    if s in ("medium", "mid", "中"):
        return "medium"
    if s in ("low", "低"):
        return "low"
    return s or "low"


def consistency_issue_fingerprint(iss: dict) -> str:
    """单条矛盾条目的稳定指纹，供前端「已知悉」回传 ``consistency_issue_ack``。"""
    payload = {
        "severity": _normalize_severity(iss.get("severity")),
        "type": (str(iss.get("type") or "")).strip(),
        "description": (str(iss.get("description") or iss.get("issue") or "")).strip()[:800],
        "suggestion": (str(iss.get("suggestion") or "")).strip()[:300],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def list_chapter_relevant_consistency_issue_dicts(
    project_extra: dict,
    manifest_names: list[str],
) -> list[dict]:
    """
    与 ``_build_consistency_issues_block`` 相同的过滤规则，返回 dict 列表（含 fingerprint）。

    @param project_extra: ``Project.extra``
    @param manifest_names: 本章 manifest 角色名
    """
    issues: list = []
    if isinstance(project_extra, dict):
        issues = project_extra.get("consistency_issues") or []
    if not issues:
        return []

    name_set = {n for n in manifest_names if n}
    out: list[dict] = []
    for iss in issues[:20]:
        if isinstance(iss, dict):
            desc = iss.get("description") or iss.get("issue") or ""
            row = dict(iss)
        else:
            desc = str(iss)
            row = {"description": desc}
        desc = str(desc).strip()
        if not desc:
            continue
        if len(issues) <= 5 or (name_set and any(name in desc for name in name_set)):
            row["_fingerprint"] = consistency_issue_fingerprint(
                row if isinstance(iss, dict) else {"description": desc}
            )
            out.append(row)
    return out


def _level_names_and_ranks(ps: PowerSystem) -> tuple[dict[str, int], set[str]]:
    """从 PowerSystem.levels 提取 name->rank 与合法名称集合。"""
    name_to_rank: dict[str, int] = {}
    names: set[str] = set()
    for lv in ps.levels or []:
        if not isinstance(lv, dict):
            continue
        n = (lv.get("name") or "").strip()
        if not n:
            continue
        names.add(n)
        r = lv.get("rank")
        try:
            if r is not None:
                name_to_rank[n] = int(r)
        except (TypeError, ValueError):
            pass
    return name_to_rank, names


def collect_realm_mismatch_lines(
    db: Session,
    project_id: str,
    manifest_names: list[str],
) -> list[str]:
    """
    检查 manifest 内人物：若有 ``power_system_id`` 且填写了 ``current_realm``，
    则境界名必须出现在对应体系的 ``levels[].name`` 中；若同时有 ``realm_rank`` 则须与该名称的 rank 一致。

    manifest 为空时不检查（避免误杀无大纲数据项目）。
    """
    name_set = {n for n in manifest_names if n}
    if not name_set:
        return []

    characters = (
        db.query(Character)
        .filter(Character.project_id == project_id, Character.name.in_(list(name_set)))
        .all()
    )
    systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    ps_by_id = {str(s.id): s for s in systems}
    lines: list[str] = []

    for c in characters:
        realm = (c.current_realm or "").strip()
        if not realm or not c.power_system_id:
            continue
        ps = ps_by_id.get(str(c.power_system_id))
        if not ps or not ps.levels:
            continue
        name_to_rank, valid_names = _level_names_and_ranks(ps)
        if realm not in valid_names:
            lines.append(
                f"「{c.name}」当前境界「{realm}」不在体系「{ps.name}」的 levels 名称列表中；"
                "请先在人物卡或境界表中修正后再写作。"
            )
            continue
        if c.realm_rank is not None and name_to_rank:
            expected = name_to_rank.get(realm)
            if expected is not None and int(c.realm_rank) != int(expected):
                lines.append(
                    f"「{c.name}」境界序号 realm_rank={c.realm_rank} 与体系「{ps.name}」中"
                    f"「{realm}」的 rank={expected} 不一致；请先对齐后再写作。"
                )
    return lines


def prewrite_gate_violation(
    db: Session,
    project: Project,
    chapter: Any,
    ctx: dict,
    cfg: dict,
    ack_fingerprints: list[str] | None,
) -> dict | None:
    """
    写章前硬门。若应阻止起笔，返回 FastAPI ``detail`` dict；否则 ``None``。

    @param ctx: ``_build_draft_context`` 的返回值（须含 ``chapter_manifest``）
    @param cfg: ``merge_writing_config`` 的结果
    @param ack_fingerprints: 作者已确认的矛盾指纹列表（与 blocking 集合须一致才放行）
    """
    project_extra = getattr(project, "extra", None) or {}
    if not isinstance(project_extra, dict):
        project_extra = {}

    manifest = ctx.get("chapter_manifest") or []
    if not isinstance(manifest, list):
        manifest = []

    ack_set = {str(x).strip() for x in (ack_fingerprints or []) if str(x).strip()}

    # ── 一致性矛盾 ─────────────────────────────────────────────
    if cfg.get("block_on_consistency_issues"):
        rel = list_chapter_relevant_consistency_issue_dicts(project_extra, manifest)
        block_sev = set(cfg.get("consistency_block_severities") or ["high"])
        blocking = [
            it
            for it in rel
            if _normalize_severity(it.get("severity")) in block_sev
        ]
        fps_required = {it.get("_fingerprint") or consistency_issue_fingerprint(it) for it in blocking}
        missing = fps_required - ack_set
        if missing:
            issues_out = []
            for it in blocking:
                fp = it.get("_fingerprint") or consistency_issue_fingerprint(it)
                issues_out.append(
                    {
                        "fingerprint": fp,
                        "severity": it.get("severity"),
                        "type": it.get("type"),
                        "description": it.get("description") or it.get("issue"),
                        "suggestion": it.get("suggestion"),
                    }
                )
            return {
                "error": "draft_prewrite_blocked",
                "reason": "consistency_issues",
                "message": (
                    "项目存在未处理的 Bootstrap 全局一致性（高优先级）条目，且与本章人物相关。"
                    "请在 UI 中审阅后，将需忽略的条目指纹通过 consistency_issue_ack 原样回传以确认已知悉风险后再写作。"
                ),
                "issues": issues_out,
            }

    # ── 境界名与体系 levels 对齐 ────────────────────────────
    if cfg.get("block_on_realm_mismatch"):
        realm_lines = collect_realm_mismatch_lines(db, str(project.id), manifest)
        if realm_lines:
            return {
                "error": "draft_prewrite_blocked",
                "reason": "realm_mismatch",
                "message": "本章 manifest 内人物存在境界字段与 PowerSystem.levels 不一致，已阻止起笔。",
                "realm_violations": realm_lines,
            }

    return None


def _calc_hook_requirement(
    phase: str,
    sort_order: int,
    face_slap_pattern: str,
) -> str:
    """
    根据卷阶段与章节序号推算本章爽点等级要求，返回 MUST 约束文本。

    基于 face_slap_pattern（如"每3章一小、每10章一中、每卷一大"）与当前章节位置，
    判断本章是否为"结算章"；若是则返回强制爽点规则，否则返回空字符串。

    高潮期（climax）所有章均视为大爽点；至暗期（dark_hour）豁免。

    @param phase: 卷阶段（opening/rising/turning/dark_hour/climax/ending）
    @param sort_order: 章节在项目内的序号（1-based）
    @param face_slap_pattern: positioning.face_slap_pattern 字符串
    @returns 若本章为结算章，返回注入 prompt 的 MUST 文本；否则返回空字符串
    """
    if not sort_order or sort_order < 1:
        return ""

    phase_norm = (phase or "").strip().lower()

    # 高潮期：所有章均为大爽点
    if phase_norm == "climax":
        return (
            "\n\n▍【本章爽点硬要求 · 高潮期】\n"
            "当前为高潮期：本章必须有大级别爽感兑现（伏笔引爆/打脸高潮/突破碾压）；"
            "不得写纯铺垫章；章末钩子须炸裂（悬念级别≥关键人物/核心秘密/格局翻转）。"
        )

    # 至暗期豁免（允许无爽点，情感克制优先）
    if phase_norm == "dark_hour":
        return ""

    # 解析 face_slap_pattern 中「每 N 章一小/中」的频率
    small_interval: int | None = None
    mid_interval: int | None = None
    for m in re.finditer(r"每\s*(\d+)\s*章\s*一\s*(小|中)", face_slap_pattern or ""):
        n, lvl = int(m.group(1)), m.group(2)
        if lvl == "小":
            small_interval = n
        elif lvl == "中":
            mid_interval = n

    # 中爽优先级高于小爽（同一章不重复提示）
    if mid_interval and sort_order % mid_interval == 0:
        return (
            f"\n\n▍【本章爽点硬要求 · 中级结算（第 {sort_order} 章，每 {mid_interval} 章一中）】\n"
            "本章是「中级爽点结算章」，必须包含：打脸高潮场景（≥1处，含施压方+主角逆转+在场观众反应）"
            "或突破/习得新能力的实战验证；禁止以「心情好了很多」类心理描写替代实质爽感。"
        )
    if small_interval and sort_order % small_interval == 0:
        return (
            f"\n\n▍【本章爽点硬要求 · 小级结算（第 {sort_order} 章，每 {small_interval} 章一小）】\n"
            "本章是「小爽点结算章」，必须有≥1处可被读者截图传播的高光瞬间"
            "（狠话/反转/装x成功/敌方狼狈）；不得全程铺垫，须有明确情绪峰值点。"
        )

    return ""


def _build_consistency_issues_block(
    project_extra: dict,
    manifest_names: list[str],
) -> str:
    """
    从 Bootstrap Step 14 的扫描结果中过滤与本章涉及角色相关的矛盾条目，
    格式化为追加到 continuity_context 末尾的约束块。

    过滤规则：
    - 总条目 ≤ 5 时全量注入（避免遗漏）
    - 总条目 > 5 时：只注入描述文本中包含本章 manifest 角色名的条目

    @param project_extra: Project.extra dict（含 consistency_issues 键）
    @param manifest_names: 本章允许出场的命名角色列表，用于相关性过滤
    @returns 格式化约束块字符串；无匹配条目时返回空字符串
    """
    rows = list_chapter_relevant_consistency_issue_dicts(project_extra, manifest_names)
    if not rows:
        return ""

    lines = ["\n\n⚠️【Bootstrap 全局一致性矛盾（写章时必须规避，不得在正文中延续以下矛盾）】"]
    for it in rows:
        desc = it.get("description") or it.get("issue") or ""
        desc = str(desc).strip()
        if desc:
            lines.append(f"  · {desc}")
    return "\n".join(lines)


def hook_chapter_mandate_active(ctx: dict, chapter: Any) -> bool:
    """是否与 ``_build_draft_context`` 中注入的爽点硬约束为同一判定（非空即结算章/高潮章）。"""
    pos = ctx.get("positioning") or {}
    if not isinstance(pos, dict):
        pos = {}
    face = str(pos.get("face_slap_pattern") or "")
    phase = str(ctx.get("phase") or "")
    sort_order = int(getattr(chapter, "sort_order", None) or 0)
    return bool(_calc_hook_requirement(phase, sort_order, face).strip())
