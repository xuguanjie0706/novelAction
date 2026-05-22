# Bootstrap 阶段「不计 token」优化全案

> 视角：一个干了 30 年的总编辑 + 资深提示词工程师 + 系统架构师，对你现有 `apps/backend/app/services/bootstrap/` 真实代码逐步审稿。
> 前提：**token 不是约束**。凡是"为了省 token 才这么写"的地方，一律推翻重设计。
> 基线：本案已对照 `graph.py` / `steps/*.py` / `graph_gates.py` / `parse.py` / `context.py` 真实实现，引用的 `ctx` 键、字段名、函数名均来自现有代码，不是臆造。

---

## 0. 现状基线（先看清楚再动手）

真实拓扑（`graph.py` 的 `_build_graph`，与旧 CLAUDE.md 描述已有出入）：

```
START → positioning → gate(interrupt) → project
      → power_systems → gate_power_systems(interrupt)
      → factions → storylines → characters → gate_characters(interrupt)
      → skills_items → settings → volumes → gate_volumes(interrupt)
      → emotion_villain(并行: emotion_arc + villain_arc)
      → memory_relations(并行: memory + relations)
      → core_mysteries → opening_contract → consistency → END
```

注意：`vol1_chapters`（旧 Step 12.5）与 `ch1_scenes`（旧 Step 13）**已移出 Bootstrap**，节点保留在 `graph_nodes.py` 供写作阶段调用。另存在一条更细的平台变体 `graph_fanqie.py`（`golden_finger / face_slap_map / power_ladder / rhythm_map / contrast_design / character_functions / opening_5chapters / signal_audit / algo_positioning`）——这条线其实已经在往本案推荐的方向走了，下文第 3、5 节会专门讲收敛。

**当前体系的四条根性约束（全部由"省 token"导致）：**

1. **每步都是 single-shot**：`_call_with_retry → parse_json → 落库`。唯一例外是 Step 0 positioning（带 3 次 schema 校验重试）。没有"生成→自评→修订"的反思回路，也没有多候选择优。第一个能解析成功的 JSON 就被当成最终稿。
2. **上下文是有损摘要**：`ctx` 里全是被截断的字符串——`world_overview[:300]`、`premise[:600/700/800/1000/1500]`（每步不一样）、`power_summary` 只取 `level_names[:8]`、`char_id_hint` 只取前 8 人。下游步骤看到的永远是上游的"残卷"。
3. **闸门只在 Step 0/2/5/9 且只做人工确认**：`gate_auto` 的自动模式只是"自动放行"，**不做质量打分**。没有任何一步会因为"生成质量不达标"被强制重生成。
4. **`consistency_scan` 只检测、不修复、不回环**：`_structural_precheck`（代码预检）+ AI 叙事层分析，结果写进 `Project.extra['consistency_issues']` 就结束了。发现矛盾 → 不修 → 直接 END。

下面先立总纲（七条横切原则），再逐步开方。

---

## 1. 七条总纲（横切所有步骤）

这七条是"不计 token"后**真正能拉开质量差距**的杠杆，比任何单步 prompt 微调都重要。

### 纲一：单发 → 候选池 + 评委团（Best-of-N + LLM-as-Judge）

每个关键步骤不再"生成一份"，而是：

```
并行生成 N 份候选（N=3~5，不同 temperature / 不同切入角度）
  → 评委团逐份打分（结构分 + 编辑分）
  → 选最高分；或让"主编"做一次跨候选择优合并（take best of each）
  → 进入修订回路
```

- 适用：positioning、title、characters、volumes、core_mysteries、opening_contract（创意密度高、一次难中的步骤）。
- 关键：候选要"有差异"而不是"同一答案换皮"。在 prompt 里给每个候选**强制不同的切入约束**（例如标题候选：①意象流 ②冲突流 ③人物流 ④反差流 ⑤数字/悬念流）。

### 纲二：Reflexion 自评修订回路（generate → critique → revise → validate）

把 Step 0 已有的"3 次 schema 重试"升级为**全步骤通用的内容级回路**：

```
draft = generate()
for round in range(MAX_ROUNDS):          # 不计 token，可放到 3~5 轮
    review = critique(draft)              # 独立调用，扮演挑刺编辑
    if review.pass and validate(draft):   # 代码不变量 + 编辑评分双过线
        break
    draft = revise(draft, review)         # 带着批注重写，而非从零再来
```

- `critique` 必须是**独立的 AI 调用**，且 system prompt 是"找茬的副主编"，不是原作者自己回看（自评分严重虚高，见 Step 0 的 `hook_test` 自评）。
- `revise` 喂入"上一稿 + 批注"，定向改而不是重抽——保留已经对的部分。

### 纲三：去摘要化——全保真上下文

把 `ctx` 从"一堆截断字符串"改成**双轨**：

