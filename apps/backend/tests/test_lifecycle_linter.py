"""角色生命周期 linter 单测（LIFE-* / ALIGN-* / PROM-KILL）。

场景取自真实大纲质检报告的"低级逻辑硬伤"：
- 陆大虎 第32章被格杀、第55章再次被轰碎、第58章又活着当大将（死而复死 / 死后出场）
- 陆大虎 第19章反水救主、第32章却被当宿怨清算（阵营硬切）
- 陆长歌 承诺第10章击杀、实际拖到第47章（击杀承诺超窗）
并以"干净死亡 + 合法复活"角色作为负样本，确保不误报。
"""

from app.services.outline_linter.event_ledger import (
    CharacterRef,
    ChapterTextRow,
    build_timeline,
    extract_events_from_text,
)
from app.services.outline_linter.rules_lifecycle import (
    lint_kill_promise_window,
    lint_lifecycle,
)

_CHARS = [
    CharacterRef(id="su", name="苏云"),
    CharacterRef(id="hu", name="陆大虎"),
    CharacterRef(id="ge", name="陆长歌"),
    CharacterRef(id="qy", name="青羽"),
]


def _types(text: str) -> set[tuple[str, str]]:
    return {(cid, et) for cid, _, et, _ in extract_events_from_text(text, _CHARS)}


# ── 抽取器：施害者 / 受害者区分 ──────────────────────────────────────────────

def test_killer_not_flagged_as_victim():
    assert _types("苏云斩杀陆长歌，引出高潮") == {("ge", "death")}


def test_passive_death_across_comma():
    # 主语与"被…"分处逗号两侧，受害者应就近归属为陆大虎而非误判
    assert _types("血衣大将陆大虎再次出现，旋即被彻底轰碎") == {("hu", "death")}


def test_passive_death_with_inserted_chapter_ref():
    assert _types("陆大虎在第32章已被格杀并吞噬") == {("hu", "death")}


def test_intransitive_death():
    assert _types("陆长歌身亡，宗门震动") == {("ge", "death")}


def test_ally_subject_only():
    # 被救的苏云不应被判为反水者
    assert _types("陆大虎反水救苏云，并自曝为逆天盟守护者") == {("hu", "align_ally")}


def test_plain_mention_no_event():
    assert _types("账本记载陆大虎为血衣大将，统领前线大军") == set()


# ── 抽取器：番茄章纲格式误报回归（陆沉真实项目场景）────────────────────────

_LU_CHEN = [CharacterRef(id="lc", name="陆沉")]


def _lu_types(text: str) -> set[tuple[str, str]]:
    return {(cid, et) for cid, _, et, _ in extract_events_from_text(text, _LU_CHEN)}


def test_negated_passive_not_death():
    assert _lu_types("苏轻舟：虽未出手，但其威压制衡了陆家长老，让陆沉没被当场击杀。") == set()


def test_skill_tag_protagonist_not_death():
    assert _lu_types("因[借阵炼化]→[陆沉在阵中心疯狂吞噬大阵灵力，五行光柱纷纷炸裂]") == set()
    assert _lu_types("因[修罗灭杀]→[陆沉在短短百息内穿过阵法，地上留下了一百二十具残躯]") == set()


def test_expulsion_not_death_and_skill_hongsu_not_death():
    text = (
        "因[轰碎界碑开路]→[陆沉在万人惊呼中一拳击碎了护国神碑]。"
        "因为强行轰碎界碑，陆沉被东荒的天地意志彻底排斥，背负了东荒弃徒的诅咒。"
    )
    assert _lu_types(text) == set()


