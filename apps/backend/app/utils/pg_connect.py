"""PostgreSQL 连接参数：远程库在 Bootstrap 长 LLM 等待时易 idle 断连，统一加 TCP keepalive。"""

from __future__ import annotations


def pg_connect_kwargs() -> dict:
    """psycopg2 / psycopg3 通用 keepalive 参数。"""
    return {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