- `ctx.summary_*`：保留现有摘要，给"只需要一句话提示"的场景。
- `ctx.full_*`：完整结构化对象（完整 `levels[]`、完整人物卡 JSON、完整 `villain_arc`），给"需要严密对齐"的下游步骤。

所有 `[:300]` `[:700]` `[:800]` 这类魔法截断**全部删掉**。例如：

- `power_systems` 给 `characters` 的不再是 `power_summary`（前 8 个境界名拼接），而是**完整 levels 表 + rank 映射**，这样 `current_realm` 不可能填到不存在的境界。
- `factions` 给 `characters` 的不再是 `faction_summary` 字符串，而是**完整 faction 列表含 id**，从源头消灭"名字映射回退"的脆弱性。

### 纲四：全局和声 Pass（Showrunner's Table Read）

在所有步骤生成完之后、`consistency` 之前，插一个**"围读修复"回路**：

```
把全部产物（项目/境界/势力/故事线/人物/技能/道具/设定/卷骨架/情绪图/反派线/谜题/承诺）
完整喂进去
  → 找矛盾（语义级）
  → 不是写进 issues 列表，而是直接产出"修复补丁"（patch: 改哪张表的哪个字段成什么）
  → 应用补丁 → 重新扫描
  → 迭代到"零 high-severity"或达到 MAX_ROUNDS
```

这把 `consistency_scan` 从"体检报告"升级成"主编改稿到能签约为止"。

### 纲五：编辑部多角色评委（不是一个全能 AI，是一个编辑部）

现在所有 system prompt 都是"你是有 30 年经验的总编辑"——一个人格扮演所有角色，视角会糊。改成**五个独立人格**，每个只盯一件事：

| 评委 | 只负责 | 否决权场景 |
|---|---|---|
| 爽点编辑 | 打脸/升级/情绪收益密度 | 连续多卷无爽点 |
| 文笔/声音编辑 | 人物 voice 区分度、台词不出戏 | 人物台词同质化 |
| 设定/逻辑编辑 | 境界/技能/道具/势力联表自洽 | 力量曲线断裂 |
| 反派编辑 | 反派自驱力、威胁升级、代价 | 反派沦为障碍物 |
| 目标读者模拟器 | 扮演真实读者的弃书点 | 第 X 章想弃 |

评委结论喂回纲二的 `revise`。**关键反作用**：再加一个"差异化守门人"——专门防止评委把作品越改越像套路平均值（多候选 + 多评委天然会向"安全的同质化"收敛，必须有人专门唱反调）。

### 纲六：把"prompt 里的规则"升级成"代码里的不变量"

现在大量编辑铁律是**写在 prompt 里靠模型自觉**，模型违反了没人查。例如：

- `emotion_arc`："连续 3 卷 negative 必须穿插 1 卷 positive" —— 纯口头约束。
- `core_mysteries`："reveal_chapter 不得超过总章数 90%"、"不同谜题 reveal 不能集中同卷" —— 纯口头约束。
- `volumes`："planned_chapters 之和接近 total_chapters" —— 代码只对单卷做了 15~80 裁剪，**没校验总和**。

全部改成**生成后用代码校验不变量**，违反 → 触发纲二的定向重生成（只重生成违规的那一段，不全推翻）。这类校验是确定性的、零幻觉的，应该是第一道防线。

### 纲七：结构化解码 + 模型分工

- **JSON 可靠性**：现在靠 `parse.py` 的正则容错（修智能引号、尾逗号、无引号键）。不计 token 的话，改用**结构化输出 / function-calling / JSON-Schema 约束解码**，再加一个"解析失败 → 把坏 JSON 和 schema 一起喂回模型让它修"的回路，取代正则补丁。
- **模型路由**：`llm_task_profiles.py` 已经按任务调温度。再进一步——**结构规划类**（volumes / power_systems / core_mysteries）走擅长长程一致性的强模型；**评委**走另一个模型（异构评委更能挑出同源盲区）；**voice/台词**走文采型模型。

---

## 2. 逐步开方（Step 0 → 14）

每步给三件事：**现状诊断 → 三维优化（编辑/提示词/架构）→ 可落地的关键改写或不变量**。

---

### Step 0 · positioning（立项会议）

**现状**：`steps/positioning.py`。已是全管线最成熟的一步——有 `try_validate_positioning` schema 校验 + 3 次重试，字段含 `hook_test`、`market_risk`、`differentiation_durability`。

**诊断**：
- `reference_works`（参照作品）由模型凭记忆生成，**无任何真实市场数据 grounding**，容易给出过时或不存在的"同流派代表作"。
- `hook_test` 让模型**自己给自己的钩子打分**（"自评分:X"）——自评分系统性虚高，是典型的不可信信号。
- 单份 positioning = 单一市场判断，没有"如果换个定位会怎样"的对比。

