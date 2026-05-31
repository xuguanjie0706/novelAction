"""章节节奏约束与章纲落库辅助（共享模块）。

按卷阶段（phase）和章节编号返回注入 prompt 的细分节奏约束文字块。
vol1_chapter_plans 和 vol_chapter_plans 共用；章号校正 / 清卷章纲亦在此集中维护。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def get_chapter_phase_guidance(
    ch_num: int, total: int, phase: str, *, is_fanqie: bool = False,
) -> str:
    """按章节区间 + 卷阶段返回细分节奏约束。

    Args:
        ch_num: 当前章节编号（1-based，相对本卷）。
        total:  本卷总章数。
        phase:  卷级 phase 标记（opening/rising/turning/dark_hour/climax/ending）。
        is_fanqie: 番茄模式时使用算法导向的节奏约束。

    Returns:
        注入 prompt 的节奏约束文字块；未命中时返回空字符串。
    """
    if is_fanqie:
        return _fanqie_phase_guidance(ch_num, total, phase)
    if phase == "opening":
        if ch_num <= 5:
            return (
                "【开局1-5章·生死钩子区】前500字必须建立主角核心压力/不公正处境；"
                "主角必须在本章内主动采取行动（不是被动等待）；"
                "每章结尾留下读者必须知道答案的具体问题，不能用「主角沉思」收尾。"
            )
        elif ch_num <= 15:
            return (
                "【开局6-15章·金手指起飞区】主角开始展现核心能力，每3章至少1次具体逆转或胜利；"
                "引入第一条感情线/兄弟情，不能只推主线；"
                "开始埋本卷第一条长线伏笔，制造读者期待。"
            )
        elif ch_num <= int(total * 0.75):
            return (
                "【开局中段·扩张铺垫区】势力扩张，主角圈子开始扩大；"
                "引入更大威胁让读者感受到当前成功只是开始；"
                "感情/兄弟线要有实质性推进，不能只是点缀。"
            )
        else:
            return (
                "【开局末段·卷末冲刺区】本卷主线冲突推向高潮，至少1章有爆发点；"
                "留下一个跨卷悬念让读者必须看下一卷；"
                "回收本卷至少1条长线伏笔。"
            )
    elif phase == "rising":
        if ch_num <= int(total * 0.3):
            return (
                "【起飞前段·势力奠基区】主角快速积累资源/盟友，但必须有竞争对手压制节奏；"
                "每3章要有1次主角圈子扩大或实力背书事件；"
                "感情线/兄弟线接入，给读者除「爽」之外的情感出口。"
            )
        elif ch_num <= int(total * 0.7):
            return (
                "【起飞中段·扩张博弈区】主角势力与对立阵营正面接触，输赢都要有代价；"
                "引入「天花板」——让读者感受到主角虽强但还有更高山；"
                "至少1段感情/兄弟线有「差点失去」的险情制造情感张力。"
            )
        else:
            return (
                "【起飞末段·卷末冲刺区】主线矛盾推向本卷顶点，留种子给下卷；"
                "回收本卷至少1条伏笔，兑现本卷开头的至少1个承诺；"
                "最后3章节奏必须明显加速。"
            )
    elif phase == "turning":
        if ch_num <= int(total * 0.4):
            return (
                "【转折前段·代价启动区】主角过去的选择开始反噬，让读者看到「赢是有代价的」；"
                "至少1个之前的盟友/关系出现裂痕或转变；"
                "引入让主角无法用实力直接解决的新困境。"
            )
        else:
            return (
                "【转折后段·两难深化区】矛盾激化到无法回头，主角必须做出无完美解的选择；"
                "伏笔开始密集加热，铺垫至暗期；"
                "每章结尾必须留下「这很可能变得更糟」的预感。"
            )
    elif phase == "dark_hour":
        return (
            "【至暗期·内心突破区】允许虐主，但每次外部失败必须对应主角内心的认知突破；"
            "节奏放缓，强调情感深度而非事件密度——每章1个情感高点比3个情节事件更重要；"
            "这是人物弧度最深刻的阶段：主角的「最大谎言」（错误信念）必须在本阶段被打破；"
            "不要只写外部失败，写主角「看清了什么、接受了什么、放弃了什么」。"
        )
    elif phase == "climax":
        if ch_num <= int(total * 0.4):
            return (
                "【高潮前段·伏笔点燃区】开始密集回收此前埋下的伏笔，让读者感受到「一切都是设计好的」；"
                "主角的成长弧（内在转变）必须在战斗/决策中体现，不只是能力提升；"
                "每章要有1个「啊原来如此」的反转或揭示。"
            )
        else:
            return (
                "【高潮后段·终战收束区】所有主线悬念必须在本段有明确答案（即使留余韵）；"
                "主角的最终胜利必须来自内心成长，不只是境界/外力；"
                "最后3章为下一部/下一阶段留下1颗精准的悬念种子。"
            )
    elif phase == "ending":
        return (
            "【收束期·情感落地区】主线冲突收尾，人物关系有明确落点（成长/改变/和解/死亡）；"
            "节奏逐渐放缓，给读者情感上的「着陆感」，不要虎头蛇尾；"
            "必须留下至少1颗让读者期待下一部的悬念种子；"
            "感情线/兄弟线在本阶段有里程碑性的定格（告白/决裂/和解都算）。"
        )
    return ""


def chapter_number_for_batch_item(
    batch_start: int,
    batch_index: int,
    item: dict,
) -> int:
    """批内章号以顺位为准，避免 AI 重复 chapter_number 造成同章多条大纲。

    Args:
        batch_start: 本批起始章号（1-based）。
        batch_index: 本批数组下标（0-based）。
        item: AI 返回的单章 JSON 对象。

    Returns:
        校正后的章号（batch_start + batch_index，除非 AI 值已与顺位一致）。
    """
    expected = batch_start + batch_index
    raw = item.get("chapter_number")
    try:
        ch = int(raw)
    except (TypeError, ValueError):
        return expected
    if ch == expected:
        return ch
    logger.warning(
        "chapter_number 漂移：AI=%r 校正为 %d（batch_start=%d index=%d）",
        raw,
        expected,
        batch_start,
        batch_index,
    )
    return expected


def wipe_volume_chapter_plans(db: Any, project_id: str | UUID, volume_id: str | UUID) -> int:
    """删除某卷下全部 chapter_plan（重试 / 重跑前清场，防叠章）。

    Args:
        db: SQLAlchemy Session。
        project_id: 项目 ID。
        volume_id: 卷 OutlineNode ID。

    Returns:
        删除的章纲节点数。
    """
    from app.models import OutlineNode

    pid = str(project_id)
    vid = str(volume_id)
    plan_ids = [
        row[0]
        for row in db.query(OutlineNode.id)
        .filter(
            OutlineNode.project_id == pid,
            OutlineNode.parent_id == vid,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    ]
    if not plan_ids:
        return 0
    deleted = (
        db.query(OutlineNode)
        .filter(OutlineNode.id.in_(plan_ids))
        .delete(synchronize_session=False)
    )
    logger.info(
        "wipe_volume_chapter_plans: project=%s volume=%s deleted=%d",
        pid,
        vid,
        deleted,
    )
    return deleted


# ──────────────────────────────────────────────────────
# 番茄模式 phase guidance
# ──────────────────────────────────────────────────────


def _fanqie_phase_guidance(ch_num: int, total: int, phase: str) -> str:
    """番茄算法导向的节奏约束（替换标准文学性约束）。"""
    if phase == "opening":
        if ch_num <= 5:
            return (
                "【番茄开局1-5章·算法初审区】"
                "Ch1前200字：读者必须判断出书的类型，不能用悬疑/倒叙开局；"
                "Ch1前800字：金手指/系统/觉醒必须已触发，读者获得爽感期待；"
                "Ch1-2连续都要有可见的小胜利，证明金手指有用；"
                "Ch3前：首次打脸必须完成（有观众），算法完读率基准线；"
                "每章1500-1800字，结尾必须是「不看下章会后悔」的悬念。"
            )
        elif ch_num <= 15:
            return (
                "【番茄6-15章·算法窗口期】"
                "爽感密度铁律：每2章必须有1次可见的爽感释放，连续2章无爽感=完读率断崖；"
                "金手指至少在第8章和第12章各升级一次；"
                "打脸对象层级必须递进，禁止连续打同级；"
                "感情线可开但不能喧宾夺主——读者来看爽文不是看恋爱；"
                "禁止连续2章纯过渡/铺垫。"
            )
        elif ch_num <= int(total * 0.75):
            return (
                "【番茄中段·推荐稳定期】"
                "维持每3章至少1次打脸/升级；引入更大舞台扩大打脸格局；"
                "金手指新功能解锁让读者觉得「书还在进步」；"
                "可以开始经营感情线/兄弟线，但每条支线不超过2章。"
            )
        else:
            return (
                "【番茄卷末·冲刺区】"
                "本卷最大打脸必须在此段；至少1章让读者「看到结尾叫好」；"
                "留下一个跨卷悬念让读者追下一卷；"
                "最后3章节奏必须明显加速，字数不超过1800。"
            )
    elif phase == "rising":
        if ch_num <= int(total * 0.3):
            return (
                "【番茄起飞前段】"
                "主角快速积累资源/盟友，每3章1次实力展示事件；"
                "引入更高层级的打脸对象（从打脸地图中选）；"
                "金手指升级带来新能力，给读者「还能变更强」的期待。"
            )
        elif ch_num <= int(total * 0.7):
            return (
                "【番茄起飞中段】"
                "主角势力与更高层级正面碰撞，胜负都要有「观众在场」的画面感；"
                "引入天花板让读者感受到「前方还有更高的山」；"
                "每5章至少1次大爽点（big_win），不能全是小打小闹。"
            )
        else:
            return (
                "【番茄起飞末段·卷末冲刺】"
                "本卷主线矛盾推向顶点，安排本书到目前为止最震撼的打脸；"
                "最后3章节奏加速；留一个「不追下卷不行」的悬念种子。"
            )
    elif phase == "turning":
        return (
            "【番茄转折期】"
            "可以有1-2章挫折但必须快速给翻盘希望（读者不等）；"
            "挫折的作用是让下一次打脸更爽，不是展示主角内心；"
            "每章仍需有至少一个小爽点或期待，禁止纯铺垫。"
        )
    elif phase == "dark_hour":
        return (
            "【番茄至暗期·快速反弹区】"
            "虐主上限：连续虐主不超过2章，第3章必须开始反弹；"
            "只允许外部困境（被围困/被陷害），禁止内心崩溃/自我怀疑；"
            "暗中蓄力：虐主章内必须埋入翻盘线索（读者能看到）；"
            "反弹后的第一次打脸必须是目前为止最大的。"
        )
    elif phase == "climax":
        if ch_num <= int(total * 0.4):
            return (
                "【番茄高潮前段】"
                "密集回收伏笔+连续打脸，节奏最快的阶段；"
                "每章都要有进展或爽点，禁止过渡章；"
                "金手指达到当前最高形态，给读者视觉盛宴。"
            )
        else:
            return (
                "【番茄高潮后段·终战】"
                "本卷/本阶段最终 Boss 对决，安排最震撼的打脸场面；"
                "围观者阵容拉满，让「震惊全场」名副其实；"
                "最后1章留下一颗让读者追下一部的种子。"
            )
    elif phase == "ending":
        return (
            "【番茄收束期】"
            "快速收尾，不要拖沓；给主要关系一个明确交代；"
            "最后1章必须有一个新的悬念或更大的世界揭示；"
            "字数控制在1600-1800，干净利落。"
        )
    return ""
