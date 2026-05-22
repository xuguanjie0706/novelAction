"""Bootstrap 子包：一句话创意 → 全量小说串行初始化。

编排入口：``services/bootstrap/graph.py``（LangGraph）→ ``routers/bootstrap_graph.py``。
``GenerationService`` 作为 svc 容器，``graph_nodes.py`` 通过 _make_svc() 构造后
调用 svc._gen_*（每个代理指向 steps/ 子包对应函数）。

子模块：
- ``context`` / ``retry`` / ``parse`` / ``sse`` / ``prompts``
- ``steps``：14 个串行步骤实现（``gen_*``）
- ``graph`` / ``graph_nodes`` / ``graph_gates``：LangGraph 编排薄壳与节点

注：``save_all`` / ``completion`` / ``prompts/single_shot`` 已废弃（方案 B 已移除），
保留空模块以避免遗留 import 路径断裂，待统一清理时删除。
"""
