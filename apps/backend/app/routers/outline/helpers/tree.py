"""大纲树：扁平节点列表 → 嵌套 OutlineNodeOut 树。"""
from __future__ import annotations

from typing import List

from app.models import OutlineNode
from app.schemas import OutlineNodeOut

def build_tree(nodes: List[OutlineNode]) -> List[OutlineNodeOut]:
    """把扁平列表组装成嵌套树（所有层级均按 sort_order 排序）"""
    node_map = {str(n.id): OutlineNodeOut.model_validate(n) for n in nodes}
    # model_validate(from_attributes) 会带入 SQLAlchemy 已加载的 children；
    # 若再按 parent_id 挂接，同一子节点会出现两次（卷下两篇、章重复等）。
    for node_out in node_map.values():
        node_out.children.clear()
    roots = []
    for node_out in node_map.values():
        if node_out.parent_id is None:
            roots.append(node_out)
        else:
            parent = node_map.get(str(node_out.parent_id))
            if parent:
                parent.children.append(node_out)

    def sort_recursive(node_list: list) -> None:
        node_list.sort(key=lambda x: x.sort_order)
        for n in node_list:
            if n.children:
                sort_recursive(n.children)

    sort_recursive(roots)
    return roots
