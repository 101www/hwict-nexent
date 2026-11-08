# Java MCP：真实图谱查询服务

主路线是 `spring-ai-mcp-server/`。当前已读取三份高血压文档构建的真实图谱，提供10个工具；Nexent v2.7.0 已发现这些工具。完整说明见 [真实图谱MCP接入与测试](../docs/07-真实图谱MCP接入与测试.md)。

`mcp-java-sdk-server/` 保留为原生SDK协议示例，其中工具仍有占位实现，不能当成真实图谱服务。

## 入口和启动

环境：JDK 21、Maven 3.9+。Python 仅用于离线建图和自测客户端；Java运行时直接读JSON，不启动Python子进程。

IDEA打开 `spring-ai-mcp-server/pom.xml`，运行 `McpServerApplication.main()`。命令行也可以：

```powershell
Set-Location 'D:\JavaProject\huawei\nexent-cognitive-agent\java-mcp\spring-ai-mcp-server'
mvn spring-boot:run
```

保持终端运行。默认端口8081，SSE端点 `http://127.0.0.1:8081/sse`。日志应包含 `Loaded real graph` 以及真实路径。

先从工作目录向上寻找 `data/processed/graph.json`，未找到时从Java模块编译类目录或JAR位置向上寻找，兼容IDEA从外层工作区启动。也可在IDEA运行配置中设置环境变量 `KG_GRAPH_PATH` 为绝对路径；显式路径错误时不回退。图谱更新后重启服务。文件缺失、ID重复、正式关系端点无效时启动失败，不回退演示数据、不删改原图。

## 查询和测试

另开终端，进入项目根目录：

```powershell
Set-Location 'D:\JavaProject\huawei\nexent-cognitive-agent'
python java-mcp/query_mcp.py relations 随访
python java-mcp/query_mcp.py references WS-T872
python java-mcp/query_mcp.py clause 随访频率 --file 国家基层
python java-mcp/query_mcp.py path 随访 --end 血压达标患者 --hops 1
python java-mcp/test_real_graph_mcp.py --report docs/validation/mcp_smoke_report.json
```

`query_mcp.py` 走实际HTTP/SSE MCP协议；`tools/query_graph.py` 是直接读JSON的离线工具。这两者与Nexent中的模型问答是三个不同的测试层次。

协议验收包含工具发现及12次调用，覆盖10种工具，返回原文、条件、核验状态和版本差异。实际输入输出记录在报告中。

Java回归：

```powershell
Set-Location java-mcp/spring-ai-mcp-server
mvn test
```

当前18项Java测试（真实图谱工具13项、启动路径定位5项）。AI受限环境用 `mvn -s ../settings.verify.xml test` 将缓存写到工作区；在你自己的IDEA或终端中通常不需要指定该文件。首次运行若缺依赖，需要Maven下载测试运行器。

## 在 Nexent 注册

本次拓扑为：

- Nexent平台：`http://192.168.100.150:3000/`
- Java服务所在Windows电脑：`192.168.100.1`
- MCP名称：`kg-tools-real`
- Nexent填写的URL：`http://192.168.100.1:8081/sse`

Nexent的“智能体开发 → 智能体配置 → 工具与技能 → MCP配置”添加上述服务，再在“选择工具 → MCP → kg-tools-real”勾选工具。

仅当Java运行在Nexent对应的Docker宿主机时，才考虑 `host.docker.internal`；不同电脑之间用实际可达的地址。IP改变后配置需同步更新。

| 工具 | 用途 |
|---|---|
| graph_status | 确认当前数据文件、构建时间、文档版本及局限 |
| find_entities | 名称、别名、ID、类型查询 |
| query_relations | 已抽取关系、条件、例外及出处 |
| traverse_relations | 有界正反向证据路径，保留原始边方向 |
| lookup_clause | 保存的原文块关键词查询 |
| get_evidence | 按block_id取完整原文块 |
| check_references | 被引版本与当前候选版本核对 |
| query_candidates | 完整保留的待核验候选，支持翻页 |
| compare_threshold | 同单位数学比较，不使用未解析数字候选 |
| detect_conflicts | 待核验数值差异，不自动裁决医学冲突 |

## 结果含义

自动抽取保留 `verification: pending` 和 `confidence`。分数不是医学准确率。查到路径不等于医学推断成立，所以 `sufficient` 不会因命中而自动变成true。

常规列表支持 `limit`（最多50）与 `offset`。高频节点仅返回部分出现位置并显式标记，原图不受影响，可用block_id核对完整原文。多跳最多3跳、50条路径，并设展开上限。

`lookup_clause` 当前是关键词搜索，尚未接入向量语义检索。完整RAG对比、表格恢复、本体审核和平台Skill编排仍需后续验证。
