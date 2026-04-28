# 数据模型说明：001-enrich-novel-ui

**日期**：2026-04-28  
**与规格关系**：`spec.md` 假设「可不引入外观偏好持久化」；本文件界定 **当前交付** 与 **可选扩展** 边界。

## 当前交付（P1～P3 默认）

| 类别 | 说明 |
|------|------|
| **后端实体** | **无变更**。Project、Chapter、Character、Outline、Memory 等现有模型不受影响。 |
| **API 契约** | **无变更**。不新增查询参数或响应字段要求。 |
| **前端状态** | 布局折叠、面板开闭等继续由 **Zustand / 组件本地 state** 表达；不要求服务端持久化。 |

## 可选扩展（非阻塞）

若产品后续要求「主题 / 密度」跨设备同步，可新增下列概念（**不在本特性首版实现范围内**）：

| 实体（概念名） | 字段（示例） | 关系 |
|----------------|--------------|------|
| **UserAppearancePreference** | `user_id`（若未来有认证）、`theme`（`light` \| `dark` \| `sepia`）、`editor_font`（`system` \| `serif`）、`density`（`comfortable` \| `compact`） | 0..1 对 User；当前单用户本地可退化为 `localStorage` |

**校验规则（若实现）**：`theme` 枚举闭集；`density` 影响间距令牌覆盖而非硬编码像素散落。

## 状态转换

本特性不涉及业务状态机变更。UI 侧可选：`prefers-reduced-motion` 媒体查询 → 仅影响 CSS，无持久化。