**编辑维度**：立项会议在真实编辑部是**多人拍桌子**的。应该产出 2~3 个**互相竞争的定位方案**（例如"稳健套路向" vs "差异化博出位向"），各自标注预期签约率/天花板/风险，让人工在 gate 选。

**提示词维度**：
- 把 `hook_test` 的自评**拆出去**，由独立的"目标读者模拟器"评委打分（system：你是一个从没看过此类书的 28 岁读者，只凭这 50 字决定点不点）。原作者不许给自己打分。
- `reference_works` 字段改为"先用检索拿到真实在榜作品，再让模型在**给定的真实候选**里挑 3 部对标"，杜绝硬编。

**架构维度**：
- 新增 **Step -1 / 0.5 竞品对标**：用检索（榜单/题材库语料）把真实在售作品喂进来，positioning 在"有据"基础上生成。
- positioning 走纲一（3 候选）+ 纲五（读者模拟器评委）。
- gate 已有 `action=regenerate`，扩成"在 N 个候选间切换 + 局部编辑"。

**落地不变量**：`tropes` 互斥检测（"种田流 + 无敌流"这类自相矛盾组合代码层拦截）；`emotional_arc ∈ {none,low,medium,high}`、`pace_type ∈ {fast,medium,slow}` 已隐含，做成硬枚举校验。

---

### Step 1 · project（项目基础信息 + 书名）

**现状**：`steps/project.py`。一次性生成 `title / genre / premise / world_overview / story_core`，直接建 `Project` 行。

**诊断**：
- **书名是网文点击率的头号变量，却是 single-shot 一个**。这是整个管线 ROI 最高的"省过头"的地方。
- `world_overview` 要求 300~500 字承载一部百万字小说的世界观——太薄。
- `premise` 是个 markdown 大 blob，难以结构化校验，也难被下游精确引用（下游只能 `premise[:700]` 截）。

**编辑维度**：书名要海选。真实编辑部一本书会列 20+ 备选名再筛。

**提示词维度**：
- 拆出 **Step 1.5 书名海选**：一次生成 15~20 个候选，**强制覆盖不同命名策略**（意象/冲突/反差/悬念/数字/人物），再让"标题评委"按"3 秒点击冲动 + 与 positioning 契合度"打分排序，gate 给人工终选。
- `premise` 改为**结构化对象**（定位/核心一句话/主题/核心矛盾/主角概况/结局倾向/收束边界/禁忌/视角各为独立字段），渲染时再拼 markdown。下游就能精确取 `premise.core_conflict` 而不是截字符串。

**架构维度**：`world_overview` 解除 500 字上限，允许长文 + 结构化（力量/势力/社会规则/地理/历史分块），下游按需取块（纲三）。

---

### Step 2 · power_systems（境界体系）

**现状**：`steps/power_systems.py`。`levels[]` 含 `rank/name/abilities/chapter_budget/gatekeeper`，`chapter_budget` 求和建议 ~70% 总章数，`coerce_power_system_rank` 兜底把中文境界名映射回 rank。

**诊断**：
- `chapter_budget 之和 ≈ 70% 总章数` 是**口头建议，代码没校验**。
- 没有"升级疲劳"审查——levels 可能能力描述前后雷同（每层都是"力量更强"），读者会腻。
- 没校验**境界层数 vs 卷数的承载关系**（境界太少撑不满全书，太多则每境界一笔带过）。

**编辑维度**：力量体系的灵魂是**每一层有"质变"而非"量变"**，且每层 `gatekeeper` 要能撑起一个高潮。应加"质变审查"：相邻两层的 `abilities` 必须有范式跃迁（解锁新玩法/新场景），不能只是数值+1。

**提示词维度**：在生成后追加一个"力量曲线评委"调用：把 levels 全表喂回，要求它指出"哪两层之间是注水的量变"并给出区分化建议，再 revise。

**架构维度**：
- 落地不变量：`sum(chapter_budget)` 必须落在 `[0.6, 0.8] × total_chapters`，否则按比例重排或重生成。
- 落地不变量：`len(levels) ≥ 6`（已要求）且 `protagonist_end_rank - start_rank` 提供的升级空间 ≥ 卷数（保证每卷至少推进感）。
- 把完整 `levels[]`（不是 `power_summary[:8]`）注入 characters/skills/consistency（纲三）。

---

### Step 3 · factions（势力体系）

**现状**：`steps/factions.py`。字段很全，`villain_timeline`（antagonist 必填、具体到卷）、`internal_factions`（内部派系）都是亮点。

**诊断**：**势力在人物之前生成**，所以 `internal_factions` 里提到的"代表人物"、`top_power`（最强战力）此刻**都还不是真实 Character 实体**。后面人物用名字字符串挂靠势力（`faction_name_to_id`），是脆弱的事后绑定。

