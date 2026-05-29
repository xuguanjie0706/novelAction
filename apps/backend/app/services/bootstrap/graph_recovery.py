"""Bootstrap checkpoint 恢复辅助模块。

进程重启后 MemorySaver 清空，此模块负责从 DB 重建 Bootstrap ctx，
使 resume 在任意 gate 节点暂停后都能正确继续后续步骤。

从 graph.py 分离的原因：_rebuild_ctx_from_db 代码量大且职责独立，
提取后可保持 graph.py < 600 行（架构红线）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def rebuild_ctx_from_db(
    db,
    project_id: str,
    gd: dict,
    logline: str,
    premise: str,
    target_words: int,
) -> dict:
    """根据已落库数据重建 Bootstrap ctx，供进程重启后 resume 使用。

    重建逻辑按 gate 类型分层：
    - gate_power_systems 暂停：需要 positioning + power_systems 数据
    - gate_characters    暂停：还需要 char_names / char_profiles 等
    - gate_volumes       暂停：还需要 _volume_ids / chapter_quota 等

    Args:
        db: 数据库会话。
        project_id: 项目 ID（字符串）。
        gd: BootstrapRun.gate_data 字典。
        logline: 小说创意一句话。
        premise: 作者补充说明。
        target_words: 全书目标字数。

    Returns:
        尽量完整的 ctx 字典，缺失字段保持默认值，不会引发 KeyError。
    """
    from app.models import Project

    positioning = gd.get("positioning") or {}
    if not project_id:
        return {
            "logline": logline,
            "premise": premise,
            "target_words": target_words,
            "positioning": positioning,
        }

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        return {
            "logline": logline,
            "premise": premise,
            "target_words": target_words,
            "positioning": positioning,
        }

    from app.services.bootstrap.ctx_merge import merge_ctx_with_project

    ctx = merge_ctx_with_project(
        db,
        proj,
        {
            "logline": logline or (proj.logline or ""),
            "premise": premise or (proj.premise or ""),
            "target_words": target_words,
            "positioning": positioning or (proj.extra or {}).get("positioning") or {},
        },
    )
    return ctx
