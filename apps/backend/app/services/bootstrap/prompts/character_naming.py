"""人物正名/别名命名约束 prompt 片段。

Bootstrap Step 5、对立面阶梯、章节复盘 new_characters 等路径共用，
避免生成「老铁」「小柔」「灵儿」等口语化/随意称呼当正名。
"""

from __future__ import annotations

import re

# 口语/昵称/网络梗——禁止作为 name 字段（可作 alias）
_FORBIDDEN_NAME_EXAMPLES = (
    "老铁、哥们、兄弟、老板、师傅（称呼词）",
    "小柔、小明、小X 式乳名（正名须为完整姓名，乳名放 alias）",
    "灵儿、婉儿、红姐、阿妹、小蝶 等「X儿/X妹/X姐」儿化/乳名式正名",
    "叠字儿化名：安安、甜甜、乐乐、萌萌（可作 alias，不得作 name）",
    "阿铁、大壮、二狗子、狗剩、铁柱（乡土绰号式正名）",
    "某某的爪牙、恶霸甲、路人乙（占位名）",
    "现代网络梗、外卖/游戏/职场口语化名",
)

# 网文 AI 高频滥名——同批次禁止整名复刻或仅改一字
_OVERUSED_NAME_PATTERNS = (
    "灵儿/婉儿/青儿/雪儿/蝶儿 等儿化名",
    "灵瑶、梦璃、苏清歌、林晨、叶轩、萧炎、慕容雪 等模板化组合",
    "全批多人共用「灵/雪/梦/嫣/菲/瑶/璃/晨/轩/辰/寒/冰/月」作唯一区别字",
)

# 姓+名中「名」部分的儿化/乳名后缀（正名禁止）
_ER_SUFFIX_RE = re.compile(r".*[儿妹姐哥弟]$")

# 高频 AI 整名黑名单（小写比较用 normalize）
_WEAK_FULL_NAMES = frozenset({
    "灵儿", "婉儿", "青儿", "雪儿", "蝶儿", "红姐", "阿妹", "小蝶",
    "苏灵儿", "林婉儿", "叶灵儿", "慕容雪", "苏清歌", "林晨", "叶轩",
    "萧炎", "唐三", "韩立", "楚风", "陈平安",
})

# 单独作为「名」时过于空泛的字（姓+此单字名视为弱名）
_WEAK_SINGLE_GIVEN = frozenset("灵雪梦嫣菲瑶璃晨轩辰寒冰月柔媚丽")


def is_weak_character_name(name: str) -> str | None:
    """检测是否为弱/随意命名；返回原因字符串，合法则返回 None。"""
    n = (name or "").strip()
    if not n or len(n) < 2:
        return "姓名过短"
    if n in _WEAK_FULL_NAMES:
        return f"命中高频模板名「{n}」"
    # 3 字常见姓+儿化名：如「苏灵儿」
    if len(n) == 3 and n[1:] in {"灵儿", "婉儿", "青儿", "雪儿", "蝶儿"}:
        return f"乳名式组合「{n}」"
    if _ER_SUFFIX_RE.match(n) and len(n) <= 3:
        return "儿化/乳名后缀不宜作正名"
    # 2 字姓名且第二字为滥用单字
    if len(n) == 2 and n[1] in _WEAK_SINGLE_GIVEN:
        return f"单字名「{n[1]}」过于空泛"
    return None


def character_naming_constraints_for_prompt(
    genre: str | None = None,
    *,
    project_title: str | None = None,
    theme: str | None = None,
    logline: str | None = None,
    existing_names: list[str] | None = None,
    require_name_meaning: bool = False,
) -> str:
    """返回注入 LLM prompt 的人物命名硬性约束块。"""
    genre_hint = (genre or "玄幻").strip() or "玄幻"
    forbidden = "\n".join(f"  ✗ {x}" for x in _FORBIDDEN_NAME_EXAMPLES)
    overused = "\n".join(f"  ✗ {x}" for x in _OVERUSED_NAME_PATTERNS)

    thematic_lines: list[str] = []
    if project_title:
        thematic_lines.append(f"- 书名《{project_title.strip()}》的意象/字根可化入核心角色名（不必直抄书名）")
    if theme:
        thematic_lines.append(f"- 故事主题「{theme.strip()[:80]}」须在至少 2 个核心角色名中有可回读的隐喻")
    if logline:
        thematic_lines.append(f"- 创意梗概中的核心矛盾/世界规则，应能在反派或关键配角姓名中留下暗示")
    thematic_block = "\n".join(thematic_lines) if thematic_lines else (
        "- 每个核心角色的姓名须能独立承载一层「读后可回味」的寓意，而非仅为好听"
    )

    existing_block = ""
    if existing_names:
        sample = "、".join(existing_names[:30])
        if len(existing_names) > 30:
            sample += f" 等共{len(existing_names)}人"
        existing_block = f"""
- 已有人物名（禁止重名、禁止仅改一字）：{sample}
- 新名与已有人物：姓氏可偶合，但「名」不得相同；禁止「林晨/林辰」「苏瑶/苏璃」式微调"""

    meaning_block = ""
    if require_name_meaning:
        meaning_block = """
- 每人须填 name_meaning（15~40字）：说明姓/名各字的字面意象，以及与本角色命运、秘密或主题的一重暗线
  · 合格示例：name「沈烬」+ name_meaning「烬=余火将熄，暗示其曾焚毁宗门却假死脱身」
  · 不合格：name_meaning 写「好听」「可爱」「很仙」等空泛评价"""

    return f"""【人物命名规范（硬性，违反则视为无效输出）】
- name 必须是正名：姓+名，共 2~4 个汉字（复姓允许 4 字），如「沈烬」「顾远山」「慕容辞衡」
- 禁止把昵称、绰号、称呼词、网络用语、乳名当作 name；口语化称呼一律写入 alias 数组
{forbidden}
- alias（可选）：外号、道号、尊称、乳名、江湖绰号；如 name「苏辞柔」+ alias ["小柔","柔姑娘"]
- 命名须贴合「{genre_hint}」题材语感，且 **有寓意、可伏笔**：
  · 玄幻/仙侠/修真：从古典意象、节气、器物、卦象、地理、功法隐喻中取字，名应暗示命运或立场
  · 都市/现言/悬疑：像真实姓名，但可埋谐音或职业/家族暗示；禁止玩笑式谐音烂梗（范统、朱逸等）
{thematic_block}
- 同批次内：
  · 姓氏重复不超过 2 人；「名」不得重复；核心角色之间辨识度要高，避免仅一字之差
  · 禁止以下高频 AI 滥名或变体：
{overused}
{existing_block}
- 反派与短期配角同样须用完整正名，不得用描述性占位代替姓名
- 取名前先在心里列出本批已用「名」，确保无重复、无近义堆砌{meaning_block}"""