**编辑维度**：势力的可信度来自"有名有姓的掌权者 + 内部裂痕"。现在内部派系是悬空的。

**提示词维度**：`villain_timeline` 已经很好，保持。增加要求：每个势力必须产出 1~2 个"待具象化的关键席位"（如"掌门""叛逃的二长老"），带功能描述，作为 Step 5 人物生成的**指定缺口**。

**架构维度（关键重构）**：把 factions 与 characters 改成**两段协同**而非前后独立：
- Step 3 生成势力 + "席位缺口清单"；
- Step 5 人物生成时**优先填这些缺口**并回写 `faction_id`（真实外键，不再靠名字回退）；
- 生成后做"势力—人物"双向闭合校验：每个 antagonist 势力至少绑定 1 个 antagonist 角色，否则补生成。

---

### Step 4 · storylines（故事线）

**现状**：`steps/storylines.py`。3~5 条线，每条 `name/line_type/core_conflict/resolution_direction`，恰好 1 条 main。

**诊断**：**最单薄的一步**。故事线只有"它是什么"，没有"它在哪几卷推进、占多少戏"。卷骨架里只用 `storyline_hint` 软提示"每卷 summary 应说明推进了哪条线"——没有任何映射或校验。结果：支线常常埋了不收、感情线占比失控。

**编辑维度**：长篇的"线管理"是命门。每条线需要**卷级在场矩阵** + **戏份预算** + **明确收束卷**。

**提示词维度**：故事线生成时即要求每条线给 `volume_presence`（这条线在第几卷起、第几卷收、各卷强度 1~3）和 `screen_time_pct`（占全书戏份）。所有线 `screen_time_pct` 之和 = 100%。

**架构维度**：
- 新增 **Step 4.5 故事线 × 卷 在场矩阵**：交叉表（行=故事线，列=卷），每格标"推进强度"。这张矩阵注入 volumes（让每卷 conflict 真正对齐某条线）和 consistency（校验"每条线都有起有收"）。
- 落地不变量：每条 `sub/romance/...` 线必须有 `resolve_volume`，且 ≤ 总卷数；main 线收束卷 = 末卷；`screen_time_pct` 求和 = 100%。

---

### Step 5 · characters（人物库）

**现状**：`steps/characters.py`。最复杂的一步：8 核心 + 5 开局配角，含 `speech_kit`、`arc_stages`、`debt_to/detonation_vol`、`fear/secrets`。生成后构建 `char_profiles`。

**诊断**：
- `speech_kit.sample_dialogues` 被**硬限制"合计≤4 条、每条≤40 字"**，注释明说是"避免输出过长被网关截断"——**这是为省 token 而牺牲了全书最重要的差异化资产（人物 voice）**。
- `char_profiles` 里 `biggest_lie` **被硬编码为空**（"由 arc 隐含，暂不单独生成"），`relationship_pressure` 也空。人物弧线缺了"谎言/伤口/渴望/需要"这条经典骨架的关键一环。
- 人物**先于关系生成**（关系在 Step 11），所以人物被创建时"不知道自己和谁什么关系"，导致动机和关系两张皮。
- `current_realm` 靠 `power_summary` 提示，仍可能填到不在白名单的境界（靠 consistency 事后抓）。

**编辑维度**：voice 是网文的护城河。要为每个核心角色建**完整声音圣经**（口头禅/句长/禁忌词/在不同情绪下的说话变化/内心独白风格/12+ 条典型台词），而不是 4 条 40 字。`biggest_lie / want / need` 必须显式生成——这是人物弧线的发动机。

**提示词维度**：
- 解除 `sample_dialogues` 上限（不计 token），每个核心角色单独一次"voice 圣经"生成调用，产出多场景台词样本。
- 显式生成 `biggest_lie`（角色相信的关于自己/世界的谎言）、`want`（想要）、`need`（真正需要），并要求 `arc` = 从相信谎言到看见 need 的轨迹。

**架构维度（关键重构）**：
- **人物 + 关系合并为一个"卡司构建"子流程**：先生成人物骨架 → 立即生成关系网 → 再回填每个人物"被关系塑造后的动机微调"。消灭两张皮。
- 把完整境界 `levels` 表注入（纲三），`current_realm` 用枚举校验（落地不变量），不合法立即定向重生成该角色。
- `debt_to`/`detonation_vol` 已是好设计；增加校验：所有 `detonation_vol` 不能都堆在同一卷（债务要分散引爆，和 core_mysteries 的 reveal 分散同理）。

---

### Step 6 · skills / Step 7 · items（技能与道具）

**现状**：`steps/skills.py`、`steps/items.py`。都强制 `plot_hook`（何时被夺/损毁/揭露代价），用 UUID 挂掌握者/持有者，名字回退映射。

