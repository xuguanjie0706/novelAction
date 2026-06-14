"""
main.py — FastAPI 应用入口。

职责（仅此三项，禁止膨胀）：
  1. ASGI 中间件（ForwardedHost、CORS、计费上下文）
  2. 路由注册
  3. startup / health 钩子

Schema DDL 请走 alembic revision，禁止在此文件新增 _ensure_* 函数。
运行时 pgvector 维度感知操作及孤儿项目归属请见 app/startup/legacy_ddl.py。
"""
from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.dependencies import get_current_user, verify_project_access
from app.startup import run_pre_start_schema, run_startup_ddl
from app.startup.alembic_upgrade import get_alembic_current_revision, get_alembic_head_revision

# ── 路由导入 ───────────────────────────────────────────────────────────────
from app.routers import (
    projects,
    world_settings,
    characters,
    outline,
    chapters,
    chapter_indexes,
    ai,

    admin_llm,
    llm_public,
    admin_llm_calls,
    admin_cover_image_calls,
    admin_rag_logs,
    admin_memory_conflict_logs,
    admin_dabai_quality_logs,
    storylines,
    power_systems,
    skills,
    items,
    factions,
    foreshadows,
    quality_debts,
    scenes,
    reader_promises,
)
from app.routers import locations as locations_router
from app.routers import export as export_router
from app.routers import cover as cover_router
from app.routers import character_portrait as character_portrait_router
from app.routers import auth as auth_router
from app.routers import admin_auth as admin_auth_router
from app.routers import dashboard as dashboard_router
from app.routers import stats as stats_router
from app.routers import bootstrap_graph as bootstrap_graph_router
from app.routers import bootstrap_step_regen as bootstrap_step_regen_router
from app.routers import bootstrap_fanfic_routes as bootstrap_fanfic_router
from app.routers import credits as credits_router
from app.routers import admin_credits as admin_credits_router
from app.routers import admin_redeem_codes as admin_redeem_codes_router
from app.routers import admin_dashboard as admin_dashboard_router
from app.routers import consistency_fix as consistency_fix_router
from app.routers import jobs as jobs_router
from app.routers import fanqie_proxy as fanqie_proxy_router
from app.routers import dabai as dabai_router  # 大白文独立分支（爽点节拍器）
from app.routers import dabai_lab_ai as dabai_lab_ai_router  # dabai 实验书架写作期 AI（质检/复盘/记忆/线索/预警）
from app.routers import dabai_lab_archive as dabai_lab_archive_router  # dabai 实验书架情节档案（按章回看）
from app.routers import dabai_lab_chapter as dabai_lab_chapter_router  # dabai 实验书架清章写作产物
from app.routers import dabai_expand as dabai_expand_router  # dabai 按卷展开章纲（写作期懒展开）
from app.routers import dabai_export as dabai_export_router  # dabai 正文/章纲导出
from app.services.llm_config import seed_llm_from_env_if_empty
from app.services.cover_storage import ensure_cover_storage_dir, resolved_cover_storage_dir
from app.services.character_portrait_storage import (
    ensure_character_portrait_dir,
    resolved_character_portrait_dir,
)


# ── ASGI 中间件：信任反向代理 X-Forwarded-Host ────────────────────────────

def _server_from_x_forwarded_host(x_forwarded_host: str, scheme: str) -> tuple[str, int] | None:
    """
    解析 X-Forwarded-Host（Vite 代理 xfwd 时传入），修正 ASGI scope['server']，
    避免 FastAPI 尾部斜杠 307 的 Location 指向后端直连地址导致前端跨域失败。

    Args:
        x_forwarded_host: 请求头原始值（可含多项，取第一项）。
        scheme: 当前请求协议（"http" 或 "https"）。

    Returns:
        (host, port) 元组；解析失败时返回 None。
    """
    raw = x_forwarded_host.strip().split(",")[0].strip()
    if not raw:
        return None
    default_port = 443 if scheme == "https" else 80
    if "]:" in raw:
        bracket_end = raw.index("]")
        host = raw[1:bracket_end]
        rest = raw[bracket_end + 1:]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, default_port
    if raw.count(":") == 1:
        host, port_s = raw.split(":", 1)
        if port_s.isdigit():
            return host, int(port_s)
    idx = raw.rfind(":")
    if idx > 0 and raw[idx + 1:].isdigit():
        return raw[:idx], int(raw[idx + 1:])
    return raw, default_port


