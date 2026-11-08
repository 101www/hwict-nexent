package com.example.ict.mcp.tools;

import com.example.ict.mcp.repo.GraphRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.*;

import static com.example.ict.mcp.repo.GraphRepository.contains;

/** 可解释的有限规则组合。数据库中的数字和证据决定结果，工具不内置医学答案。 */
final class DecisionSupport {
    private final GraphRepository repo;
    DecisionSupport(GraphRepository repo) { this.repo = repo; }

    List<Object> resolveRegimen(String population) {
        if (population == null || population.isBlank()) { throw new IllegalArgumentException("请指定完整人群"); }
        Set<String> targets = new HashSet<>();
        repo.seeds(population).stream().filter(n -> "Population".equals(n.path("type").asText()))
                .forEach(n -> targets.add(n.path("id").asText()));
        List<Object> results = new ArrayList<>();
        for (JsonNode indication : repo.records("edges")) {
            if (!"preferredRegimenFor".equals(indication.path("relation").asText())
                    || !targets.contains(indication.path("tailId").asText())) { continue; }
            String group = indication.path("regimen_group").asText();
            if (group.isBlank()) { continue; }
            List<Object> paths = new ArrayList<>();
            for (JsonNode component : repo.adjacent(indication.path("headId").asText())) {
                if (!group.equals(component.path("regimen_group").asText())
                        || !Set.of("hasComponent", "hasAlternativeComponent").contains(component.path("relation").asText())
                        || !component.path("supporting_evidence").isArray()
                        || component.path("supporting_evidence").isEmpty()) { continue; }
                // 不能把同一方案在另一合并症的用法混入；同组、原方向、定义证据必须全部匹配。
                paths.add(Map.of("nodes", List.of(name(indication.path("tailId").asText()),
                                name(indication.path("headId").asText()), name(component.path("tailId").asText())),
                        "hops", 2, "steps", List.of(Map.of("forward", false, "edge", indication),
                                Map.of("forward", true, "edge", component)),
                        "option_group", component.path("option_group").asText()));
            }
            if (!paths.isEmpty()) {
                results.add(Map.of("kind", "scoped_regimen_composition", "paths", paths,
                        "components", repo.node(indication.path("headId").asText()).path("attributes").path("components"),
                        "selection", "all_components_with_one_of_per_group", "verification", "pending",
                        "sufficient", false, "confidence", indication.path("confidence").asDouble(),
                        "confidence_basis", "rule_heuristic_not_calibrated",
                        "note", "指南原文的方案解析；保留人群、择一/联用、禁忌和版面疑点，不是个体处方。"));
            }
        }
        return results;
    }

