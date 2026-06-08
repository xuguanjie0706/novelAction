"""大白文 bootstrap —— 独立分支（不复用主仓库 app/services/bootstrap）。

爽点节拍器内核：情绪势能 → 爽点引爆 → 即时反馈 → 强钩子。
入口：python -m dabai.run --logline "..." --mock
"""

__all__ = ["config", "pipeline", "linter"]
