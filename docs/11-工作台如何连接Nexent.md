# 工作台怎样连接你部署的 Nexent 智能体

日期：2026-11-07；默认启动修复：2026-11-08，Asia/Shanghai。

## 先理解这条连接

你继续在原 Nexent 首页聊天窗口提问。工作台管理的是 Java MCP 查询的知识版本。模型并不打开工作台网页，也不直接阅读磁盘上的 JSON 文件。

```text
你在 Nexent 提问
  → 模型选择 kg-tools-real 中的工具和参数
  → Nexent 通过 http://192.168.100.1:8081/sse 调用 Java MCP
  → 工具先读取 data/evolution/production/state.json 的 current
  → 校验 releases/<current>/manifest.json 的文件哈希和发布状态
  → 版本改变时重新建立节点表、原文表、邻接表
  → 在该次调用固定的图谱快照内查关系、走路径或计算
  → 返回证据 JSON ＋ knowledge_version
  → 模型据此回答
```

审核工作台写入同一仓库的 `state.json`。这是两者相连的实际位置；没有增加一个必须让模型去浏览的网页。

## 你现在怎么操作

1. 在项目根目录双击 `启动正式图谱MCP.cmd`，保持窗口运行。8081 已有服务时不要重复启动；先用下面的检查命令确认服务。
2. 双击 `打开知识更新工作台.cmd`，保持窗口运行，打开 http://127.0.0.1:8765/ 。
3. 双击 `检查智能体知识版本.cmd`。应显示 `matches_current_published_version: true`、`document_count: 3`。网页中也有“检查 Java MCP 实际正在使用的知识版本”链接。
4. 打开原 Nexent：http://192.168.100.150:3000/ 。MCP 保持 `kg-tools-real`，地址保持 `http://192.168.100.1:8081/sse`。该主机地址能从本机调用，不等于已证明虚拟机侧连通。
5. 在原智能体聊天中输入：**请调用 graph_status，告诉我当前 knowledge_version.release_id、文档数量和核验状态。不要猜测。**
6. 版本应与工作台 current 相同。目前是 `R-20261107T012120-d13d786332`；后续发布会改变，不要把这个值硬编码进提示词。

当前三文档正式基线已建立，保留原有知识，324 节点、2503 边、216 原文块。基线导入不是人工审核；自动抽取继续 `pending`。现有 12 个工具输入参数未改变，输出新增实际版本字段。只有在 Nexent 选错 MCP、未选择 graph_status 或缓存连接失效时，才需要到工具配置中检查、重连或重新选择，不能凭空保证平台已连接成功。

## 后续发布怎么生效

在工作台选择资料 → 填写提案说明 → 生成待审提案 → 查看差异和原文 → 审核人填写理由并批准 → 单独点击发布。下一次 Java 工具调用读取新发布版本，无需重启。只批准而不发布不会生效。

回滚也是改变 current，下一次工具调用读取回滚版本，不删除后续版本和候选。进行中的单次调用固定使用开始时的快照；同一次查询不会把两个版本的邻接表混在一起。一次模型回答可能包含多次工具调用，如果两次调用之间发生发布，模型会看到不同的版本号；需要严格整轮一致时应重试该回答，目前不提供模型对话级版本锁。

当前基线已经包含三份全文，不能再用“加入同一份已存在文件”冒充新知识。历史标准→基层指南的 0→2→0 路径演示在隔离仓库完成。真正更新要提交新增资料、显式改过的来源或经确认的本体；本工作台只接受已有重排文本，不包含 PDF OCR/表格识别。

## 正式、历史、测试怎么区分

| 用途 | 仓库 | 页面/服务 |
|---|---|---|
| 供现有智能体使用 | data/evolution/production | 8765；Java8081 跟随此仓库 |
| 原历史提案，完整保留 | data/evolution/workbench | 双击“打开历史回放工作台.cmd”，8766 |
| 自动化回归 | 独立临时或 automated-* 仓库 | 临时本机端口，结束关闭 |

正式 Java 不接受自动测试审核发布的版本。只有隔离测试 JVM 显式传 `-Dkg.allowTestReleases=true` 才能测试此类版本；正式启动脚本没有此开关。流程批准不把任何医学知识改成已核验。

## 代码在哪，实际如何实现

- `tools/evolve_graph.py`：`production()` 复制现有完整图谱为基线；`launch-java` 传 `--kg.evolution-store`，不是只传某个固定 graph.json。页面审核/发布调用 `EvolutionStore`。
- `pipeline/evolution.py`：`publish()` 保存审核后的完整快照，原子替换 state.json；`rollback()` 只改 current 并记录事件。
- `java-mcp/spring-ai-mcp-server/src/main/java/com/example/ict/mcp/repo/GraphRepository.java`：`snapshot()` 每次工具调用读取 current、检查哈希；版本改变时调用固定文件构造方法重新建索引，返回独立快照。失败明确报错，不拿旧版本冒充当前结果。
- `java-mcp/spring-ai-mcp-server/src/main/java/com/example/ict/mcp/tools/KgToolsService.java`：每个工具先取得 snapshot，再委托使用该快照的工具对象；业务查询逻辑继续使用原节点表和邻接表。`page()`、`traversal()` 及 Map 响应加入 knowledge_version。
- `tools/check_live_connection.py`：实际调用 graph_status，把工具返回版本与 production/state.json 对比；不调用模型。

2026-11-08修复：IDEA直接运行 `McpServerApplication`、Maven或JAR启动时，两项配置都未填写且项目已有 `data/evolution/production`，会默认跟随正式仓库。只有显式设置 `--kg.graph-path` 才固定文件；项目尚无正式仓库时仍兼容读取原graph.json。已存在的正式仓库损坏会报错，不会偷偷退回旧图。两个配置不能同时设置。`knowledge_version.load_mode` 明确返回 `published_store` 或 `fixed_file`，`version_store` 指出仓库路径。已有进程必须重启一次才能加载这次代码修复，后续知识发布/回滚无需重启。部署在另一台机器时需把版本仓库与 Java 服务放在同一主机或正确共享路径；Nexent 不需要直接访问本机磁盘。

## 本轮验收边界

- Python：47 项通过；Java：29 项通过，其中新增 6 项动态切版测试，覆盖全部 12 工具的版本返回、坏指针/哈希、审核隔离和单次调用版本固定。
- `docs/validation/evolution-live-mcp.json`：同一个真实 JVM、同一个 SSE MCP 会话，待审0条 → 批准未发布0条 → 发布2条 → 回滚0条；坏指针显式报错。自动测试审核，不代表临床审核。
- `docs/validation/production-mcp-connection.json`：主机原地址8081实际响应，三份文档、两跳方案2条、随访关系4条，版本与正式仓库一致。
- 2026-11-07曾因浏览器操作故障未完成页面验收。2026-11-08已补测并修复IDEA默认启动：Nexent原“高血压用药决策助手”实际调用 graph_status，原始响应的 source 为正式仓库快照，release_id与current一致，load_mode=published_store，文档3份、pending。见 `docs/validation/nexent-version-startup-fix-20261108.json` 及同名截图/完整调用文本。模型曾把JSON字符串当字典，解析出错后通过json.loads恢复；此项性能问题尚未优化。Java现30项测试通过。
- 这是 MCP 知识版本连接，不等于已经接入 Nexent 原生 Skills，也不等于本体自主学习。原生 Skills、算法对照评测、真实多模态表格处理仍需后续完成。
