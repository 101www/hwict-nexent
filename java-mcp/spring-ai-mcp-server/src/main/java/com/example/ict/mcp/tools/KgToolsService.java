package com.example.ict.mcp.tools;

import com.example.ict.mcp.model.GraphModel.*;
import com.example.ict.mcp.repo.GraphRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Service;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static com.example.ict.mcp.repo.GraphRepository.contains;
import static com.example.ict.mcp.repo.GraphRepository.fileContains;
import static com.example.ict.mcp.repo.GraphRepository.normalized;

/** 从真实图谱检索证据；命中、连通、数值比较均不自动构成已核验的临床结论。 */
@Service
public class KgToolsService {
    private static final Set<String> STRUCTURAL = Set.of("evidencedBy", "containsSection", "references");
    private static final List<String> CANDIDATES = List.of(
            "edge_candidates", "entity_candidates", "extraction_candidates", "threshold_candidates");
    private final GraphRepository repo;

    public KgToolsService(GraphRepository repo) { this.repo = repo; }

    @Tool(name = "graph_status", description = "查看当前加载的真实图谱文件、构建时间、文档版本、数量及局限。先用此工具确认数据来源。")
    public Map<String, Object> graphStatus() {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).graphStatus(); }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("source", repo.source().toString());
        result.put("mode", "real_graph_snapshot");
        result.put("knowledge_version", repo.version());
        result.put("meta", repo.meta());
        result.put("nodes", repo.records("nodes").size());
        result.put("edges", repo.records("edges").size());
        result.put("blocks", repo.records("blocks").size());
        result.put("candidate_count", CANDIDATES.stream().mapToInt(k -> repo.records(k).size()).sum());
        result.put("sufficient", false);
        result.put("message", "已加载真实图谱；自动抽取仍待核验。发布仓库模式在下次工具调用时加载当前发布版本；固定文件模式仍需重启。");
        return result;
    }

    @Tool(name = "find_entities", description = "按名称、别名、ID、类型查找真实图谱节点。返回待核验状态和少量出处；未命中不代表原文不存在。")
    public QueryResult findEntities(
            @ToolParam(description = "关键词，例如：血压达标患者") String keyword,
            @ToolParam(description = "类型，如 Disease/DrugClass/Population/Equipment/SourceDoc，可留空", required = false) String type,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).findEntities(keyword, type, limit, offset); }
        List<JsonNode> matches = repo.find(keyword, type);
        // 高频节点含很多出现位置，只压缩工具响应，不修改原图。block_id 可用于取完整原文。
        List<JsonNode> summaries = matches.stream().map(node -> {
            ObjectNode copy = node.deepCopy();
            if (copy.path("evidences").isArray()) {
                JsonNode all = copy.path("evidences");
                var sample = JsonNodeFactory.instance.arrayNode();
                for (int i = 0; i < Math.min(3, all.size()); i++) { sample.add(all.get(i)); }
                copy.set("evidences", sample);
                copy.put("evidence_count", all.size());
                copy.put("evidences_truncated", all.size() > 3);
            }
            return (JsonNode) copy;
        }).toList();
        return page(summaries, offset, limit, "节点命中不等于结论；出处可用 get_evidence 进一步核对。");
    }

    @Tool(name = "query_relations", description = "按实体名称或关系名称查找关系，返回完整条件、例外、原文、页码、置信分和待核验状态。")
    public QueryResult queryRelations(
            @ToolParam(description = "关键词，例如：随访、血压达标患者、requiresEquipment") String keyword,
            @ToolParam(description = "限定文件名，可留空", required = false) String file,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).queryRelations(keyword, file, limit, offset); }
        List<JsonNode> rows = new ArrayList<>();
        for (JsonNode edge : repo.records("edges")) {
            if (STRUCTURAL.contains(edge.path("relation").asText())) { continue; }
            String head = name(edge.path("headId").asText()), tail = name(edge.path("tailId").asText());
            if ((contains(head, keyword) || contains(tail, keyword) || contains(edge.path("relation").asText(), keyword))
                    && fileContains(edge.path("file").asText(), file)) {
                ObjectNode row = edge.deepCopy();
                row.put("head_name", head).put("tail_name", tail);
                rows.add(row);
            }
        }
        return page(rows, offset, limit, "返回原始关系；需联合条件、例外与原文核验。");
    }

    @Tool(name = "lookup_clause", description = "直接检索保存的文档原文块，包括尚未抽成关系的内容；返回原文、物理页码、章节和block_id。为关键词检索，非语义RAG。")
    public QueryResult lookupClause(
            @ToolParam(description = "原文关键词，例如：随访频率") String keyword,
            @ToolParam(description = "限定文件名，可留空", required = false) String standard,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).lookupClause(keyword, standard, limit, offset); }
        List<JsonNode> matches = repo.records("blocks").stream()
                .filter(b -> contains(b.path("raw").asText(), keyword)
                        && fileContains(b.path("file").asText(), standard)).toList();
        return page(matches, offset, limit, "原文块按关键词匹配；版面或章节状态需一并检查。");
    }

    @Tool(name = "get_evidence", description = "按关系或引用中的block_id取得完整原文块。偏移start/end为Python字符索引，原文不重排、不改写。")
    public QueryResult getEvidence(
            @ToolParam(description = "原文块ID，例如关系中的 block_id") String block_id) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).getEvidence(block_id); }
        JsonNode block = repo.block(block_id);
        return page(block == null ? List.of() : List.of(block), 0, 1,
                "返回构建时保存的原文；请保留文件、物理页码、章节及核验状态。");
    }

    @Tool(name = "check_references", description = "检查标准引用的指南及版本，区分未入库、版本不匹配和已匹配；有同名文档不代表引用要求已补全。")
    public QueryResult checkReferences(
            @ToolParam(description = "来源文件或被引文件关键词，可留空", required = false) String keyword,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).checkReferences(keyword, limit, offset); }
        List<JsonNode> rows = new ArrayList<>();
        for (JsonNode edge : repo.records("edges")) {
            if (!"references".equals(edge.path("relation").asText())) { continue; }
            String target = name(edge.path("tailId").asText());
            if (!fileContains(edge.path("file").asText(), keyword) && !contains(target, keyword)) { continue; }
            ObjectNode row = edge.deepCopy();
            row.put("target_name", target);
            // 防止下游误把“文档在库里”解读为“条款已核实”。
            row.put("sufficient", false);
            row.put("message", switch (edge.path("resolution").asText()) {
                case "missing" -> "被引用的指定文件未入库，无法据此给出其具体要求。";
                case "version_mismatch" -> "同名候选文档与引用版本不同，需核验版本和具体条款。";
                case "resolved" -> "文件及版本已匹配，仍需查询和核对具体条款。";
                default -> "引用版本未确认，需进一步核验。";
            });
            rows.add(row);
        }
        return page(rows, offset, limit, "不要用另一版本静默替代标准实际引用的版本。");
    }

    @Tool(name = "query_candidates", description = "查询保留的待核验抽取，包括未解析药物语句、数值和重叠实体。候选不作为已确认知识使用；支持翻页，不删除原始记录。")
    public QueryResult queryCandidates(
            @ToolParam(description = "关键词，例如：转诊、ARNI") String keyword,
            @ToolParam(description = "集合名，可留空；edge_candidates/entity_candidates/extraction_candidates/threshold_candidates", required = false) String collection,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).queryCandidates(keyword, collection, limit, offset); }
        if (collection != null && !collection.isBlank() && !CANDIDATES.contains(collection)) {
            throw new IllegalArgumentException("未知候选集合: " + collection);
        }
        List<Object> rows = new ArrayList<>();
        for (String key : CANDIDATES) {
            if (collection != null && !collection.isBlank() && !collection.equals(key)) { continue; }
            for (JsonNode item : repo.records(key)) {
                if (contains(item.toString(), keyword)) {
                    rows.add(Map.of("collection", key, "record", item));
                }
            }
        }
        return page(rows, offset, limit, "这些是待核验候选，不能据此直接给出临床建议。");
    }

    @Tool(name = "traverse_relations", description = "沿业务关系做有界多跳检索，支持正反向查找且保留每条边的原始方向、条件和证据。结果只表示证据连通，不是已验证的医学推断。")
    public TraverseResult traverseRelations(
            @ToolParam(description = "起点名称或ID，例如：血压达标患者") String start_entity,
            @ToolParam(description = "限定关系，可留空", required = false) String relation,
            @ToolParam(description = "最大跳数，默认2，最多3", required = false) Integer hops,
            @ToolParam(description = "可选终点的准确名称或ID", required = false) String end_entity,
            @ToolParam(description = "最大路径数，默认10，最多50", required = false) Integer limit) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).traverseRelations(start_entity, relation, hops, end_entity, limit); }
        if (normalized(start_entity).isEmpty()) { throw new IllegalArgumentException("起点不能为空"); }
        int depth = hops == null ? 2 : Math.max(1, Math.min(3, hops));
        int cap = cap(limit);
        var queue = new ArrayDeque<Walk>();
        for (JsonNode seed : repo.seeds(start_entity)) {
            queue.add(new Walk(List.of(seed.path("id").asText()), List.of()));
        }
        List<EvidencePath> paths = new ArrayList<>();
        int expanded = 0;
        while (!queue.isEmpty() && expanded < 2000) {
            Walk walk = queue.removeFirst();
            expanded++;
            String current = walk.ids().getLast();
            for (JsonNode edge : repo.adjacent(current)) {
                String rel = edge.path("relation").asText();
                if (STRUCTURAL.contains(rel) || (relation != null && !relation.isBlank() && !relation.equals(rel))) { continue; }
                boolean forward = edge.path("headId").asText().equals(current);
                String next = edge.path(forward ? "tailId" : "headId").asText();
                if (walk.ids().contains(next)) { continue; }
                List<String> ids = new ArrayList<>(walk.ids());
                ids.add(next);
                List<PathStep> steps = new ArrayList<>(walk.steps());
                steps.add(new PathStep(name(current), name(next), forward, edge));
                boolean target = end_entity == null || end_entity.isBlank()
                        || normalized(name(next)).equals(normalized(end_entity))
                        || normalized(next).equals(normalized(end_entity));
                if (target) {
                    if (paths.size() == cap) { return traversal(paths, true); }
                    paths.add(new EvidencePath(ids.stream().map(this::name).toList(), List.copyOf(steps),
                            steps.size(), "evidence_path", false, "pending",
                            steps.stream().mapToDouble(s -> s.edge().path("confidence").asDouble(0)).min().orElse(0),
                            "minimum_edge_heuristic_not_calibrated"));
                }
                if (steps.size() < depth && (end_entity == null || end_entity.isBlank() || !target)) {
                    queue.addLast(new Walk(ids, steps));
                }
            }
        }
        return traversal(paths, !queue.isEmpty());
    }

    @Tool(name = "compare_threshold", description = "仅将数值与已结构化的数值约束作数学比较，保留适用条件和出处。需要匹配单位；命中不构成临床结论，未核验数字候选不会参与。")
    public QueryResult compareThreshold(
            @ToolParam(description = "主题关键词，例如：血压达标患者随访间隔") String subject,
            @ToolParam(description = "要比较的数值") Double value,
            @ToolParam(description = "单位，必须与记录相同，例如：月") String unit) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).compareThreshold(subject, value, unit); }
        if (value == null || !Double.isFinite(value) || unit == null || unit.isBlank()) {
            throw new IllegalArgumentException("需要有限数值和明确单位");
        }
        List<Object> rows = new ArrayList<>();
        for (JsonNode t : repo.records("thresholds")) {
            if (!contains(t.path("subject").asText(), subject) || !normalized(t.path("unit").asText()).equals(normalized(unit))) { continue; }
            double expected = t.path("value").asDouble();
            Boolean matches = switch (t.path("operator").asText()) {
                case "<" -> value < expected;
                case "<=", "≤" -> value <= expected;
                case ">" -> value > expected;
                case ">=", "≥" -> value >= expected;
                case "==", "=" -> value == expected;
                default -> null;
            };
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("constraint", t);
            row.put("actual", value);
            row.put("matches", matches);
            rows.add(row);
        }
        return page(rows, 0, 50, "matches 仅表示数学比较；患者条件、管理目的和条款仍需核验，不执行单位换算。");
    }

    @Tool(name = "resolve_regimen", description = "按完整人群组合两跳证据：人群←首选方案→择一/必要药物成分。只连接同regimen_group并核对代号定义，保留限制和排版疑点，不是个体处方。")
    public QueryResult resolveRegimen(@ToolParam(description = "完整人群，例如高血压合并糖尿病患者") String population) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).resolveRegimen(population); }
        return page(new DecisionSupport(repo).resolveRegimen(population), 0, 50,
                "已组合适用人群与代号定义两跳；仍待核验，不自动产生个体处方。");
    }

    @Tool(name = "evaluate_blood_pressure", description = "对收缩压/舒张压进行OR组合边界比较，并检查诊室、规范测量、4周内非同日3次等条款前提。单次140/90只达到边界，不自动确诊。不得猜测用户未提供的测量条件。")
    public Map<String, Object> evaluateBloodPressure(
            @ToolParam(description = "收缩压数值") Double systolic,
            @ToolParam(description = "舒张压数值") Double diastolic,
            @ToolParam(description = "单位，目前只支持mmHg") String unit,
            @ToolParam(description = "office/home/ambulatory/unknown；用户未说明时传unknown", required = false) String measurement_method,
            @ToolParam(description = "是否规范测量，用户未说明时不填", required = false) Boolean standardized,
            @ToolParam(description = "可选复测记录JSON数组，每项date为YYYY-MM-DD、sbp/dbp为数值；不得编造复测记录", required = false) String readings_json) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).evaluateBloodPressure(systolic, diastolic, unit, measurement_method, standardized, readings_json); }
        Map<String, Object> result = new LinkedHashMap<>(new DecisionSupport(repo).evaluateBp(systolic, diastolic, unit, measurement_method, standardized, readings_json));
        result.put("knowledge_version", repo.version());
        return result;
    }

    @Tool(name = "detect_conflicts", description = "比较已结构化数值差异及药物推荐作用域。区分配备vs一线初始用药、同范围正反推荐与条件不足；均保留原文，不能自动裁决医学冲突。")
    public QueryResult detectConflicts(
            @ToolParam(description = "主题关键词，可留空", required = false) String subject,
            @ToolParam(description = "返回条数，默认10，最多50", required = false) Integer limit,
            @ToolParam(description = "翻页起点，默认0", required = false) Integer offset) {
        GraphRepository snapshot = repo.snapshot();
        if (snapshot != repo) { return new KgToolsService(snapshot).detectConflicts(subject, limit, offset); }
        Map<List<JsonNode>, List<JsonNode>> groups = new LinkedHashMap<>();
        for (JsonNode t : repo.records("thresholds")) {
            if (contains(t.path("subject").asText(), subject)) {
                var key = List.of(t.path("subject"), t.path("indicator"), t.path("unit"), t.path("context"), t.path("comparison_scope"));
                groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(t);
            }
        }
        List<Object> rows = new ArrayList<>();
        for (List<JsonNode> items : groups.values()) {
            Set<String> signatures = new HashSet<>(), files = new HashSet<>();
            for (JsonNode t : items) {
                signatures.add(t.path("operator").asText() + ":" + t.path("value").asDouble());
                files.add(t.path("file").asText());
            }
            if (signatures.size() > 1) {
                rows.add(Map.of("status", "needs_review", "items", items,
                        "scope", files.size() > 1 ? "cross_document" : "within_document",
                        "verification", "pending", "confidence", 0.4,
                        "confidence_basis", "rule_heuristic_not_calibrated",
                        "reason", "数值差异不等于医学冲突；需核对适用人群、目的、条件和版本。"));
            }
        }
        rows.addAll(new DecisionSupport(repo).drugComparisons(subject));
        return page(rows, offset, limit, "仅检查已覆盖数值和关系模式；零条结果不表示全文一致，potential_conflict仍待审核。");
    }

    private String name(String id) {
        JsonNode node = repo.node(id);
        return node == null ? id : node.path("name").asText();
    }

    private static int cap(Integer limit) { return limit == null ? 10 : Math.max(1, Math.min(50, limit)); }

    private QueryResult page(List<?> rows, Integer offset, Integer limit, String message) {
        int begin = Math.min(rows.size(), offset == null ? 0 : Math.max(0, offset));
        int end = Math.min(rows.size(), begin + cap(limit));
        String note = rows.isEmpty() ? "未命中；不能据此判断原文不存在相关内容。" : message;
        return new QueryResult(List.copyOf(rows.subList(begin, end)), rows.size(), begin, end < rows.size(),
                false, "pending", note, repo.version());
    }

    private TraverseResult traversal(List<EvidencePath> paths, boolean truncated) {
        return new TraverseResult(List.copyOf(paths), truncated, false, "pending",
                paths.isEmpty() ? "没有匹配路径；不代表原文没有相关知识。"
                        : "仅表示证据图连通；适用条件、例外、联合方案及临床结论尚未核验。", repo.version());
    }

    private record Walk(List<String> ids, List<PathStep> steps) { }
}
