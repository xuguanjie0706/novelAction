"""一致性问题 AI 修复 + 重扫接口。

POST /api/v1/projects/{project_id}/consistency/fix
接收选中的一致性问题序号 + 用户补充提示，调用 AI 生成结构化修复补丁，
依次写入 Character / Faction / Skill 表，并在 Project.extra.consistency_issues 中
标记已修复条目。

POST /api/v1/projects/{project_id}/consistency/rescan
修复完成后重新调用 gen_consistency_scan，对当前数据库状态做全量交叉核验，
覆盖写入 Project.extra.consistency_issues，返回最新问题列表。

支持的修复操作（entity_type.field）：
- character.current_realm
- character.faction
- faction.name
- faction.description
- skill.mastered_by
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Character, Faction, Item, Skill, StoryLine
from app.models.outline import OutlineNode
from app.models.project import Project
from app.services.ai_service import AIService
from app.services.bootstrap.context import hydrate_ctx_from_project
from app.services.bootstrap.steps.consistency_scan import gen_consistency_scan
from app.services.consistency_fix_service import EntityCodebook, generate_fix_patches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["consistency"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ConsistencyFixRequest(BaseModel):
    """
    修复请求体。

    Args:
        selected_indices: 要修复的 consistency_issues 序号列表（0-based）。
        user_prompt: 用户补充说明，用于引导 AI 修复方向（可为空）。
        model_profile: 使用的模型线路（``"local"`` 或 ``"gemini"``）。
        llm_provider_id: 管理后台配置的 LlmProvider UUID（可选，gemini 线路时传入）。
    """
    selected_indices: list[int]
    user_prompt: str = ""
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: UUID | None = None


class AppliedPatch(BaseModel):
    """单条已成功应用的修复操作。"""
    issue_index: int
    entity_type: str
    entity_name: str
    field: str
    old_value: Any
    new_value: Any
    applied: bool
    reason: str


class SkippedPatch(BaseModel):
    """未能自动修复的条目及原因。"""
    issue_index: int
    reason: str
    suggestion: str = ""


class ConsistencyFixResponse(BaseModel):
    """修复结果汇总。"""
    applied: list[AppliedPatch]
    skipped: list[SkippedPatch]
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owned_or_404(db: Session, project_id: str, current_user) -> Project:
    """查询项目并校验归属，不存在或越权时 raise HTTPException。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.user_id and str(project.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="无访问权限")
    return project


# 每种实体允许被 AI 修改的字段白名单，防止 prompt 注入越权写入
_ALLOWED_FIELDS: dict[str, set[str]] = {
    "character": {"current_realm", "faction"},
    "faction":   {"name", "description"},
    "skill":     {"mastered_by"},
}

# 仅支持手动处理的问题类型（不调用远程 LLM，避免无谓触发安全过滤）
_MANUAL_ONLY_ISSUE_TYPES = frozenset({"volume_order_gap", "storyline_gap"})


def _is_manual_only_issue(issue: dict) -> bool:
    """判断该条是否超出当前自动修复字段能力（如改境界体系表）。"""
    t = str(issue.get("type") or "")
    if t in _MANUAL_ONLY_ISSUE_TYPES:
        return True
    desc = str(issue.get("description") or "")
    if t == "realm_mismatch" and "境界体系" in desc:
        return True
    return False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/{project_id}/consistency/fix", response_model=ConsistencyFixResponse)
