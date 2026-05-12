"""Step A smoke test：验证 bootstrap 包拆分后行为不变。

运行：
    apps/backend/.venv/bin/python apps/backend/scripts/_smoke_step_a.py

通过条件：脚本末尾打印 `STEP A SMOKE: ALL OK`，且 exit code = 0。
任何 assert 失败都会让命令以非 0 退出。
"""
from __future__ import annotations

import os
import sys

# 让 `app.xxx` 能被 import（与 uvicorn cwd 一致）
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from app.services import generation_service as gm
from app.services.bootstrap.parse import parse_json, safe_int, coerce_power_system_rank
from app.services.bootstrap.sse import sse
from app.services.bootstrap.prompts import (
    GEMINI_SETTING_BLUEPRINTS,
    single_shot_prompt,
    setting_extra_with_defaults,
    book_length_constraints_for_prompt,
)


def check(label, ok, detail=""):
    mark = "OK " if ok else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        raise SystemExit(f"smoke failed at: {label}")


print("1) alias identity (老 import 路径必须命中新实现):")
check("gm._parse_json IS parse_json", gm._parse_json is parse_json)
check("gm._safe_int IS safe_int", gm._safe_int is safe_int)
check(
    "gm._coerce_power_system_rank IS coerce_power_system_rank",
    gm._coerce_power_system_rank is coerce_power_system_rank,
)
check("gm._sse IS sse", gm._sse is sse)
check(
    "gm.GEMINI_SETTING_BLUEPRINTS IS bootstrap blueprints",
    gm.GEMINI_SETTING_BLUEPRINTS is GEMINI_SETTING_BLUEPRINTS,
)
check("gm._single_shot_prompt IS single_shot_prompt", gm._single_shot_prompt is single_shot_prompt)

print()
print("2) constants (test_premise_and_draft 用到的全量):")
check("blueprint count >= 20", len(gm.GEMINI_SETTING_BLUEPRINTS) >= 20, str(len(gm.GEMINI_SETTING_BLUEPRINTS)))
check("CHARACTER_TARGET == 8", gm.CHARACTER_TARGET == 8)
check("FACTION_MIN_TARGET == 4", gm.FACTION_MIN_TARGET == 4)
check("FACTION_MAX_TARGET == 6", gm.FACTION_MAX_TARGET == 6)
check("SKILL_MIN_TARGET == 5", gm.SKILL_MIN_TARGET == 5)
check("SKILL_MAX_TARGET == 8", gm.SKILL_MAX_TARGET == 8)
check("ITEM_MIN_TARGET == 5", gm.ITEM_MIN_TARGET == 5)
check("ITEM_MAX_TARGET == 8", gm.ITEM_MAX_TARGET == 8)

print()
print("3) _single_shot_prompt 内容守护（与 test_premise_and_draft 等价）:")
prompt = gm._single_shot_prompt("废柴少年重建丹田", "", 1_200_000)
check("prompt len > 1000", len(prompt) > 1000, f"len={len(prompt)}")
check(
    "contains 'settings 必须生成 N 张'",
    f"settings 必须生成 {len(gm.GEMINI_SETTING_BLUEPRINTS)} 张" in prompt,
)
check(
    "contains 'characters 必须生成 N 个'",
    f"characters 必须生成 {gm.CHARACTER_TARGET} 个" in prompt,
)
check(
    "contains '下面是字段结构说明'",
    "下面是字段结构说明，不代表数组数量" in prompt,
)
check(
    "NO inline 'characters: [' example",
    '"characters": [' not in prompt,
)

print()
print("4) safe_int / coerce_power_system_rank / parse_json 边界:")
check("safe_int('abc12') == 12", gm._safe_int("abc12") == 12)
check("safe_int(None, default=7) == 7", gm._safe_int(None, default=7) == 7)
check("safe_int(0, min_v=1) == 1", gm._safe_int(0, min_v=1) == 1)
check("safe_int(99, max_v=10) == 10", gm._safe_int(99, max_v=10) == 10)
check("safe_int(True) is None (bool 不算 int)", gm._safe_int(True) is None)
check(
    "coerce_power_system_rank('练气一层', levels=[{name=练气,rank=1}]) == 1",
    gm._coerce_power_system_rank("练气一层", [{"name": "练气", "rank": 1}], default=0) == 1,
)

sample = "<think>x</think>\n```json\n{\"a\": 1}\n```"
check("parse_json 去 think + fence", gm._parse_json(sample) == {"a": 1})

print()
print("5) _sse 输出格式:")
line = gm._sse("step_done", step="project", count=1)
check("_sse 以 'data: ' 开头", line.startswith("data: "))
check("_sse 以 \\n\\n 结尾", line.endswith("\n\n"))
check("_sse payload 含 event/step/count", '"event": "step_done"' in line and '"step": "project"' in line)

print()
print("6) _setting_extra_with_defaults:")
extra = gm._setting_extra_with_defaults({"title": "作品立意", "extra": {"core": {}}})
check("category == 世界背景", extra.get("category") == "世界背景")
check("schema_version == 2", extra.get("schema_version") == 2)
check("reveal_timing 占位为 ''", extra.get("reveal_timing") == "")

print()
print("7) _book_length_constraints_for_prompt:")
b = gm._book_length_constraints_for_prompt(2_000_000)
check("contains '2,000,000'", "2,000,000" in b)
check("contains '200 万字'", "200 万字" in b)

print()
print("STEP A SMOKE: ALL OK")