**诊断**：
- 技能与道具**互相独立生成**，没有"组合设计"（招式 × 法宝的化学反应是战斗爽点的核心，现在没人管）。
- 所有 `plot_hook` 是各写各的，**没有去重 / 时序编排**——可能多个 hook 都被设定在"第 2 卷高潮"同一时刻引爆，造成拥挤。
- `grade`（技能/道具品阶）与 `power_system` 境界**没有对齐校验**（divine 级功法配 mortal 级体系会割裂）。

**编辑维度**：道具/技能不是清单，是"成长里程碑"。它们的获得/损毁/进化应当**贴在卷骨架的关键节点上**，形成"读者预期—兑现"的节拍。

**提示词维度**：skills 与 items 改为**同一次生成或显式交叉引用**，要求至少 1~2 组"功法+法宝联动"（法宝放大某功法、某功法是用某法宝的钥匙）。

**架构维度**：
- 合并 `skills_items`（图里本来就是合并节点 `node_skills_items`）为"装备库"统一生成，共享人物/势力上下文。
- 落地不变量：所有 `plot_hook` 的触发卷做**直方图校验**，同卷 hook 数超阈值 → 重排到相邻卷；`grade` 与体系 `levels` 数量做档位映射校验。

---

### Step 8 · settings（世界观设定卡）

**现状**：`steps/settings.py`。按 `GEMINI_SETTING_BLUEPRINTS` 分批并行（6 张/批），明确"不要重复境界/势力"，`who_knows_now` 要求填真实人名。已经是工程上比较成熟的一步。

**诊断**：批次之间**并行且互不可见**（`asyncio.gather`），所以两批可能各自写出语义重叠/口径冲突的设定卡，没有跨批去重/对齐。

**编辑维度**：设定卡的价值在"能落地的名词、规则、代价、例外、冲突"（prompt 已要求，很好）。缺的是"卡与卡之间不打架"。

**提示词维度**：保持分批生成，但加一个**批后融合调用**：把全部设定卡标题+摘要喂回，做"撞车检测 + 口径统一"，重写冲突卡。

**架构维度**：`gen_settings_append` 已有"防撞车"逻辑（喂已有标题去重），把这套逻辑**前置到首轮批间**，而不只用于事后追加。

---

### Step 9 · volumes（卷级骨架）

**现状**：`steps/volumes.py`。强项很多：`words_to_plan(tw)` 定卷数、phase 单调推进、`villain_timelines` 对齐 phase、`entity_block` 实体校验、生成后 `lint_volume_entity_issues`。

**诊断**：
- 卷数**完全由字数硬算**（`n_volumes = plan["total_volumes"]`），且强制"数组长度必须等于 n_volumes"。这在结构上很整齐，但**故事的自然弧段数不一定等于字数除法**——强行凑卷会注水或挤压。
- `planned_chapters` 只对单卷做 15~80 裁剪，**总和没校验**（口头说"尽量接近"）。
- `summary` 截到 60 字，卷级信息太薄，下游章纲展开时缺料。

**编辑维度**：卷的切分应服务"情绪/冲突的自然换气点"，字数是约束不是目标。允许在 `n_volumes ± 1` 的弹性区间里，让模型按叙事节拍定卷，再校验总章数落在目标带宽内。

**提示词维度**：把 Step 4.5 的"故事线×卷在场矩阵"注入，让每卷 `conflict` 明确承接某条线的某段，而不是泛泛"矛盾升级"。

**架构维度**：
- 落地不变量：`sum(planned_chapters)` 必须落在 `[0.9, 1.1] × total_chapters`，否则定向重排（只调整偏离最大的卷）。
- phase 序列校验已隐含，补一条代码校验：`opening` 必为首卷、`climax/ending` 必在末段，违反则纠正。

---

### Step 9.5 · emotion_arc（情绪节律图）

**现状**：`steps/emotion_arc.py`。总编辑视角给每卷情绪收支（deposit/cost/net_balance/dominant_emotion），写 `Project.extra['emotion_arc']`。编辑铁律写在 prompt 里。

**诊断**：四条编辑铁律（连续 3 卷 negative 必穿插 positive、climax/ending 必 positive、opening 必 positive、全书至少 1 卷 warm/romantic）**全是口头约束，零代码校验**。模型违反了直接落库。

**提示词维度**：铁律保留，但作为"软目标"；硬约束移到代码。

**架构维度（这步最该上不变量）**：
- 生成后用代码逐条校验那四条铁律 → 任一违反 → 把"违规说明 + 原情绪图"喂回做定向 revise（纲二），而不是接受。
- 与 `villain_arc` 是并行节点（`node_emotion_villain`），但二者**逻辑强相关**（反派 win 的卷往往该是 negative）。建议并行生成后加一次"情绪图 × 反派线"对齐校验：`villain vol_result=win` 的卷 `net_balance` 不应为 positive。

---

### Step 9.8 · villain_arc（反派行动线）