async def fix_consistency_issues(
    project_id: str,
    body: ConsistencyFixRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ConsistencyFixResponse:
    """AI 辅助修复选中的一致性问题。

    流程：
    1. 读取 project.extra.consistency_issues[selected_indices]
    2. 查询项目下的人物、势力、技能作为上下文
    3. 让 AI 生成结构化 patch 列表
    4. 依次应用 patch（entity_type/field 白名单校验）
    5. 将 consistency_issues 中已修复条目标记 ``status="fixed"``
    6. 返回操作明细

    Raises:
        HTTPException 400: 无一致性问题记录或未选择有效条目。
        HTTPException 500: AI 调用失败或数据库提交异常。
    """
    project = _owned_or_404(db, project_id, current_user)
    extra = project.extra if isinstance(project.extra, dict) else {}
    all_issues: list = extra.get("consistency_issues") or []

    if not all_issues:
        raise HTTPException(status_code=400, detail="暂无一致性问题记录，请先完成 Bootstrap 生成")

    # 过滤掉已修复的条目；只处理 selected_indices 中有效的
    selected_pairs: list[tuple[int, dict]] = []
    for idx in body.selected_indices:
        if 0 <= idx < len(all_issues):
            issue = all_issues[idx]
            if isinstance(issue, dict) and issue.get("status") == "fixed":
                continue
            selected_pairs.append((idx, issue if isinstance(issue, dict) else {"description": str(issue)}))

    if not selected_pairs:
        raise HTTPException(status_code=400, detail="未选择有效（未修复）的问题条目")

    # 查询项目实体
    characters: list[Character] = db.query(Character).filter(Character.project_id == project_id).all()
    factions:   list[Faction]   = db.query(Faction).filter(Faction.project_id == project_id).all()
    skills:     list[Skill]     = db.query(Skill).filter(Skill.project_id == project_id).all()

    auto_pairs = [(idx, iss) for idx, iss in selected_pairs if not _is_manual_only_issue(iss)]
    manual_pairs = [(idx, iss) for idx, iss in selected_pairs if _is_manual_only_issue(iss)]

    profile = "gemini" if body.model_profile == "gemini" else "default"
    svc = AIService(profile, db=db, llm_provider_id=body.llm_provider_id)
    codebook = EntityCodebook(characters, factions, skills)

    patches: list = []
    if auto_pairs:
        try:
            patches = await generate_fix_patches(
                svc,
                auto_pairs,
                characters,
                factions,
                skills,
                user_prompt=body.user_prompt,
            )
        except Exception as exc:
            exc_str = str(exc)
            logger.exception("consistency_fix AI 调用失败: %s", exc)
            if "blocked" in exc_str.lower() or "safety" in exc_str.lower():
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "远程模型安全过滤拦截了本次请求（可能因角色/势力/技能名称触发）。"
                        "建议：① 在「模型/线路」切换为本地模型后重试；"
                        "② 或减少一次选中的问题数量，分批修复。"
                    ),
                )
            raise HTTPException(status_code=500, detail=f"AI 调用失败：{exc}")

    char_map    = {c.name: c for c in characters}
    faction_map = {f.name: f for f in factions}
    skill_map   = {s.name: s for s in skills}

    pair_by_idx = {idx: iss for idx, iss in selected_pairs}

    applied_list: list[AppliedPatch] = []
    skipped_list: list[SkippedPatch] = [
        SkippedPatch(
            issue_index=idx,
            reason="该问题需在大纲/境界体系等页面手动调整，当前接口不支持自动写入",
            suggestion=str(iss.get("suggestion") or ""),
        )
        for idx, iss in manual_pairs
    ]

    for patch in patches:
        seq         = patch.get("issue_seq")
        entity_type = str(patch.get("entity_type") or "").lower()
        entity_name_raw = str(patch.get("entity_name") or "")
        field       = str(patch.get("field") or "")
        new_value   = patch.get("new_value")
        reason      = str(patch.get("reason") or "")

        real_idx = patch.get("_real_idx")
        if real_idx is None:
            real_idx = (
                auto_pairs[seq][0]
                if isinstance(seq, int) and 0 <= seq < len(auto_pairs)
                else -1
            )

        entity_name = codebook.resolve_entity_name(entity_type, entity_name_raw) or entity_name_raw

        def _skip(msg: str) -> None:
            iss = pair_by_idx.get(real_idx, {})
            skipped_list.append(SkippedPatch(
                issue_index=real_idx,
                reason=msg,
                suggestion=str(iss.get("suggestion") or ""),
            ))

        allowed = _ALLOWED_FIELDS.get(entity_type)
        if allowed is None:
            _skip(f"不支持的实体类型：{entity_type}")
            continue
        if field not in allowed:
            _skip(f"不支持的字段：{field}（允许：{', '.join(allowed)}）")
            continue

        entity = {"character": char_map, "faction": faction_map, "skill": skill_map}[entity_type].get(entity_name)
        if entity is None:
            _skip(f"找不到实体：{entity_name}")
            continue

        old_value = getattr(entity, field, None)
        try:
            setattr(entity, field, new_value)
            db.flush()
            applied_list.append(AppliedPatch(
                issue_index=real_idx,
                entity_type=entity_type,
                entity_name=entity_name,
                field=field,
                old_value=old_value,
                new_value=new_value,
                applied=True,
                reason=reason,
            ))
        except Exception as exc:
            db.rollback()
            _skip(f"写入失败：{exc}")

    # 标记已修复条目
    if applied_list:
        fixed_indices = {r.issue_index for r in applied_list}
        updated = list(all_issues)
        for idx in fixed_indices:
            if 0 <= idx < len(updated):
                item = dict(updated[idx]) if isinstance(updated[idx], dict) else {"description": str(updated[idx])}
                item["status"] = "fixed"
                updated[idx] = item
        project.extra = {**extra, "consistency_issues": updated}
        flag_modified(project, "extra")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"数据库提交失败：{exc}")

    n_applied = len(applied_list)
    n_skipped = len(skipped_list)
    message = f"已自动修复 {n_applied} 项" + (f"，{n_skipped} 项需手动处理" if n_skipped else "")

    return ConsistencyFixResponse(applied=applied_list, skipped=skipped_list, message=message)


