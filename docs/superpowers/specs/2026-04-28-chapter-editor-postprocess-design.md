# Chapter Editor And Postprocess Queue Design

## Context

The current writing surface can edit chapter text, call AI drafting, run quality checks, extract memory, and submit debrief updates. Most of this behavior is concentrated in `ChapterEditor.tsx`, so the author can perform many actions but the product does not clearly model the lifecycle of writing a chapter.

The reference project at `/Users/xgj/Documents/Claude/Projects/novel-writing` suggests a stronger chapter-level workflow: before writing, capture the chapter purpose, scene list, and ending hook; after writing, run checks, record memory, and preserve revision notes. The web app should keep its richer UI, but adopt that chapter lifecycle.

## Goals

- Split the chapter writing experience into planning, manuscript editing, and aftercare.
- Add a default automatic postprocess queue after meaningful chapter saves.
- Keep the postprocess workflow switchable to manual mode later.
- Use one backend orchestration endpoint for quality check, suggestions, memory extraction, and auto debrief.
- Persist postprocess results so refreshes do not lose quality reports, suggestions, memory changes, or pending debrief suggestions.
- Prevent AI automation from silently changing canonical story facts that should require author confirmation.

## Non-Goals

- Replace TipTap or redesign the entire writing page.
- Force authors through a rigid chapter state machine in the first iteration.
- Auto-apply character state or storyline changes without confirmation.
- Merge streaming manuscript generation and postprocess orchestration into one endpoint.

## Recommended Architecture

The writing page should evolve from one large editor component into three focused surfaces:

| Surface | Responsibility |
| --- | --- |
| `ChapterPlanningPanel` | Chapter purpose, scene cards, ending hook, linked storylines, foreshadowing targets, and chapter-specific writing goals. |
| `ChapterManuscriptEditor` | TipTap content editing, autosave, manual save, snapshots, AI drafting, inline rewrite actions, and word/session statistics. |
| `ChapterAftercarePanel` | Quality result, AI revision suggestions, extracted memories, pending debrief suggestions, revision notes, and author confirmation actions. |

The existing generation queue should become a generic AI task queue. It should still handle outline generation, but also support chapter postprocessing:

```ts
type GenTaskType =
  | 'full_generate'
  | 'batch_expand'
  | 'chapter_postprocess'
```

The visible label should change from "大纲生成队列" to "AI 任务队列".

## Chapter Planning Data

Add chapter-level planning fields directly to `Chapter` in the first implementation. This keeps the first migration small and lets existing chapter APIs return the full editing context without an additional round trip.

Recommended first-pass fields:

- `purpose`: why this chapter exists, such as main plot progress, character movement, foreshadowing, or pacing adjustment.
- `scene_cards`: array of scene objects with location, present characters, goal, obstacle, and result.
- `ending_hook`: the intended reason readers continue to the next chapter.
- `revision_notes`: author-facing revision notes and postprocess notes.
- `draft_goal`: short instruction used by AI drafting for this chapter.
- `completion_checklist`: structured flags for whether the chapter changed situation, relationship, reader knowledge, or stakes.

These fields should be included in AI drafting and quality prompts. This is the main product lift from the reference project: AI should not just continue prose; it should help complete a chapter's narrative job.

## Postprocess Trigger Policy

Default mode is automatic:

| Trigger | Behavior |
| --- | --- |
| AI draft inserted and saved | Automatically enqueue full postprocess. |
| Manual save | Automatically enqueue full postprocess if content changed meaningfully. |
| Frequent autosave | Save content only; do not run full postprocess. |
| Status changed to `done` or `reviewed` | Enqueue full postprocess unless the same content hash already completed. |

Manual mode should be supported later by a setting. In manual mode, the same queue task is created only when the user clicks a postprocess action.

## Postprocess Endpoint

Add one orchestration endpoint:

```http
POST /api/v1/projects/{project_id}/chapters/{chapter_id}/postprocess/stream
```

Request:

```json
{
  "trigger": "auto_after_save",
  "mode": "auto",
  "jobs": ["quality_check", "suggestions", "memory_extract", "auto_debrief"],
  "model_profile": "local",
  "llm_provider_id": null,
  "suggestion_prompt": "请检查本章节奏、人物动机、章末钩子是否有效",
  "content_hash": "sha256..."
}
```

Response uses SSE events:

