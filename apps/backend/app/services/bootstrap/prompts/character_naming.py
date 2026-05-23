"""人物正名/别名命名约束 prompt 片段。

Bootstrap Step 5、章节复盘 new_characters 等路径共用，避免生成「老铁」「小柔」等口语化称呼当正名。
"""

from __future__ import annotations

# 口语/昵称/网络梗——禁止作为 name 字段（可作 alias）
_FORBIDDEN_NAME_EXAMPLES = (
    "老铁、哥们、兄弟、老板、师傅（称呼词）",
    "小柔、小明、小X 式乳名（正名须为完整姓名，乳名放 alias）",
    "阿铁、大壮、二狗子、狗剩、铁柱（乡土绰号式正名）",
    "某某的爪牙、恶霸甲、路人乙（占位名）",
    "现代网络梗、外卖/游戏/职场口语化名",
)


def character_naming_constraints_for_prompt(genre: str | None = None) -> str:
    """返回注入 LLM prompt 的人物命名硬性约束块。"""
    genre_hint = (genre or "玄幻").strip() or "玄幻"
    forbidden = "\n".join(f"  ✗ {x}" for x in _FORBIDDEN_NAME_EXAMPLES)
    return f"""【人物命名规范（硬性，违反则视为无效输出）】
- name 必须是正名：姓+名，共 2~4 个汉字（复姓允许 4 字），如「林煌」「苏远山」「慕容清歌」
- 禁止把昵称、绰号、称呼词、网络用语当作 name；口语化称呼一律写入 alias 数组
{forbidden}
- alias（可选）：外号、道号、尊称、乳名、江湖绰号；如 name「苏柔」+ alias ["小柔","柔姑娘"]
- 命名须贴合「{genre_hint}」题材语感：
  · 玄幻/仙侠/修真：优先古典意象字（霆、煌、渊、澜、玄、霜、墨、清、钧、遥、辞、珩…），避免现代感过强的字组合
  · 都市/现言/悬疑：可用常见姓+双字名，但仍须像真实姓名，禁止玩笑式谐音烂梗（范统、朱逸等）
- 同批次内：姓氏重复不超过 2 人；核心角色之间名字辨识度要高，避免仅一字之差
- 反派与短期配角同样须用完整正名，不得用描述性占位代替姓名"""

