# World Setting Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor generated world settings into readable core/focus structures and present them in the settings page before long-form text.

**Architecture:** Keep the existing `WorldSetting` API and persist new structured fields in `extra.core` and `extra.focus`. Extract small client presentation helpers so the page can stay compatible with old data while rendering dedicated panels for `作品立意` and normal setting focus summaries.

**Tech Stack:** FastAPI, SQLAlchemy, React 18, TypeScript, Zustand, Vite, TailwindCSS

---

### Task 1: Add Client Presentation Helpers

**Files:**
- Create: `apps/client/src/utils/settingsPresentation.ts`

- [ ] Define `PremiseCore` and `SettingFocus` types.
- [ ] Add `getPremiseCore(setting)` to read `setting.extra.core` with safe string defaults.
- [ ] Add `getSettingFocus(setting)` to read `setting.extra.focus` with safe string defaults.
- [ ] Add `getSettingPreview(setting)` to prefer core/focus summaries before falling back to content.

### Task 2: Refactor Settings Detail UI

**Files:**
- Modify: `apps/client/src/pages/SettingsPage.tsx`

- [ ] Import the presentation helpers.
- [ ] Add a dedicated `PremiseCorePanel` for `作品立意`.
- [ ] Add a reusable `FocusPanel` for normal settings.
- [ ] Show the core/focus panel above the long description editor.
- [ ] Show meaningful previews in the left list.
- [ ] Keep existing category editing, tag editing, delete, save, and project premise sync behavior.

### Task 3: Tighten Setting Generation Prompt

**Files:**
- Modify: `apps/backend/app/services/generation_service.py`

- [ ] Update `_gen_settings()` prompt examples so each generated card returns `extra.category` plus either `extra.core` or `extra.focus`.
- [ ] Require concise scan fields and keep long-form `content` as supporting detail.
- [ ] Keep old `tags` and `content` fields unchanged for compatibility.

### Task 4: Verify

**Files:**
- No code files

- [ ] Run `pnpm --filter novel-system-frontend build`.
- [ ] If build fails, fix only issues introduced by this refactor.
- [ ] Report that no automated client behavior tests were run because this workspace does not currently include a test runner.
