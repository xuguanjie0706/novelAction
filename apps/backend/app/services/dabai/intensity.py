"""叙事烈度档（intensity）—— 大白文「降调/克制」总开关。

设计动机：整套 dabai 引擎默认按「爽点最大化」调（金手指当章见效、见证者递进到
心服、采样偏高温），缺一个让正文「收着写」的档位。本模块仿 ``writing_style``
（plain/standard/dense）那套——统一读取 + 全链路落点（正文 system / 采样 / 质检），
消除「正文降调、质检又按够炸验收」的跨环拉锯。

三档：
  - ``restrained``（克制）：见证者反应封顶在沉默/僵住，主角不喊口号，旁白禁感叹号堆砌
    与「全场哗然」套话，payoff 用冷处理代替全场沸腾；采样降温。
  - ``standard``（默认）：保持现有行为，不注入任何块、不改采样。
  - ``loud``（够炸）：显式允许更外放，目前与 standard 行为一致（保留档位以备扩展）。

写入侧：``Project.extra.intensity`` 与 ``positioning.intensity`` 双写（PATCH
``/dabai/projects/{id}/settings`` 落库）；下游统一经 ``resolve_dabai_intensity`` 读取。
"""
from __future__ import annotations

from typing import Any, Optional

VALID_INTENSITY = ("restrained", "standard", "loud")


def normalize_intensity(value: Any) -> str:
    """把任意输入规整为合法档位；非法/空回落 ``standard``。"""
    v = str(value or "").strip().lower()
    return v if v in VALID_INTENSITY else "standard"


def intensity_from_extra(
    positioning: Optional[dict],
    extra: Optional[dict],
) -> str:
    """优先 positioning.intensity，回退 extra.intensity，再回退 standard。"""
    pos = positioning if isinstance(positioning, dict) else {}
    raw = pos.get("intensity")
    if not raw:
        ex = extra if isinstance(extra, dict) else {}
        raw = ex.get("intensity")
    return normalize_intensity(raw)


def resolve_dabai_intensity(project: Any) -> str:
    """从 DabaiProject（或任何带 positioning/extra 的对象）解析烈度档。"""
    if project is None:
        return "standard"
    return intensity_from_extra(
        getattr(project, "positioning", None),
        getattr(project, "extra", None),
    )


_RESTRAINED_PROSE_BLOCK = (
    "\n★叙事烈度：克制档（降调，务必收着写）★：\n"
    "- 见证者反应封顶在「沉默、僵住、脸色发白、移开目光、低声议论」——"
    "禁止写跪地求饶、痛哭、狂呼、仰天、震天欢呼、不敢相信自己的眼睛；分级递进到「惊」即可，不到「跪服」；\n"
    "- 主角：赢了也克制——不喊口号、不仰天大笑、不大段内心狂喜独白，台词短而冷，"
    "情绪靠动作与细节落地，不靠形容词层层加码；\n"
    "- 旁白：禁感叹号堆砌（每段至多 1 个「！」），禁排比/连续反问渲染气势，"
    "禁「全场哗然/炸开了锅/鸦雀无声中突然爆发」这类套话；\n"
    "- 爽点落点用冷处理：对手哑口无言、四下死寂、没人敢接话、有人悄悄后退，"
    "胜过「全场沸腾」式喧闹；力度留白给读者自己体会；\n"
    "- ★正向替代★：情绪不靠台词/表情堆砌，靠**物件·动作·空间**转义——"
    "把愤怒写成捏碎的杯子、把胜利写成某人无声后退半步、把震惊写成茶盏停在半空；"
    "每场至少一个这样的「位移/物件反应」细节，让读者自己读出情绪。\n"
)

# standard / loud 也注入：降 AI 味，与 restrained 的「物件转义」同向但不降调
_WITNESS_PROSE_HINT = (
    "\n★见证者与自然度（硬）★：\n"
    "- 见证者反应须【分级递进】且【每章换写法】；优先物件/动作/空间（工具掉落、后退半步、"
    "算盘停、茶盏悬在半空），少用「不敢置信/如坠冰窟/眼珠子都要掉出来/倒吸凉气」；\n"
    "- 同一套话全书不超过 2 次；近章已出现的表达须换说法；\n"
    "- 多个见证者时：主见证者写满阶梯，次见证者只写一镜动作，勿人人「震惊三连」。\n"
)

_LOUD_PROSE_BLOCK = ""  # 预留：当前与 standard 同，避免无谓加码


def intensity_prose_block(intensity: str) -> str:
    """正文 system 注入块；standard 也带见证者自然度提示。"""
    intensity = normalize_intensity(intensity)
    base = _WITNESS_PROSE_HINT
    if intensity == "restrained":
        return base + _RESTRAINED_PROSE_BLOCK
    if intensity == "loud":
        return base + _LOUD_PROSE_BLOCK
    return base


_RESTRAINED_QC_NOTE = (
    "【叙事烈度验收 · 克制档】本书要求降调克制："
    "正文出现喊口号、感叹号过密、「全场哗然/炸开了锅」类套话、"
    "见证者跪服/痛哭/狂呼、主角仰天大笑或大段狂喜独白——均按缺陷处理，"
    "在 chapter_suggestions 写一条 [烈度] 前缀的修复建议并相应压低 hook_score；"
    "反之，直白、冷处理、留白克制不扣分。"
)


def intensity_qc_note(intensity: str) -> str:
    """质检 prompt 注入块；非克制档返回空串。"""
    if normalize_intensity(intensity) == "restrained":
        return _RESTRAINED_QC_NOTE
    return ""


def lab_write_sampling(intensity: str, *, replace_existing: bool = False) -> Optional[dict]:
    """正文写作采样档。

    - standard/loud：保持现有行为（重写时高温换写法，否则走 ``dabai.write`` 默认档）。
    - restrained：降温抑制浮夸；重写时仍降温但加大 penalty 换写法。
    """
    intensity = normalize_intensity(intensity)
    if intensity == "restrained":
        if replace_existing:
            return {
                "temperature": 0.62,
                "top_p": 0.88,
                "presence_penalty": 0.35,
                "frequency_penalty": 0.35,
            }
        return {
            "temperature": 0.6,
            "top_p": 0.88,
            "presence_penalty": 0.2,
            "frequency_penalty": 0.25,
        }
    # standard / loud：沿用原逻辑（重写高温，否则任务默认档）
    if replace_existing:
        return {"temperature": 0.92, "presence_penalty": 0.35, "frequency_penalty": 0.35}
    return None
