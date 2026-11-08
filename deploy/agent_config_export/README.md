# 智能体配置导出

**这是初赛必交材料**（赛题要求"附上需要同步提交的 json 文件"）。

## 当前文件

| 文件 | 来源与用途 |
|---|---|
| mcp_tools_v0.2.0.json | 实际 MCP initialize/tools/list 返回的服务信息与10个工具schema |
| agent_native_skills_snapshot_20261108.json | 当前2611081425版手工UI快照：12工具、4Skill、24条使用要求及验收证据；非原生导出 |
| agent_draft_snapshot.json | 2610182221版历史手工UI快照：模型、工具、角色、约束、示例与运行策略 |
| agent_snapshot_before_home_fix.json | 首页故障修复前的快照，保留当时只完成草稿的状态 |
| role_in_nexent.txt / constraints_in_nexent.txt | 旧发布阶段的角色与21条使用要求；新增Skills后的完整24条见constraints_native_skill_draft.txt |
| few_shots_in_nexent.txt / few_shots_before_home_fix.txt | 当前实时工具查询示例与此前旧单文档答案示例 |
| constraints_before_home_fix.txt | 新增首页检索渠道规则之前的12条使用要求 |
| onboarding_in_nexent.json | 当前配置的开场白及四个示例问题 |
| *_before_mcp.* | 修改前的相应文本，便于恢复和解释迭代过程 |
| real_graph_constraints.txt | 较详细的本地建议模板，和平台当前精简文本不同 |

`agent_draft_snapshot.json` 对应2610182221历史版本，明确标记为手工UI配置快照，**不是Nexent平台导出格式，不能直接导入**。该阶段已在首页新对话完成原始随访问题测试；此前版本和旧会话保留。运行策略中“严格输出协议与静默修复”已开启，其他未改动的策略见快照。正式参赛提交前仍需平台实际导出文件，不以手工快照冒充。

## 正式版本导出

2026-11-08已内部发布 `高血压用药决策助手-2611081425`。`native_skill_routing_appendix.txt` 为初始补充文本，`constraints_native_skill_draft.txt` 为保留文件名的完整24条使用要求，本轮发布前已重载核对。新增 `agent_native_skills_snapshot_20261108.json` 是手工UI配置快照，**不是平台原生导出，不可直接导入**；原快照和旧约束均保留。五题结果见 `../../eval/native_skill_acceptance_results_20261108.json`，仍有流程遗漏。四个Skill的源码导入文件在 `../skill_packages/`，当前接入状态见 `../../docs/12-Nexent原生Skills编排与复用.md`。创建资源、绑定智能体、运行读取正文是不同步骤，需分别验证。

1. 在 Nexent 界面导出智能体 / 工作流 json
2. 放到本目录，命名：`agent_<名称>_v<版本>.json`
3. 按参赛开源计划保存到版本控制（当前目录尚未初始化Git仓库）

## 清单
| 文件 | 内容 | 导出时间 |
|---|---|---|
| | 智能体配置 | |
| | MCP 工具配置 | |
| | 知识库清单 | |
