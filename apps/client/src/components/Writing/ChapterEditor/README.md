# ChapterEditor 包

> AI 改代码前必读：**全仓库 ≤600 行** [`.cursor/rules/file-size-600-global.mdc`](../../../../.cursor/rules/file-size-600-global.mdc)；本包落点 [`.cursor/rules/god-files-chapter-editor.mdc`](../../../../.cursor/rules/god-files-chapter-editor.mdc)。

## 结构

| 路径 | 职责 |
|------|------|
| `index.tsx` | **编排壳 only**（≤600 行） |
| `hooks/` | 全部业务状态、API、副作用 |
| `*Toolbar.tsx` / `*Area.tsx` / `*Panel.tsx` / `*Modal.tsx` | 展示 + 事件回调 |
| `types.ts` / `utils.ts` / `constants.tsx` | 共享类型与工具 |

## 新增功能 checklist

1. 能否放进已有 hook？（见 mdc 落点表）
2. 若需新 hook：单文件 ≤600 行，并在 `index.tsx` 仅增加 1 行解构 + props 透传
3. 跑 `wc -l index.tsx` 确认仍 ≤600
