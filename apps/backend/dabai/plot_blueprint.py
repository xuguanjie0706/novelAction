"""情节蓝图：bootstrap 自动选材 + 独立步拆解情节骨架。

流程：
  ① benchmark 步：据 logline 自动选定同题材 3-5 部高分对标书 + 立项定位（轻量）
  ② plot_blueprint 步：拆解情节骨架 + 卷章映射（独立 LLM，避免 benchmark 过载失败）
  ③ storylines / volumes / 章纲 / 正文按映射换皮改编+扩写
"""

from __future__ import annotations

from dabai.config import DabaiConfig

_ADAPT_RULES = (
    "★情节蓝图硬规则★：按下方「改编映射」骨架写，可扩写场面/对话/细节以增完整度；"
    "禁止照搬对标书人名/地名/门派/功法/原句；同一 beat 须换成本书金手指与人物关系。"
)


def plot_blueprint_enabled(cfg: DabaiConfig | None = None, ctx: dict | None = None) -> bool:
    """情节蓝图默认开启；plot_blueprint_mode=False 时整链跳过 plot_blueprint 步。"""
    if cfg is not None and cfg.plot_blueprint_mode is False:
        return False
    if ctx is not None and ctx.get("plot_blueprint_mode") is False:
        return False
    return True


def auto_reference_books_prompt(cfg: DabaiConfig) -> str:
    """benchmark 步专用：自动选材说明（不在此步拆情节骨架）。"""
    if not plot_blueprint_enabled(cfg=cfg):
        return ""
    override = [b.strip() for b in (cfg.reference_novels or []) if b and b.strip()]
    base = (
        "\n★自动选材（benchmark 步必做）★：根据 logline 推断题材/读者爽点，"
        "从番茄/起点/七猫 **同品类** 自动选定 3-5 部「数据验证过的高分作品」"
        "（追读标杆/万订级/品类天花板；优先真实存在的头部书）。\n"
        "每本 reference_books 须填：market_tier、data_proof（为何高分）、"
        "plot_role_in_adaptation（后续情节步将借它什么：开篇/升级/副线/高潮）、"
        "why_comparable / core_appeal / structure_note。\n"
        "★本步只选材+定位★：情节骨架拆解在下一步 plot_blueprint 单独完成，"
        "此处不要输出 plot_blueprints / adaptation_plan。\n"
    )
    if override:
        base += (
            f"\n【运营指定加分对标（须全部纳入 reference_books）】\n"
            f"  {'、'.join(override[:5])}\n"
        )
    return base


def merge_plot_into_benchmark(bm: dict, plot_data: dict) -> dict:
    """把 plot_blueprint 步产物合并进 benchmark 列（持久化与下游注入统一读 benchmark）。"""
    out = dict(bm or {})
    if not isinstance(plot_data, dict):
        return out
    out["plot_blueprints"] = plot_data.get("plot_blueprints") or []
    out["adaptation_plan"] = plot_data.get("adaptation_plan") or {}
    return out


def storylines_plot_addendum(cfg: DabaiConfig, ctx: dict) -> str:
    """storylines 步：故事线须从 plot_blueprint 映射推导。"""
    if not plot_blueprint_enabled(cfg=cfg, ctx=ctx):
        return ""
    bm = ctx.get("benchmark") or {}
    if not bm.get("plot_blueprints") and not bm.get("adaptation_plan"):
        return (
            "\n★注意★：情节蓝图尚未就绪，故事线仍须具体可拍，"
            "待 plot_blueprint 步完成后会在卷纲/章纲步对齐对标骨架。\n"
        )
    return (
        "\n★情节蓝图驱动故事线（硬约束）★：必须基于上方【情节蓝图·改编映射】。\n"
        "1. 主线 nodes 逐卷对齐 adaptation_plan.volume_mapping.adapted_arc；\n"
        "2. 每个 node 填 adapted_from：「《书名》·节拍名·换皮说明」（≤40字）；\n"
        "3. 副线从 plot_blueprints.borrowable_beats 借鉴，绑定本书人物；\n"
        "4. plot_assets / 谜题须有对标书「功能等价物」，换成本书设定名。\n"
    )


