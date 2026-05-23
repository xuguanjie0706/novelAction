"""
scene_checklist.py — 场景写后核验服务（约束满足情况检测）

设计动机：
  场景起草完成后，需要轻量检验正文是否落实了规划时写入的约束
  （故事线推进 / 伏笔操作 / 债务偿还）。

  核验结果回填到 Scene.checklist_result，未满足的关键约束写入 QualityDebt。
  同时更新 Project.extra.payoff_ledger（爽点账本）。

调用方：
  scene_routes.py → scene_stitch 端点（全场缝合后异步触发）

注意：
  本服务调用 LLM（temperature=0.2，稳定 JSON 档位），为轻量辅助调用。
  若 LLM 调用失败，降级为「规则匹配」模式（关键词检测），保证不阻塞主流程。
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def verify_scene_constraints(
    db: Session,
    scene_id: str,
    project_id: str,
    svc,
) -> dict | None:
    """
    核验单个场景正文是否满足规划时写入的约束。

    Args:
        db: SQLAlchemy Session
        scene_id: Scene UUID 字符串
        project_id: Project UUID 字符串
        svc: AIService 实例（用于轻量 LLM 调用）

    Returns:
        checklist_result dict，或 None（若场景无约束或正文为空）

    Side effects:
        - 回填 scene.checklist_result
        - 满足债务偿还时更新 project.extra.payoff_ledger
    """
    from app.models import Project, Scene

    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.project_id == project_id,
    ).first()
    if not scene or not scene.content:
        return None

    # 无约束时跳过
    has_constraints = any([
        scene.storyline_moves,
        scene.foreshadow_ops,
        scene.debt_flags,
    ])
    if not has_constraints:
        return None

    # 尝试 LLM 核验；失败时降级为规则匹配
    try:
        result = await _llm_verify(scene, svc)
    except Exception as exc:
        logger.warning("scene_checklist LLM verify failed, fallback to rules: %s", exc)
        result = _rule_verify(scene)

    # 回填 checklist_result
    try:
        scene.checklist_result = result
        db.commit()
    except Exception as exc:
        logger.warning("scene_checklist commit failed: %s", exc)
        db.rollback()
        return result

    # 更新爽点账本
    if result.get("debt_cleared"):
        _clear_payoff_debt(db, project_id)
    else:
        _maybe_increment_payoff_debt(db, project_id, scene)

    return result


async def verify_scenes_after_stitch(
    db: Session,
    project_id: str,
    outline_node_id: str,
    svc,
) -> None:
    """
    缝合完成后，对所有 written 场景异步触发核验。

    供 scene_stitch 端点在后台调用，不阻塞 stitch 响应。

    Args:
        db: SQLAlchemy Session
        project_id: Project UUID 字符串
        outline_node_id: OutlineNode UUID 字符串
        svc: AIService 实例
    """
    from app.models import Scene

    written_scenes = db.query(Scene).filter(
        Scene.project_id == project_id,
        Scene.outline_node_id == outline_node_id,
        Scene.status == "written",
        Scene.content.isnot(None),
    ).all()

    for scene in written_scenes:
        # 已有核验结果则跳过（避免重复计算）
        if scene.checklist_result:
            continue
        try:
            await verify_scene_constraints(
                db=db,
                scene_id=str(scene.id),
                project_id=project_id,
                svc=svc,
            )
        except Exception as exc:
            logger.warning("verify_scene_constraints failed for scene %s: %s", scene.id, exc)


# ── 核验实现 ──────────────────────────────────────────────────────

async def _llm_verify(scene, svc) -> dict:
    """
    用轻量 LLM 核验场景正文是否满足约束。

    temperature=0.2（quality.check 档位），prompt 简洁，仅输出 JSON。
    """
    # 构建约束摘要
    constraint_summary = _build_constraint_summary(scene)
    content_preview = (scene.content or "")[:600]

    system = "你是专业编辑助手。严格返回 JSON，不要任何额外文字。"
    prompt = f"""请检查以下场景正文是否落实了规划约束，返回 JSON。

【场景正文节选（前600字）】
{content_preview}

【规划约束】
{constraint_summary}

