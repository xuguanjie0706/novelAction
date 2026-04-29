# World Setting Core Design

## Context

The settings page currently treats every generated setting as a flat text card. This makes the most important generated card, `作品立意`, hard to read because the author must manually extract the book's core promise, conflict, reader hook, and boundaries from a long paragraph.

The system is an AI-first novel creation tool, so the fix should improve both generation output and the reading/editing surface. The AI should produce structured author-facing signals, and the UI should present those signals before the long-form description.

## Goals

- Make the first read of generated settings answer: what is this book, what drives it, what conflict powers it, why will readers continue, and what must not drift.
- Preserve existing `WorldSetting` storage and API compatibility by writing new structure into `WorldSetting.extra`.
- Give `作品立意` a dedicated core panel instead of treating it like a normal worldbuilding card.
- Give normal setting cards category-specific focus fields where useful, while still preserving the existing long description editor.
- Keep older projects usable even when their settings do not have the new structured `extra` fields.

## Non-Goals

- Add a new database table for premise/core settings.
- Replace the existing structured worldbuilding page for storylines, power systems, skills, items, or factions.
- Build a visual graph or full redesign of project navigation.
- Add a client test framework in this pass.

## Design

### Generation Shape

`generation_service._gen_settings()` should ask the model to return `extra` fields for each setting card.

For `作品立意`, `extra.core` should contain:

- `core_concept`: the one-sentence book promise.
- `genre_position`: genre, audience, length, and market positioning.
- `protagonist_drive`: why the protagonist must act.
- `core_conflict`: the central opposition.
- `reader_hook`: what readers keep chasing.
- `emotional_tone`: the dominant emotional flavor.
- `boundaries`: things the story should avoid or not write off-course.
- `ending_direction`: the intended ending direction.

For rules, history, geography, culture, resources, and other cards, `extra.focus` should contain short scan-friendly fields such as `summary`, `story_function`, `conflict_seed`, `cost_or_risk`, and category-specific fields.

### UI Shape

The settings page should keep the left category/list navigation, but the selected detail should start with a readable dashboard:

- `作品立意` shows a dedicated core panel with compact labeled fields, then the original long description.
- Other cards show a compact focus panel when `extra.focus` exists, then category controls and the long description.
- The list should prioritize the premise card and show short previews to make selection meaningful.

### Compatibility

Old data without `extra.core` or `extra.focus` should still render exactly enough to edit: title, category, content, and tags remain available. The core panel should be additive and should not require migrations.

## Acceptance Criteria

- Newly generated `作品立意` includes structured core fields in `extra.core`.
- Newly generated setting cards include scan-friendly focus fields in `extra.focus`.
- Selecting `作品立意` shows the core fields before the paragraph description.
- Existing settings without structured fields still load and save.
- Saving a premise card still syncs project `premise`.
- Client build succeeds after the refactor.
