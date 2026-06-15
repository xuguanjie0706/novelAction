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
from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiRelation

logger = logging.getLogger("dabai.persist")


def make_chapter_outline_row(
    project_id: UUID,
    volume_id: UUID | None,
    ch: dict,
    fallback_number: int = 0,
) -> DabaiChapterOutline:
    """章纲 dict → DabaiChapterOutline 行（bootstrap 与写作期卷展开共用同一字段映射）。

    Args:
        project_id: 所属项目 id。
        volume_id: 目标卷 id（bootstrap=第1卷；卷展开=被展开卷）。
        ch: pipeline 归一化后的章纲 dict（normalize_chapter 产物）。
        fallback_number: ch 缺 chapter_number 时的兜底全局章号。
    """
    return DabaiChapterOutline(
        project_id=project_id, volume_id=volume_id,
        chapter_number=int(ch.get("chapter_number", fallback_number)),
        title=ch.get("title"), shuang_type=ch.get("shuang_type"),
        location=ch.get("location"),
        yaqu_setup=ch.get("yaqu_setup"), emotion_turn=ch.get("emotion_turn"),
        yinbao=ch.get("yinbao"),
        shuang_payoff=ch.get("shuang_payoff"), witnesses=ch.get("witnesses") or [],
        end_hook=ch.get("end_hook"), new_info_count=int(ch.get("new_info_count", 1)),
        involved_characters=ch.get("involved_characters") or [],
        is_big_beat=bool(ch.get("is_big_beat", False)),
        expected_words=int(ch.get("expected_words", 2000)),
        realm_rank=ch.get("realm_rank"),
        realm_sub_rank=ch.get("realm_sub_rank"),
    )


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
            benchmark={}, positioning={}, golden_finger={}, power_ladder={},
            linter_report={}, meta={}, failed_steps=[],
        )
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.project)
        return self.project

    def merge_extra(self, updates: dict) -> None:
        """合并写 project.extra（JSON 列须整体替换才能触发脏标记）。"""
        p = self.project
        p.extra = {**(p.extra or {}), **{k: v for k, v in updates.items()
                                         if v is not None}}

    def save_step(self, step: str, data: Any) -> None:
        """按步骤把产物写入对应列/表，立即 commit。"""
        p = self.project
        assert p is not None
        if step in ("benchmark", "positioning", "golden_finger", "power_ladder"):
            setattr(p, step, data or {})
        elif step == "antagonist_ladder":
            self.merge_extra({"antagonist_ladder": data or []})
        elif step == "mystery_schedule":
            self.merge_extra({"mystery_schedule": data or {}})
            self._save_mystery_clues(data or {})
        elif step == "title_blurb":
            self.merge_extra({"title_blurb": data or {}})
            chosen = str((data or {}).get("chosen_title") or "").strip()
            if chosen:
                p.title = chosen[:120]
        elif step == "factions":
            for i, f in enumerate(data or []):
                self.db.add(DabaiFaction(
                    project_id=p.id, name=f.get("name", ""), stance=f.get("stance"),
                    role=f.get("role"), power_tier=f.get("power_tier"),
                    note=f.get("note"), locations=f.get("locations") or [],
                    sort_order=i,
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
                    summary=s.get("summary"), nodes=s.get("nodes") or [],
                    bound_characters=s.get("bound_characters") or [], sort_order=i,
                ))
        elif step == "story_assets":
            self._save_story_assets(data or {})
            # 规划快照：vol 2+ build_expand_ctx 回读，给 chapter_design_context 提供
            # relations_block（开局关系张力）与 assets_block（剧情资产台账）上下文。
            # 不存则 vol 2+ 的全量章纲路径（volume_chapters/beat_sequence/chapter_outlines）
            # 的 assets/relations 注入块均为空串。
            self.merge_extra({"story_assets": data or {}})
        elif step == "volumes":
            self._save_volumes(data or [])
        self.db.commit()

    def _save_mystery_clues(self, data: dict) -> None:
        """谜题排程 → dabai_clues 种子（open，复盘期回收；按标题去重防与资产线索重复）。"""
        p = self.project
        existing = {
            (c.title or "").strip()
            for c in self.db.query(DabaiClue.title)
            .filter(DabaiClue.project_id == p.id).all()
        }
        for m in (data.get("mysteries") or [])[:6]:
            if not isinstance(m, dict):
                continue
            title = str(m.get("name") or "").strip()[:120]
            if not title or title in existing:
                continue
            desc = (
                f"[谜题] {str(m.get('hook_question') or '')[:60]}"
                f"（第{m.get('final_reveal_volume', '?')}卷揭底；"
                f"真相：{str(m.get('essence') or '')[:80]}）"
            )
            self.db.add(DabaiClue(
                project_id=p.id, title=title, clue_type="foreshadow",
                description=desc, chapter_planted=0, status="open",
                source="bootstrap",
            ))
            existing.add(title)

    def _protagonist_name(self) -> str:
        """主角名（characters 步已落库后调用）。"""
        rows = (
            self.db.query(DabaiCharacter)
            .filter(DabaiCharacter.project_id == self.project.id)
            .order_by(DabaiCharacter.sort_order)
            .all()
        )
        for c in rows:
            if "主角" in (c.role or ""):
                return c.name
        return rows[0].name if rows else "主角"

    def _save_story_assets(self, data: dict) -> None:
        """剧情资产+初始关系分流落库（台账种子）。

        - debut=start（开局既有）→ DabaiAsset(source=seed, active)
        - debut=later（剧情规划）→ DabaiClue(foreshadow, chapter_planted=0)
          ——未获得的东西不得进「当前台账」注入，否则模型会提前用（能力漂移）
        - initial_relations → DabaiRelation(source=seed, history 锚定第0章)
        """
        from app.services.dabai.story_asset_debut import resolve_plot_asset_debut

        p = self.project
        protag = self._protagonist_name()
        for a in (data.get("plot_assets") or [])[:8]:
            if not isinstance(a, dict) or not str(a.get("name") or "").strip():
                continue
            kind = str(a.get("kind") or "item").lower()
            kind = kind if kind in ("skill", "item") else "item"
            name = str(a["name"]).strip()[:120]
            desc = f"[{a.get('plot_role', '')}] {str(a.get('description') or '')[:200]}"
            if resolve_plot_asset_debut(a, protag) == "later":
                self.db.add(DabaiClue(
                    project_id=p.id, title=name, clue_type="foreshadow",
                    description=f"{desc}（规划第{a.get('planned_volume', '?')}卷登场）",
                    chapter_planted=0, status="open", source="bootstrap",
                ))
            else:
                self.db.add(DabaiAsset(
                    project_id=p.id, kind=kind, name=name,
                    owner=str(a.get("owner") or protag).strip()[:100] or protag,
                    description=desc, status="active", source="seed",
                ))
        for r in (data.get("initial_relations") or [])[:10]:
            if not isinstance(r, dict) or not str(r.get("to") or "").strip():
                continue
            attitude = str(r.get("attitude") or "中立").strip()[:40]
            tension = str(r.get("tension") or "")[:200]
            self.db.add(DabaiRelation(
                project_id=p.id,
                from_name=str(r.get("from") or protag).strip()[:100] or protag,
                to_name=str(r["to"]).strip()[:100],
                attitude=attitude, note=tension, last_change_chapter=0,
                history=[{"chapter": 0, "attitude": attitude,
                          "reason": tension or "开局设定"}],
                source="seed",
            ))

    # 卷骨架深挖版的富字段（章段施工图/情绪收支/新登场人物/追读锚点）一并落 extra，
    # 供卷展开期 build_expand_ctx 回读、给章纲生成更稠密的卷级上下文。
    _VOL_EXTRA_KEYS = (
        "boss", "storyline_moves", "mystery_moves",
        "opening_setup", "chapter_beat_map", "emotion_ledger",
        "new_characters", "new_settings", "reader_hook",
    )

    def _save_volumes(self, vols: list[dict]) -> None:
        p = self.project
        rows: list[DabaiVolume] = []
        for v in vols:
            extra = {k: v[k] for k in self._VOL_EXTRA_KEYS if v.get(k)}
            row = DabaiVolume(
                project_id=p.id,
                volume_number=int(v.get("volume_number", len(rows) + 1)),
                title=v.get("title"), phase=v.get("phase"),
                planned_chapters=int(v.get("planned_chapters", self.cfg.volume_chapters)),
                big_beats=v.get("big_beats") or [],
                volume_climax=v.get("volume_climax"), end_hook=v.get("end_hook"),
                realm_start_rank=v.get("realm_start_rank"),
                realm_end_rank=v.get("realm_end_rank"),
                extra=extra,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        if rows:
            self.first_volume_id = rows[0].id  # 章纲默认归第 1 卷

    def save_chapter_batch(self, batch: list[dict]) -> int:
        """落一批章纲（章号沿用全卷连续序），返回累计章数。

        bootstrap 路径只展开第 1 卷，volume_id 归第 1 卷；写作期按卷展开
        走 make_chapter_outline_row（带目标卷 id），不经过本方法。
        """
        p = self.project
        for ch in batch:
            self._chapter_seq += 1
            self.db.add(make_chapter_outline_row(
                p.id, self.first_volume_id, ch, fallback_number=self._chapter_seq,
            ))
        self.db.commit()
        return self._chapter_seq

    def finalize(
        self, linter_report: dict | None, failed_steps: list[str], meta: dict,
        extra_update: dict | None = None,
    ) -> DabaiProject:
        p = self.project
        if extra_update:
            self.merge_extra(extra_update)
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
                 "antagonist_ladder", "factions", "characters", "storylines",
                 "story_assets", "mystery_schedule", "volumes", "title_blurb"):
        if ctx.get(step) is not None:
            persister.save_step(step, ctx[step])
    if ctx.get("chapter_outlines"):
        persister.save_chapter_batch(ctx["chapter_outlines"])
    project = persister.finalize(
        result.linter_report, result.failed_steps, result.to_json().get("meta", {}),
        extra_update={"beat_sequence_vol1": ctx.get("beat_sequence") or None},
    )
    if persister._chapter_seq > 0 and not result.failed_steps:
        from app.services.dabai.lab_outline_lint import run_dabai_project_linter
        run_dabai_project_linter(db, project)
    return project
