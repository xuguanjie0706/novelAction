"""大纲质检 / 修复工作流 WebSocket（浏览器用 ?token= JWT）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.workflow_graph import workflow_runs

ws_router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline-ws"])
@ws_router.websocket("/workflows/{run_id}/ws")
async def outline_workflow_websocket(
    project_id: str,
    run_id: str,
    websocket: WebSocket,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    """
    WS 鉴权约定：浏览器 WebSocket 不能设 Authorization 头，统一改为 ``?token=<JWT>`` 查询串。

    1. 解码 JWT，校验失败立即关闭（policy violation = 1008）
    2. 校验 project 归属当前用户，越权返回 4404 自定义码
    3. 通过后再交给 workflow_runs 推送事件流
    """
    from app.utils.auth import decode_access_token
    from app.models.user import User
    from app.models.project import Project

    if not token:
        await websocket.close(code=1008)
        return
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=1008)
        return
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        await websocket.close(code=1008)
        return
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.user_id != user.id:
        await websocket.close(code=4404)
        return

    await workflow_runs.stream_to_websocket(run_id, websocket)
