# 本体候选抽取提示词

> 用途：让 LLM 从领域文档中抽取候选实体与关系，作为"半自动化"的自动化环节。

## 角色
你是领域知识工程师，负责从下方文档片段中抽取知识图谱的候选实体与关系。

## 输入
- 文档片段：`{chunk_text}`
- 来源元数据：`{file} / 第 {page} 页 / 章节 {section}`
- 现有本体（用于复用，避免造新词）：`{existing_schema}`

## 输出（严格 JSON）
```json
{
  "entities": [
    {"name": "", "type": "", "aliases": [], "attributes": {}, "evidence": "原文片段", "verification": "pending", "confidence": 0.0}
  ],
  "relations": [
    {"head": "", "relation": "", "tail": "", "condition": "", "evidence": "原文片段", "verification": "pending", "confidence": 0.0}
  ],
  "numeric_constraints": [
    {"subject": "", "operator": ">=|<=|>|<|==", "value": 0, "unit": "", "evidence": "", "verification": "pending", "confidence": 0.0}
  ],
  "schema_suggestions": [
    {"action": "add_type|add_relation", "name": "", "reason": ""}
  ],
  "confidence": 0.0
}
```

## 硬性约束
1. **禁止编造证据**：能够定位时输出原文；已有候选若无法定位，不得删除，保留完整候选、原始片段和缺失原因，标记 `verification: pending`、`confidence`，证据未知可为空。
2. **优先复用**：能用现有本体类型就不要新建。
3. 数值必须带单位与出处页码。
4. 矛盾表述单独放 `conflicts` 字段，不要自行裁决。
5. 任何不确定结果都必须保留，逐条提供 `verification: pending`、`confidence` 和核验原因。confidence 是抽取评分，不能当作医学正确率。
6. 区分配备要求、药物选择、一线初始用药、联合方案及禁忌。A=ACEI或ARB是择一组；A+B不能解释为ACEI、ARB和β受体阻滞剂同时使用。药物规则依据基层指南5.4.2/5.4.3，并保留每份来源的适用条件。