```json
{ "event": "progress", "job": "quality_check", "label": "正在质检", "done": false }
{ "event": "result", "job": "quality_check", "data": { "overall_score": 7.8 } }
{ "event": "progress", "job": "memory_extract", "label": "已提取 5 条记忆", "done": true }
{ "event": "complete", "message": "章节后处理完成" }
```

The endpoint should execute selected jobs sequentially. It should continue after non-critical job failures and return per-job error events, so one failed suggestion call does not prevent memory extraction.

## Postprocess Jobs

### Quality Check

Run the existing quality check logic and persist:

- `Chapter.last_quality_score`
- `Chapter.last_quality_report`
- `Chapter.quality_checked_at`

The report should include chapter planning context when available.

### Suggestions

Generate structured revision suggestions, not direct edits. Persist the result in a new `chapter_postprocess_reports` table with `suggestions` in the result payload.

Suggestions should focus on chapter purpose completion, scene pressure, motivation, pacing, ending hook, and continuity with prior chapters.

### Memory Extraction

Run memory extraction and write `MemoryChunk` rows. Add dedupe protection so rerunning postprocess for unchanged content does not create duplicate memory rows.

Minimum viable dedupe:

- include source chapter id and content hash in memory metadata or tags;
- before inserting, skip matching memory type/title/content for the same chapter and hash.

### Auto Debrief

Run the existing auto debrief extraction, but do not automatically mutate characters or storylines. Persist pending suggestions for the aftercare panel. The author must confirm before canonical character states, skills, items, or storylines are updated.

## Queue Behavior

The frontend queue runner should add a `runChapterPostprocess` executor. It should:

- call the new postprocess SSE endpoint;
- push per-job progress into the task card;
- refresh the active chapter after quality results;
- refresh memory after memory extraction;
- refresh the aftercare panel after suggestions and debrief output;
- mark the task done even if some optional jobs failed, while surfacing job-level errors.

Task params:

```ts
{
  chapterId: string
  chapterTitle: string
  trigger: 'auto_after_ai_save' | 'auto_after_manual_save' | 'status_done' | 'manual'
  jobs: Array<'quality_check' | 'suggestions' | 'memory_extract' | 'auto_debrief'>
  model_profile: 'local' | 'gemini'
  llm_provider_id?: string
  content_hash?: string
}
```

## Safety And Idempotency

The automatic mode needs three protections:

- Content hash dedupe: if the same chapter content hash already completed the same job set, skip or report "already complete".
- Time throttle: avoid enqueueing another full postprocess for the same chapter within a short window after manual saves.
- Confirmation boundary: quality, suggestions, and memory may persist automatically; character and storyline changes remain pending until confirmed.

The content hash should be computed from normalized manuscript text: strip HTML tags, decode common entities, collapse whitespace, trim, and hash the result with SHA-256. Planning fields should not be part of the content hash; changing planning fields can be handled by manual rerun or a later planning-hash extension.

## Implementation Phasing

### Phase 1: Queue And Endpoint

- Add `chapter_postprocess` queue task type.
- Rename the queue UI to "AI 任务队列".
- Add backend postprocess SSE endpoint.
- Wire AI draft insertion and manual save to enqueue postprocess automatically.
- Persist quality results and extracted memories.
- Store suggestions and pending debrief output in a durable report shape.

### Phase 2: Editor Decomposition

- Extract planning, manuscript, and aftercare surfaces from `ChapterEditor.tsx`.
- Add chapter planning fields to the UI.
- Pass planning fields into AI drafting and quality prompts.

### Phase 3: Manual Mode And Controls

- Add a project or local setting for automatic versus manual postprocess mode.
- Add job selection controls for users who only want selected checks.
- Add retry controls for failed postprocess jobs.

## Acceptance Criteria

- After AI-generated text is inserted and saved, a `chapter_postprocess` task appears in the AI task queue without additional user action.
- The postprocess task shows separate progress for quality, suggestions, memory extraction, and auto debrief.
- Manual saves enqueue postprocess only when content changed meaningfully and throttling allows it.
- Autosave does not repeatedly run full postprocess while the user is typing.
- Quality results persist on the chapter and are visible after refresh.
- Extracted memories persist and do not duplicate for the same unchanged chapter content.
- Auto debrief results appear as pending suggestions and do not mutate characters or storylines until confirmed.
- The same backend endpoint supports future manual mode by changing the trigger and frontend dispatch behavior.
