"""
AI Service — 统一使用 OpenAI 兼容协议

实现已迁至 ``app.services.ai`` 包（按能力拆分 Mixin），本模块仅保留兼容导入路径：
``from app.services.ai_service import AIService``。
"""

from app.services.ai import AIService

__all__ = ["AIService"]
