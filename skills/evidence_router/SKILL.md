---
name: clinical-evidence-router
description: "高血压资料问答的总流程。随访、用药、血压数值、指南版本、配备与一线推荐比较时先使用；检查发布版本，选择检索或推理工具，转交相关专用Skill及溯源Skill。"
---

# 证据问答总流程（模板1.0.0）

本Skill只编排已绑定的真实MCP，不包含医学答案。适用于三份全文的资料查询；不能把自动抽取当成医生审核。其他行业迁移时替换实体与路由表，保留版本、证据、适用条件和未知状态的处理。

## 第一步：实际查询版本并解析工具响应

Nexent CodeAgent的MCP工具常返回JSON字符串，不能直接对字符串调用.get。每轮定义或复用以下函数；只使用json标准库，不读取本地磁盘，不猜测文件路径。

```python
import json
def decode_result(raw):
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("工具响应不是JSON对象")
    return data
status = decode_result(graph_status())
workflow_release = status.get("knowledge_version", {}).get("release_id")
print(status)
```

版本来自本轮响应，不硬编码release_id。若无版本或为unversioned，明确说明版本未纳管，不宣称使用当前已发布版本。工具报错说明连接/执行失败，不能说原文不存在。

后续每次查询都先decode_result，并比较knowledge_version.release_id是否等于workflow_release。发生变化则放弃本次混合证据，从graph_status开始最多重试一次；仍变化则说明更新中，不能拼接两版作单一结论。

## 第二步：选择相关流程，检索与推理协同

- 随访、机构管理与配备：query_relations；随访关系关键词用followUpEvery。逐一收集命中边的条件、文件、page、section、block_id，再用get_evidence核对不同原文块，同一block_id只查一次。
- 合并症首选用药或图上路径：先实际读取read_skill_md(skill_name="clinical-multi-hop")，按该Skill执行。
- 数值是否达到标准：evaluate_blood_pressure，参数仅来自用户；未给measurement_method则传unknown，不编造standardized或readings_json。读取边界与rule.requirements，区分数学比较、适用性和确诊前提。单独比较已有约束可用compare_threshold，禁止自动单位换算。
- 指定指南引用或版本：check_references。若resolution=missing/version_mismatch，能说明现有引用，不能拿另一年份全文冒充指定版本原文。
- 配备与一线推荐是否矛盾、跨文件数值差异：先实际读取read_skill_md(skill_name="clinical-conflict-check")，再按该Skill执行。
- 明确查询文件/原文：lookup_clause。实体不明确先find_entities。结构化结果未命中再lookup_clause，必要时query_candidates；候选仅待核验线索。若已有平台knowledge_base_search可补检，但与图谱是不同来源，未命中不能替另一来源作结论。

每个专用Skill加载后才依其正文执行；不要仅在回答中声称用了Skill。read_skill_md缺失或读取失败要明确记录，不能把自行选工具当作原生Skill已执行。

## 第三步：形成证据包并使用溯源流程

在代码变量evidence_packet中组织本轮实际返回内容：question、release_id、route、observed_tool_calls、paths/claims、citations、conditions、uncertainties。citations保留文件、物理页、实际/语义章节、block_id、原文及pending。只收录实际调用，不编造调用记录。数值输入和中间比较来自工具响应。

实际读取read_skill_md(skill_name="clinical-trace-report")并按它输出。普通问答含出处默认不超过200字符，详细证据报告仅用户要求时展开。展示知识版本时可单列；若发生版次混用风险不能为凑字数省略。

所有不确定知识保留verification=pending和原confidence；confidence是未校准规则分，不是正确率。不要创建、发布、批准或删除知识更新；这个问答流程无审核权限。
