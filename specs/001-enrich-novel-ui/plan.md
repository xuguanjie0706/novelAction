# 实现计划：小说创作工作台视觉与内容情境增强

**分支**：`001-enrich-novel-ui` | **日期**：2026-04-28 | **规格**：[spec.md](./spec.md)  
**输入**：来自本目录 `spec.md` 的功能规格（绝对路径：`/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/spec.md`）

**说明**：本文件由 `/speckit.plan` 命令填写。

## 摘要

在**不改动后端数据模型与 REST 契约**的前提下，通过前端 **设计令牌（颜色、间距、圆角、阴影、字体层级）**、**布局壳层（AppLayout / TopBar / Sidebar）**、**可复用空状态与加载反馈**、**章节编辑区行长与 Prose 样式**、**AI 与队列辅区视觉降级**等切片交付，满足规格中的 FR-001～FR-008 与成功标准 SC-001～SC-005。  
技术路径以现有 **React 18 + TypeScript + Vite + Tailwind CSS 3 + TipTap** 为主；调研结论见同目录 `research.md`。阶段 1 产出：`data-model.md`、`contracts/`、`quickstart.md`。

## 技术上下文

**语言/版本**：TypeScript 5.4+；Node 用于本地构建（与仓库 `.python-version` 无冲突，后端本特性不修改）  
**主要依赖**：React 18.3、react-router-dom 6、Zustand 4、TipTap 2、Tailwind CSS 3.4、axios、react-query、lucide-react、react-hot-toast  
**存储**：本特性 P1～P2 **不引入**新持久化实体；可选远期「外观偏好」见 `data-model.md`  
**测试**：当前 `frontend/package.json` 无自动化 UI 测试脚本；验收以 **`pnpm run build`** 无错误 + 规格走查清单为主；后续可在 `/speckit.tasks` 中增加 Vitest/Playwright 为非阻塞项  
**目标平台**：现代桌面浏览器（Chromium / Safari / Firefox 最近两个大版本）；窄屏以现有布局折叠能力为界增强  
**项目类型**：Web 单页应用（Vite SPA），仓库内与 `backend/` 并存  
**性能目标**：首屏与编辑交互不因大面积背景图或重滤镜产生可感知卡顿；动画遵守 `prefers-reduced-motion`  
**约束**：正文区对比度不因装饰低于可读基线；不新增第二条「对话/API」产品主轴（见宪章 I）  
**规模/范围**：约 8 个页面级路由 + 共享布局与 AI/队列/向导等复合组件（见下方源码树）

## 宪章检查

*门禁：阶段 0 调研前通过；以下为阶段 1 设计后复核（与阶段 0 结论一致）。*

对照 `/Users/xgj/Documents/Claude/Projects/novelAction/.specify/memory/constitution.md` 核查：

| 原则 | 结论 |
|------|------|
| **I. 控制面主轴** | **通过**。仅增强呈现与文案，不新增并行 Session/Message/Run 语义或第二套创作 API。 |
| **II. 契约先行** | **通过（N/A 为主）**。无跨服务新编排；若未来接流式 AI，仍走既有 `ai`/`generate` 路由，本计划不改变载荷契约。 |
| **III. 切片交付** | **通过**。建议顺序：全局令牌与 `index.css` 基底 → `AppLayout`/`Sidebar`/`TopBar` → `ChapterEditor`/写作页 → 各页空状态 → `AIPanel`/`GenerationQueuePanel`。每步可单独合并并走查。 |
| **IV. 安全基线** | **通过**。无新密钥、无跨用户数据路径；文案不记录敏感信息。 |
| **V. 可测交付** | **通过**。规格中用户故事、FR、SC 完整；`quickstart.md` 给出可复现验收步骤。 |
| **VI. 完整交付闭包** | **通过**。合并前需：`pnpm run build`、走查清单签字、`quickstart.md` 中已知限制（如无 E2E）。 |

## 阶段 0 / 阶段 1 产出索引

| 产物 | 路径 |
|------|------|
| 调研与决策 | `/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/research.md` |
| 数据与持久化边界 | `/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/data-model.md` |
| 界面契约（走查用） | `/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/contracts/ui-surfaces.md` |
| 验收 Quickstart | `/Users/xgj/Documents/Claude/Projects/novelAction/specs/001-enrich-novel-ui/quickstart.md` |

## 项目结构

### 文档（本特性）

```text
specs/001-enrich-novel-ui/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── ui-surfaces.md
├── spec.md
└── checklists/
    └── requirements.md
```

### 源码（仓库根目录）

```text
backend/
├── app/
│   ├── main.py
│   ├── routers/
│   ├── models/
│   └── services/
└── requirements.txt（本特性默认不修改）

frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── api/client.ts
│   ├── store/index.ts
│   ├── types/index.ts
│   ├── pages/
│   │   ├── ProjectsPage.tsx
│   │   ├── WritePage.tsx
│   │   ├── OutlinePage.tsx
│   │   ├── CharactersPage.tsx
│   │   ├── MemoryPage.tsx
│   │   └── SettingsPage.tsx
│   └── components/
│       ├── Layout/
│       │   ├── AppLayout.tsx
│       │   ├── Sidebar.tsx
│       │   ├── TopBar.tsx
│       │   └── GenerationQueuePanel.tsx
│       ├── Writing/
│       │   └── ChapterEditor.tsx
│       ├── AI/
│       │   └── AIPanel.tsx
│       ├── Outline/
│       │   └── OutlineAIPanel.tsx
│       └── Bootstrap/
│           └── GenerateWizard.tsx
└── tests/（当前无；可后续补充）
```

**结构决策**：采用仓库现有 **前后端分目录** 布局；本特性**实现改动集中在 `frontend/`**（`tailwind.config.js`、`src/index.css`、Layout、Pages、AI/Writing 相关组件），后端仅在若引入「用户偏好 API」时扩展（当前规格列为非 P1 阻塞）。

## 复杂度追踪

本特性**无**需向宪章申请的违规项；未引入额外运行时或仓储复杂度。
