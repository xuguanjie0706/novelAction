# Chapter Postprocess And Editor Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build automatic chapter postprocess queueing after meaningful saves, persist postprocess results, and split the writing experience into planning, manuscript, and aftercare surfaces without breaking current chapter editing.

**Architecture:** The backend will gain chapter planning fields plus a `chapter_postprocess_reports` store and a single SSE orchestration endpoint that runs quality check, suggestions, memory extraction, and auto debrief in sequence. The frontend will extend the existing generation queue into a generic AI task queue, auto-enqueue chapter postprocess work after AI-save and meaningful manual saves, then progressively extract `ChapterEditor.tsx` into focused planning and aftercare panels while preserving the current manuscript editing flow.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React 18, TypeScript, Zustand, Vite, TipTap, SSE, pytest, Vitest, React Testing Library

---

### Task 1: Add Minimal Test Harnesses For Backend And Client

**Files:**
- Create: `apps/backend/tests/conftest.py`
- Create: `apps/backend/tests/test_chapter_postprocess_router.py`
- Create: `apps/client/src/test/setup.ts`
- Create: `apps/client/src/components/Layout/GenerationQueuePanel.test.tsx`
- Modify: `apps/backend/requirements.txt`
- Modify: `apps/client/package.json`
- Modify: `apps/client/tsconfig.json`
- Modify: `apps/client/vite.config.ts`

- [ ] **Step 1: Add backend test dependencies**

Update [requirements.txt](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/requirements.txt) to include the minimum backend test stack:

```txt
pytest==8.3.2
pytest-asyncio==0.23.8
```

- [ ] **Step 2: Add client test dependencies and scripts**

Update [package.json](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/package.json) with:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "test": "vitest run"
},
"devDependencies": {
  "@testing-library/jest-dom": "^6.6.3",
  "@testing-library/react": "^16.0.1",
  "@testing-library/user-event": "^14.5.2",
  "jsdom": "^25.0.1",
  "vitest": "^2.1.1"
}
```

- [ ] **Step 3: Configure backend test database fixture**

Create [conftest.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/tests/conftest.py) with a SQLite test DB and dependency override:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_chapter_postprocess.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 4: Configure client test setup**

Create [setup.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/test/setup.ts):

```ts
import '@testing-library/jest-dom'
```

Update [vite.config.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/vite.config.ts) to include:

```ts
test: {
  environment: 'jsdom',
  setupFiles: './src/test/setup.ts',
}
```

- [ ] **Step 5: Add a first failing backend router test**

Create [test_chapter_postprocess_router.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/tests/test_chapter_postprocess_router.py) with a failing endpoint existence test:

```python
def test_postprocess_stream_endpoint_exists(client):
    response = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000001/chapters/00000000-0000-0000-0000-000000000002/postprocess/stream",
        json={"trigger": "manual", "mode": "manual", "jobs": ["quality_check"]},
    )
    assert response.status_code != 404
```

- [ ] **Step 6: Add a first failing queue panel test**

Create [GenerationQueuePanel.test.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Layout/GenerationQueuePanel.test.tsx) with:

```tsx
import { render, screen } from '@testing-library/react'
import GenerationQueuePanel from './GenerationQueuePanel'
import { useAppStore } from '../../store'

test('shows AI task queue label when chapter postprocess task exists', () => {
  useAppStore.setState({
    genQueueOpen: true,
    genQueue: [{
      id: 'task-1',
      type: 'chapter_postprocess',
      projectId: 'p1',
      label: '第1章后处理',
      status: 'pending',
      progress: [],
      params: {},
      createdAt: Date.now(),
    }],
  } as any)

  render(<GenerationQueuePanel />)
  expect(screen.getByText('AI 任务队列')).toBeInTheDocument()
})
```

- [ ] **Step 7: Run the tests to confirm red**

Run backend:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/backend && .venv/bin/pytest tests/test_chapter_postprocess_router.py -q
```

Expected: FAIL because the route does not exist yet.

Run client:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm test -- GenerationQueuePanel.test.tsx
```

Expected: FAIL because `chapter_postprocess` is not part of `GenTaskType` and the queue label still says "大纲生成队列".

### Task 2: Extend Chapter Data Model And Persistence

**Files:**
- Modify: `apps/backend/app/models/chapter.py`
- Create: `apps/backend/app/models/chapter_postprocess_report.py`
- Modify: `apps/backend/app/models/__init__.py`
- Modify: `apps/backend/app/schemas/chapter.py`
- Modify: `apps/backend/app/schemas/__init__.py`
- Modify: `apps/backend/app/main.py`
- Modify: `apps/client/src/types/index.ts`

- [ ] **Step 1: Add failing backend assertions for planning/report fields**

Extend [test_chapter_postprocess_router.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/tests/test_chapter_postprocess_router.py) with a schema-level assertion that will fail until the new fields exist:

```python
from app.schemas.chapter import ChapterOut