**现状**：`steps/villain_arc.py`。每卷反派 `vol_goal/obstacle/key_choice/cost/result/threat_escalation/hidden_move`，铁律含"dark_hour 卷必 win、climax 卷必 lose、vol_goal 不得写'阻止主角'"。设计思想很好（反派是第二引擎）。

**诊断**：同 emotion_arc——**铁律全靠模型自觉**。尤其"vol_goal 不得写'阻止主角'"这种最容易被违反（模型偷懒就写"阻止主角"）。`hidden_move` 是绝佳设计但无人校验它是否真的"埋在主角盲区"。

**编辑维度**：反派线要和 core_mysteries、故事线的 antagonist 线**三表合一**，否则反派的"隐藏布局"和"核心谜题"会各说各话。

**提示词维度**：`vol_goal` 加反例清单 + 代码关键词拦截（含"阻止/打败/对抗主角"字样直接判失败重生成）。

**架构维度**：
- 落地不变量：`dark_hour` 卷 result 必 win、`climax` 卷 result 必 lose、每卷 `vol_cost` 非空、`vol_goal` 不含禁用词。
- `hidden_move` 与 `core_mysteries` 建立引用：反派的隐藏布局应当能对应到某条核心谜题的 lay/heat，形成"反派做局—读者后知后觉"的闭环。

---

### Step 10 · memory（记忆库种子）

**现状**：`steps/memory.py`。10 条种子记忆（境界锚点/人物初态/故事线起点/设定规则/核心伏笔），自动 embed。

**诊断**：10 条对百万字小说是**最低限度**，且是凭空生成而非从前面已落库的结构化数据**抽取**。它和 power/character/storyline/foreshadow 表其实是**冗余的二次表达**，可能与源表口径不一致。

**架构维度（重构思路）**：记忆种子不该"再生成一遍"，而该**从已落库的真实实体里抽取/投影**——把境界 levels、人物初始 realm、故事线 start、core_mysteries 的 lay 直接转成记忆条目（确定性，零幻觉），再让 AI **补充**那些结构表里没有的"隐性规则/口头约定"。这样记忆永远是源表的忠实投影 + 增量。不计 token 的话，种子量从 10 提到 30~50。

---

### Step 11 · relations（人物关系）

**现状**：`steps/relations.py`。只覆盖 `core_char_names`，pairwise，`unresolved_tension/trigger_event` 必填，写 `evolution_note`。

**诊断**：
- 关系是**单向行**（A→B），没有**互反一致性**校验（A→B 是"师徒"，B→A 应是"徒师"而非随便）。
- 与人物生成割裂（见 Step 5 重构建议）。
- 没有"关系网拓扑"校验（主角应当与多数核心角色有连边，不能有孤立核心角色）。

**架构维度**：
- 并入 Step 5 的"卡司构建"子流程。
- 落地不变量：互反关系类型一致性表；主角连通度校验（主角到每个核心角色有路径）；`intensity ∈ [1,10]`。
- `trigger_event`（关系质变事件）应当能对应到某卷——和故事线/反派线挂钩，否则只是孤立设定。

---

### Step 11.5 · core_mysteries（核心谜题）

**现状**：`steps/core_mysteries.py`。5~8 条跨卷谜题，每条锚定 lay/heat/reveal 章号，写 `Foreshadow` 表。设计是全管线最有"长篇钢筋"意识的一步。

**诊断**：lay/heat/reveal 都是**模型猜的绝对章号**，而此时**章节根本还没生成**（chapter_plan 已移出 bootstrap）。这些章号：
- 不保证落在合法卷边界内；
- 铁律"reveal ≤ 90% 总章""不同谜题 reveal 不集中同卷""heat 至少 3 个均匀分布"——**全口头**。

**编辑维度**：谜题是"读者追更的隐形绳索"（prompt 原话，认同）。绳索的张力来自**节奏均匀**，所以分布校验是刚需。

**架构维度**：
- 把章号锚点改成**卷锚点 + 卷内相对位置**（lay=第1卷前段，reveal=第6卷中段），等章纲在写作阶段展开时再落到具体章。这样不依赖尚不存在的章节。
- 落地不变量：`reveal ≤ 0.9 × total`；reveal 卷分布做唯一性/分散校验；`lay < heat[*] < reveal` 单调；至少 1 条 `identity` 类型（已要求，代码兜底校验）。
- 与 villain_arc 的 `hidden_move` 交叉引用（见 9.8）。

---

### Step 12 · opening_contract（开局追读承诺）

**现状**：`steps/opening_contract.py`。前 10 章追读承诺（200 字测试/章1钩子/章3爽点/章5伏笔/章10订阅理由），并 `seed_reader_promises` 落 `ReaderPromise`。