def test_lu_chen_chapter_chain_no_life_issues():
    """主角陆沉贯穿全书：修复后不得再链式报 LIFE-01/LIFE-02。"""
    rows = [
        ChapterTextRow(
            6,
            "苏轻舟：虽未出手，但其威压制衡了陆家长老，让陆沉没被当场击杀。",
            "n6",
            involved_character_ids=["lc"],
        ),
        ChapterTextRow(
            7,
            "因[舍命搏杀]→[陆沉在回廊连杀三名执法队员，并以断指为代价，生生捏碎了魏青的配刀]。",
            "n7",
            involved_character_ids=["lc"],
        ),
        ChapterTextRow(
            16,
            "因[借阵炼化]→[陆沉在阵中心疯狂吞噬大阵灵力，五行光柱纷纷炸裂，家主被震退百步]。",
            "n16",
            involved_character_ids=["lc"],
        ),
        ChapterTextRow(
            29,
            "因[修罗灭杀]→[陆沉在短短百息内穿过阵法，地上留下了一百二十具陆家弟子的残躯，山门破碎]。",
            "n29",
            involved_character_ids=["lc"],
        ),
        ChapterTextRow(
            58,
            "因[轰碎界碑开路]→[陆沉一拳击碎了护国神碑]。"
            "因为强行轰碎界碑，陆沉被东荒的天地意志彻底排斥，背负了东荒弃徒的诅咒。",
            "n58",
            involved_character_ids=["lc"],
        ),
    ]
    appearances = {"lc": [r.global_chapter for r in rows]}
    timeline = build_timeline(_LU_CHEN, rows)
    issues = lint_lifecycle(timeline, appearances, window_lo=1, window_hi=60)
    assert not any("陆沉" in i.message for i in issues)


# ── 规则：报告全景 ──────────────────────────────────────────────────────────

def _report_timeline():
    rows = [
        ChapterTextRow(19, "陆大虎反水救苏云，并自曝为逆天盟守护者", "n19", involved_character_ids=["hu", "su"]),
        ChapterTextRow(32, "苏云与陆大虎宿怨爆发，陆大虎被格杀并吞噬", "n32", involved_character_ids=["hu", "su"]),
        ChapterTextRow(47, "苏云历经苦战，终于斩杀陆长歌，复仇成功", "n47", involved_character_ids=["ge", "su"]),
        ChapterTextRow(55, "血衣大将陆大虎再次出现，旋即被彻底轰碎", "n55", involved_character_ids=["hu"]),
        ChapterTextRow(58, "账本记载陆大虎为血衣大将，统领前线大军", "n58", involved_character_ids=["hu"]),
        # 负样本：青羽 干净死亡 + 合法复活后出场
        ChapterTextRow(20, "青羽力竭身亡，众人悲痛", "n20", involved_character_ids=["qy"]),
        ChapterTextRow(25, "青羽借尸还魂，死而复生归来", "n25", involved_character_ids=["qy"]),
        ChapterTextRow(30, "青羽重返战场，再立新功", "n30", involved_character_ids=["qy"]),
    ]
    appearances: dict[str, list[int]] = {}
    for r in rows:
        for cid in r.involved_character_ids:
            appearances.setdefault(cid, []).append(r.global_chapter)
    for v in appearances.values():
        v.sort()
    return build_timeline(_CHARS, rows), appearances


def test_lifecycle_rules_full_scenario():
    timeline, appearances = _report_timeline()
    issues = lint_lifecycle(timeline, appearances, window_lo=1, window_hi=60)
    by_rule = {i.rule_id for i in issues}

    assert "LIFE-01" in by_rule  # 死而复死
    assert "LIFE-02" in by_rule  # 死后出场
    assert "ALIGN-01" in by_rule  # 阵营硬切
    # LIFE-01 阻断级
    assert any(i.rule_id == "LIFE-01" and i.severity == "critical" for i in issues)
    # 死后出场报在第58章（55 章本身是再次死亡，归 LIFE-01）
    assert any(i.rule_id == "LIFE-02" and "第58章" in i.message for i in issues)


def test_no_false_positive_on_legitimate_revive():
    timeline, appearances = _report_timeline()
    issues = lint_lifecycle(timeline, appearances, window_lo=1, window_hi=60)
    assert not any("青羽" in i.message for i in issues)


