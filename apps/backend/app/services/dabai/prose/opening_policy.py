"""第1章开篇裁决：对标改编 / opening_setup / 导演单对齐。"""
from __future__ import annotations

from app.models.dabai import DabaiChapterOutline, DabaiProject, DabaiVolume

from dabai.first_chapter_opening import skip_ch1_cliche_lint
from dabai.plot_blueprint import ch1_opening_guidance_block


def volume_opening_setup(volume: DabaiVolume | None) -> str:
    if volume is None:
        return ""
    extra = volume.extra or {}
    return str(extra.get("opening_setup") or "").strip()


def build_ch1_opening_ctx(
    project: DabaiProject,
    volume: DabaiVolume | None = None,
) -> dict:
    """组装 ch1 对标开篇 ctx（章纲/导演单/正文/分场共用）。"""
    vols: list[dict] = []
    if volume is not None:
        vols.append({
            "volume_number": volume.volume_number,
            "opening_setup": volume_opening_setup(volume),
            "extra": volume.extra or {},
        })
    return {
        "logline": project.logline or "",
        "golden_finger": project.golden_finger or {},
        "positioning": project.positioning or {},
        "benchmark": project.benchmark or {},
        "volumes": vols,
    }


def ch1_benchmark_block(
    project: DabaiProject,
    volume: DabaiVolume | None = None,
) -> str:
    """第1章对标开篇块（无 benchmark 时返回空）。"""
    return ch1_opening_guidance_block(build_ch1_opening_ctx(project, volume))


def opening_policy_block(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    volume: DabaiVolume | None = None,
    pre_warn_result: dict | None = None,
) -> str:
    """开篇章额外硬约束（注入 prewarn / sceneplan prompt）。"""
    if int(ch.chapter_number or 0) != 1:
        return ""
    lines = ["【第1章开篇政策（硬约束）】"]
    benchmark_guidance = ch1_benchmark_block(project, volume)
    if benchmark_guidance.strip():
        lines.append(benchmark_guidance.strip())
    else:
        setup = volume_opening_setup(volume)
        if setup:
            lines.append(f"- 卷级 opening_setup：{setup[:300]}")
        lines.append(
            "- 无 benchmark 时：从 logline + 主角身份推导开篇，禁止退婚/踹 cliff 模板"
        )
    lines.append(
        "- beat_execution.yaqu 须按对标改编换皮，不得与章纲 yaqu_setup 原句雷同"
    )
    opening = ""
    if isinstance(pre_warn_result, dict):
        opening = str(pre_warn_result.get("opening_directive") or "").strip()
    if opening:
        lines.append(f"- 导演单开头写法：{opening[:200]}")
    return "\n".join(lines) + "\n"


def should_skip_beat_copy_guard(project: DabaiProject) -> bool:
    """章纲已按 benchmark 生成时，允许 beat 与 yaqu 语义对齐。"""
    return skip_ch1_cliche_lint(build_ch1_opening_ctx(project))