class ForwardedHostASGIMiddleware:
    """信任反向代理传入的 X-Forwarded-Host，修正重定向 URL 的 host/port。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for key, val in scope.get("headers") or []:
                if key.lower() != b"x-forwarded-host":
                    continue
                parsed = _server_from_x_forwarded_host(
                    val.decode("latin1"), scheme=scope.get("scheme") or "http"
                )
                if parsed:
                    scope["server"] = parsed
                break
        await self.app(scope, receive, send)


# ── 启动期 Schema 初始化 ──────────────────────────────────────────────────
# create_all 补 ORM 表 → Alembic upgrade head 补列/索引（见 app/startup/db_schema.py）。
# 新增字段请写 alembic revision；禁止在 main 增加 _ensure_* DDL。
run_pre_start_schema()
run_startup_ddl(engine)
seed_llm_from_env_if_empty()

# ── FastAPI 应用 ──────────────────────────────────────────────────────────
app = FastAPI(
    title="Novel System API",
    description="小说创作管理系统后端",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def llm_billing_user_context_middleware(request: Request, call_next):
    """
    将 Bearer JWT 解析为计费用户 UUID，写入 ContextVar。

    供 SamplingMixin 在 log_llm_call / 积分预检中统一读取，
    避免各路由漏传 AIService.user_id。使用 http 中间件而非 BaseHTTPMiddleware，
    保证与路由在同异步上下文内传播 ContextVar。
    """
    from app.services.llm_billing_context import (
        billing_user_id_from_authorization_header,
        pop_llm_billing_user,
        push_llm_billing_user,
    )
    tok = push_llm_billing_user(
        billing_user_id_from_authorization_header(request.headers.get("Authorization"))
    )
    try:
        return await call_next(request)
    finally:
        pop_llm_billing_user(tok)


@app.on_event("startup")
async def _on_startup() -> None:
    """
    FastAPI startup 事件：保存主事件循环 + 恢复残留生成任务。

    - 保存 uvicorn 主 event loop，供 sync 路由（线程池）中的 embed_*_async 使用。
    - 扫描服务重启前残留的 running/waiting_input/pending 任务做状态修复（非阻塞）。
    """
    from app.services.embedding_service import set_main_event_loop
    set_main_event_loop(asyncio.get_running_loop())

    from app.services.draft_graph.worker import recover_stale_jobs
    asyncio.create_task(recover_stale_jobs(), name="draft-job-recovery")

    # Bootstrap checkpointer：AsyncPostgresSaver（持久化到同一 PG，重启/多 worker 安全）
    from app.services.bootstrap.graph import init_bootstrap_graph
    from app.config import settings as _settings
    await init_bootstrap_graph(_settings.DATABASE_URL)

    from app.services.graph_store.neo4j_client import ensure_schema
    ensure_schema()

    from app.startup.logging_config import ensure_app_logging

    ensure_app_logging()

    import logging
    from app.services.tencent_cos import normalized_cover_storage_backend
    log = logging.getLogger(__name__)
    backend = normalized_cover_storage_backend()
    if backend == "local":
        log.info("封面存储：本地磁盘（COVER_STORAGE_BACKEND=local，默认）")
    else:
        from app.services.tencent_cos import _require_cos_config
        try:
            _require_cos_config()
            log.info("封面存储：腾讯云 COS 桶（COVER_STORAGE_BACKEND=cos）")
        except ValueError as e:
            log.error("封面 COS 配置不完整：%s", e)


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """关闭 Bootstrap AsyncPostgresSaver 连接池。"""
    from app.services.bootstrap.graph import close_bootstrap_graph
    from app.services.graph_store.neo4j_client import close_driver
    await close_bootstrap_graph()
    close_driver()


# ── 中间件注册 ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ForwardedHostASGIMiddleware)

# ── 路由注册 ──────────────────────────────────────────────────────────────
# auth：自身完成登录鉴权，不需要外层依赖。
app.include_router(auth_router.router, prefix="/api/v1")

# credits：需 Bearer token。
app.include_router(credits_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# admin 系列：路由内部校验 admin role，无需外层注入。
app.include_router(admin_credits_router.router, prefix="/api/v1")
app.include_router(admin_redeem_codes_router.router, prefix="/api/v1")
app.include_router(admin_auth_router.router, prefix="/api/v1")
app.include_router(admin_dashboard_router.router, prefix="/api/v1")
app.include_router(consistency_fix_router.router, prefix="/api/v1")

# projects：详情/子资源访问权由路由内部 _owned_or_404 校验。
app.include_router(projects.router, prefix="/api/v1")

# bootstrap：LangGraph 队列（串行步进 / 番茄专属）。
app.include_router(bootstrap_graph_router.router, prefix="/api/v1")
app.include_router(bootstrap_step_regen_router.router, prefix="/api/v1")
app.include_router(bootstrap_fanfic_router.router, prefix="/api/v1")

# 生成任务队列。
app.include_router(jobs_router.router, prefix="/api/v1")

# 番茄小说 API 代理（无需项目绑定，凭据独立存储）。
app.include_router(fanqie_proxy_router.router, prefix="/api/v1")

# 大白文独立分支：自带 pipeline + dabai_* 表，路由内部按 Bearer user 隔离。
app.include_router(dabai_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dabai_lab_ai_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dabai_lab_archive_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dabai_lab_chapter_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dabai_expand_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dabai_export_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# 全局只读 / 管理（需登录，不绑项目）。
app.include_router(admin_llm.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_llm_calls.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_cover_image_calls.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(admin_rag_logs.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(
    admin_memory_conflict_logs.router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    admin_dabai_quality_logs.router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)],
)
app.include_router(llm_public.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(dashboard_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(stats_router.router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# 项目子资源：统一挂 verify_project_access 校验归属。
_project_scoped_dep = [Depends(verify_project_access)]
app.include_router(world_settings.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(characters.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(outline.router, prefix="/api/v1", dependencies=_project_scoped_dep)
# 大纲工作流 WS：handler 内部以 ?token= 自行鉴权。
app.include_router(outline.ws_router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(chapter_indexes.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(ai.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(storylines.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(power_systems.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(skills.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(items.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(factions.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(foreshadows.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(export_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(quality_debts.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(scenes.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(reader_promises.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(locations_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(cover_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)
app.include_router(character_portrait_router.router, prefix="/api/v1", dependencies=_project_scoped_dep)

# ── 静态文件挂载 ──────────────────────────────────────────────────────────
ensure_cover_storage_dir()
app.mount(
    "/api/v1/covers/files",
    StaticFiles(directory=str(resolved_cover_storage_dir())),
    name="novel_cover_files",
)
ensure_character_portrait_dir()
app.mount(
    "/api/v1/character-portraits/files",
    StaticFiles(directory=str(resolved_character_portrait_dir())),
    name="novel_character_portrait_files",
)


@app.get("/health")
def health():
    """服务健康检查端点（含 Alembic revision，便于确认库已与代码同步）。"""
    head = get_alembic_head_revision()
    current = get_alembic_current_revision(engine)
    schema_ok = current == head
    payload: dict = {
        "status": "ok" if schema_ok else "degraded",
        "version": "0.1.0",
        "alembic_current": current,
        "alembic_head": head,
        "schema_aligned": schema_ok,
    }
    if not schema_ok:
        payload["schema_hint"] = (
            "数据库迁移落后于代码。请在 apps/backend 执行：python -m app.cli.db_upgrade"
        )
    return payload