def plot_blueprint_block(ctx: dict, cfg: DabaiConfig | None = None) -> str:
    """下游注入：改编映射 + 可借用节拍。"""
    if not plot_blueprint_enabled(cfg=cfg, ctx=ctx):
        return ""
    bm = ctx.get("benchmark") or {}
    plan = bm.get("adaptation_plan") or {}
    blueprints = bm.get("plot_blueprints") or []
    refs = bm.get("reference_books") or []
    if not plan and not blueprints and not refs:
        return ""

    lines = ["\n【情节蓝图·高分对标改编映射（须按骨架展开，可扩写细节）】"]
    if refs:
        ref_line = "、".join(
            f"《{b.get('title', '')}》({b.get('market_tier') or str(b.get('data_proof', ''))[:12]})"
            for b in refs[:5] if isinstance(b, dict)
        )
        if ref_line:
            lines.append(f"  自动选定高分对标：{ref_line}")
    if plan.get("strategy"):
        lines.append(f"  策略：{plan['strategy']}")
    for vm in (plan.get("volume_mapping") or [])[:6]:
        if not isinstance(vm, dict):
            continue
        lines.append(
            f"  卷{vm.get('volume')}：借《{vm.get('primary_ref', '')}》{vm.get('ref_span', '')} → "
            f"本书{vm.get('local_span', '')}｜{str(vm.get('adapted_arc', ''))[:120]}"
        )
    hints = plan.get("chapter_beat_hints") or []
    if hints:
        hint_lines = []
        for h in hints[:12]:
            if isinstance(h, dict):
                hint_lines.append(
                    f"    章{h.get('span')}：{h.get('ref_beat', '')} → 须命中：{str(h.get('must_hit', ''))[:80]}"
                )
        if hint_lines:
            lines.append("  章段节拍提示：\n" + "\n".join(hint_lines))
    for exp in (plan.get("expansion_notes") or [])[:4]:
        lines.append(f"  扩写：{exp}")
    for bp in blueprints[:3]:
        if not isinstance(bp, dict):
            continue
        title = bp.get("title", "")
        role = bp.get("plot_role_in_adaptation", "")
        if role:
            lines.append(f"  《{title}》借鉴角色：{role[:80]}")
        sk = bp.get("plot_skeleton") or {}
        if sk.get("climax_pattern"):
            lines.append(f"  《{title}》高潮模式：{str(sk['climax_pattern'])[:100]}")
        for beat in (bp.get("borrowable_beats") or [])[:5]:
            if isinstance(beat, dict):
                lines.append(
                    f"    ·{beat.get('label', '')}({beat.get('ref_span', '')}) "
                    f"{beat.get('emotion_arc', '')}｜{str(beat.get('adapt_hint', ''))[:60]}"
                )
    lines.append(f"  {_ADAPT_RULES}")
    return "\n".join(lines) + "\n"


def _span_covers_ch1(span: str) -> bool:
    """chapter_beat_hints.span 是否覆盖第1章。"""
    s = str(span or "").strip()
    if not s:
        return False
    if s == "1" or s.startswith("1-"):
        return True
    if "-" in s:
        try:
            lo, hi = s.split("-", 1)
            return int(lo.strip()) <= 1 <= int(hi.strip())
        except ValueError:
            return False
    return False


