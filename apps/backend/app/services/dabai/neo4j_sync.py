"""Neo4j 同步：debrief 提取的 graph_facts → 图节点/边；写章期读取最新人物状态。

写入侧（apply_graph_facts）：AT_REALM / TRAVELED_TO / RELATES 三类事实，边上带 chapter。
读取侧（build_graph_context_block / fetch_character_states）：按 chapter 取**最新**事实，
供写正文 prompt 注入；Neo4j 未配置或不可用时一律静默降级为空（零阻塞）。

⚠️ 历史 bug 备忘：旧版读取用字面量「主角」做节点 key（与 debrief 写入的真实人名永不匹配），
且 Cypher 未按 chapter 排序导致命中旧状态。现读取必须传入真实人名。
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.graph_store.neo4j_client import get_driver, neo4j_enabled

logger = logging.getLogger(__name__)


def _char_key(project_id: str, name: str) -> str:
    return f"{project_id}:{name}"


def _loc_key(project_id: str, name: str) -> str:
    return f"{project_id}:{name}"


# ──────────────────────────── 写入侧 ────────────────────────────

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
                if ftype == "at_realm" and fact.get("character"):
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
                elif ftype == "traveled" and fact.get("character") and fact.get("to"):
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
                elif ftype == "relation" and fact.get("a") and fact.get("b"):
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


# ──────────────────────────── 读取侧 ────────────────────────────

_STATE_CYPHER = """
MATCH (c:Character {key: $ck})
OPTIONAL MATCH (c)-[ar:AT_REALM]->(r:RealmLevel)
WITH c, ar, r ORDER BY coalesce(ar.chapter, 0) DESC
WITH c, [x IN collect({rank: r.rank, chapter: ar.chapter}) WHERE x.rank IS NOT NULL][0] AS realm
OPTIONAL MATCH (c)-[t:TRAVELED_TO]->(l:Location)
WITH c, realm, t, l ORDER BY coalesce(t.chapter, 0) DESC
WITH c, realm,
     [x IN collect({loc: l.name, chapter: t.chapter, reason: t.reason})
      WHERE x.loc IS NOT NULL][..3] AS moves
OPTIONAL MATCH (c)-[h:RELATES]-(e:Character)
WHERE h.edge = 'HOSTILE'
RETURN realm, moves,
       [n IN collect(DISTINCT e.name) WHERE n IS NOT NULL][..6] AS enemies
"""


def _query_character_state(session: Any, project_id: str, name: str) -> dict | None:
    """单人物最新状态：境界（最新章）/ 行踪（近3次）/ 敌对名单。"""
    rec = session.run(_STATE_CYPHER, ck=_char_key(project_id, name)).single()
    if not rec:
        return None
    realm = rec.get("realm") or {}
    moves = [m for m in (rec.get("moves") or []) if isinstance(m, dict) and m.get("loc")]
    enemies = [e for e in (rec.get("enemies") or []) if e]
    if not realm and not moves and not enemies:
        return None
    return {
        "name": name,
        "realm_rank": realm.get("rank") if isinstance(realm, dict) else None,
        "realm_chapter": realm.get("chapter") if isinstance(realm, dict) else None,
        "moves": moves,          # [{loc, chapter, reason}] 最新在前
        "enemies": enemies,
    }


def fetch_character_states(project_id: str, names: list[str]) -> dict[str, dict]:
    """批量查询人物最新状态；不可用/未命中返回空 dict（调用方自行兜底 DB）。"""
    names = [n.strip() for n in names or [] if n and n.strip()]
    if not names or not neo4j_enabled():
        return {}
    driver = get_driver()
    if not driver:
        return {}
    out: dict[str, dict] = {}
    try:
        with driver.session() as session:
            for name in names[:8]:
                state = _query_character_state(session, project_id, name)
                if state:
                    out[name] = state
        return out
    except Exception as exc:
        logger.warning("neo4j 状态查询失败 project=%s: %s", project_id, exc)
        return out


def _format_moves(moves: list[dict]) -> str:
    parts = []
    for m in moves:
        ch = f"第{m['chapter']}章" if m.get("chapter") else ""
        reason = f"（{str(m['reason'])[:30]}）" if m.get("reason") else ""
        parts.append(f"{ch}→{m['loc']}{reason}")
    return " ⇐ ".join(parts)  # 最新在前


def build_graph_context_block(project_id: str, protagonist: str) -> str:
    """写章注入：主角当前境界/最新位置/行踪轨迹/敌对关系（零 LLM）。

    Args:
        protagonist: 主角**真实姓名**（必须与 debrief 落图时的人名一致，
            禁止传「主角」字面量——那是旧版恒空 bug 的根因）。
    """
    if not protagonist or not protagonist.strip():
        return ""
    states = fetch_character_states(project_id, [protagonist.strip()])
    state = states.get(protagonist.strip())
    if not state:
        return ""
    lines = [f"【人物图谱·{protagonist}当前状态（以此为准，禁止矛盾）】"]
    if state.get("realm_rank") is not None:
        upto = f"（截至第{state['realm_chapter']}章）" if state.get("realm_chapter") else ""
        lines.append(f"- 境界档：第{state['realm_rank']}档{upto}")
    moves = state.get("moves") or []
    if moves:
        lines.append(f"- 当前位置：{moves[0]['loc']}")
        if len(moves) > 1:
            lines.append(f"- 近期行踪：{_format_moves(moves)}")
    if state.get("enemies"):
        lines.append(f"- 敌对关系：{'、'.join(state['enemies'])}")
    return "\n".join(lines)
