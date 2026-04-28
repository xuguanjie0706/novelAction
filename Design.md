# Client UI 规范与强对齐改造计划

## Summary

基于参考图，将 `apps/client` 统一成“轻量写作工作台”风格：浅灰页面背景、白色卡片、暖橙主色、低对比边框、细阴影、紧凑表单与清晰写作空间。目标是让首页、项目内导航、写作页、大纲/人物/世界观等页面使用同一套 token、组件规则和页面骨架。

## UI 规范

- 色彩：
  - 主色 `#FF9800`，浅主色 `#FFF4DB`
  - 页面背景 `#F7F8FA`，卡片背景 `#FFFFFF`
  - 边框 `#E6EAF0`
  - 主文本 `#1F2329`，次文本 `#6B7280`，弱文本 `#9AA3AF`
  - 成功 `#22C55E`，提醒 `#F59E0B`，错误 `#EF4444`
- 字体：
  - 字体族沿用 `-apple-system, PingFang SC, Microsoft YaHei, sans-serif`
  - 页面标题 `20px / bold`
  - 小标题 `16px / semibold`
  - 正文 UI `14px / regular`
  - 辅助说明 `12px / regular`
  - 写作正文单独使用 `16px`、较大行高，保证阅读舒适
- 圆角与阴影：
  - 卡片、按钮、输入框默认 `8px`
  - 弹窗、浮层、下拉菜单可用 `12px`
  - 标签、头像、开关使用 pill/full 圆角
  - 卡片阴影保持浅：`0 8px 24px rgba(31,35,41,0.04)`；浮层更深但不厚重
- 布局：
  - 全局工作区使用浅色左侧导航，不再使用深色图标栏作为主风格
  - 桌面侧栏宽度约 `176-192px`，顶部栏高度约 `72px`
  - 主内容区最大宽度约 `1180-1240px`，页面 padding `24-32px`
  - 禁止卡片套卡片；页面区块用留白和分隔线组织，卡片只用于独立信息单元
- 组件：
  - 主按钮：橙底白字，40px 高，左侧可带 lucide 图标
  - 次按钮：白底、浅边框、深灰文字
  - 文本按钮：透明背景，用于低优先级操作
  - 输入框：40px 高，focus 使用橙色边框 + 浅橙 ring
  - 标签：浅橙底、橙色文字，可关闭标签带 `x`
  - 消息提示：成功/提醒/错误/通知都必须“图标 + 文案 + 色彩”组合，不只依赖颜色
  - 图标统一用 `lucide-react`，常规尺寸 `16/18/20px`，stroke 2px

## Implementation Changes

- 新增一份规范文档，建议路径：`docs/client-ui-guidelines.md`，记录 token、组件、页面骨架、验收规则。
- 在 `apps/client/tailwind.config.js` 和 `apps/client/src/index.css` 中沉淀设计 token，减少组件内硬编码 hex。
- 建立轻量 UI primitives：`Button`、`Input`、`Card`、`Badge/Tag`、`IconButton`、`PanelHeader`，后续页面只组合这些基础件。
- 强对齐现有核心表面：
  - `ProjectsPage` 首页保留工作台属性，但统一成参考图的浅色侧栏、顶部搜索、数据卡片、列表卡片风格。
  - `AppLayout`、`Sidebar`、`TopBar` 改为浅色导航体系，项目内页面和首页不再割裂。
  - `WritePage`、`ChapterEditor` 强化“左侧章节导航 + 中央写作区 + 辅助面板”的写作工作台结构。
  - 大纲、人物、世界观、记忆页按同一套列表、详情、表单、空状态规范迁移。

## Test Plan

- 运行 `pnpm --dir apps/client run build`，确保 TypeScript 和 Vite 构建通过。
- 桌面验收：在 `1440x900` 检查首页、写作页、大纲页、人物页、世界观页。
- 移动验收：在 `390x844` 检查文本不溢出、按钮不挤压、导航可访问。
- 视觉验收：核对主色、背景、卡片、输入框、标签、toast、空状态、加载态、错误态。
- 可用性验收：所有可点击控件有 hover/focus/disabled 状态；关键操作不只靠颜色表达状态。

## Assumptions

- 已选择“强对齐”：client 后续整体向参考图靠拢，而不是只做局部 token 微调。
- 不改后端 API，不改数据结构。
- `lucide-react` 继续作为唯一图标体系。
- 卡片圆角收敛为 `8px`，弹窗/浮层可用 `12px`，避免界面变得过度圆润。
