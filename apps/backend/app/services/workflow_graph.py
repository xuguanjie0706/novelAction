import asyncio
import inspect
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import WebSocket


WorkflowContext = dict[str, Any]
WorkflowNodeHandler = Callable[[WorkflowContext], WorkflowContext | Awaitable[WorkflowContext | None] | None]


@dataclass(frozen=True)
class WorkflowNode:
    key: str
    label: str
    handler: WorkflowNodeHandler


class WorkflowGraph:
    def __init__(self, nodes: list[WorkflowNode]):
        self.nodes = nodes


class WorkflowRunRegistry:
    """
    Lightweight in-process workflow bus.

    This deliberately keeps the first graph layer small: business nodes stay
    plain Python functions, while this registry owns progress replay and
    WebSocket fan-out. A persistent table/Redis bus can replace it later
    without changing the workflow node contracts.
    """

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def create_run(self, workflow_type: str, metadata: dict[str, Any] | None = None) -> str:
        run_id = str(uuid.uuid4())
        async with self._lock:
            self._runs[run_id] = {
                "workflow_type": workflow_type,
                "metadata": metadata or {},
                "status": "pending",
                "events": [],
            }
            self._subscribers[run_id] = set()
        await self.publish(run_id, {
            "event": "workflow_created",
            "run_id": run_id,
            "workflow_type": workflow_type,
            "metadata": metadata or {},
        })
        return run_id

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        payload = {"run_id": run_id, **event}
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run["events"].append(payload)
            if payload.get("event") in {"workflow_done", "workflow_error"}:
                run["status"] = "done" if payload["event"] == "workflow_done" else "error"
            elif payload.get("event") == "workflow_started":
                run["status"] = "running"
            subscribers = list(self._subscribers.get(run_id, set()))
        for queue in subscribers:
            await queue.put(payload)

    async def run_graph(self, run_id: str, graph: WorkflowGraph, context: WorkflowContext) -> WorkflowContext:
        await self.publish(run_id, {
            "event": "workflow_started",
            "total_nodes": len(graph.nodes),
        })
        try:
            current = dict(context)
            for index, node in enumerate(graph.nodes, start=1):
                await self.publish(run_id, {
                    "event": "node_start",
                    "node_key": node.key,
                    "label": node.label,
                    "step": index,
                    "total": len(graph.nodes),
                })
                result = node.handler(current)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, dict):
                    current = result
                await self.publish(run_id, {
                    "event": "node_done",
                    "node_key": node.key,
                    "label": node.label,
                    "step": index,
                    "total": len(graph.nodes),
                })
            await self.publish(run_id, {
                "event": "workflow_done",
                "result": current.get("result"),
            })
            return current
        except Exception as exc:
            await self.publish(run_id, {
                "event": "workflow_error",
                "message": str(exc),
            })
            raise

    async def stream_to_websocket(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                await websocket.send_json({
                    "event": "workflow_error",
                    "run_id": run_id,
                    "message": "Workflow run not found",
                })
                await websocket.close()
                return
            replay = list(run["events"])
            self._subscribers.setdefault(run_id, set()).add(queue)

        try:
            for event in replay:
                await websocket.send_json(event)
                if event.get("event") in {"workflow_done", "workflow_error"}:
                    await websocket.close()
                    return

            while True:
                event = await queue.get()
                await websocket.send_json(event)
                if event.get("event") in {"workflow_done", "workflow_error"}:
                    await websocket.close()
                    return
        finally:
            async with self._lock:
                self._subscribers.get(run_id, set()).discard(queue)


workflow_runs = WorkflowRunRegistry()