def test_chapter_schema_exposes_planning_fields(client):
    fields = ChapterOut.model_fields
    assert "purpose" in fields
    assert "scene_cards" in fields
    assert "ending_hook" in fields
    assert "revision_notes" in fields
    assert "draft_goal" in fields
    assert "completion_checklist" in fields
```

- [ ] **Step 2: Add chapter planning fields and report model**

Update [chapter.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/models/chapter.py) to add:

```python
purpose = Column(Text)
scene_cards = Column(JSON, default=list)
ending_hook = Column(Text)
revision_notes = Column(Text)
draft_goal = Column(Text)
completion_checklist = Column(JSON, default=dict)
```

Create [chapter_postprocess_report.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/models/chapter_postprocess_report.py):

```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class ChapterPostprocessReport(Base):
    __tablename__ = "chapter_postprocess_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    trigger = Column(String(50), nullable=False)
    mode = Column(String(20), nullable=False, default="auto")
    jobs = Column(JSON, default=list)
    quality_report = Column(JSON)
    suggestions_report = Column(JSON)
    auto_debrief_report = Column(JSON)
    memory_summary = Column(JSON, default=dict)
    error_summary = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chapter = relationship("Chapter", back_populates="postprocess_reports")
```

- [ ] **Step 3: Link model exports and chapter relationship**

Update [models/__init__.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/models/__init__.py) and [chapter.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/models/chapter.py):

```python
postprocess_reports = relationship(
    "ChapterPostprocessReport",
    back_populates="chapter",
    cascade="all, delete-orphan",
)
```

and export:

```python
from app.models.chapter_postprocess_report import ChapterPostprocessReport
```

- [ ] **Step 4: Expose the new fields through schemas and client types**

Update [chapter.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/schemas/chapter.py):

```python
class ChapterCreate(BaseModel):
    title: str
    outline_node_id: Optional[uuid.UUID] = None
    content: str = ""
    sort_order: int = 0
    purpose: Optional[str] = None
    scene_cards: List[dict] = []
    ending_hook: Optional[str] = None
    revision_notes: Optional[str] = None
    draft_goal: Optional[str] = None
    completion_checklist: dict = {}
```

Mirror them in `ChapterUpdate` and `ChapterOut`.

Update [index.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/types/index.ts):

```ts
purpose?: string
scene_cards: Array<{
  id?: string
  location?: string
  present_characters?: string[]
  goal?: string
  obstacle?: string
  result?: string
}>
ending_hook?: string
revision_notes?: string
draft_goal?: string
completion_checklist?: Record<string, boolean>
```

- [ ] **Step 5: Add dev-time schema compatibility DDL**

Update [main.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/main.py) with a new `_ensure_chapter_columns()` and `_ensure_chapter_postprocess_report_table()` helper, following the existing compatibility pattern:

```python
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS purpose TEXT"
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS scene_cards JSON"
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS ending_hook TEXT"
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS revision_notes TEXT"
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS draft_goal TEXT"
"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS completion_checklist JSON"
```

- [ ] **Step 6: Run focused checks**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/backend && .venv/bin/pytest tests/test_chapter_postprocess_router.py -q
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm build
```

Expected: backend test still fails on missing endpoint, client build passes with expanded chapter types.

### Task 3: Build Backend Postprocess Orchestration

**Files:**
- Modify: `apps/backend/app/routers/ai.py`
- Modify: `apps/backend/app/services/ai_service.py`
- Create: `apps/backend/app/services/chapter_postprocess_service.py`
- Modify: `apps/backend/tests/test_chapter_postprocess_router.py`

- [ ] **Step 1: Write failing backend integration test for the orchestration flow**

Replace the initial route-existence test file content with an end-to-end test that seeds a project and chapter, then asserts SSE events:

```python
def test_postprocess_stream_runs_quality_and_returns_events(client):
    # seed project + chapter
    response = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}/postprocess/stream",
        json={
            "trigger": "manual",
            "mode": "manual",
            "jobs": ["quality_check"],
            "content_hash": "abc123",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert '"event": "progress"' in body
    assert '"event": "complete"' in body
```