def ch1_opening_guidance_block(ctx: dict) -> str:
    """从 benchmark + adaptation_plan 抽取第1章开篇改编指引（优先于系统固定菜单）。"""
    bm = ctx.get("benchmark") or {}
    if not isinstance(bm, dict) or not bm:
        return ""

    lines: list[str] = []
    plan = bm.get("adaptation_plan") or {}
    if isinstance(plan, dict) and plan.get("strategy"):
        lines.append(f"改编总策略：{plan['strategy']}")

    primary_ref = ""
    vols = ctx.get("volumes") or []
    v1 = vols[0] if vols and isinstance(vols[0], dict) else {}
    v1_extra = v1.get("extra") or {}
    opening_setup = (
        str(v1.get("opening_setup") or v1_extra.get("opening_setup") or "").strip()
    )
    if opening_setup:
        lines.append(f"卷1 opening_setup：{opening_setup[:200]}")

    for vm in (plan.get("volume_mapping") or []) if isinstance(plan, dict) else []:
        if not isinstance(vm, dict) or int(vm.get("volume") or 0) != 1:
            continue
        primary_ref = str(vm.get("primary_ref") or "").strip()
        lines.append(
            f"卷1主借《{primary_ref}》{vm.get('ref_span', '')} → "
            f"{str(vm.get('adapted_arc', ''))[:160]}"
        )
        break

    ch1_hint = None
    for h in (plan.get("chapter_beat_hints") or []) if isinstance(plan, dict) else []:
        if isinstance(h, dict) and _span_covers_ch1(h.get("span")):
            ch1_hint = h
            break
    if ch1_hint is None:
        hints = (plan.get("chapter_beat_hints") or []) if isinstance(plan, dict) else []
        if hints and isinstance(hints[0], dict):
            ch1_hint = hints[0]
    if ch1_hint:
        lines.append(
            f"第1章段({ch1_hint.get('span', '')})：借「{ch1_hint.get('ref_beat', '')}」"
            f" → 须兑现：{str(ch1_hint.get('must_hit', ''))[:120]}"
        )

    blueprints = bm.get("plot_blueprints") or []
    for bp in blueprints:
        if not isinstance(bp, dict):
            continue
        title = str(bp.get("title") or "")
        if primary_ref and title and title != primary_ref:
            continue
        sk = bp.get("plot_skeleton") or {}
        if isinstance(sk, dict):
            for arc in sk.get("opening_arc") or []:
                if isinstance(arc, dict) and arc.get("beats"):
                    lines.append(
                        f"《{title}》开篇弧({arc.get('span', '')})："
                        f"{str(arc.get('beats', ''))[:140]}"
                    )
        for beat in bp.get("borrowable_beats") or []:
            if not isinstance(beat, dict):
                continue
            label = str(beat.get("label") or "")
            ref_span = str(beat.get("ref_span") or "")
            if "开篇" in label or _span_covers_ch1(ref_span) or ref_span.startswith("1"):
                lines.append(
                    f"可借节拍·{label}({ref_span})："
                    f"{str(beat.get('adapt_hint', ''))[:100]}"
                )

    refs = bm.get("reference_books") or []
    for ref in refs[:5]:
        if not isinstance(ref, dict):
            continue
        role = str(ref.get("plot_role_in_adaptation") or ref.get("core_appeal") or "")
        if role and ("开篇" in role or not lines):
            lines.append(f"《{ref.get('title', '')}》借鉴点：{role[:100]}")
            break

    if not lines:
        titles = "、".join(
            f"《{b.get('title', '')}》" for b in refs[:3] if isinstance(b, dict) and b.get("title")
        )
        if titles:
            lines.append(f"高分对标：{titles}（开篇须按情节蓝图换皮改编，禁止照搬原句）")

    if not lines:
        return ""
    body = "\n".join(f"  · {ln}" for ln in lines if ln.strip())
    return (
        "\n【第1章开篇·对标改编指引（优先于任何系统默认模板）】\n"
        f"{body}\n"
        "  · 硬规则：只借对标书的「结构/情绪节拍/功能」，换成本书 logline、金手指、人物；"
        "禁止照搬对标书人名/地名/门派/原句。\n"
    )