    Map<String, Object> evaluateBp(Double sbp, Double dbp, String unit, String method,
                                    Boolean standardized, String readingsJson) {
        requireReading(sbp, dbp);
        if (!"mmHg".equals(unit)) { throw new IllegalArgumentException("当前仅支持mmHg，不自动换算单位"); }
        JsonNode rule = repo.records("decision_rules").stream()
                .filter(n -> "blood_pressure_boundary".equals(n.path("kind").asText()))
                .findFirst().orElseThrow(() -> new IllegalArgumentException("未加载血压组合规则，不能拿数字候选代替"));
        List<JsonNode> thresholds = repo.records("thresholds").stream()
                .filter(n -> rule.path("id").asText().equals(n.path("decision_rule_id").asText())).toList();
        if (thresholds.size() != 2 || !"OR".equals(rule.path("logic").asText())) {
            throw new IllegalArgumentException("血压组合规则不完整");
        }
        double sbpLimit = boundary(thresholds, "sbp"), dbpLimit = boundary(thresholds, "dbp");
        boolean specified = method != null && !method.isBlank() && !"unknown".equals(method);
        boolean applicable = rule.path("measurement_method").asText().equals(method);
        boolean mismatch = specified && !applicable;
        List<String> missing = new ArrayList<>();
        if (!specified) { missing.add("measurement_method=office"); }
        if (!Boolean.TRUE.equals(standardized)) { missing.add("standardized_measurement"); }
        JsonNode requirements = rule.path("requirements");
        List<Object> visits = new ArrayList<>();
        boolean historyMatches = false;
        if (readingsJson == null || readingsJson.isBlank()) {
            missing.add("dated_repeat_visits");
        } else {
            try {
                JsonNode readings = new ObjectMapper().readTree(readingsJson);
                if (readings == null || !readings.isArray() || readings.size() > 100) {
                    throw new IllegalArgumentException("复测数据应为不超过100条的JSON数组");
                }
                Set<LocalDate> days = new HashSet<>();
                boolean allReached = true;
                for (JsonNode reading : readings) {
                    if (!reading.path("sbp").isNumber() || !reading.path("dbp").isNumber()) {
                        throw new IllegalArgumentException("每次复测需要数值sbp/dbp和date");
                    }
                    double s = reading.path("sbp").asDouble(), d = reading.path("dbp").asDouble();
                    requireReading(s, d);
                    LocalDate day = LocalDate.parse(reading.path("date").asText());
                    days.add(day);
                    boolean reached = s >= sbpLimit || d >= dbpLimit;
                    allReached &= reached;
                    visits.add(Map.of("date", day.toString(), "sbp", s, "dbp", d, "reaches_boundary", reached));
                }
                boolean countOk = days.size() >= requirements.path("minimum_visits").asInt();
                boolean separate = days.size() == readings.size();
                boolean windowOk = !days.isEmpty() && ChronoUnit.DAYS.between(Collections.min(days), Collections.max(days))
                        <= requirements.path("maximum_days").asInt();
                historyMatches = countOk && separate && windowOk && allReached;
                if (!countOk) { missing.add("minimum_distinct_visits"); }
                if (!separate) { missing.add("non_same_day_visits"); }
                if (!windowOk) { missing.add("visits_within_rule_window"); }
                if (!allReached) { missing.add("every_visit_reaches_boundary"); }
            } catch (java.io.IOException | java.time.DateTimeException e) {
                throw new IllegalArgumentException("复测JSON或ISO日期格式无效", e);
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("kind", "blood_pressure_rule_evaluation");
        result.put("input", Map.of("sbp", sbp, "dbp", dbp, "unit", unit,
                "measurement_method", specified ? method : "unknown"));
        result.put("systolic_reaches", mismatch ? null : sbp >= sbpLimit);
        result.put("diastolic_reaches", mismatch ? null : dbp >= dbpLimit);
        result.put("reference_boundary_reached", mismatch ? null : sbp >= sbpLimit || dbp >= dbpLimit);
        result.put("scope_status", mismatch ? "measurement_method_mismatch" : applicable ? "office" : "method_unconfirmed");
        result.put("protocol_status", mismatch ? "not_applicable" : missing.isEmpty() && historyMatches
                ? "reported_conditions_match_pending_rule" : "insufficient_or_unmet_conditions");
        result.put("missing_or_unmet_conditions", missing);
        result.put("visits", visits);
        result.put("rule", rule);
        result.put("thresholds", thresholds);
        result.put("sufficient", false);
        result.put("verification", "pending");
        result.put("note", "OR表示收缩压或舒张压任一达到即可。单次读数只比较边界；条件齐全也仅表示所报资料符合待核验条款，不自动确诊。未达到本边界不等于排除高血压。");
        return result;
    }

    List<Object> drugComparisons(String keyword) {
        List<Object> results = new ArrayList<>();
        List<JsonNode> negatives = repo.records("edges").stream()
                .filter(n -> "excludedFromFirstLine".equals(n.path("relation").asText())).toList();
        for (JsonNode negative : negatives) {
            String drugId = negative.path("headId").asText();
            if (!contains(name(drugId), keyword)) { continue; }
            for (JsonNode positive : repo.adjacent(drugId)) {
                String rel = positive.path("relation").asText();
                boolean stock = Set.of("requiresDrugClass", "recommendsDrugClass").contains(rel)
                        && drugId.equals(positive.path("tailId").asText());
                boolean firstLine = "firstLineFor".equals(rel) && drugId.equals(positive.path("headId").asText())
                        && negative.path("tailId").equals(positive.path("tailId"));
                if (!stock && !firstLine) { continue; }
                String status, reason;
                if (stock) {
                    status = "not_conflicting_different_purpose";
                    reason = "机构药物配备与无合并症患者一线初始用药是不同决策；配备不意味着所有患者首选，非首选也不意味着禁用。";
                } else if (scopeComplete(positive) && scopeComplete(negative)
                        && positive.path("scope").equals(negative.path("scope"))
                        && positive.path("condition").equals(negative.path("condition"))) {
                    status = "potential_conflict_same_scope";
                    reason = "同一人群、目的及条件出现正反推荐，需人工复核原文与版本；不自动选择胜方。";
                } else {
                    status = "scope_or_condition_requires_review";
                    reason = "适用范围或条件缺失/不一致，不能仅凭相反词语认定矛盾，也不能直接断言不矛盾。";
                }
                results.add(Map.of("kind", "drug_recommendation_scope_comparison", "subject", name(drugId),
                        "status", status, "items", List.of(positive, negative), "reason", reason,
                        // 文件名含2025，但文内刊期可能是2024；把版本证据随断言一起交给模型。
                        "source_documents", sourceDocuments(List.of(positive, negative)),
                        "verification", "pending", "sufficient", false, "confidence", 0.55,
                        "confidence_basis", "rule_heuristic_not_calibrated"));
            }
        }
        return results;
    }

    private List<JsonNode> sourceDocuments(List<JsonNode> edges) {
        Set<String> files = new HashSet<>();
        edges.forEach(e -> files.add(e.path("file").asText()));
        List<JsonNode> documents = new ArrayList<>();
        repo.meta().path("documents").forEach(d -> {
            if (files.contains(d.path("file").asText())) { documents.add(d); }
        });
        return documents;
    }

    private static boolean scopeComplete(JsonNode edge) {
        return !edge.path("scope").path("population").asText().isBlank()
                && !edge.path("scope").path("purpose").asText().isBlank();
    }
    private String name(String id) { return repo.node(id).path("name").asText(); }
    private static double boundary(List<JsonNode> rows, String role) {
        JsonNode row = rows.stream().filter(n -> role.equals(n.path("role").asText())).findFirst().orElseThrow();
        if (!row.path("value").isNumber() || !">=".equals(row.path("operator").asText())
                || !"mmHg".equals(row.path("unit").asText())) { throw new IllegalArgumentException("不支持的血压边界规则"); }
        return row.path("value").asDouble();
    }
    private static void requireReading(Double sbp, Double dbp) {
        if (sbp == null || dbp == null || !Double.isFinite(sbp) || !Double.isFinite(dbp) || sbp <= 0 || dbp <= 0) {
            throw new IllegalArgumentException("收缩压和舒张压均需要有限正数");
        }
    }
}