- [ ] **Step 2: Add a dedicated chapter postprocess service**

Create [chapter_postprocess_service.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/services/chapter_postprocess_service.py):

```python
class ChapterPostprocessService:
    def __init__(self, db, model_profile="local", llm_provider_id=None):
        self.db = db
        self.ai = AIService("gemini" if model_profile == "gemini" else "default", db=db, llm_provider_id=llm_provider_id)

    def normalize_content(self, html: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", html or "")
        clean = html_module.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
```

- [ ] **Step 3: Implement sequential job runners**

In [chapter_postprocess_service.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/services/chapter_postprocess_service.py), add methods:

```python
async def run_quality_check(...)
async def run_suggestions(...)
async def run_memory_extract(...)
async def run_auto_debrief(...)
```

and one coordinator:

```python
async def run_jobs(self, *, chapter, jobs, trigger, mode, content_hash):
    yield {"event": "progress", "job": "quality_check", "label": "正在质检", "done": False}
```

Each runner should capture errors and return structured report fragments instead of raising unless the chapter itself is missing.

- [ ] **Step 4: Add suggestions support in AI service**

Extend [ai_service.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/services/ai_service.py) with a non-streaming structured suggestions method:

```python
async def chapter_revision_suggestions(
    self,
    chapter_title: str,
    chapter_content: str,
    chapter_purpose: str = "",
    ending_hook: str = "",
) -> dict:
```

Return JSON with `summary`, `strengths`, `risks`, and `suggestions`.

- [ ] **Step 5: Add the SSE endpoint**

In [ai.py](/Users/xgj/Documents/Claude/Projects/novelAction/apps/backend/app/routers/ai.py), add:

```python
@router.post("/projects/{project_id}/chapters/{chapter_id}/postprocess/stream")
async def postprocess_stream(...):
```

Use a new Pydantic request model:

```python
class ChapterPostprocessRequest(BaseModel):
    trigger: str
    mode: Literal["auto", "manual"] = "auto"
    jobs: List[Literal["quality_check", "suggestions", "memory_extract", "auto_debrief"]]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    suggestion_prompt: Optional[str] = None
    content_hash: Optional[str] = None
```

- [ ] **Step 6: Persist reports and dedupe memory**

Inside the service, create a `ChapterPostprocessReport` row once per completed request. During memory extraction, skip duplicates using:

```python
existing = db.query(MemoryChunk).filter(
    MemoryChunk.chapter_id == chapter.id,
    MemoryChunk.memory_type == item["memory_type"],
    MemoryChunk.title == item["title"],
    MemoryChunk.content == item["content"],
).first()
```

- [ ] **Step 7: Run backend tests**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/backend && .venv/bin/pytest tests/test_chapter_postprocess_router.py -q
```

Expected: PASS for the new endpoint test.

### Task 4: Extend Frontend Task Queue And API Client

**Files:**
- Modify: `apps/client/src/types/index.ts`
- Modify: `apps/client/src/api/client.ts`
- Modify: `apps/client/src/store/index.ts`
- Modify: `apps/client/src/components/Layout/GenerationQueuePanel.tsx`
- Modify: `apps/client/src/components/Layout/GenerationQueuePanel.test.tsx`

- [ ] **Step 1: Write failing client tests for new queue behavior**

Extend [GenerationQueuePanel.test.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Layout/GenerationQueuePanel.test.tsx):

```tsx
test('renders chapter postprocess progress items', () => {
  useAppStore.setState({
    genQueueOpen: true,
    genQueue: [{
      id: 'task-1',
      type: 'chapter_postprocess',
      projectId: 'p1',
      label: '第1章后处理',
      status: 'running',
      progress: [{ step: 'quality_check', label: '正在质检', done: false, error: false }],
      params: {},
      createdAt: Date.now(),
    }],
  } as any)

  render(<GenerationQueuePanel />)
  expect(screen.getByText('第1章后处理')).toBeInTheDocument()
  expect(screen.getByText('正在质检')).toBeInTheDocument()
})
```

- [ ] **Step 2: Extend queue types**

Update [index.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/types/index.ts):

```ts
export type GenTaskType = 'full_generate' | 'batch_expand' | 'chapter_postprocess'
```

and add a typed params shape for `chapter_postprocess`.

- [ ] **Step 3: Add API helper**

Update [client.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/api/client.ts):

```ts
chapterPostprocessStreamUrl: (pid: string, chapterId: string) =>
  `/api/v1/projects/${pid}/chapters/${chapterId}/postprocess/stream`,