**诊断**：这是"签约审核项"，质量极高度依赖这一份的好坏，**却是 single-shot**。而且这些承诺**在 bootstrap 阶段无法被验证**——要等真正写出第 1 章才知道兑现没兑现（写作阶段的 ReaderPromise 闭环负责，但 bootstrap 内没有任何"承诺可行性"预检）。

**编辑维度**：开局是网文生死线。这一份该用纲一（多候选）+ 纲五（读者模拟器评委打"追读意愿分"）双重加固。

**提示词维度**：每条承诺要求附"反例"（"不要写'小小展示实力'这种废话"已有，扩展到每个字段）。

**架构维度**：
- 多候选 + 读者模拟器择优。
- 落地校验：`chapterN_*` 承诺与 core_mysteries 的 `lay_chapter`（前 20 章内）对齐——开局伏笔应当就是某条核心谜题的埋设，不要两套伏笔体系打架。

---

### Step 14 · consistency（一致性扫描）

**现状**：`steps/consistency_scan.py`。两阶段——`_structural_precheck`（死亡人物仍出场/技能境界倒挂/道具登场缺口/卷序跳号/势力实体）纯代码，AI 补语义层。结果写 `Project.extra['consistency_issues']`。

**诊断**：**只检测，不修复，是终点**。发现 high-severity 矛盾后，流程照样 END。等于体检报告塞抽屉。

**架构维度（升级为纲四的修复回路）**：
```
issues = precheck + ai_scan
while issues.has_high and round < MAX:
    patches = propose_patches(issues, full_state)   # 产出"改哪表哪字段成什么"
    apply_patches(patches)                          # 写库
    issues = precheck + ai_scan                     # 重扫
```
- `propose_patches` 要求模型给**结构化补丁**（target_table / target_id / field / new_value / reason），而非散文建议。
- `apply_patches` 走白名单字段，禁止改主键/外键拓扑。
- 收敛失败（达到 MAX 仍有 high）→ 落"必须人工介入"标记，进 gate。

`_structural_precheck` 本身可以扩更多确定性规则（纲六的不变量都该在这里集中实现）：故事线收束完整性、emotion_arc 铁律、core_mysteries 分布、plot_hook 拥挤、关系互反一致性、势力—反派绑定。

---

## 3. 新增 / 重排步骤建议（汇总）

| 位置 | 新增步骤 | 作用 | 对应总纲 |
|---|---|---|---|
| Step -0.5 | 竞品对标（检索 grounding） | 给 positioning/reference_works 真实市场依据 | 纲七 |
| Step 1.5 | 书名海选（20 候选 + 评委排序） | 最高 ROI 的"省过头"修正 | 纲一 |
| Step 4.5 | 故事线 × 卷 在场矩阵 | 解决支线埋了不收、戏份失控 | 纲六 |
| Step 5（重构） | 人物 + 关系合并为"卡司构建" | 消灭人物/关系两张皮 | 纲三 |
| Step 6+7（合并） | 装备库统一生成 + 联动设计 | 技能×道具组合爽点 | — |
| Step 9.9 | 设定和声（power×skill×item×faction 联表校验） | 力量曲线/品阶/势力自洽 | 纲六 |
| Step 13.5 | 全局围读修复回路（升级 consistency） | 检测→修复→再扫到不动点 | 纲四 |

**关于 `graph_fanqie.py`**：你们这条变体已经把"打脸地图 / 金手指 / 力量阶梯 / 节奏图 / 反差设计 / 角色功能 / 开局5章 / 信号审计 / 算法定位"拆成了独立步骤——这正是本案纲六（细粒度可校验单元）的方向。建议不要维护两套并行图，而是把 fanqie 的细粒度步骤**抽象成主图的可插拔编辑模块**，由 positioning 的 `pace_type/平台` 决定启用哪些（番茄向启用打脸地图+信号审计，起点向启用力量阶梯，等等）。

---

## 4. 架构落地：如何贴合你们的"编排薄壳"红线

本案所有"回路/候选/评委"必须落进现有红线（单文件 <600、薄壳模式、step 三段式），否则会把薄壳重新养成上帝文件。落地方式：

**4.1 新建 `services/bootstrap/critics/` 包**（评委团，纲五）
```
critics/
├── __init__.py          # 评委注册表
├── base.py              # Critic 协议: async def review(draft, ctx) -> Review
├── pacing_critic.py     # 爽点编辑
├── voice_critic.py      # 文笔/声音编辑
├── logic_critic.py      # 设定/逻辑编辑
├── villain_critic.py    # 反派编辑
├── reader_sim.py        # 目标读者模拟器
└── diversity_guard.py   # 差异化守门人（防同质化）
```
每个评委是独立 AI 调用、独立 system 人格、独立 model 路由。

