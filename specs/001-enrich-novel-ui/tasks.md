---
description: 功能实现任务列表 — 001-enrich-novel-ui
---

# 任务：小说创作工作台视觉与内容情境增强

**输入**：`/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/` 下 `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`  
**前置**：`plan.md`、`spec.md` 已就绪  

**测试**：规格未要求 TDD；本列表**不含**自动化测试任务。合并前以 `pnpm run build` + `quickstart.md` 走查为准。

**组织方式**：按用户故事（US1～US4）与 `spec.md` 优先级分组，任务描述含确切文件路径。

## 格式说明

`- [ ] Tnnn [P] [USn] 描述 + 路径` — **Setup / Foundational / Polish** 阶段无 `[USn]`；可并行项标 `[P]`。

---

## 阶段 1：搭建（共享基础）

**目的**：对齐设计契约与仓库边界，无重型脚手架。

**独立测试**：能口头复述 `contracts/ui-surfaces.md` 中 S-01～S-09 与本轮将改动的 `frontend/` 路径。

- [ ] T001 阅读并对照实现范围：`specs/001-enrich-novel-ui/contracts/ui-surfaces.md`、`specs/001-enrich-novel-ui/research.md`（确认与 `frontend/` 文件修改清单一致）

---

## 阶段 2：基础（阻塞性前置）

**目的**：设计令牌与全局基底；**未完成前不得开始 US1～US4 的界面改造**。

**独立测试**：启动 `frontend` 后根节点应用语义背景/文字色；系统开启「减少动态效果」时动画显著减弱或关闭。

- [ ] T002 在 `frontend/src/index.css` 定义语义 CSS 变量（如 surface、ink、border、radius、elevated shadow）并添加 `@media (prefers-reduced-motion: reduce)` 下 transition 降级规则  
- [ ] T003 在 `frontend/tailwind.config.js` 的 `theme.extend` 中将颜色、圆角、阴影等映射到 `var(--*)`（与 `research.md` 一致）  
- [ ] T004 [P] 在 `frontend/index.html` 添加正文区使用的中文衬线 Web 字体 `<link>`（思源宋体或 Noto Serif SC 等 CDN 其一，若团队决定不引外链则改为在 `index.html` 用注释记录决策并跳过加载）  
- [ ] T005 在 `frontend/src/App.tsx` 根布局包裹元素上应用全局 `bg-*` / `text-*` 语义类，使令牌在路由切换下仍生效  

**检查点**：阶段 2 完成后方可并行或串行进入各用户故事。

---

## 阶段 3：用户故事 1 — 进入即有「在书房里开工」的场域感（优先级：P1）🎯 MVP

**目标**：壳层主次分区、导航当前态、顶栏上下文可识别（对齐 `spec.md` 用户故事 1、FR-001、FR-002、contracts S-09）。

**独立测试**：不进入具体业务数据页，仅切换侧栏路由即可验证层次与「当前模块」可识别性。

- [ ] T006 [US1] 在 `frontend/src/components/Layout/AppLayout.tsx` 实现主内容区与侧栏的层次（背景阶、间距、可选轻过渡 150～250ms）  
- [ ] T007 [P] [US1] 在 `frontend/src/components/Layout/Sidebar.tsx` 强化当前路由选中态、图标与标签对比度及 hover/focus 样式（tokens）  
- [ ] T008 [P] [US1] 在 `frontend/src/components/Layout/TopBar.tsx` 增加或调整页面上下文标题/副标题，使一级模块切换时作者可明确当前位置  

**检查点**：US1 单独走查可通过，且不依赖 US2～US4。

---

## 阶段 4：用户故事 2 — 写作与阅读长文时眼睛与注意力「有落点」（优先级：P1）

**目标**：章节编辑区行长、正文层级、与 AI 区的边界清晰（对齐 `spec.md` 用户故事 2、FR-003、FR-007、FR-008、contracts S-02）。

