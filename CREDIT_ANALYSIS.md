# 网络小说生成系统 - 积分扣除逻辑覆盖分析

## 执行摘要

本报告对 novelAction 项目进行了全量代码扫描，分析所有 AI 生成/消耗算力的场景。

**整体评分：95/100 ✅**
- **覆盖率**：21/22 个 AI 端点已覆盖（95%）
- **缺口**：1 个端点（封面生成）未扣积分
- **优先级**：P0 立即修复

---

## 核心发现

### 积分系统架构

系统采用**两层积分控制**：

1. **预检层**（`credit_service.py`）
   - 余额查询与预检（`is_sufficient`）
   - 计费档位判定（heavy/standard/light）
   - 费率表：heavy 5+15，standard 1+3，light 0

2. **自动扣费层**（`llm_call_log.py`）
   - 所有 LLM 调用必经之路
   - **关键设计**：在 `log_llm_call()` 成功时自动调用 `credit_service.deduct()`
   - 保证日志与扣费原子性（同事务）

### 积分触发机制

```
用户请求 AI 功能
  ↓
AIService._call_ai() / _stream_ai()
  ↓
_preflight_credit_check()  ← 余额预检（若配置为 hard 则返回 402）
  ↓
LLM API 调用（httpx/OpenAI SDK）
  ↓
log_llm_call(user_id=..., status="ok")  ← 关键入口
  ↓
credit_service.deduct(user_id, cost, ...)  ← 自动扣费（原子）
  ↓
credit_transactions 流水记录
```

---

## AI 端点覆盖矩阵

| # | 功能 | API 端点 | 是否扣费 | 实现路径 |
|---|------|---------|--------|--------|
| A1 | Bootstrap 一句话 | `/bootstrap/stream` | ✅ | GenerationService → log_llm_call |
| A2 | 大纲展开 | `/outline/ai-expand` | ✅ | routes_ai_expand → log_llm_call |
| A3 | 大纲质检 | `/outline/ai-quality-check` | ✅ | routes_quality → log_llm_call |
| A4 | 大纲质检工作流 | `/outline/ai-quality-check/workflow` | ✅ | workflow_graph → log_llm_call |
| A5 | 大纲修复工作流 | `/outline/ai-repair/workflow` | ✅ | workflow_graph → log_llm_call |
| A6 | 质量门控写作 | `/ai/gated-draft-stream` | ✅ | gated_draft_routes → log_llm_call |
| A7 | 质量债务微调 | `/ai/quality-debt-micro-fix` | ✅ | quality_routes → log_llm_call |
| A8 | AI 对话 | `/ai/chat/stream` | ✅ | chat_routes → log_llm_call |
| A9 | 记忆提取 | `/ai/extract-memory` | ✅ | memory_routes → log_llm_call |
| A10 | 自动复盘 | `/ai/auto-debrief` | ✅ | debrief_routes → log_llm_call |
| A11 | 章节复盘 | `/ai/chapter-debrief` | ✅ | debrief_routes（仅数据，无 LLM） |
| A12 | 连贯性检查 | `/ai/chapter-coherence-check` | ✅ | coherence_routes → log_llm_call |
| A13 | 连贯性报告 | `/ai/chapter-coherence-reports` | ✅ | coherence_routes（仅数据） |
| A14 | 连贯性预览 | `/ai/chapter-coherence-apply/preview` | ✅ | coherence_routes → log_llm_call |
| A15 | 连贯性提交 | `/ai/chapter-coherence-apply/commit` | ✅ | coherence_routes（仅数据） |
| A16 | 写前预警 | `/ai/pre-write-warning` | ✅ | quality_routes → log_llm_call |
| A17 | 章节分析 | `/ai/chapter-analysis` | ✅ | quality_routes → log_llm_call |
| A18 | 读者模拟 | `/ai/reader-simulation` | ✅ | reader_simulation_routes → log_llm_call |
| A19 | 钩子检测 | `/ai/hook-check` | ✅ | quality_routes → log_llm_call |
| A20 | 分场计划 | `/ai/scene-plan` | ✅ | draft_routes → log_llm_call |
| A21 | 世界观生成 | `/ai/world-settings/generate` | ✅ | ai/world_settings_generate_routes → log_llm_call |
| A22 | 🔴 **封面生成** | `/cover/generate` | ❌ | **routers/cover.py → httpx 直接调用** |