```

- [ ] **Step 4: Rename and generalize the queue panel**

Update [GenerationQueuePanel.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Layout/GenerationQueuePanel.tsx):

```tsx
<span className="text-xs font-semibold text-gray-700 flex-1">AI 任务队列</span>
```

Add a new executor:

```ts
async function runChapterPostprocess(task, pushProgress, onComplete, onError, signal) {
  const { chapterId, ...payload } = task.params
  const res = await fetch(aiApi.chapterPostprocessStreamUrl(task.projectId, chapterId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}
```

- [ ] **Step 5: Dispatch the new executor**

Inside `executeTask`:

```ts
if (task.type === 'full_generate') { ... }
else if (task.type === 'batch_expand') { ... }
else { await runChapterPostprocess(...) }
```

- [ ] **Step 6: Run client tests**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm test -- GenerationQueuePanel.test.tsx
```

Expected: PASS with the queue rename and `chapter_postprocess` support.

### Task 5: Add Automatic Postprocess Enqueueing

**Files:**
- Modify: `apps/client/src/components/Writing/ChapterEditor.tsx`
- Modify: `apps/client/src/pages/WritePage.tsx`
- Modify: `apps/client/src/store/index.ts`
- Create: `apps/client/src/utils/chapterPostprocess.ts`

- [ ] **Step 1: Add failing helper-level expectations**

Create [chapterPostprocess.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/utils/chapterPostprocess.ts) with a testable shape first:

```ts
export function shouldEnqueuePostprocess() {
  return false
}
```

Use build-driven verification in this task, since the repo has no existing utility test pattern yet.

- [ ] **Step 2: Implement content normalization and queue payload helper**

In [chapterPostprocess.ts](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/utils/chapterPostprocess.ts):

```ts
export function normalizeChapterHtml(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

export async function hashChapterContent(html: string): Promise<string> {
  const data = new TextEncoder().encode(normalizeChapterHtml(html))
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('')
}
```

- [ ] **Step 3: Enqueue after AI save and meaningful manual save**

Update [ChapterEditor.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterEditor.tsx):

```ts
const enqueuePostprocess = async (trigger: 'auto_after_ai_save' | 'auto_after_manual_save' | 'status_done') => {
  const contentHash = await hashChapterContent(editor?.getHTML() || chapter.content)
  addGenTask({
    type: 'chapter_postprocess',
    projectId,
    label: `${chapter.title}后处理`,
    params: {
      chapterId: chapter.id,
      trigger,
      mode: 'auto',
      jobs: ['quality_check', 'suggestions', 'memory_extract', 'auto_debrief'],
      model_profile: modelProfileFromRoute(route),
      ...routeLlmProviderPayload(route),
      content_hash: contentHash,
    },
  })
}
```

- [ ] **Step 4: Restrict autosave to content save only**

Keep `autoSave()` in [ChapterEditor.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterEditor.tsx) free of full postprocess enqueueing. Remove direct memory extraction from autosave path once queue-driven postprocess is active. Preserve manual explicit save and status transitions as queue triggers.

- [ ] **Step 5: Refresh write page data when queue completes**

Update [WritePage.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/pages/WritePage.tsx) to listen for a new store flag, for example:

```ts
chapterDataNeedsReload: boolean
setChapterDataNeedsReload: (v: boolean) => void
```

Then rerun `chaptersApi.list(projectId)` and `storylinesApi.list(projectId)` when needed.

- [ ] **Step 6: Run client build**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm build
```

Expected: PASS with automatic queue payload wiring.

### Task 6: Split Planning And Aftercare Panels Out Of ChapterEditor

**Files:**
- Create: `apps/client/src/components/Writing/ChapterPlanningPanel.tsx`
- Create: `apps/client/src/components/Writing/ChapterAftercarePanel.tsx`
- Modify: `apps/client/src/components/Writing/ChapterEditor.tsx`
- Modify: `apps/client/src/pages/WritePage.tsx`

- [ ] **Step 1: Extract planning panel first**

Create [ChapterPlanningPanel.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterPlanningPanel.tsx) to render and edit:

```tsx
purpose
scene_cards
ending_hook
draft_goal
completion_checklist
```

Use controlled props so `ChapterEditor` remains the orchestration shell in this pass.

- [ ] **Step 2: Extract aftercare panel**

Create [ChapterAftercarePanel.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterAftercarePanel.tsx) to render:

```tsx
quality result
suggestions report
memory summary
pending debrief suggestions
revision notes
```

- [ ] **Step 3: Replace inline right-rail sections**

Update [ChapterEditor.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterEditor.tsx) so the current right rail mounts:

```tsx
{contextTab === 'plan' && <ChapterPlanningPanel ... />}
{contextTab === 'debrief' && <ChapterAftercarePanel ... />}
```

Preserve the manuscript editor body and toolbar unchanged in this pass.

- [ ] **Step 4: Thread planning data into AI drafting**

Update the draft request in [ChapterEditor.tsx](/Users/xgj/Documents/Claude/Projects/novelAction/apps/client/src/components/Writing/ChapterEditor.tsx) and the backend drafting route to ensure the newly added chapter planning fields are available to the prompt path. Prefer chapter-level fields over freeform notes when both are present.

- [ ] **Step 5: Verify the writing page still builds**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm build
```

Expected: PASS with `ChapterEditor` slimmer and planning/aftercare extracted.

### Task 7: End-To-End Verification And Cleanup

**Files:**
- Modify: `docs/superpowers/specs/2026-04-28-chapter-editor-postprocess-design.md`
- Create: `docs/superpowers/verification/chapter-postprocess-checklist.md`

- [ ] **Step 1: Add a verification checklist**

Create [chapter-postprocess-checklist.md](/Users/xgj/Documents/Claude/Projects/novelAction/docs/superpowers/verification/chapter-postprocess-checklist.md):

```md
# Chapter Postprocess Verification

- AI draft save enqueues a `chapter_postprocess` task
- Manual save enqueues only once per meaningful content change
- Autosave does not enqueue
- Queue shows per-job progress
- Quality results persist after refresh
- Memory extraction dedupes unchanged content
- Auto debrief stays pending until confirmation
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/backend && .venv/bin/pytest tests/test_chapter_postprocess_router.py -q
```

Expected: PASS.

- [ ] **Step 3: Run client tests and build**

Run:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm test -- GenerationQueuePanel.test.tsx
cd /Users/xgj/Documents/Claude/Projects/novelAction/apps/client && pnpm build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke test**

Run the app, open a chapter, trigger AI draft save, and verify:

```bash
cd /Users/xgj/Documents/Claude/Projects/novelAction && ./restart.sh
```

Manual expectations:

- queue label reads `AI 任务队列`
- draft save creates one postprocess task
- task progress shows `quality_check`, `suggestions`, `memory_extract`, `auto_debrief`
- re-saving unchanged content does not duplicate memory

- [ ] **Step 5: Commit in logical slices**

Suggested commit sequence:

```bash
git add apps/backend/requirements.txt apps/backend/tests apps/client/package.json apps/client/src/test apps/client/vite.config.ts
git commit -m "test: add chapter postprocess test harness"

git add apps/backend/app/models apps/backend/app/schemas apps/backend/app/main.py apps/client/src/types/index.ts
git commit -m "feat: add chapter planning and postprocess models"

git add apps/backend/app/routers/ai.py apps/backend/app/services
git commit -m "feat: add chapter postprocess orchestration"

git add apps/client/src/api/client.ts apps/client/src/store/index.ts apps/client/src/components/Layout/GenerationQueuePanel.tsx apps/client/src/utils/chapterPostprocess.ts
git commit -m "feat: queue chapter postprocess tasks"

git add apps/client/src/components/Writing apps/client/src/pages/WritePage.tsx docs/superpowers/verification/chapter-postprocess-checklist.md
git commit -m "refactor: split chapter planning and aftercare panels"
```

## Self-Review

Spec coverage check:

- automatic postprocess queue is covered by Tasks 3, 4, and 5
- chapter planning fields are covered by Tasks 2 and 6
- persistence of quality, suggestions, memory, and pending debrief is covered by Tasks 2 and 3
- generic AI task queue rename and extension is covered by Task 4
- manual-mode future compatibility is preserved by the request model and queue payload structure in Tasks 3 and 5

Placeholder scan:

- no `TODO` or `TBD` markers remain in executable steps
- each task names concrete files and commands
- verification commands are explicit

Type consistency check:

- backend request job names match frontend queue payload names: `quality_check`, `suggestions`, `memory_extract`, `auto_debrief`
- frontend queue task type name is consistently `chapter_postprocess`
- chapter planning field names are consistent across model, schema, and client type definitions
