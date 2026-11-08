# 真实图谱接入验证记录

## 原生Skills接入进度（2026-11-08）

四个原生Skill已在平台创建、绑定原智能体，并内部发布为 **高血压用药决策助手-2611081425**，保留12个kg-tools-real工具。五道首页独立新对话均已运行，四个Skill均有实际read_skill_md记录。随访和冲突题展示了核心链路；多跳、数值和缺失版本仍有执行或表达遗漏，不能记为全面通过。五个短答均少于200字符，自动知识仍待核验。详见[本轮逐题结果](native-skills-acceptance-20261108.md)和[原生Skills编排](../12-Nexent原生Skills编排与复用.md)。下方2026-10-18等段落为历史记录。

验证日期：2026-10-18，Asia/Shanghai。

## 三个层次分别验证

| 层次 | 证据 | 结果和范围 |
|---|---|---|
| Python建图 | eval/test_graph_pipeline.py | 31项通过；参考文献定位、原文偏移、待核验保留与历史快照等 |
| Java工具 | RealGraphToolsTest.java | 18项通过；真实文件读取、条件保留、分页、标准编号、方向与不足提示等 |
| Java启动路径 | GraphPathResolutionTest.java | 5项回归；外层工作区、JAR位置、工作目录优先、显式路径优先且错误不回退、不扫描无关子项目 |
| MCP协议 | mcp-v04-smoke-report.json | initialize/tools/list及14次tools/call成功，覆盖12个工具 |
| Nexent工具发现 | nexent-mcp-tools.png | v2.7.0平台注册kg-tools-real，发现10个工具 |
| Nexent模型问答 | 下表及对应原始页面记录 | 已验证模型确实调用真实工具；仍需扩大题集，不能作为准确率指标 |

本机Java URL为 `http://192.168.100.1:8081/sse`，Nexent为 `http://192.168.100.150:3000/`。Java日志显示Nexent请求协议2025-11-25，服务建议2024-11-05，随后完成工具发现和调用。版本协商成功不表示服务实现了全部较新协议功能。

## 实际调试迭代

| 轮次 | 问题与观察 | 处理与状态 |
|---|---|---|
| 1 | 随访频率对比；13次工具调用，页面显示22.17s；达标/未达标、至少、两份出处与pending得到保留 | 核心事实与原文相符，但回答过长、工具调用过多。记录在nexent-followup-transcript.md |
| 2 | 引用版本核查；4次调用、16.62s；2021与2025的版本差异结论正确 | 模型错误称为“规范性引用”，并错误声称正文与参考文献共用block；不能算完整通过。记录在nexent-version-transcript-before-fix.md |
| 3 | 新会话版本核查；按WS/T 872查文件未命中，最后输出DSML调用语法而未回答 | 明确失败，保留nexent-format-failure.md；补标准编号归一化与Java回归，收紧提示词 |
| 4 | 修正后新会话；3次调用、6.93s；check_references + graph_status + get_evidence | 核心事实、出处与不能替代的理由相符，最终自然语言未再出现上述引用性质/block错误；回答仍超过测试要求的200字，长度约束未通过。见nexent-version-transcript.md及nexent-version-answer.png |
| 5 | 在第4轮同一会话中追问指定2021版诊断阈值逐字原文及PDF页码；8次工具调用（7次图谱MCP、1次平台knowledge_base_search），页面显示22.46s | 明确说明2021版全文未入库，未编造阈值原文或页码，未用2025版替代；给出标准自身第4页引用文字及第8页文献信息。核心缺失版本处理符合预期，但检索冗余、回答偏长；不是独立新会话验收。见nexent-missing-version-transcript.md |
| 6 | 用户在首页询问“血压达标和未达标患者分别多久随访”，旧版只搜索临床摘要后拒答，页面显示11.29s | 读取实际历史会话，代码中有7次knowledge_base_search、没有图谱MCP查询；当时平台当前发布版仍为2610132226。保存nexent-home-followup-before-fix.md；本机独立MCP仍返回4条关系及3个原文块（followup-routing-local-check.json），不能归咎文件名 |
| 7 | 补选草稿模型、补检索渠道规则后，草稿原句复测850ms便结束，输出DSML但未执行工具 | 失败记录nexent-home-draft-format-failure.md。启用平台“严格输出协议与静默修复”，并把旧单文档医学答案示例改为实时查询流程示例；两项修改同时发生，不能单独归因某一项 |
| 8 | 新草稿会话使用4次图谱MCP及1次parallel_executor，页面显示6.29s；核心随访频次与两份出处正确 | 附加解释错误称“3个月是间隔下限”，并将标准8.4套到另一份指南，不能算完整通过。保存nexent-home-draft-after-format-fix.md；补频次语义及跨文件章节引用规则 |
| 9 | 发布2610182135后，在首页新建会话，原样询问“血压达标和未达标患者分别多久随访”；页面显示5.80s | 5次工具调用：1次search_memory、1次query_relations、3次get_evidence，未调用knowledge_base_search。两人群频次、至少、直至达标、两份出处及pending符合原文，未再出现上轮两处扩展错误；回答仍偏长。见nexent-home-followup-after-fix.md、nexent-home-followup-answer.png及发布状态记录nexent-home-published-version.md |

