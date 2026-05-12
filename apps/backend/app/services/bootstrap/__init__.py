"""Bootstrap 子包：一句话创意 → 全量小说初始化。

编排薄壳仍在 ``services/generation_service.py`` 的 ``GenerationService``；本包包含：

- ``context`` / ``retry`` / ``parse`` / ``sse`` / ``prompts``
- ``steps``：14 个串行步骤实现（``gen_*``）
- ``save_all`` / ``completion``：方案 B 落库与补齐

外部 import 兼容性：原 ``generation_service`` 模块顶层 re-export 符号保持不变，
``from app.services.generation_service import _parse_json`` 等写法不受影响。
"""