**独立测试**：在含数百字样例的章节中上下滚动阅读，确认段落/标题区分与编辑区最大宽度；与侧栏/AI 区边界可指认。

- [ ] T009 [US2] 在 `frontend/src/index.css` 中扩展 `.prose` 与 `.ProseMirror` 相关规则（行长、标题/正文间距、占位符对比度），避免正文区强纹理  
- [ ] T010 [US2] 在 `frontend/src/components/Writing/ChapterEditor.tsx` 为编辑器外层容器设置 `max-w-*` 与水平居中（或与 `WritePage.tsx` 协同），满足与侧栏并排时的稳定布局  
- [ ] T011 [US2] 在 `frontend/src/pages/WritePage.tsx` 调整主从栏比例、滚动容器与焦点环（使用语义色），使「当前可输入区」可辨识  

**检查点**：US2 可在 US3 未完成时单独验收写作路径。

---

## 阶段 5：用户故事 3 — 空白与加载也有「下一笔写什么」的引导（优先级：P2）

**目标**：关键空状态与加载/失败反馈符合 `contracts/ui-surfaces.md` 空状态与加载契约（`spec.md` 用户故事 3、FR-004、FR-005）。

**独立测试**：在无数据或断网情况下打开各列表页，验证情境文案 + 单一主行动 + 加载/错误提示。

- [ ] T012 [US3] 新建可复用组件 `frontend/src/components/ui/EmptyState.tsx`（props：标题、说明、主按钮/操作、可选次要链）  
- [ ] T013 [P] [US3] 在 `frontend/src/pages/ProjectsPage.tsx` 空列表分支接入 `EmptyState.tsx` 与小说语境文案（contracts S-01）  
- [ ] T014 [P] [US3] 在 `frontend/src/pages/OutlinePage.tsx` 空大纲/空列表分支接入 `EmptyState.tsx`（contracts S-03）  
- [ ] T015 [P] [US3] 在 `frontend/src/pages/CharactersPage.tsx` 空列表分支接入 `EmptyState.tsx`（contracts S-04）  
- [ ] T016 [P] [US3] 在 `frontend/src/pages/MemoryPage.tsx` 空列表分支接入 `EmptyState.tsx`（contracts S-05）  
- [ ] T017 [US3] 在 `frontend/src/pages/ProjectsPage.tsx`、`frontend/src/pages/WritePage.tsx`、`frontend/src/pages/OutlinePage.tsx` 等为数据加载与请求失败补充可见反馈（skeleton/spinner/文案）及重试或引导（对齐 FR-005，避免裸状态码）  

**检查点**：US3 完成后 SC-003 抽检可按 contracts 执行。

---

## 阶段 6：用户故事 4 — AI 与生成队列「像助手桌」（优先级：P3）

**目标**：AI 与队列辅区视觉层级、状态可辨、失败人类可读（`spec.md` 用户故事 4、FR-005、FR-006、contracts S-07、S-08）。

**独立测试**：展开 AI 面板与队列，扫视 5 秒内理解可操作项与队列状态；人为触发失败时可见说明与下一步。

- [ ] T018 [US4] 在 `frontend/src/components/AI/AIPanel.tsx` 应用辅区背景阶、标题/副标题分区与作者向术语微调（不改动 API 调用语义）  
- [ ] T019 [P] [US4] 在 `frontend/src/components/Outline/OutlineAIPanel.tsx` 与 `AIPanel.tsx` 对齐辅区视觉语言（contracts S-07）  
- [ ] T020 [US4] 在 `frontend/src/components/Layout/GenerationQueuePanel.tsx` 区分等待/进行中/完成/失败态（图标+文案或色+文案组合），失败时含可读说明与重试/下一步  

**检查点**：US4 可独立于空状态故事之后合并，但建议在 US1 壳层令牌完成后实施。

---

## 阶段 7：打磨与横切

**目的**：剩余表面与构建验收，满足 FR-002 全站一致与闭包交付。

