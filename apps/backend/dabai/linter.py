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
from dabai.first_chapter_opening import lint_banned_ch1_tropes, lint_ch1_cliche_template
from dabai.hooks import is_known_hook_type
from dabai.golden_finger_bind import is_awakening_chapter, lint_bind_ladder
from dabai.naming import known_character_names, lint_names_in_chapter
from dabai.realm_spine import lint_power_vs_rank, lint_sub_rank

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
    ctx: dict | None = None,
) -> LinterReport:
    """对一卷章纲跑全部大白文规则（含境界脊柱 REALM 闸门）。

    realm_max:   境界体系最高档；realm_range: 本卷 (start,end) 区间；volumes: 卷列表（跨卷单调检查）。
    """
    report = LinterReport()
    add = report.issues.append
    _lint_realm(chapters, add, realm_max, realm_range, volumes)
    if ctx:
        lint_power_vs_rank(chapters, ctx, add)
    lint_sub_rank(chapters, add)
    known = set(known_character_names(ctx or {}))

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
        lint_names_in_chapter(ch, known, add)

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

    _lint_sameness(chapters, add)
    _lint_hooks_emotion(chapters, add)
    _lint_future_cast_protection(chapters, add)
    for ch in chapters:
        if int(ch.get("chapter_number") or 0) != 1:
            continue
        banned = lint_banned_ch1_tropes(ch)
        if banned:
            msg, sug = banned
            add(Issue("DB-13", "medium", 1, msg, sug))
        cliche = lint_ch1_cliche_template(ch, ctx)
        if cliche:
            msg, sug = cliche
            add(Issue("DB-17", "medium", 1, msg, sug))
    return report


def _lint_sameness(chapters: list[dict], add) -> None:
    """DB-11/12 反同质化：场景载体与标题句式坍缩检查（章纲一个模子是正文 AI 味根因）。

    存量书章纲无 location 字段：全批皆空时跳过 DB-11，避免 relint 误报刷屏。
    """
    has_loc = any((ch.get("location") or "").strip() for ch in chapters)
    for i, ch in enumerate(chapters):
        num = ch.get("chapter_number")
        loc = (ch.get("location") or "").strip()
        # DB-11：场景载体缺失 / 相邻雷同
        if not has_loc:
            pass
        elif not loc:
            add(Issue("DB-11", "medium", num,
                      "location 为空——本章没有场景载体，正文会默认写回演武场/大殿",
                      "补具体场景载体（地点+事件，如 万宝拍卖行·斗宝）"))
        elif i > 0:
            prev_loc = (chapters[i - 1].get("location") or "").strip()
            if prev_loc and (loc == prev_loc or loc[:4] == prev_loc[:4]):
                add(Issue("DB-11", "medium", num,
                          f"相邻两章场景载体雷同：『{prev_loc}』→『{loc}』",
                          "换场景载体（宴席/拍卖/秘境/刑堂/夜袭…），一章一集戏"))
        # DB-12：相邻标题以相同字词开头（句式坍缩信号）
        if i > 0:
            t_now = _title_body(ch.get("title") or "")
            t_prev = _title_body(chapters[i - 1].get("title") or "")
            if t_now and t_prev and t_now[:2] == t_prev[:2]:
                add(Issue("DB-12", "medium", num,
                          f"相邻章标题开头雷同：『{t_prev}』→『{t_now}』——标题句式坍缩",
                          "轮换标题策略：悬念式/台词式/反差式/动作式/数字式"))


def _lint_hooks_emotion(chapters: list[dict], add) -> None:
    """DB-15/16：目标情绪 + 章尾钩子类型（情绪先于故事 + 追读钩子轮换）。

    存量书章纲无这两个字段：全批皆空时跳过，避免 relint 误报刷屏。
    """
    has_emotion = any((ch.get("target_emotion") or "").strip() for ch in chapters)
    has_hook = any((ch.get("hook_type") or "").strip() for ch in chapters)
    prev_hook = ""
    for i, ch in enumerate(chapters):
        num = ch.get("chapter_number")
        # DB-15：缺目标情绪——说不清交付什么情绪的章不该存在
        if has_emotion and not (ch.get("target_emotion") or "").strip():
            add(Issue("DB-15", "medium", num,
                      "target_emotion 为空——本章说不清交付什么情绪",
                      "补一词目标情绪（爽感释放/扬眉吐气/憋屈蓄势/甜…）"))
        # DB-16：章尾钩子类型缺失/非库内/相邻雷同（追读引擎轮换）
        hook = (ch.get("hook_type") or "").strip()
        if has_hook:
            if not hook:
                add(Issue("DB-16", "medium", num,
                          "hook_type 为空——章尾钩子未归类，易坍缩成同一招",
                          "标章尾钩子类型（13式之一：强敌登场/打脸预告/反转钩…）"))
            else:
                if not is_known_hook_type(hook):
                    add(Issue("DB-16", "medium", num,
                              f"hook_type『{hook}』不在 13 式钩子库内",
                              "归一到库内类型：强敌登场/身份揭露/危机降临/反转钩…"))
                if prev_hook and hook == prev_hook:
                    add(Issue("DB-16", "medium", num,
                              f"相邻两章章尾钩子同为『{hook}』——追读钩子坍缩",
                              "轮换钩子类型，相邻章不得同式"))
                prev_hook = hook
        # 情绪同质：连续 4 章同一目标情绪（弱信号，medium）
        if has_emotion and i >= 3:
            window = [(chapters[i - k].get("target_emotion") or "").strip() for k in range(4)]
            if window[0] and len(set(window)) == 1:
                add(Issue("DB-15", "medium", num,
                          f"连续 4 章目标情绪同为『{window[0]}』——情绪一条直线、缺张弛",
                          "插入憋屈蓄势/甜/虐等不同情绪，制造起伏"))


def _title_body(title: str) -> str:
    """剥掉『第X章』前缀，取标题正文用于句式比较。"""
    t = title.strip()
    if "章" in t[:6]:
        t = t.split("章", 1)[1]
    return t.strip(" ：:·-—")


def _lint_future_cast_protection(chapters: list[dict], add) -> None:
    """DB-14：本章节拍不得暗示写死后序章 involved 人物。"""
    death_hints = ("死", "殁", "毙", "诛", "杀", "身亡", "殒命", "灭口")
    for i, ch in enumerate(chapters):
        num = ch.get("chapter_number")
        future: set[str] = set()
        for j in range(i + 1, min(i + 3, len(chapters))):
            for name in chapters[j].get("involved_characters") or []:
                nm = str(name or "").strip()
                if nm:
                    future.add(nm)
        if not future:
            continue
        blob = " ".join(
            str(ch.get(k) or "") for k in ("yinbao", "shuang_payoff", "end_hook", "yaqu_setup")
        )
        for name in future:
            if name in blob and any(k in blob for k in death_hints):
                add(Issue(
                    "DB-14", "high", num,
                    f"第{num}章节拍涉及后续章主线人物「{name}」且含死亡/消灭暗示，"
                    f"与后序章纲冲突",
                    "改为击退/羞辱/暂退，或调整后续章纲出场安排",
                ))


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