**4.2 step 内三段式升级为四段式**（纲一/二）
现有 step 已是 `_build_prompt / _persist`。升级为：
```
_build_prompt   → 构造（含候选差异约束）
_generate_n     → 并行 N 候选（纲一）
_critique       → 评委团打分 + 选优/合并
_revise_loop    → Reflexion 回路到达标（纲二）
_validate       → 代码不变量（纲六）
_persist        → 落库（不变）
```
薄壳 `graph.py` 完全不动——它只管 yield 事件和分发节点。回路全在 step 文件内，单文件仍可控（把不变量校验抽到 `validators/`）。

**4.3 `gate_auto` 升级为质量门**（纲一/四）
现在自动模式只是"自动放行"。改成：自动模式下先跑评委打分，**分数过线才放行，不过线自动触发该步 regenerate**（复用已有的 `regenerate_power_systems/characters/volumes` 机制），人工模式则把评委分一并 `emit` 给前端供参考。

**4.4 `ctx` 双轨化**（纲三）
`context.py` 增加 `ctx["full"]` 命名空间装完整结构化对象；保留现有摘要键向后兼容。新代码取 `ctx["full"]`，老代码不受影响，渐进迁移。

**4.5 全局围读**（纲四）
新建 `steps/table_read.py`（`gen_table_read_repair`），放在 `consistency` 之前或合并进 `consistency`，产出结构化补丁并应用。补丁应用器 `services/bootstrap/patch_apply.py`（白名单字段）。

---

## 5. 落地优先级（ROI 排序）

不计 token ≠ 一次全上。按"质量增量 / 实现成本"排序：

1. **书名海选（Step 1.5）** — 投入极小，ROI 最高。一次生成 20 个 + 评委排序即可。
2. **代码不变量层（纲六）** — 把 emotion_arc/villain_arc/volumes/core_mysteries/storylines 的口头铁律变成 `validators/` 里的确定性校验 + 定向重生成。零幻觉、收益立竿见影。
3. **consistency 升级为修复回路（纲四 / Step 13.5）** — 把"体检报告"变成"改到能签约"。复用已有 precheck。
4. **去摘要化（纲三）** — 删掉所有 `[:300]/[:700]` 截断，ctx 双轨。消灭一大类"下游看不全上游"的隐性 bug。
5. **人物 voice 解锁 + 卡司构建合并（Step 5 重构）** — 护城河资产，但改动较大。
6. **评委团 + Best-of-N（纲一/五）** — 质量天花板最高，但实现与调参成本也最高，放在框架（critics 包 + 四段式）就位后铺开。
7. **竞品对标 grounding（Step -0.5）** — 依赖检索语料/榜单数据源，基建成本最高，最后做。

---

## 6. 风险与反作用（总编辑的"踩刹车"）

不计 token 的优化有它自己的副作用，必须同时设防：

- **多候选 + 多评委会把作品推向"套路平均值"**：评委都偏好"安全的爽"，合议结果趋同质化。**对策**：纲五的"差异化守门人"有一票否决"这跟市面上 X 本书没区别"的权力。
- **自评分不可信**：Step 0 的 `hook_test` 自评、任何"让作者给自己打分"都系统性虚高。**对策**：打分一律由**独立人格、最好异构模型**的评委做，原作者不参与评分。
- **修复回路可能不收敛**：补丁改 A 引入 B 矛盾。**对策**：`MAX_ROUNDS` + 每轮 high-severity 必须单调下降，否则停手转人工 gate。
- **全保真上下文会诱导"抄设定"**：把完整设定喂进去，模型可能整段复述而非创造（Step 8 的"不要重复"正是在防这个）。**对策**：上下文分"参照区（只读不抄）"与"扩展区（在此基础上新增）"，prompt 明确指令。
- **延迟与失败面放大**：N 候选 × 多评委 × 多轮 = 调用数指数级增长，单步耗时和失败概率都涨。现有 `_run_step` 是 300s 超时 + 失败 interrupt 人工重试——回路化后要把超时/重试粒度下沉到"候选级"和"轮次级"，避免一个候选拖垮整步。
- **多 worker checkpoint 问题已是现存隐患**：`graph.py` 用进程内 `MemorySaver`，`WEB_CONCURRENCY>1` 会 resume miss。回路化让单 run 存活更久，**更容易撞上重启丢 checkpoint**——上线前应先切 `PostgresSaver`（代码注释里已标注），否则本案的长回路会放大这个 bug。

---

## 附：一句话总括

> 现在的 Bootstrap 是**一条高质量的单行流水线**——每个工位都很用心，但都"做完就交给下一站"。
> 不计 token 之后，要把它改成**一个有编辑部、有围读、有返工的出版社**：每份稿子多人写、多人挑、改到达标、最后全员围读到无硬伤才签约。
> 真正的杠杆不在某一步的 prompt，而在于**把"口头铁律"变成"代码不变量"，把"单发"变成"生成—评审—返工回路"，把"检测"变成"修复"**。
