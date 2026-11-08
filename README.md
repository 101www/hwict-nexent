# 领域资产认知智能体（华为 ICT 大赛 · 赛题3）

当前已实现三份高血压文档的离线建图，以及读取真实 `graph.json` 的 Spring AI Java MCP（12个工具）。Nexent v2.7.0 当前内部发布版为 `高血压用药决策助手-2611081425`（此前2610182221）。本轮增加同方案组两跳取证、诊室血压OR边界及复测条件检查、跨文档药物配备/一线推荐作用域比较；不确定候选全部保留为pending。做法和自己运行的步骤见 [三类推理学习说明](docs/08-三类推理是怎么做出来的.md)，真实协议和首页问答分别留在 [验证记录](docs/validation/README.md)。下方未完成的竞赛规划以TODO标识，不代表已实现。

> 基于 **ModelEngine Nexent** 打造的可进化决策智能体：多模态行业数据 → 知识图谱本体 →
> 检索-推理双驱动 → 跨文档多跳推理 + 决策链路可溯源。

学习代码实现请看 [从原文到两跳查询：逐行代码讲解](docs/09-从原文到两跳查询-逐行代码讲解.md)：解释Python规则怎样生成节点和边、Java如何定位JSON并建立邻接表，以及两跳组合和通用遍历的区别。

四个原生Skill已在平台创建、绑定原智能体，并内部发布为 **高血压用药决策助手-2611081425**，保留12个kg-tools-real工具。五道首页独立新对话均已运行，四个Skill均有实际read_skill_md记录。随访和冲突题展示了核心链路；多跳、数值和缺失版本仍有执行或表达遗漏，不能记为全面通过。五个短答均少于200字符，自动知识仍待核验。详见 [Nexent原生Skills编排与复用](docs/12-Nexent原生Skills编排与复用.md)及[本轮验收报告](docs/validation/native-skills-acceptance-20261108.md)。

知识版本连接已补齐，见 [工作台如何连接 Nexent](docs/11-工作台如何连接Nexent.md)：双击 `启动正式图谱MCP.cmd` 与 `打开知识更新工作台.cmd`，2026-11-08已修复IDEA默认启动：项目存在正式仓库时，直接运行主类也会自动跟随发布版本。8081 Java MCP 跟随 `data/evolution/production` 当前发布版本；8765 管理审核和发布。双击 `检查智能体知识版本.cmd` 可核对真实服务版本。现有三份全文已纳入正式基线；原历史提案保留在独立8766工作台。同一JVM/同一MCP会话发布与回滚已实测，0→2→0条两跳路径。2026-11-08已在Nexent原智能体内实际验证正式版本号与published_store模式，证据见 `docs/validation/nexent-version-startup-fix-20261108.json`；本体自主学习仍待完成；原生Skills已接入，执行可靠性仍需改进。

## 一、这是什么

面向 **{行业}** 场景，把沉睡的多模态存量数据资产（PDF / 扫描件 / 表格 / 图文报告）
统一识别、理解并资产标识，构建可动态更新的领域知识图谱本体，并基于 Nexent 的
MCP 协议与 Skills 编排能力，实现"检索-推理"双驱动的可溯源决策辅助。

**一句话**：不是聊天机器人，是"行业认知底座 + 可编排工具箱 + 每一步可倒查原件"的系统。

## 二、快速开始（复现步骤）

### 1. 环境要求
| 项 | 最低 | 推荐 |
|---|---|---|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GiB | 16 GiB |
| 磁盘 | 40 GiB | 100 GiB |
| 软件 | Docker 24+ / Docker Compose v2+ | 同左 |

### 2. 启动 Nexent
```bash
git clone https://github.com/ModelEngine-Group/nexent.git
cd nexent
bash deploy.sh docker
```
默认访问 `http://localhost:3000`。首次使用超级管理员 `suadmin@nexent.com` 登录，
进入【租户资源】创建租户与租户管理员，再用新账号登录。

### 3. 导入本项目的智能体与工具
双击项目根目录 `启动正式图谱MCP.cmd`，或在根目录运行：

```powershell
python -X utf8 tools/evolve_graph.py --production launch-java
```

需要 JDK 21、Maven。Nexent 的 MCP 配置填写 Java 所在电脑的可达地址；本次为 `http://192.168.100.1:8081/sse`，选择 `kg-tools-real` 的工具。配置文本与平台实际导出JSON需区分，导出清单见 `deploy/agent_config_export/`。

### 4. 复现效果
```powershell
# 保持Java服务运行，在项目根目录另开终端：
python java-mcp/query_mcp.py relations 随访
python java-mcp/test_real_graph_mcp.py --report docs/validation/mcp_smoke_report.json
```

查询返回原文、页码与pending状态。协议验收覆盖12种工具和14次调用；不是医学准确率评测，也不等于图谱+RAG优于RAG。

## 三、目录结构
```
ontology/        本体定义、LLM 抽取提示词、人工确认日志、标准对齐映射、版本
pipeline/        多模态解析管线（PDF / OCR / 表格）与图谱构建
mcp_servers/     自研 MCP 工具（图谱查询 / 标准检索 / 数值计算）
skills/          可复用 Skill 工作流模板
eval/            评测集、朴素 RAG 基线、对比结果
demo/            可视化 Demo 页面
deploy/          Nexent 部署配置与智能体配置导出
data/            原始数据（raw）与处理后数据（processed）
docs/            开发设计文档（初赛提交材料源稿）
```

## 四、关键指标
| 指标 | 朴素 RAG 基线 | 本方案 | 说明 |
|---|---|---|---|
| 多跳问答准确率 | TODO | TODO | eval/dataset.jsonl，共 N 题 |
| 溯源命中率 | TODO | TODO | 结论出处是否指向正确文件+页码 |
| 跨文档跳数（平均） | 1 | TODO | 需 ≥ 2 跳 |
| 本体构建人时 | TODO 人天 | TODO 人天 | 证明"半自动化" |
| 行业迁移耗时 | — | TODO | 附加分：多行业模板迁移 |

## 五、开源
- GitHub: TODO
- GitCode: TODO

## 六、许可证
MIT（见 `LICENSE`）。Nexent 本体亦为 MIT。
