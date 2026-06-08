"""【已废弃存根】原「势力+功法+法宝」三合一步骤。

为支持「功法/法宝精确挂人物 UUID」，三合一已拆分为：
- ``factions_antagonist_doupo.py``：势力 + 卷级对立面（人物前）；
- 通用 CORE ``skills_items``：功法 + 法宝（人物后，精确挂 UUID + 按境界择人）。

本文件不再被任何地方 import（register_nodes 已改注册 factions_antagonist_doupo），
保留为空存根仅为避免历史引用 ImportError。请勿在此新增逻辑。
"""
from __future__ import annotations