- [ ] T021 [P] 在 `frontend/src/components/Bootstrap/GenerateWizard.tsx` 统一用语义色、圆角与间距（contracts 未单列但属高频向导）  
- [ ] T022 [P] 在 `frontend/src/pages/SettingsPage.tsx` 应用与其他页一致的层次与表单聚焦样式（contracts S-06）  
- [ ] T023 在 `frontend/` 执行 `pnpm run build` 无错误，并按 `specs/001-enrich-novel-ui/quickstart.md` 全链路走查记录结果（写入 PR 或发布说明）  

---

## 依赖与执行顺序

### 阶段依赖

| 阶段 | 依赖 |
|------|------|
| 阶段 1 | 无 |
| 阶段 2 | 阶段 1 完成（理解契约） |
| 阶段 3～6 | **均依赖阶段 2 完成** |
| 阶段 7 | 计划交付范围内 US1～US4 均已完成或产品明确裁剪 |

### 用户故事依赖

| 故事 | 依赖 | 说明 |
|------|------|------|
| US1 | 阶段 2 | 不依赖 US2～US4 |
| US2 | 阶段 2 | 可与 US1 串行或在其后并行（不同文件为主） |
| US3 | 阶段 2；**T012 先于 T013～T016** | T017 可与各页空状态穿插，建议 EmptyState 落地后再统一加载态 |
| US4 | 阶段 2；建议 US1 壳层已稳定 | 与 US2 共享写作页周边时注意避免同一 PR 大冲突 |

### 建议故事完成顺序（串行 MVP）

`阶段2 → US1 → US2 → US3 → US4 → 阶段7`

### 并行机会（阶段 2 之后）

- **US1 内**：T007、T008 可并行（不同文件）。  
- **US2**：T009 与 T010 可部分并行（同一故事内先定 `index.css` 再绑编辑器容器更稳，故 T009 建议先于或与 T010 紧耦合）。  
- **US3**：T013、T014、T015、T016 在 T012 完成后可 **[P] 并行**（四页独立）。  
- **US4**：T019 可与 T018 并行在人力充足时（注意视觉一致）。  
- **阶段 7**：T021、T022 可并行。

---

## 并行示例：用户故事 3

在 **T012** 合并后，可由不同执行体同时修改：

- `frontend/src/pages/ProjectsPage.tsx`（T013）  
- `frontend/src/pages/OutlinePage.tsx`（T014）  
- `frontend/src/pages/CharactersPage.tsx`（T015）  
- `frontend/src/pages/MemoryPage.tsx`（T016）  

---

## 实施策略

### MVP（最小可用增量）

1. 完成阶段 1 + 阶段 2  
2. 完成阶段 3（US1）→ 按 `quickstart.md` 壳层段落走查 → 可演示「不再白板后台感」  

### 增量交付

1. US1 → 走查 → 合并/演示  
2. US2 → 走查 → 合并/演示  
3. US3 → 走查 → 合并/演示  
4. US4 → 走查 → 合并/演示  
5. 阶段 7 → `pnpm run build` + 全 quickstart  

### 多人分工示例

- 成员 A：阶段 2 + US1 + US4（布局与 AI）  
- 成员 B：US2 + US3（编辑器与空状态）  
- 成员 C：阶段 7 与走查文档  

---

## 任务统计（生成时快照）

| 指标 | 数量 |
|------|------|
| 任务总数 | 23 |
| 阶段 1 | 1 |
| 阶段 2 | 4 |
| US1 | 3 |
| US2 | 3 |
| US3 | 6 |
| US4 | 3 |
| 阶段 7 | 3 |
| 含 `[P]` 可并行任务 | 10 |

---

## 备注

- 所有路径相对于仓库根：`/Users/xgj/Documents/Claude/Projects/novelAction/`  
- 后端 `backend/app/` 默认不在本特性修改范围内（见 `data-model.md`）  
- 格式校验：本文件任务行均满足 `- [ ] Tnnn ...` 及故事阶段 `[USn]` 要求  
