"""斗破式大白文玄幻线（mode=doupo）专属步骤包。

完全基于通用（sequential）线，仅替换三处题材语义步骤 + 一处合并：
- positioning_doupo：斗破式立项（输出对齐 xianxia positioning schema）
- power_axis_doupo：单条斗气主轴（replaces 修仙多轴 power_systems）
- factions_antagonist_doupo：势力 + 卷级对立面 一次 LLM（replaces factions，吞 antagonist_ladder）
- world_doupo：精简斗气大陆世界设定卡（replaces settings）
功法/法宝复用通用 CORE skills_items（人物后生成，精确挂人物 UUID）。
（world_kit_doupo.py 为已废弃存根，原三合一方案——见其文件头注。）

零番茄（fanqie）代码耦合。红线：每个文件 ≤ 600 行。
"""
