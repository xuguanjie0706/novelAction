# 阶段 0 调研：001-enrich-novel-ui

**日期**：2026-04-28  
**范围**：前端视觉与内容情境增强（见 `spec.md`）

## 1. 设计系统落点（Tailwind + CSS 变量）

**Decision**：在 `frontend/src/index.css` 的 `@layer base` 中定义 **语义化 CSS 变量**（如 `--color-surface`、`--color-ink`、`--radius-card`、`--shadow-elevated`），并在 `tailwind.config.js` 的 `theme.extend` 中 `colors` / `boxShadow` / `borderRadius` **映射到 `var(...)`**，组件层只使用语义类名（如 `bg-surface-raised`、`text-ink-muted`）。

**Rationale**：单一真相源便于日后换肤；避免在几十个组件里硬编码十六进制；与现有 Tailwind 用法兼容。

**Alternatives considered**：

- **仅扩展 tailwind.config 硬编码色板**：改主题要改多处，弃用。  
- **引入 shadcn/ui 全套**：学习曲线与 diff 面过大，与「切片、少分叉」冲突，暂不采用。

## 2. 文学气质 vs 可读性

**Decision**：整体 **暖中性纸感**（略偏米/羊皮纸背景 + 深墨正文），**正文编辑区**保持高对比；装饰性纹理仅用于 **壳层或侧栏**，`ProseMirror` 内不用满版强纹理。

**Rationale**：符合规格中「书房工作台」与 FR-008；降低眼疲劳争议。

**Alternatives considered**：

- **冷灰极简**：与「太素」反馈方向相反。  
- **高饱和主题色块**：易抢正文焦点，不符合 FR-006。

## 3. 字体与行长

**Decision**：UI 壳层继续 **系统无衬线栈**（与现 `index.css` 一致）；**正文 `.prose` / TipTap** 可选引入 **一套中文衬线 Web 字体**（如通过 `index.html` 或 `@import` 加载 **思源宋体 / Noto Serif SC** 之一），并设 `max-width`（例如 `65ch`～`42rem` 区间由实现微调）与居中容器，满足 FR-003。

**Rationale**：衬线仅限长文区可强化「阅读稿纸」感而不拖慢整个 UI。

**Alternatives considered**：

- **全站衬线**：导航与小控件可读性变差。  
- **不引入 Web 字体**：零请求但文学感弱；规格允许轻量隐喻，故采用分区字体策略。

## 4. 动效与可访问性

**Decision**：过渡时长控制在 **150～250ms**；全局 `@media (prefers-reduced-motion: reduce)` 下将 `transition` 降为 `none` 或极短。

**Rationale**：满足规格边界「性能与动画」与常见 a11y 预期。

**Alternatives considered**：无动效 — 层次感略差；保留为轻量。

## 5. 空状态与加载

**Decision**：抽取小型 **`EmptyState` 模式**（标题 + 一句情境文案 + 主按钮 + 可选次链），在各 Page 列表/树为空分支复用；加载沿用或轻增强 **react-hot-toast / 局部 skeleton**，避免布局 CLS（规格 FR-005、用户故事 3）。

**Rationale**：满足 FR-004 与 SC-003 的可抽检一致性。

**Alternatives considered**：每页手写一段 div — 易不一致，难维护。

## 6. AI 与队列「辅桌」

**Decision**：侧栏/抽屉使用 **较壳层更深或更浅的单一辅面色带** + 较正文更小的标题层级；队列状态用 **图标形状 + 文案 + 颜色编码** 三套中至少两套可区分（色盲友好倾向图标+文案）。

**Rationale**：对齐 FR-006 与用户故事 4。

**Alternatives considered**：纯边框无底色 — 层次仍弱；辅面色带性价比更高。

---

**结论**：技术上下文中 **无** 未决 `NEEDS CLARIFICATION`；上述决策已足够进入阶段 1 设计与实现任务拆分。
