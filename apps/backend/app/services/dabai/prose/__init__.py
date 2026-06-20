"""dabai 实验书架正文写作 pipeline（BeatContract + prompt 组装 + 编排）。

注意：不在包 init 里 import prompt_assemble，避免 draft_prompt ↔ pre_warn 循环 import。
"""

from app.services.dabai.prose.beat_contract import BeatContract, resolve_beats

__all__ = ["BeatContract", "build_prose_prompt", "resolve_beats"]


def __getattr__(name: str):
    if name == "build_prose_prompt":
        from app.services.dabai.prose.prompt_assemble import build_prose_prompt

        return build_prose_prompt
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
