# 大白文 Bootstrap（独立分支 · dabai）

> 一条**完全独立**的大白文（番茄/七猫纯爽文）一句话生成链路。
> **不复用** `app/services/bootstrap/` 任何代码，自带 LLM 客户端、prompt、schema、编排器、linter。
> 离线 mock 可直接跑通并产出完整 JSON。

---

## 为什么要独立分支

主仓库的章纲引擎内核是**精品文因果链**：`欲望 → 障碍 → 选择 → 代价`，并把 `choice_cost` 非空设成 critical 阻断（CH-04）。

大白文的内核不是这个。大白文读者在手机上碎片化阅读，要的是**情绪势能 → 爽点引爆 → 即时爽感反馈 → 更强钩子**这条循环。在大白文里「零代价的爽」恰恰是卖点——主角扮猪吃虎、打脸装逼就是不用付代价，强行加代价反而劝退。

所以本分支换掉主引擎：章纲的一等公民不是「代价」，而是**爽点类型（shuang_type）**。整条链围绕「爽点节拍器」设计，linter 也换成大白文专属规则（校验爽点/憋屈/观众/钩子/信息密度/黄金三章，**不校验 choice_cost**）。

---

## 完整闭环链路

```
logline（一句话创意）
  │
  ├─ Step 1  positioning      立项定位    目标读者·爽点池·打脸频率·黄金三章·节奏·禁忌
  ├─ Step 2  golden_finger    金手指外挂  大白文爽点引擎（系统/吞噬/重生/天赋）+ 限制
  ├─ Step 3  power_ladder     境界阶梯    清晰可数的升级体系（升级爽的标尺）
  ├─ Step 4  factions         势力阵营    压迫方 vs 主角方（打脸对象的土壤）
  ├─ Step 5  characters       人物档案    主角 + 打脸对象 + 工具人配角
  ├─ Step 6  storylines       故事线      主线(升级打脸) + 可选感情线/复仇线
  ├─ Step 7  volumes          卷骨架      每卷爽点大节拍 + 卷末高潮 + phase
  ├─ Step 8  chapter_outlines 章纲        ★爽点节拍器（先排爽点序列，再展开每章）
  │
  └─ Step 9  linter           大白文质检  爽点/憋屈/观众/钩子/信息密度/黄金三章/反同质
       ↓
   complete bootstrap JSON
```

每一步：输入累积上下文 → JSON 导向 prompt → LLM/mock → parse → normalize → 进上下文。
全程产物均为 JSON，最终汇总成一份 `bootstrap_<slug>.json`。

---

## 爽点节拍器（本分支的核心创新）

章纲生成分两阶段，而不是一次性让 AI 填空：

**阶段 A · 排节拍序列**：先让 AI 为整卷排一串爽点类型（`打脸/升级/获宝/扮猪吃虎/救场/装逼/群嘲反转/收小弟…`），约束：
- 不连续同质（相邻章爽点类型必须换）
- 强度阶梯上升（每 N 章一个大爆点）
- 黄金三章必有强爽点

**阶段 B · 展开每章**：每章围绕指定的 `shuang_type` 填四拍：

| 字段 | 含义 |
|------|------|
| `yaqu_setup` | 憋屈势能：谁在压主角 / 什么不公（爽点的前置弹簧） |
| `shuang_type` | 本章爽点类型（一等公民，阶段 A 已排定） |
| `shuang_payoff` | 爽感量化：打了谁的脸 / 震了谁 / 当众获得什么（**必须有观众/见证者**） |
| `end_hook` | 章末强钩子：更大的危机或更大的爽点预告 |
| `new_info_count` | 本章引入的新东西数量（信息密度控制，超 2 报警） |

注意：**没有 choice_cost**。这是和主仓库最根本的区别。

---

## 大白文 linter 规则（替换 CH-* 那套）

| 规则 | 级别 | 检查 |
|------|------|------|
| `DB-01` | critical | `shuang_type` 为空——本章没有爽点 |
| `DB-02` | critical | 前 3 章无强爽点——黄金三章失守 |
| `DB-03` | high | `shuang_payoff` 为空 / 无观众——爽点没人看 |
| `DB-04` | high | `yaqu_setup` 为空——爽点没有憋屈势能 |
| `DB-05` | high | `end_hook` 为空 / 套话（「悬念丛生」类） |
| `DB-06` | medium | `new_info_count > 2`——信息密度超载 |
| `DB-07` | medium | 连续 3 章 `shuang_type` 相同——爽点同质化 |

**不阻断 `choice_cost`**（主仓库 CH-04 在大白文里是反的）。

---

## 运行

```bash
# 离线 mock 跑通（不需要 API key），产出完整 JSON
python -m dabai.run --logline "废柴少年觉醒吞噬系统，一路逆袭打脸天才" --mock

# 接真实 LLM（OpenAI 兼容）
export DABAI_BASE_URL="https://api.xxx.com/v1"
export DABAI_API_KEY="sk-..."
export DABAI_MODEL="gpt-4o-mini"
python -m dabai.run --logline "..." --volume-chapters 30

# 只看某一步
python -m dabai.run --logline "..." --mock --stop-after chapter_outlines
```

产物写到 `dabai/outputs/bootstrap_<slug>.json`，并打印 linter 报告。

---

## 目录结构

```
dabai/
├── README.md          本文档（设计 + 链路图 + 运行）
├── config.py          配置（模型/温度/卷数/链路顺序）
├── schemas.py         每步 JSON 输出契约 + 轻量校验
├── llm_client.py      OpenAI 兼容客户端 + mock 分发
├── mock_responses.py  离线 mock：连贯吞噬流样本（每步一份 JSON）
├── prompts.py         每步 JSON 导向 prompt（system + user 模板）
├── steps.py           每步生成函数（组装 prompt → 调用 → parse → normalize）
├── linter.py          大白文章纲爽点节拍器 linter
├── pipeline.py        编排薄壳（串联 step、累积上下文、落 JSON）
└── run.py             CLI 入口
```

> 架构遵循主仓库红线：单文件 ≤600 行；编排薄壳 + 步骤函数 + prompt/parse 分层。
