---
name: clinical-conflict-check
description: "用于高血压指南和标准的表面矛盾、药物配备与一线用药、同范围正反推荐及数值差异比较。核对人群、用途、条件、版本与两份原文，保留潜在冲突，不自动裁决。"
---

# 比较适用范围与冲突（模板1.0.0）

输入用户问题和本轮release_id；独立执行先graph_status。实际调用detect_conflicts(subject=用户主题)。处理JSON字符串先json.loads；逐次核对knowledge_version，不混合发布版本。

读取items中的status、reason、items和source_documents。比较每条原始断言的实体/关系、人群、purpose、条件、例外、单位、测量场景和规范版本，再用get_evidence核对涉及的不同block_id。缺少的条件保持未知，禁止脑补。

- not_conflicting_different_purpose：仅说明这两条断言的目的不同。例如配备药品与初始治疗推荐不能直接当成同一命题。保留两份出处，不扩大为“全文完全一致”。
- potential_conflict_same_scope：同范围正反推荐是待人工核对的潜在冲突，完整保留双方证据，不替医学规范决定胜方。
- scope_or_condition_requires_review、needs_review：条件或数值有待核对；数值不同不自动等于规范冲突。若缺少单位/人群/目的，不做等价比较。
- 结果为空：只能说当前已覆盖模式未命中，不能宣称全文没有冲突。可继续query_relations/lookup_clause补检。

版本更新不天然意味着更高效力；不依据文件名年份选胜方。source_documents有实际year及warning时保留；引用版本缺失时用check_references核对，不静默替代。

将两边claims、状态、适用范围、具体证据放入evidence_packet，交给clinical-trace-report。所有候选保留pending与原confidence，本Skill不批准/发布/删除知识。