上述耗时为页面实测的单次显示值。题目、上下文和提示词有变化，不是受控性能对比，不能据此声称某方案提速多少或证明优于RAG。没有把一次未复现的格式错误宣称为永久解决。

第5轮还暴露了两项局限：模型虽说明pending，但未在最终出处中明确传达标准第4页的`section_status: needs_layout_review`；平台已有“医疗-高血压”知识库仍可被调用，其中检索到的是旧临床摘要。Java的`lookup_clause`仍是原文块关键词检索，本次未把三份全文升级为平台语义知识库，也未完成受控RAG对比。

原始页面记录中的账号文本已替换为占位符。截图包含界面上下文；对外分享可优先使用去掉账号页眉的nexent-version-answer-crop.png。

## 2026-10-18交付状态（历史；当前版本见页首）

当前发布版本为 `高血压用药决策助手-2610182221`，替换此前2610132226在首页使用的配置，旧版本及旧会话保留。草稿配置经页面重载核对后发布；首页新对话原句验收完成。已补选deepseek-flash模型、发布12个图谱MCP工具、更新示例与21条使用要求，并启用“严格输出协议与静默修复”。修改前后文本及手工配置快照在 `deploy/agent_config_export/`。旧会话历史中的错误回答不会被改写，复测应新建对话。

`agent_draft_snapshot.json` 是明确标记的UI配置记录，不是平台导出格式；`mcp_tools_v0.2.0.json` 则来自实际MCP协议响应。参赛要求的平台完整导出仍需后续完成。

这些验证不等于医疗审核、全面覆盖评测、图谱+RAG效果对比或Skill编排验收。自动抽取仍保留pending与未校准confidence。

## IDEA启动目录故障回归

用户提供的启动异常末层为“找不到 data/processed/graph.json”，实际文件存在。此前仅从工作目录向上查找，IDEA以外层 `D:\JavaProject\huawei` 为工作目录时无法发现子项目数据。现补充从Java模块编译类/JAR所在位置向上定位，显式配置仍优先且配置错误不回退，不扫描无关子项目。

修正后18项Java测试通过（13项工具、5项路径，失败/错误均0），Maven打包成功。分别用Spring Boot运行插件和打包后JAR模拟从 `D:\JavaProject\huawei` 启动，均加载实际图谱（322节点、2498关系、216块）、注册10工具并完成启动。最终JAR使用临时随机端口55626，通过HTTP/SSE调用`graph_status`，返回真实图谱路径；这是本地启动验证，没有重新执行Nexent模型问答。

本轮结束已停止由Agent启动的旧8081服务及临时验证进程，交由用户从IDEA运行。若用户之后自行启动服务，当前运行状态以其IDEA控制台为准。

随后首页故障排查时，用户运行的8081服务可用，并完成了第6—9轮验证；未再停止用户的服务。这些后续操作没有修改或重命名三份源文档，也没有重建或删除pending图谱记录。本次没有改Java/Python逻辑，沿用前一轮18项Java与29项Python测试结果；新增验证为本地4次MCP调用及Nexent实际问答。新版的独立版本核查、缺失版本回归和更大题集仍待完成，单个首页样例成功不证明格式问题永久消失或全题集正确。


## 三类推理扩展与最终首页验收

最新完整记录见[三类推理及简答验收](nexent-reasoning-three-cases.md)，初学者解释见[三类推理是怎么做出来的](../08-三类推理是怎么做出来的.md)。最终2221版三道独立首页会话完成核读，答复107/107/143字符；中间两轮的错误及遗漏全部保留。31项Python、23项Java、12工具/14调用的协议smoke及8项专项协议验收通过。未证明图谱优于RAG、原创算法优势或全题稳定性。


## 2026-11-07 知识更新审核闭环

新增本地差异提案、审核、版本发布及回滚；47项Python回归通过，真实Java MCP回放两跳路径0→2→0。自动审核明确为测试，默认人工工作台仍待审，正式图谱未改。见[本轮验收](evolution-summary.md)和[操作说明](../10-知识更新审核与版本回放.md)。尚未接入Nexent原生Skills。


## 2026-11-07 发布仓库连接

- `evolution-live-mcp.json`：同一JVM同一MCP会话，发布和回滚无需重启；测试审核隔离。
- `production-mcp-connection.json`：真实主机8081读取三文档正式版本，非Nexent页面验收。
- `production-connection-summary.json`：本轮测试、正式迁移和页面验收边界。
- 使用说明：`../11-工作台如何连接Nexent.md`。


## 2026-11-08 IDEA默认启动修复及Nexent补测

`nexent-version-startup-fix-20261108.json`：修复前unversioned、无参数JAR启动后的正式版本、30项Java测试与Nexent原始工具响应。配套 `.txt` 保留调用及字符串解析错误恢复，`.png` 截取原智能体标题、工具响应与最终回答。没有改写医学知识及审核状态。
