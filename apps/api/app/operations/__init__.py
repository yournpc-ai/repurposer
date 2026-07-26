"""Operation Model — 操作日志层（ADR-032）。

三前端（editor / chat / mcp）共用的产物级编辑操作层：op 注册表 + 应用服务 +
路由。plan 级节点操作不归这里（RunPlan 小拓扑，两家族分开登记）。
"""