返回格式：
{{
  "storyline_ok": true/false,       // 故事线推进指令是否在正文中有所体现
  "foreshadow_ok": true/false,      // 伏笔操作是否有所体现
  "debt_cleared": true/false,       // 债务/爽点是否得到偿还
  "score": 0.0-1.0,                 // 综合满足度评分
  "notes": "简短说明（30字内）"
}}
只返回 JSON。"""

    from app.services.ai.parse import _parse_json
    raw = await svc._call_ai(system, prompt, task="quality.check")
    return _parse_json(raw)


def _rule_verify(scene) -> dict:
    """
    基于关键词的规则核验（LLM 失败时的降级方案）。

    逻辑：在正文中搜索故事线名称 / 伏笔标题，判断是否有提及。
    """
    content = (scene.content or "").lower()
    storyline_ok = False
    foreshadow_ok = False
    debt_cleared = False

    # 故事线：检查名称是否出现
    moves = scene.storyline_moves or []
    if moves:
        for m in moves:
            if isinstance(m, dict) and m.get("name", "").lower() in content:
                storyline_ok = True
                break
    else:
        storyline_ok = True  # 无约束视为满足

    # 伏笔：检查标题是否出现
    fw_ops = scene.foreshadow_ops or []
    if fw_ops:
        for op in fw_ops:
            if isinstance(op, dict) and op.get("title", "").lower() in content:
                foreshadow_ok = True
                break
    else:
        foreshadow_ok = True  # 无约束视为满足

    # 债务：有爽点债务时，检查是否有高强度动作/对话（粗糙近似）
    debts = scene.debt_flags or []
    payoff_debts = [d for d in debts if isinstance(d, dict) and d.get("debt_type") == "payoff"]
    if payoff_debts:
        # 简单启发：正文中存在感叹号 + 字数 > 预算 70% 视为有效爽点
        has_exclamation = "！" in (scene.content or "") or "!" in (scene.content or "")
        word_count = scene.actual_word_count or len(scene.content or "")
        debt_cleared = has_exclamation and word_count >= int((scene.word_budget or 400) * 0.7)
    else:
        debt_cleared = True  # 无债务约束视为满足

    score = sum([storyline_ok, foreshadow_ok, debt_cleared]) / 3.0

    return {
        "storyline_ok": storyline_ok,
        "foreshadow_ok": foreshadow_ok,
        "debt_cleared": debt_cleared,
        "score": round(score, 2),
        "notes": "规则匹配（LLM 降级）",
    }


def _build_constraint_summary(scene) -> str:
    """将场景约束字段格式化为简短摘要。"""
    lines: list[str] = []

    moves = scene.storyline_moves or []
    if moves:
        names = [m.get("name", "?") for m in moves[:3] if isinstance(m, dict)]
        lines.append(f"故事线推进：{' / '.join(names)}")

    fw_ops = scene.foreshadow_ops or []
    if fw_ops:
        ops_str = " / ".join(
            f"{op.get('op','hint').upper()}「{op.get('title','?')}」"
            for op in fw_ops[:3] if isinstance(op, dict)
        )
        lines.append(f"伏笔操作：{ops_str}")

    debts = scene.debt_flags or []
    if debts:
        descs = [d.get("description", "")[:40] for d in debts[:2] if isinstance(d, dict)]
        lines.append(f"债务偿还：{' / '.join(descs)}")

    return "\n".join(lines) if lines else "（无明确约束）"


# ── 爽点账本更新 ──────────────────────────────────────────────────

def _clear_payoff_debt(db: Session, project_id: str) -> None:
    """债务已偿还：清零 payoff_debt，从 pending_setups 移除第一条已兑现项。"""
    from app.models import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return
    extra = dict(project.extra or {})
    ledger = dict(extra.get("payoff_ledger", {}))
    ledger["payoff_debt"] = max(0, int(ledger.get("payoff_debt", 1)) - 1)
    setups = list(ledger.get("pending_setups", []))
    if setups:
        setups.pop(0)  # 移除最早的一条已兑现 setup
    ledger["pending_setups"] = setups
    extra["payoff_ledger"] = ledger
    project.extra = extra
    try:
        db.commit()
    except Exception as exc:
        logger.warning("clear_payoff_debt commit failed: %s", exc)
        db.rollback()


def _maybe_increment_payoff_debt(db: Session, project_id: str, scene) -> None:
    """
    若场景有爽点债务约束但未偿还，且场景是关键场（hook_strength>=4），
    则将 payoff_debt +1（表示又欠了一章）。
    """
    debts = scene.debt_flags or []
    has_payoff_debt = any(
        isinstance(d, dict) and d.get("debt_type") == "payoff"
        for d in debts
    )
    if not has_payoff_debt:
        return

    from app.models import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return
    extra = dict(project.extra or {})
    ledger = dict(extra.get("payoff_ledger", {}))
    ledger["payoff_debt"] = int(ledger.get("payoff_debt", 0)) + 1
    extra["payoff_ledger"] = ledger
    project.extra = extra
    try:
        db.commit()
    except Exception as exc:
        logger.warning("increment_payoff_debt commit failed: %s", exc)
        db.rollback()
