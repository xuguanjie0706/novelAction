#!/usr/bin/env python3
"""
pgvector 索引验证脚本
=====================
用法：
    cd apps/backend
    source .venv/bin/activate      # 或 conda activate <env>
    python verify_pgvector.py

    # 可选：指定查询词进行语义搜索测试
    python verify_pgvector.py --query "主角突破金丹期" --top-k 5

    # 批量补跑缺失 embedding（适合迁移后修复历史数据）
    python verify_pgvector.py --reembed

检查项：
  [1] pgvector Python 包是否安装
  [2] PostgreSQL vector 扩展是否启用
  [3] memory_chunks 表是否有 embedding 列及其维度
  [4] HNSW 索引是否存在
  [5] 已索引（non-NULL embedding）条数 vs 总条数
  [6] 随机一条 chunk 的 embedding 摘要（维度 / 前3值 / 后3值 / L2 norm）
  [7] 语义搜索测试（默认 query="主角" top-k=3）
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import textwrap
import time
from pathlib import Path

# ── 路径处理：支持从项目根或 apps/backend 下运行 ────────────────────────────
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

# 让 pydantic_settings 能找到 .env
os.chdir(_here)

# ── 颜色输出（ANSI，非 TTY 时自动关闭） ──────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


OK   = _c("32", "✓")
FAIL = _c("31", "✗")
WARN = _c("33", "!")
INFO = _c("36", "i")
SEP  = _c("90", "─" * 60)


def _section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {_c('1', title)}")
    print(SEP)


def _ok(msg: str) -> None:
    print(f"  {OK}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {FAIL}  {_c('31', msg)}")


def _warn(msg: str) -> None:
    print(f"  {WARN}  {_c('33', msg)}")


def _info(msg: str) -> None:
    print(f"  {INFO}  {msg}")


# ────────────────────────────────────────────────────────────────────────────
# [1] pgvector Python 包
# ────────────────────────────────────────────────────────────────────────────

def check_python_package() -> bool:
    _section("[1] pgvector Python 包")
    try:
        import pgvector
        version = getattr(pgvector, "__version__", "unknown")
        _ok(f"pgvector 已安装，版本 {version}")
        return True
    except ImportError:
        _fail("pgvector 未安装")
        _info("修复：pip install pgvector  （或 pip install -r requirements.txt）")
        return False


# ────────────────────────────────────────────────────────────────────────────
# [2] PostgreSQL vector 扩展
# ────────────────────────────────────────────────────────────────────────────

def check_pg_extension(conn) -> bool:
    _section("[2] PostgreSQL vector 扩展")
    try:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if row:
            _ok(f"vector 扩展已启用，版本 {row[0]}")
            return True
        else:
            _fail("vector 扩展未安装（pg_extension 中无 'vector' 行）")
            _info("修复（需 superuser）：CREATE EXTENSION vector;")
            _info("或运行：alembic upgrade head")
            return False
    except Exception as exc:
        _fail(f"查询 pg_extension 失败：{exc}")
        return False


# ────────────────────────────────────────────────────────────────────────────
# [3] embedding 列存在 + 维度
# ────────────────────────────────────────────────────────────────────────────

def check_embedding_column(conn, expected_dim: int) -> bool:
    _section("[3] memory_chunks.embedding 列")
    try:
        row = conn.execute("""
            SELECT atttypmod
            FROM   pg_attribute
            JOIN   pg_class ON pg_class.oid = pg_attribute.attrelid
            WHERE  pg_class.relname = 'memory_chunks'
              AND  pg_attribute.attname = 'embedding'
              AND  pg_attribute.attnum  > 0
        """).fetchone()

        if row is None:
            _fail("embedding 列不存在")
            _info("修复：alembic upgrade head")
            return False

        actual_dim = row[0]          # vector(N) 存为 atttypmod
        if actual_dim == expected_dim:
            _ok(f"embedding 列存在，维度 = {actual_dim}（与 EMBEDDING_DIM 一致）")
            return True
        else:
            _warn(
                f"embedding 列维度 {actual_dim} ≠ EMBEDDING_DIM={expected_dim}；"
                "需 DROP COLUMN + 重建，历史向量全部作废"
            )
            _info("修复：修改 .env 的 EMBEDDING_DIM，再 alembic upgrade head")
            return False
    except Exception as exc:
        _fail(f"查询列信息失败：{exc}")
        return False


# ────────────────────────────────────────────────────────────────────────────
# [4] HNSW 索引
# ────────────────────────────────────────────────────────────────────────────

def check_hnsw_index(conn) -> bool:
    _section("[4] HNSW 索引")
    try:
        row = conn.execute("""
            SELECT indexname, indexdef
            FROM   pg_indexes
            WHERE  tablename = 'memory_chunks'
              AND  indexname  = 'idx_memory_chunks_embedding_cosine'
        """).fetchone()

        if row:
            _ok(f"索引存在：{row[0]}")
            _info(f"定义：{row[1]}")
            return True
        else:
            _warn("HNSW 索引不存在（余弦检索会退化为全表扫描）")
            _info("修复：alembic upgrade head  或手动：")
            _info("  CREATE INDEX idx_memory_chunks_embedding_cosine")
            _info("  ON memory_chunks USING hnsw (embedding vector_cosine_ops);")
            return False
    except Exception as exc:
        _fail(f"查询索引失败：{exc}")
        return False


# ────────────────────────────────────────────────────────────────────────────
# [5] 已索引条数
# ────────────────────────────────────────────────────────────────────────────

def check_indexed_count(conn) -> tuple[int, int]:
    _section("[5] 已索引条数")
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM memory_chunks"
        ).fetchone()[0]
        indexed = conn.execute(
            "SELECT COUNT(*) FROM memory_chunks WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        missing = total - indexed

        _info(f"总记忆条数      : {total}")
        _info(f"已向量化（indexed）: {indexed}")
        if missing == 0:
            _ok("全部条目已向量化")
        else:
            _warn(f"还有 {missing} 条缺失 embedding（可用 --reembed 补跑）")
        return total, indexed
    except Exception as exc:
        _fail(f"查询条数失败：{exc}")
        return 0, 0


# ────────────────────────────────────────────────────────────────────────────
# [6] 单条 embedding 摘要
# ────────────────────────────────────────────────────────────────────────────

def check_sample_embedding(conn) -> None:
    _section("[6] 样本 embedding 摘要")
    try:
        row = conn.execute("""
            SELECT id, title, memory_type, chapter_number,
                   embedding::text
            FROM   memory_chunks
            WHERE  embedding IS NOT NULL
            ORDER  BY created_at DESC
            LIMIT  1
        """).fetchone()

        if row is None:
            _warn("无已向量化的记忆条目，跳过摘要")
            return

        chunk_id, title, mtype, chap_no, vec_text = row

        # 解析向量文本 "[0.1, 0.2, ...]"
        raw = vec_text.strip("[]")
        vals = [float(v) for v in raw.split(",")]
        dim = len(vals)

        import math
        l2 = math.sqrt(sum(v * v for v in vals))

        _ok(f"chunk_id    : {chunk_id}")
        _info(f"标题        : {title or '（无）'}")
        _info(f"类型/章节   : {mtype} / 第 {chap_no} 章")
        _info(f"向量维度    : {dim}")
        _info(f"前 3 值     : {[round(v, 6) for v in vals[:3]]}")
        _info(f"后 3 值     : {[round(v, 6) for v in vals[-3:]]}")
        _info(f"L2 norm     : {l2:.6f}（≈1.0 说明已归一化）")
    except Exception as exc:
        _fail(f"查询样本失败：{exc}")


# ────────────────────────────────────────────────────────────────────────────
# [7] 语义搜索测试
# ────────────────────────────────────────────────────────────────────────────

async def check_semantic_search(query: str, top_k: int) -> None:
    _section(f"[7] 语义搜索测试  query={repr(query)}  top_k={top_k}")
    try:
        from app.services.embedding_service import embed_texts
        from app.config import settings

        embed_base = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
        _info(f"embedding 端点 : {embed_base}")
        _info(f"embedding 模型 : {settings.EMBEDDING_MODEL}")
        _info(f"向量维度       : {settings.EMBEDDING_DIM}")

        t0 = time.perf_counter()
        vecs = await embed_texts([query])
        elapsed_embed = (time.perf_counter() - t0) * 1000

        if not vecs:
            _fail("embed_texts 返回空列表，请检查 embedding 服务是否启动")
            return

        vec = vecs[0]
        _ok(
            f"向量化成功：{len(vec)} 维，耗时 {elapsed_embed:.1f} ms"
        )

        # 直连数据库做 pgvector 查询
        from sqlalchemy import create_engine, text as sa_text
        engine = create_engine(settings.DATABASE_URL)

        if len(vec) != settings.EMBEDDING_DIM:
            _fail(
                f"向量维度 {len(vec)} ≠ EMBEDDING_DIM={settings.EMBEDDING_DIM}，"
                "请检查 EMBEDDING_MODEL 与 .env 配置"
            )
            return

        vec_str = "[" + ",".join(str(v) for v in vec) + "]"

        with engine.connect() as conn:
            t1 = time.perf_counter()
            rows = conn.execute(sa_text("""
                SELECT id, title, memory_type, chapter_number,
                       1 - (embedding <=> CAST(:qv AS vector)) AS cosine_sim
                FROM   memory_chunks
                WHERE  embedding IS NOT NULL
                ORDER  BY embedding <=> CAST(:qv AS vector)
                LIMIT  :top_k
            """), {"qv": vec_str, "top_k": top_k}).fetchall()
            elapsed_search = (time.perf_counter() - t1) * 1000

        if not rows:
            _warn("检索结果为空（数据库中无已向量化的记忆条目）")
            return

        _ok(f"pgvector 检索耗时 {elapsed_search:.1f} ms，返回 {len(rows)} 条：")
        print()
        for rank, r in enumerate(rows, 1):
            sim = r[4]
            sim_bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
            print(
                f"    #{rank}  [{sim_bar}] {sim:.4f}  "
                f"「{r[1] or '无标题'}」  "
                f"类型={r[2]}  第{r[3]}章"
            )
        print()
    except Exception as exc:
        _fail(f"语义搜索测试失败：{exc}")
        import traceback
        traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# --reembed：批量补跑缺失 embedding
# ────────────────────────────────────────────────────────────────────────────

async def do_reembed() -> None:
    _section("补跑缺失 embedding（--reembed）")
    try:
        from app.config import settings
        from app.database import SessionLocal
        from app.models.memory import MemoryChunk
        from app.services.embedding_service import embed_chunks_bulk

        with SessionLocal() as db:
            chunks = (
                db.query(MemoryChunk.id, MemoryChunk.title, MemoryChunk.content)
                .filter(MemoryChunk.embedding == None)  # noqa: E711
                .all()
            )

        if not chunks:
            _ok("无缺失 embedding，无需补跑")
            return

        _info(f"待补跑 {len(chunks)} 条……")
        pairs = [
            (c.id, f"{c.title or ''}\n{c.content}".strip())
            for c in chunks
        ]
        t0 = time.perf_counter()
        ok_count = await embed_chunks_bulk(pairs, SessionLocal)
        elapsed = time.perf_counter() - t0
        _ok(f"补跑完成：成功 {ok_count}/{len(chunks)} 条，耗时 {elapsed:.1f} s")
    except Exception as exc:
        _fail(f"补跑失败：{exc}")
        import traceback
        traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# 主函数
# ────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="pgvector 索引验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            示例：
              python verify_pgvector.py
              python verify_pgvector.py --query "青云宗叛徒" --top-k 5
              python verify_pgvector.py --reembed
        """),
    )
    parser.add_argument("--query", default="主角", help="语义搜索测试用的查询词（默认 '主角'）")
    parser.add_argument("--top-k", type=int, default=3, help="语义搜索返回条数（默认 3）")
    parser.add_argument("--reembed", action="store_true", help="批量补跑缺失 embedding 后退出")
    args = parser.parse_args()

    print(_c("1;36", "\n  pgvector 索引验证报告"))
    print(_c("90", f"  {Path(__file__).name}  —  {time.strftime('%Y-%m-%d %H:%M:%S')}"))

    # [1] Python 包
    has_pgvector_pkg = check_python_package()
    if not has_pgvector_pkg:
        print("\n" + _c("31", "  ⚠  pgvector Python 包缺失，后续检查将跳过。请先安装后重试。\n"))
        sys.exit(1)

    # 连接数据库（用 SQLAlchemy engine 的原生连接）
    try:
        from app.config import settings
        from sqlalchemy import create_engine, text as sa_text
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))  # 连通性测试

        _section("数据库连接")
        _ok(f"已连接：{settings.DATABASE_URL.split('@')[-1]}")  # 隐去账密
    except Exception as exc:
        _section("数据库连接")
        _fail(f"连接失败：{exc}")
        sys.exit(1)

    with engine.connect() as conn:
        ok_ext = check_pg_extension(conn)
        if not ok_ext:
            print("\n" + _c("33", "  ⚠  vector 扩展未安装，跳过列/索引检查。\n"))
            sys.exit(1)

        check_embedding_column(conn, settings.EMBEDDING_DIM)
        check_hnsw_index(conn)
        check_indexed_count(conn)
        check_sample_embedding(conn)

    # --reembed
    if args.reembed:
        await do_reembed()
        print(f"\n{SEP}\n")
        return

    # [7] 语义搜索
    await check_semantic_search(args.query, args.top_k)

    print(f"\n{SEP}")
    print(_c("1", "  验证完成。如有 ✗ 项请按提示修复后重跑。"))
    print(f"{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