def test_declared_deaths_drive_lifecycle_when_regex_misses():
    """结构化生死声明：正文无杀戮动词、正则抽不到，但 deaths 声明仍触发 LIFE-01。"""
    rows = [
        # 两章正文都不含杀戮动词，纯靠 declared_deaths
        ChapterTextRow(2, "叶辰在乱战中倒下，再也没能起身", "n2",
                       involved_character_ids=["su"], declared_deaths=["苏云"]),
        ChapterTextRow(5, "尘埃落定，往事终成定局", "n5",
                       involved_character_ids=["su"], declared_deaths=["苏云"]),
    ]
    appearances = {"su": [2, 5]}
    timeline = build_timeline(_CHARS, rows)
    issues = lint_lifecycle(timeline, appearances, window_lo=1, window_hi=30)
    assert any(i.rule_id == "LIFE-01" for i in issues)


def test_declared_revive_clears_death_no_false_positive():
    """声明复活解除死亡：第2章死、第4章 revives 声明、第5章再死 → 不报 LIFE-01。"""
    rows = [
        ChapterTextRow(2, "苏云陨落", "n2", involved_character_ids=["su"], declared_deaths=["苏云"]),
        ChapterTextRow(4, "苏云竟然回来了", "n4", involved_character_ids=["su"], declared_revives=["苏云"]),
        ChapterTextRow(5, "苏云这次是真的去了", "n5", involved_character_ids=["su"], declared_deaths=["苏云"]),
    ]
    appearances = {"su": [2, 4, 5]}
    timeline = build_timeline(_CHARS, rows)
    issues = lint_lifecycle(timeline, appearances, window_lo=1, window_hi=30)
    assert not any(i.rule_id == "LIFE-01" for i in issues)


def test_life_issues_carry_chapter_number_for_repair():
    """P1 修复回路：LIFE-01/02/ALIGN-01 须带本卷内章号，否则 build_repair_seed 会丢弃。

    window_lo=31 模拟「本卷首章为全书第31章」：卷内章号 = 全书章号 - 31 + 1。
    """
    timeline, appearances = _report_timeline()
    issues = lint_lifecycle(timeline, appearances, window_lo=31, window_hi=90)
    by_rule = {i.rule_id: i for i in issues}
    for rid in ("LIFE-01", "LIFE-02", "ALIGN-01"):
        assert rid in by_rule, rid
        iss = by_rule[rid]
        assert isinstance(iss.chapter_number_in_volume, int)
        assert iss.chapter_number_in_volume >= 1
        assert iss.field  # 非空，供 repair 字段映射

    from app.services.outline_linter.schemas import LinterReport
    from app.services.outline_linter.repair_hints import build_repair_seed

    seed = build_repair_seed(LinterReport(issues=issues))
    # LIFE-01 再次死亡在全书第55章 → 卷内 55-31+1=25 章
    assert 25 in seed["must_fix_chapter_numbers"]


def test_kill_promise_window():
    timeline, _ = _report_timeline()
    promises = [{
        "text": "开篇立誓：前十章内斩杀陆长歌作为高潮爽点",
        "src_chapter": 1,
        "window": 9,  # deadline = 第10章
        "priority": 5,
    }]
    issues = lint_kill_promise_window(
        promises, _CHARS, timeline,
        max_global=60, is_fast_pace=True, window_lo=1, window_hi=60,
    )
    assert any(i.rule_id == "PROM-KILL" for i in issues)
    assert any("陆长歌" in i.message and "第47章" in i.message for i in issues)


def test_kill_promise_satisfied_in_window_no_issue():
    # 承诺第10章前击杀，实际第8章击杀 → 不报
    rows = [ChapterTextRow(8, "苏云一剑斩杀陆长歌", "n8", involved_character_ids=["ge", "su"])]
    timeline = build_timeline(_CHARS, rows)
    promises = [{"text": "前十章斩杀陆长歌", "src_chapter": 1, "window": 9, "priority": 5}]
    issues = lint_kill_promise_window(
        promises, _CHARS, timeline,
        max_global=60, is_fast_pace=True, window_lo=1, window_hi=60,
    )
    assert not any(i.rule_id == "PROM-KILL" for i in issues)
