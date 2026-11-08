# 真实图谱 MCP 接入与测试

当前主路线为 `java-mcp/spring-ai-mcp-server`。它在启动时读取真实 `data/processed/graph.json`，不再加载 `seedDemoData()`。原生 SDK 路线仍为协议示例，不能用于证明真实图谱已接入。

## 现在的数据怎么流动

```text
三份原始文本 → build_graph.py → graph.json
                                 ↓ Java 启动时读取
Nexent 模型 → MCP tools/call → GraphRepository → 关系、条件、出处和核验状态
                                 ↓ get_evidence / lookup_clause
                          图谱中保存的原始文档块
```

`query_relations` 查询已抽取的关系；`lookup_clause` 在保存的原文块中做关键词检索；`get_evidence` 根据 block_id 返回完整块。没有在提问时重新抽取 PDF，也没有实现向量语义检索。这些工具与离线 Python 查询读取同一份图谱。

Nexent原先配置的“医疗-高血压”知识库仍可通过平台`knowledge_base_search`调用；本次缺失版本测试中实际检索到了其中的旧临床摘要。它与本项目Java图谱工具是两条检索路径，不能把旧摘要描述成三份全文已完成语义入库，也不能把检索命中当成指定版本原文已存在。

## 第一次启动

在 IDEA 打开 `java-mcp/spring-ai-mcp-server/pom.xml`，等待 Maven 导入，使用 JDK 21，然后运行：

`src/main/java/com/example/ict/mcp/McpServerApplication.java` 的 `main()`。

也可以在 PowerShell 运行：

```powershell
Set-Location 'D:\JavaProject\huawei\nexent-cognitive-agent\java-mcp\spring-ai-mcp-server'
mvn spring-boot:run
```

日志应包含 `Loaded real graph`、实际文件路径和 `Registered tools: 10`，HTTP 端口为 8081。不要重复启动多个实例；8081 被占用时先确认已有服务是否就是本项目。

默认先从工作目录逐级向上寻找 `data/processed/graph.json`；未找到时，再从Java编译类目录或可执行JAR所在目录向上寻找。因此IDEA从外层 `D:\JavaProject\huawei` 启动也能定位模块所属项目的图谱。显式设置路径时以该路径为准，不会在配置错误时偷偷换用别的文件。

如果仍提示找不到图谱，在 IDEA 顶部运行配置旁的菜单打开“编辑配置”，添加环境变量：

```text
KG_GRAPH_PATH=D:\JavaProject\huawei\nexent-cognitive-agent\data\processed\graph.json
```

或者将“工作目录”设为 `D:\JavaProject\huawei\nexent-cognitive-agent`。PowerShell环境变量需要在启动Java的同一个终端中设置，不会自动影响已经打开的IDEA：

```powershell
$env:KG_GRAPH_PATH = 'D:\JavaProject\huawei\nexent-cognitive-agent\data\processed\graph.json'
```

文件不存在、ID 重复或正式关系的端点无效时启动会失败，不会偷偷切回演示数据；候选集合仍完整保留在原图中。图谱更新后需重启 Java 服务。

## 不打开 Nexent 也能测试 MCP

保持 Java 服务运行，另开一个终端：

```powershell
Set-Location 'D:\JavaProject\huawei\nexent-cognitive-agent'
python java-mcp/query_mcp.py relations 随访
python java-mcp/query_mcp.py references WS-T872
python java-mcp/query_mcp.py clause 随访频率 --file 国家基层
python java-mcp/query_mcp.py path 随访 --end 血压达标患者 --hops 1
```

这些命令通过 HTTP/SSE 连接 Java MCP，与 `python tools/query_graph.py ...` 直接读取 JSON 不同。输出 `实际调用 MCP 工具：query_relations` 说明请求已到达 Java 工具。

完整协议验收：

```powershell
python java-mcp/test_real_graph_mcp.py --report docs/validation/mcp_smoke_report.json
```

验证 initialize、tools/list 和 14 次 tools/call，覆盖 12 种工具及候选翻页（最新报告mcp-v04-smoke-report.json）。报告保存实际工具 schema、参数、返回值与测试时间；它证明 Java MCP 的真实数据链路，不单独证明模型选工具正确。

## 工具一览

| 工具 | 返回内容 |
|---|---|
| graph_status | 实际图谱路径、构建时间、文档版本、数量与局限 |
| find_entities | 节点及少量出现位置；高频证据会明确标记截断，可按 block_id 查原文 |
| query_relations | 关系完整字段，含 condition/scope/exceptions 等已有信息 |
| traverse_relations | 有界正反向路径、每步原始方向和完整关系；不自动形成医学推断 |
| lookup_clause | 原文块的关键词检索，可限定文件 |
| get_evidence | 按 block_id 取完整原文块 |
| check_references | 指定引用版本、候选版本和 missing/version_mismatch 等状态 |
| query_candidates | 保留的待核验候选，支持集合筛选、limit/offset 翻页 |
| compare_threshold | 同单位数学比较，不使用 threshold_candidates |
| detect_conflicts | 数值差异及药物推荐作用域对照，区分不同目的与潜在冲突 |
| resolve_regimen | 完整人群经同方案组连接到代号定义，两跳取证及择一/联用限制 |
| evaluate_blood_pressure | 双指标OR边界、测量方式和带日期复测前提检查；不自动确诊 |

