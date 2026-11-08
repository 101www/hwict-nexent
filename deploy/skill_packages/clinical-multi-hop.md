---
name: clinical-multi-hop
description: "高血压合并症首选药或图谱多跳路径问题使用。按同方案组连接人群、方案、药物类别，逐跳核对原文和条件，区分同文跨节与跨文档路径，不把通用连通路径当作临床推断。"
---

# 有条件的多跳取证（模板1.0.0）

输入：用户原问题、总流程本轮release_id（若独立执行，先graph_status）。工具JSON字符串必须json.loads后读取；所有响应版本须一致。

## 专用两跳

对“合并糖尿病的高血压患者首选哪类药”这种问题：实际调用resolve_regimen(population="高血压合并糖尿病患者")，其他人群用工具可识别的完整名称，不能把糖尿病答案套用到未知合并症。

读取items中的paths、components、selection和restrictions等实际存在字段。每条path的steps[].edge必须保留id、headId、tailId、relation、regimen_group、条件和原文出处。确认两条边属于同一个非空regimen_group，再解释人群←首选方案→成分。按components的one_of解读择一，不能把可替代类别变成联用方案。

读取每一跳的supporting_evidence及原文block_id，实际get_evidence核对首选句、定义句和限制句；同一块去重。首选句若section_status=needs_layout_review，同时保留semantic_section、实际section/page，面向用户说明“版面待核验”。不要只引用类别定义冒充人群首选证据。

## 通用路径

未知实体先find_entities。traverse_relations从实际实体开始，最多3跳；查看steps的forward、边本身方向、条件与跳数。路径连通仅表示证据连通，不能由此自动传递药物适应证、禁忌或处方。没有合法可组合路径就报告未找到这类结构化证据，必要时回到原文查找，不强凑两跳。

## 交付给溯源流程

在evidence_packet保留路径和每一跳出处，按路径实际文件去重计数。文件数1且章节不同称“同文跨节两跳”，文件数至少2才称“跨文档路径”；不能把全文入库3份说成每次推理跨了3份。

保留verification=pending、confidence原值和confidence_basis。未核验的两跳结果不能变成个体化处方。最后交给clinical-trace-report；不在Skill中预填药物结论或页码。
