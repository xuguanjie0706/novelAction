"""大白文 bootstrap 产物 → dabai_* 表落库（增量 + 一次性两种用法）。

持久化优先（硬规则）：生成结果必须落 PostgreSQL。
DabaiPersister 支持**增量**：先 create（status=generating），再随事件流逐步 save，
最后 finalize（写 linter + status）。SSE 路由用它边生成边落库；
persist_bootstrap_result 是非流式一次性封装（复用同一持久化逻辑）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import (
    DabaiCharacter, DabaiChapterOutline, DabaiFaction,
    DabaiProject, DabaiStoryline, DabaiVolume,
)

logger = logging.getLogger("dabai.persist")


class DabaiPersister:
    """一次生成的增量落库器。每个 save_* 立即 commit，保证中断也不丢已生成部分。"""

    def __init__(self, db: Session, cfg: Any, user_id: UUID | None):
        self.db = db
        self.cfg = cfg
        self.user_id = user_id
        self.project: DabaiProject | None = None
        self.first_volume_id: UUID | None = None
        self._chapter_seq = 0

    # ── 生命周期 ──────────────────────────────────────────────────────────────
    def create(self) -> DabaiProject:
        """建项目行（status=generating），返回带 id 的 project。"""
        self.project = DabaiProject(
            user_id=self.user_id,
            logline=self.cfg.logline,
            title=(self.cfg.logline or "")[:40] or None,
            status="generating",
            mock=bool(self.cfg.mock),
            benchmark={}, positioning={}, golden_finger={}, power_ladder={},
            linter_report={}, meta={}, failed_steps=[],
        )
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.project)
        return self.project

    def save_step(self, step: str, data: Any) -> None:
        """按步骤把产物写入对应列/表，立即 commit。"""
        p = self.project
        assert p is not None
        if step in ("benchmark", "positioning", "golden_finger", "power_ladder"):
            setattr(p, step, data or {})
        elif step == "factions":
            for i, f in enumerate(data or []):
                self.db.add(DabaiFaction(
                    project_id=p.id, name=f.get("name", ""), stance=f.get("stance"),
                    role=f.get("role"), power_tier=f.get("power_tier"),
                    note=f.get("note"), sort_order=i,
                ))
        elif step == "characters":
            for i, c in enumerate(data or []):
                known = {"name", "role", "tier", "start_realm", "persona", "function"}
                extra = {k: v for k, v in c.items() if k not in known}
                self.db.add(DabaiCharacter(
                    project_id=p.id, name=c.get("name", ""), role=c.get("role"),
                    tier=c.get("tier"), start_realm=c.get("start_realm"),
                    persona=c.get("persona"), function=c.get("function"),
                    extra=extra, sort_order=i,
                ))
        elif step == "storylines":
            for i, s in enumerate(data or []):
                self.db.add(DabaiStoryline(
                    project_id=p.id, name=s.get("name", ""), type=s.get("type"),
                    summary=s.get("summary"), sort_order=i,
                ))
        elif step == "volumes":
            self._save_volumes(data or [])
        self.db.commit()

    def _save_volumes(self, vols: list[dict]) -> None:
        p = self.project
        rows: list[DabaiVolume] = []
        for v in vols:
            row = DabaiVolume(
                project_id=p.id,
                volume_number=int(v.get("volume_number", len(rows) + 1)),
                title=v.get("title"), phase=v.get("phase"),
                planned_chapters=int(v.get("planned_chapters", self.cfg.volume_chapters)),
                big_beats=v.get("big_beats") or [],
                volume_climax=v.get("volume_climax"), end_hook=v.get("end_hook"),
                realm_start_rank=v.get("realm_start_rank"),
                realm_end_rank=v.get("realm_end_rank"),
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        if rows:
            self.first_volume_id = rows[0].id  # 章纲默认归第 1 卷

    def save_chapter_batch(self, batch: list[dict]) -> int:
        """落一批章纲（章号沿用全卷连续序），返回累计章数。"""
        p = self.project
        for ch in batch:
            self._chapter_seq += 1
            self.db.add(DabaiChapterOutline(
                project_id=p.id, volume_id=self.first_volume_id,
                chapter_number=int(ch.get("chapter_number", self._chapter_seq)),
                title=ch.get("title"), shuang_type=ch.get("shuang_type"),
                yaqu_setup=ch.get("yaqu_setup"), emotion_turn=ch.get("emotion_turn"),
                yinbao=ch.get("yinbao"),
                shuang_payoff=ch.get("shuang_payoff"), witnesses=ch.get("witnesses") or [],
                end_hook=ch.get("end_hook"), new_info_count=int(ch.get("new_info_count", 1)),
                involved_characters=ch.get("involved_characters") or [],
                is_big_beat=bool(ch.get("is_big_beat", False)),
                expected_words=int(ch.get("expected_words", 2000)),
                realm_rank=ch.get("realm_rank"),
            ))
        self.db.commit()
        return self._chapter_seq

    def finalize(self, linter_report: dict | None, failed_steps: list[str], meta: dict) -> DabaiProject:
        p = self.project
        p.linter_report = linter_report or {}
        p.failed_steps = failed_steps or []
        p.meta = meta or {}
        p.status = "failed" if failed_steps else "generated"
        self.db.commit()
        self.db.refresh(p)
        logger.info("dabai 落库完成 project=%s 章=%d failed=%s",
                    p.id, self._chapter_seq, failed_steps)
        return p


def persist_bootstrap_result(db: Session, result: Any, user_id: UUID | None) -> DabaiProject:
    """非流式一次性落库：用 DabaiPersister 把完整 BootstrapResult 写入。"""
    ctx = result.ctx
    persister = DabaiPersister(db, result.cfg, user_id)
    persister.create()
    for step in ("benchmark", "positioning", "golden_finger", "power_ladder",
                 "factions", "characters", "storylines", "volumes"):
        if ctx.get(step) is not None:
            persister.save_step(step, ctx[step])
    if ctx.get("chapter_outlines"):
        persister.save_chapter_batch(ctx["chapter_outlines"])
    return persister.finalize(
        result.linter_report, result.failed_steps, result.to_json().get("meta", {}),
    )
