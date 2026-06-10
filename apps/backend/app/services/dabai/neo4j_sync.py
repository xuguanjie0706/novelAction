"""Neo4j 同步：debrief 提取的 graph_facts → 图节点/边。"""
from __future__ import annotations

import logging
from typing import Any

from app.services.graph_store.neo4j_client import get_driver, neo4j_enabled

logger = logging.getLogger(__name__)


def _char_key(project_id: str, name: str) -> str:
    return f"{project_id}:{name}"


def _loc_key(project_id: str, name: str) -> str:
    return f"{project_id}:{name}"


def apply_graph_facts(project_id: str, facts: list[dict]) -> dict:
    """写入图事实；Neo4j 不可用时返回 fallback 状态。"""
    if not neo4j_enabled():
        return {"status": "fallback", "applied": 0}
    driver = get_driver()
    if not driver:
        return {"status": "fallback", "applied": 0}

    applied = 0
    try:
        with driver.session() as session:
            session.run(
                "MERGE (p:Project {project_id: $pid}) SET p.updated = timestamp()",
                pid=str(project_id),
            )
            for fact in facts or []:
                if not isinstance(fact, dict):
                    continue
                ftype = (fact.get("type") or "").strip().lower()
                if ftype == "at_realm":
                    session.run(
                        """
                        MERGE (c:Character {key: $ck})
                        SET c.name = $name, c.project_id = $pid
                        MERGE (r:RealmLevel {key: $rk})
                        SET r.rank = $rank, r.project_id = $pid
                        MERGE (c)-[:AT_REALM {chapter: $ch}]->(r)
                        """,
                        ck=_char_key(project_id, fact.get("character", "")),
                        name=fact.get("character", ""),
                        pid=str(project_id),
                        rk=f"{project_id}:rank:{fact.get('realm_rank')}",
                        rank=fact.get("realm_rank"),
                        ch=fact.get("chapter"),
                    )
                    applied += 1
                elif ftype == "traveled":
                    session.run(
                        """
                        MERGE (c:Character {key: $ck})
                        SET c.name = $name, c.project_id = $pid
                        MERGE (l:Location {key: $lk})
                        SET l.name = $to, l.project_id = $pid
                        MERGE (c)-[:TRAVELED_TO {reason: $reason, chapter: $ch}]->(l)
                        """,
                        ck=_char_key(project_id, fact.get("character", "")),
                        name=fact.get("character", ""),
                        pid=str(project_id),
                        lk=_loc_key(project_id, fact.get("to", "")),
                        to=fact.get("to", ""),
                        reason=(fact.get("reason") or "")[:200],
                        ch=fact.get("chapter"),
                    )
                    applied += 1
                elif ftype == "relation":
                    session.run(
                        """
                        MERGE (a:Character {key: $ak})
                        SET a.name = $an, a.project_id = $pid
                        MERGE (b:Character {key: $bk})
                        SET b.name = $bn, b.project_id = $pid
                        MERGE (a)-[r:RELATES {edge: $edge}]->(b)
                        SET r.reason = $reason, r.chapter = $ch
                        """,
                        ak=_char_key(project_id, fact.get("a", "")),
                        an=fact.get("a", ""),
                        bk=_char_key(project_id, fact.get("b", "")),
                        bn=fact.get("b", ""),
                        pid=str(project_id),
                        edge=fact.get("edge", "RELATED"),
                        reason=(fact.get("reason") or "")[:200],
                        ch=fact.get("chapter"),
                    )
                    applied += 1
        return {"status": "ok", "applied": applied}
    except Exception as exc:
        logger.warning("neo4j_sync 失败 project=%s: %s", project_id, exc)
        return {"status": "error", "applied": applied, "message": str(exc)}


def build_graph_context_block(project_id: str, protagonist: str = "主角") -> str:
    """写章注入：主角当前境界/位置/敌对关系（零 LLM）。"""
    if not neo4j_enabled():
        return ""
    driver = get_driver()
    if not driver:
        return ""
    try:
        with driver.session() as session:
            rec = session.run(
                """
                MATCH (c:Character {key: $ck})-[:AT_REALM]->(r:RealmLevel)
                OPTIONAL MATCH (c)-[:TRAVELED_TO]->(l:Location)
                OPTIONAL MATCH (c)-[h:RELATES {edge: 'HOSTILE'}]->(e:Character)
                RETURN r.rank AS rank, l.name AS loc, collect(DISTINCT e.name) AS enemies
                ORDER BY h.chapter DESC LIMIT 1
                """,
                ck=_char_key(project_id, protagonist),
            ).single()
            if not rec:
                return ""
            enemies = "、".join(rec.get("enemies") or []) or "无"
            return (
                f"\n【图数据库·主角状态】境界档={rec.get('rank')} "
                f"近期位置={rec.get('loc') or '未知'} 敌对={enemies}\n"
            )
    except Exception:
        return ""
