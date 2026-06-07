"""开局承诺 ↔ roster 一致性（OC-LADDER）单测。

核心场景：开局承诺写"第10章斩杀陆长歌"，但 roster 将陆长歌定为第3卷 Boss——
前10章不可能兑现，开局承诺与大纲必然矛盾，应判 OC-LADDER。
"""

from app.services.bootstrap.opening_contract_consistency import check_contract_vs_ladder

_LADDER = [
    {"vol_index": 0, "boss_name": "王九", "realm_at_climax": "筑基境圆满"},
    {"vol_index": 1, "boss_name": "赵长老", "realm_at_climax": "金丹境中期"},
    {"vol_index": 2, "boss_name": "陆长歌", "realm_at_climax": "元婴境"},
]


def _rules(contract: dict) -> set[str]:
    return {i["rule_id"] for i in check_contract_vs_ladder(contract, _LADDER)}


def test_promise_kill_later_volume_boss_flagged():
    contract = {"chapter10_subscribe_reason": "第10章末，主角终于斩杀陆长歌，复仇成功，引出更大黑手"}
    assert "OC-LADDER" in _rules(contract)


def test_promise_clear_first_volume_boss_ok():
    contract = {"chapter3_payoff": "第3章主角击杀王九，夺回宗门信物"}
    assert _rules(contract) == set()


def test_later_boss_as_killer_not_flagged():
    # 陆长歌是施害者（屠主角满门），并非被击杀目标 → 不应误报
    contract = {"chapter1_hook": "陆长歌屠主角满门，血海深仇就此结下"}
    assert _rules(contract) == set()


def test_later_boss_only_pressures_no_death_promise_ok():
    contract = {"chapter5_foreshadow": "陆长歌远程降下威压，留下'百日之约'的死亡威胁"}
    assert _rules(contract) == set()


def test_empty_inputs():
    assert check_contract_vs_ladder({}, _LADDER) == []
    assert check_contract_vs_ladder({"chapter1_hook": "斩杀陆长歌"}, []) == []


def test_issue_payload_shape():
    contract = {"chapter10_subscribe_reason": "主角斩杀陆长歌"}
    issues = check_contract_vs_ladder(contract, _LADDER)
    assert issues and issues[0]["severity"] == "high"
    assert issues[0]["type"] == "opening_contract_ladder_conflict"
    assert "第3卷" in issues[0]["description"]
