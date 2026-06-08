"""大白文章纲 linter（爽点节拍器质检）。

与主仓库 CH-* 规则的根本区别：
  - ★不校验 choice_cost★（大白文里零代价的爽是卖点，强加代价是反的）。
  - 校验的是大白文真正的命门：爽点明确、憋屈势能、爽感有观众、强钩子、
    信息密度、黄金三章、爽点不同质。

规则级别：critical 阻断落库，high/medium 仅警告。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dabai.config import DabaiConfig
from dabai.golden_finger_bind import is_awakening_chapter, lint_bind_ladder

# 套话黑名单（end_hook 命中即判废话）
_HOOK_CLICHES = ("悬念丛生", "让人期待", "敬请期待", "精彩继续", "欲知后事", "扣人心弦")

_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1}
BLOCKING = {"critical"}


@dataclass
class Issue:
    rule_id: str
    severity: str
    chapter: int | None
    message: str
    suggestion: str = ""

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "chapter": self.chapter, "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class LinterReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(i.severity in BLOCKING for i in self.issues)

    @property
    def status(self) -> str:
        if self.blocked:
            return "blocked"
        return "warning" if self.issues else "ok"

    def score(self) -> int:
        if not self.issues:
            return 100
        worst = max(_SEVERITY_RANK.get(i.severity, 1) for i in self.issues)
        return {3: 40, 2: 60, 1: 78}.get(worst, 80)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "score": self.score(),
            "issue_count": len(self.issues),
            "critical_count": sum(1 for i in self.issues if i.severity == "critical"),
            "issues": [i.as_dict() for i in self.issues],
        }


def _has_witness(ch: dict) -> bool:
    if ch.get("witnesses"):
        return True
    payoff = ch.get("shuang_payoff", "")
    # 文本里出现「当着…的面 / 众人 / 全场」也算有观众
    return any(k in payoff for k in ("当着", "当众", "众人", "全场", "围观", "面前"))


def _lint_realm(chapters, add, realm_max, realm_range, volumes) -> None:
    """境界脊柱闸门：REALM-01 回退（阻断）/02 越界/03 跳出卷区间/04 卷间不单调。"""
    lo, hi = (realm_range or (None, None))
    prev = None
    for ch in chapters:
        num = ch.get("chapter_number")
        rr = ch.get("realm_rank")
        if not isinstance(rr, int):
            add(Issue("REALM-02", "high", num, "缺 realm_rank——本章主角境界未锚定",
                      "给本章标主角境界档（指向境界体系数字）"))
            continue
        if prev is not None and rr < prev:
            add(Issue("REALM-01", "critical", num,
                      f"境界回退：第{num}章 realm_rank={rr} < 上一章 {prev}",
                      "境界只能升不能降；改为 ≥ 上一章档位"))
        if rr < 1 or (realm_max and rr > realm_max):
            add(Issue("REALM-02", "high", num,
                      f"realm_rank={rr} 越界（体系 1~{realm_max or '?'}）", "落回体系档位范围内"))
        if (lo and rr < lo) or (hi and rr > hi):
            add(Issue("REALM-03", "medium", num,
                      f"realm_rank={rr} 跳出本卷区间[{lo}~{hi}]", "本卷境界须落在卷区间内"))
        prev = max(prev, rr) if prev is not None else rr

    # REALM-04：卷间区间单调、首尾相接
    if volumes:
        ordered = sorted(volumes, key=lambda v: v.get("volume_number", 0))
        last_end = None
        for v in ordered:
            s, e = v.get("realm_start_rank"), v.get("realm_end_rank")
            if isinstance(s, int) and isinstance(e, int) and e < s:
                add(Issue("REALM-04", "medium", None,
                          f"第{v.get('volume_number')}卷区间逆序({s}>{e})", "卷末档 ≥ 卷初档"))
            if last_end is not None and isinstance(s, int) and s < last_end:
                add(Issue("REALM-04", "medium", None,
                          f"第{v.get('volume_number')}卷起点{s} < 上卷终点{last_end}（境界回退）",
                          "下一卷起点应 ≥ 上一卷终点"))
            if isinstance(e, int):
                last_end = e


def lint_chapters(
    chapters: list[dict], cfg: DabaiConfig, *,
    realm_max: int | None = None,
    realm_range: tuple[int | None, int | None] | None = None,
    volumes: list[dict] | None = None,
    golden_finger_name: str = "",
) -> LinterReport:
    """对一卷章纲跑全部大白文规则（含境界脊柱 REALM 闸门）。

    realm_max:   境界体系最高档；realm_range: 本卷 (start,end) 区间；volumes: 卷列表（跨卷单调检查）。
    """
    report = LinterReport()
    add = report.issues.append
    _lint_realm(chapters, add, realm_max, realm_range, volumes)

    # ── 逐章规则 ──────────────────────────────────────────────────────────────
    for ch in chapters:
        num = ch.get("chapter_number")
        # DB-01 critical：本章没有爽点
        if not ch.get("shuang_type", "").strip():
            add(Issue("DB-01", "critical", num,
                      "本章没有 shuang_type——大白文每章必须有明确爽点",
                      "指定一个爽点类型（打脸/升级/获宝…）"))
        # DB-03 high：爽感没人看
        if not ch.get("shuang_payoff", "").strip():
            add(Issue("DB-03", "high", num, "shuang_payoff 为空——爽点没有反馈",
                      "写明当着谁的面、爽在哪、对方什么反应"))
        elif not _has_witness(ch):
            add(Issue("DB-03", "high", num, "爽点缺观众/见证者——爽感打折",
                      "补 witnesses 或在 payoff 里点明『当众』"))
        # DB-04 high：爽点没有憋屈势能
        if not ch.get("yaqu_setup", "").strip():
            add(Issue("DB-04", "high", num, "yaqu_setup 为空——爽点没有前置憋屈弹簧",
                      "补一句谁在压主角/什么不公"))
        # DB-09 high：缺转折拍——情绪会硬跳
        et = ch.get("emotion_turn", "").strip()
        if not et:
            add(Issue("DB-09", "high", num, "emotion_turn 为空——从憋屈到引爆缺『转折拍』，正文会情绪硬跳",
                      "补情绪扳机：从X情绪→靠什么触发→转到Y情绪"))
        elif "触发" not in et and "→" not in et and "听到" not in et and "看到" not in et:
            add(Issue("DB-09", "medium", num, "emotion_turn 没有明确触发点——情绪转折缺扳机",
                      "写清楚靠什么具体触发（一句话/一个细节/一声提示）"))
        # DB-10 high：金手指觉醒章缺「疑→证→择」绑定节拍
        if is_awakening_chapter(ch, golden_finger_name=golden_finger_name,
                                golden_chapters=cfg.golden_chapters):
            bind_msg = lint_bind_ladder(et)
            if bind_msg:
                add(Issue("DB-10", "high", num,
                          "金手指觉醒章 emotion_turn 缺绑定节拍——正文易写成秒接受系统",
                          bind_msg))
        # DB-05 high：章末钩子缺失/套话
        hook = ch.get("end_hook", "").strip()
        if not hook:
            add(Issue("DB-05", "high", num, "end_hook 为空——读者没有点下一章的理由",
                      "补一个具体钩子：更强敌人/更大机缘/打脸预告"))
        elif any(c in hook for c in _HOOK_CLICHES):
            add(Issue("DB-05", "high", num, f"end_hook 是套话：{hook}",
                      "换成具体手法，不要『悬念丛生』类空话"))
        # DB-06 medium：信息密度超载
        nic = ch.get("new_info_count", 1)
        if isinstance(nic, int) and nic > cfg.max_new_info_per_chapter:
            add(Issue("DB-06", "medium", num,
                      f"单章引入 {nic} 个新东西，超过上限 {cfg.max_new_info_per_chapter}",
                      "把新设定/新人物分散到不同章逐个引入"))

    # ── 卷级规则 ──────────────────────────────────────────────────────────────
    # DB-02 critical：黄金三章失守
    golden = chapters[: cfg.golden_chapters]
    if golden and not any(
        c.get("is_big_beat") or c.get("shuang_type") in ("打脸", "升级", "装逼", "群嘲反转")
        for c in golden
    ):
        add(Issue("DB-02", "critical", None,
                  f"前 {cfg.golden_chapters} 章没有强爽点——黄金三章失守，开局留不住读者",
                  "让黄金三章内至少有一次当众大打脸或越级升级"))

    # DB-07 medium：连续 3 章爽点同质
    for i in range(len(chapters) - 2):
        a, b, c = (chapters[i + k].get("shuang_type") for k in range(3))
        if a and a == b == c:
            add(Issue("DB-07", "medium", chapters[i + 2].get("chapter_number"),
                      f"连续 3 章爽点同为『{a}』——爽点同质化",
                      "轮换爽点类型，避免读者腻"))

    # DB-08 medium：大爆点间隔过疏
    big_idx = [c.get("chapter_number") for c in chapters if c.get("is_big_beat")]
    if chapters and not big_idx:
        add(Issue("DB-08", "medium", None,
                  "整卷没有任何大爆点（is_big_beat）——节奏平淡",
                  f"每 {cfg.big_beat_every} 章安排一个大爆点"))

    return report


def format_report(report: LinterReport) -> str:
    """人类可读的报告文本（CLI 打印用）。"""
    d = report.as_dict()
    head = (f"大白文 linter：status={d['status']} score={d['score']} "
            f"问题={d['issue_count']}（critical={d['critical_count']}）")
    if not report.issues:
        return head + "\n  ✓ 全部通过"
    lines = [head]
    for it in report.issues:
        loc = f"第{it.chapter}章" if it.chapter else "卷级"
        lines.append(f"  [{it.severity:8}] {it.rule_id} {loc}：{it.message}")
    return "\n".join(lines)
