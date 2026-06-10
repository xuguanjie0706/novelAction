"""Neo4j 图存储客户端（dabai 章末总结 · 关系/空间/境界事实）。"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_driver = None


def neo4j_enabled() -> bool:
    return bool((os.getenv("NEO4J_URI") or "").strip())


def get_driver():
    global _driver
    if _driver is not None:
        return _driver
    uri = (os.getenv("NEO4J_URI") or "").strip()
    if not uri:
        return None
    try:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(
            uri,
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "novelaction"),
            ),
        )
        return _driver
    except Exception as exc:
        logger.warning("Neo4j driver 初始化失败: %s", exc)
        return None


def ensure_schema() -> None:
    """启动时创建约束（幂等）。"""
    driver = get_driver()
    if not driver:
        return
    stmts = [
        "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
        "CREATE CONSTRAINT char_key IF NOT EXISTS FOR (c:Character) REQUIRE c.key IS UNIQUE",
        "CREATE CONSTRAINT loc_key IF NOT EXISTS FOR (l:Location) REQUIRE l.key IS UNIQUE",
    ]
    try:
        with driver.session() as session:
            for s in stmts:
                session.run(s)
    except Exception as exc:
        logger.warning("Neo4j schema ensure 失败: %s", exc)


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