---

## 严重缺口（Critical Gap）

### GAP-1：封面生成积分未扣

**文件**：`apps/backend/app/routers/cover.py`

**问题**：图片生成采用直接 httpx 调用，绕过 AIService

```python
# 当前实现（错误）
@router.post("/projects/{project_id}/cover/generate")
async def generate_cover(...):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{provider.endpoint}/v1/images/generations",
            headers={...},
            json={"prompt": prompt, ...},
        )
    # 落库到 cover_image_call_logs
    # ❌ 但未调用 log_llm_call()
    # ❌ 未进行积分扣费
```

**实际后果**：
- 所有封面生成调用零成本
- 用户可无限免费生成
- 流水记录缺失（仅有 cover_image_call_logs，无 credit_transactions）

**修复方案**：

```python
# 修复后（添加积分扣费）
from app.services.llm_call_log import log_llm_call

start = time.perf_counter()
try:
    response = await client.post(...)
    log_llm_call(
        mode='image_generation',
        model=provider.model_name,
        llm_endpoint=f"{provider.endpoint}/v1/images/generations",
        context={'project_id': project_id},
        duration_ms=int((time.perf_counter() - start) * 1000),
        status='ok',
        prompt_text=prompt,
        usage={'prompt_tokens': len(prompt.split())},  # 图片 token 估算
        output_payload={'image_url': result_url},
        user_id=current_user.id,  # ← 关键：传入用户 ID
        task='cover_generation',
        db=db,
    )
except Exception as e:
    log_llm_call(..., status='error', error=str(e), ...)
```

---

## 风险评估

| 风险 | 场景 | 现状 | 建议 |
|-----|------|------|-----|
| **RISK-1** | 流式响应中断 | ✅ 已在 finally 块处理 | 无需修复 |
| **RISK-2** | 工作流后台任务身份 | ⚠️ 需验证 | 检查 workflow context 传递 |
| **RISK-3** | 重试机制重复计费 | ✅ 仅记录成功调用 | 无需修复 |
| **RISK-4** | Bootstrap 部分失败 | ✅ 仅 status="ok" 扣费 | 无需修复 |

---

## 修复优先级

| 优先级 | 项目 | 工作量 |
|------|-----|--------|
| **P0** | [GAP-1] 封面生成积分扣费 | 1-2h |
| **P1** | [RISK-2] 工作流身份验证 | 2-3h |
| **P2** | [TEST] 集成测试覆盖 | 3-4h |

---

## 技术细节

### 费率表

```
档位        input 费率        output 费率       适用场景
heavy       5积分/1k         15积分/1k       GPT-4, Claude Opus
standard    1积分/1k         3积分/1k        GPT-3.5, Claude Haiku
light       0积分            0积分           本地模型（免费）
```

### 配置项

```python
# config.py
CREDIT_ENFORCEMENT: str = "soft"  # off | soft | hard
  - off：跳过检查（开发模式）
  - soft：允许调用，扣费后可为0（默认）
  - hard：余额<1 时返回 402（生产推荐）

CREDIT_NEW_USER_BONUS: int = 10000  # 新用户注册赠送
```

### 流水记录示例

```json
{
  "id": "uuid",
  "user_id": "user-uuid",
  "delta": -35,
  "balance_after": 9965,
  "ref_type": "llm_call",
  "ref_id": "llm_call_log-uuid",
  "model": "gpt-4o",
  "prompt_tokens": 1000,
  "completion_tokens": 2000,
  "task": "chapter_analysis",
  "created_at": "2026-05-14T12:34:56Z"
}
```

---

## 验证清单

- [ ] 修复 GAP-1（封面生成）
- [ ] 验证工作流中的 user_id 传递
- [ ] 测试流式中断场景
- [ ] 添加集成测试
- [ ] 更新 API 文档

---

**报告日期**：2026-05-14
**分析范围**：novelAction 全量代码扫描
**覆盖率**：95%+（21/22 端点）