# ---------------------------------------------------------------------------
# Rescan endpoint
# ---------------------------------------------------------------------------

class ConsistencyRescanRequest(BaseModel):
    """重扫请求体。

    Args:
        model_profile: 使用的模型线路（``"local"`` 或 ``"gemini"``）。
        llm_provider_id: 管理后台配置的 LlmProvider UUID（可选）。
    """
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: UUID | None = None


class ConsistencyRescanResponse(BaseModel):
    """重扫结果。"""
    issues: list[dict]
    count: int
    message: str


class _AiSvcProxy:
    """对 gen_consistency_scan 暴露的最小 svc 接口：_call_with_retry + db。

    gen_consistency_scan 只依赖这两个属性，无需传入完整的 GenerationService。
    """

    def __init__(self, ai_svc: AIService, db: Session) -> None:
        self._ai_svc = ai_svc
        self.db = db

    async def _call_with_retry(self, system: str, prompt: str, **kwargs: Any) -> str:
        """转发至 AIService._call_ai（AIService 内部已含重试逻辑）。"""
        return await self._ai_svc._call_ai(system, prompt, **kwargs)


def _build_rescan_ctx(db: Session, project: Project) -> dict:
    """在 hydrate_ctx_from_project 基础上补充 gen_consistency_scan 所需的额外字段。

    补充字段：
    - ``char_realms``：人物名 → current_realm 映射
    - ``skill_names``：技能名列表
    - ``item_names``：道具名列表
    - ``storyline_summary``：故事线摘要字符串
    - ``volumes_summary``：卷级骨架摘要字符串
    """
    ctx = hydrate_ctx_from_project(db, project)

    pid = str(project.id)

    # 人物境界映射
    chars = db.query(Character).filter(Character.project_id == pid).all()
    ctx["char_realms"] = {
        c.name: (c.current_realm or "未设定")
        for c in chars
        if c.name
    }

    # 技能 / 道具名列表
    ctx["skill_names"] = [
        s.name for s in db.query(Skill).filter(Skill.project_id == pid).all() if s.name
    ]
    ctx["item_names"] = [
        i.name for i in db.query(Item).filter(Item.project_id == pid).all() if i.name
    ]

    # 故事线摘要
    storylines = db.query(StoryLine).filter(StoryLine.project_id == pid).all()
    if storylines:
        ctx["storyline_summary"] = "；".join(
            f"{sl.name}（{sl.storyline_type}）" for sl in storylines if sl.name
        )
    else:
        ctx["storyline_summary"] = "（未设定）"

    # 卷级骨架摘要
    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == pid,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if volumes:
        ctx["volumes_summary"] = "\n".join(
            f"第{v.sort_order or i + 1}卷《{v.title or ''}》：{v.summary or ''}"
            for i, v in enumerate(volumes)
        )
    else:
        ctx["volumes_summary"] = "（未设定）"

    return ctx


@router.post("/{project_id}/consistency/rescan", response_model=ConsistencyRescanResponse)
async def rescan_consistency(
    project_id: str,
    body: ConsistencyRescanRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ConsistencyRescanResponse:
    """修复完成后重新对当前数据库状态做全量一致性扫描。

    流程：
    1. 从 DB 重新构建项目上下文（境界、势力、人物境界、技能、道具、故事线、卷骨架）
    2. 调用与 Bootstrap Step 14 相同的 gen_consistency_scan prompt
    3. 覆盖写入 Project.extra.consistency_issues
    4. 返回最新问题列表

    Raises:
        HTTPException 404/403: 项目不存在或无权限。
        HTTPException 500: AI 调用或 DB 提交失败。
    """
    project = _owned_or_404(db, project_id, current_user)

    ctx = _build_rescan_ctx(db, project)

    profile = "gemini" if body.model_profile == "gemini" else "default"
    ai_svc = AIService(profile, db=db, llm_provider_id=body.llm_provider_id)
    svc_proxy = _AiSvcProxy(ai_svc, db)

    try:
        issues = await gen_consistency_scan(svc_proxy, project, ctx)
    except Exception as exc:
        logger.exception("consistency rescan 失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"重新扫描失败：{exc}")

    n = len(issues)
    unfixed = sum(1 for iss in issues if isinstance(iss, dict) and iss.get("status") != "fixed")
    message = f"重新扫描完成，发现 {unfixed} 处待确认项" if unfixed else "重新扫描完成，暂无矛盾项"

    return ConsistencyRescanResponse(issues=issues, count=n, message=message)