所有查询不把命中自动标记为充分证据。`verification: pending` 表示仍待核验；`confidence` 为未校准的启发式规则分数。路径分数是沿途最低边分数，不是推理正确率。`truncated: true` 时可用 offset 翻页；路径检索最多3跳、50条结果且有展开上限。

## 本次 Nexent 网络配置

平台地址：`http://192.168.100.150:3000/`，页面版本 v2.7.0。

Java 所在 Windows 电脑在该网络的地址为 `192.168.100.1`。在 Nexent 中使用：

```text
服务器名称：kg-tools-real
服务器URL：http://192.168.100.1:8081/sse
```

本次已由 Nexent 页面完成工具发现，看到10个工具，并实际用 deepseek-flash 完成随访与版本核查问答。工具接通与生成质量分开验收，失败记录和复测结果见 [验证记录](validation/README.md)。`host.docker.internal` 只适用于 Java 服务运行在对应 Docker 宿主机的情况，不能在不同电脑之间盲用。IP 变更后需同步修改配置。无需为了此测试关闭防火墙。

助手现选择12个工具（早期基线为10个），使用要求备份在 `deploy/agent_config_export/constraints_before_mcp.txt`，修改后文本在 `constraints_in_nexent.txt`。角色、示例和开场白也保留修改前后记录。当前发布版本为 `高血压用药决策助手-2610182221`，已用首页新对话验证随访问答。编辑页点击“调试”使用草稿，首页使用已发布配置；以后修改草稿还需发布后在首页复测。

标准编号兼容 `WS/T 872—2025` 和 `WS-T872-2025` 等分隔符差异，关键词匹配兼容Unicode空白；这一修正来自平台模型实际调用暴露的未命中问题。

### 明明已有随访条款，助手却说未找到

先区分“图谱没有记录”和“本次对话没有调用图谱”。Nexent首页可能使用已发布版本，编辑页“调试”使用草稿；在草稿中选中MCP工具不代表旧发布版本也已经带上这些工具。

可先在本机运行 `python java-mcp/query_mcp.py relations followUpEvery --limit 10`。正常应返回4条关系，来源为管理标准PDF第5页8.3.2.1/8.3.2.2及基层指南PDF第13页8.1。若本机查询成功，而Nexent回答只引用旧临床摘要，需要检查本轮执行记录是否出现`query_relations`或`get_evidence`、是否使用预期助手/版本、MCP URL是否仍可达。只出现`knowledge_base_search`不足以证明图谱里没有依据。

本轮用户报告后的本机复核见 `docs/validation/followup-routing-local-check.json`：4条关系、3个原文块均通过真实HTTP/SSE返回。随后已发布2610182135，并在首页原句复测：1次query_relations与3次get_evidence给出有据回答，另有1次平台search_memory；详见 `docs/validation/nexent-home-followup-after-fix.md`。该结论来自首页实际问答，不能只靠本机MCP记录代替。原始文件无需为了这类路由问题改名或重复上传。

平台模型还曾把动作输出为DSML文字而没有执行工具。当前已在“高级设置→运行策略”启用“严格输出协议与静默修复”，并将示例改为实时图谱查询流程。该选项经页面重载确认保存；样例复测成功仍不能保证模型所有输出都稳定。

## 原文定位修正与回归

参考文献标题支持“参 考 文 献”等空白形式，结束此前附录章节。标准第8页的参考年证据已从错误的 A.1 改为 REFERENCES；原文、物理页码、pending 状态不变，旧图谱完整保存在 history 快照中。

Python 管线31项测试通过；Java测试23项（真实图谱工具18项、启动路径定位5项）。Java测试检查多来源关系、原文偏移、版本差异、别名、标准编号格式差异、反向路径、结果截断、候选保留、无效文件启动失败及IDEA外层工作目录定位。

```powershell
python -m unittest discover -s eval -p test_graph_pipeline.py
Set-Location java-mcp/spring-ai-mcp-server
mvn test
```

Agent 受限环境使用 `mvn -s ../settings.verify.xml test` 将 Maven 缓存写入工作区；你在自己的 IDEA/终端中通常不需要该参数。

后续工作仍包括：语义检索/RAG对比评测、关键表格恢复、本体变更审核与平台Skill编排验证。本次不能据此宣称已完成这些功能。


## 三类推理扩展（0.4规则）

当前图谱324节点、2503边、6条阈值、1条组合规则。新增能力和初学者逐步解释见[学习说明](08-三类推理是怎么做出来的.md)。现有8081后台Java进程已载入新快照；同端口不要再启动第二个IDEA进程。单击运行项目根目录“验证三类推理.cmd”或执行`python -X utf8 eval/run_reasoning_acceptance.py`可查询真实MCP。报告中的数值差异统计仍只覆盖数值，药物作用域比较在MCP工具运行时计算。
