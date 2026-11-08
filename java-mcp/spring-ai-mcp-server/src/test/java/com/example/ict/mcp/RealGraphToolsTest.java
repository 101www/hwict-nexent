package com.example.ict.mcp;

import com.example.ict.mcp.model.GraphModel.QueryResult;
import com.example.ict.mcp.repo.GraphRepository;
import com.example.ict.mcp.tools.KgToolsService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class RealGraphToolsTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private JsonNode graph;
    private KgToolsService tools;
    @TempDir Path temp;

    @BeforeEach
    void loadActualGraph() throws Exception {
        Path path = Path.of("../../data/processed/graph.json").toRealPath();
        graph = mapper.readTree(Files.readString(path));
        tools = new KgToolsService(new GraphRepository(mapper, path.toString()));
    }

    private JsonNode json(Object value) { return mapper.valueToTree(value); }

    @Test
    void loadsActualSnapshotRatherThanSeedData() {
        var status = tools.graphStatus();
        assertEquals("real_graph_snapshot", status.get("mode"));
        assertEquals(graph.path("nodes").size(), status.get("nodes"));
        assertEquals(graph.path("edges").size(), status.get("edges"));
        assertEquals(3, json(status).path("meta").path("documents").size());
    }

    @Test
    void followupRelationsKeepBothDocumentsAndExactSourceRecords() {
        QueryResult result = tools.queryRelations("followUpEvery", null, 50, 0);
        assertEquals(4, result.total());
        assertFalse(result.sufficient());
        var rows = json(result).path("items");
        var files = new java.util.HashSet<String>();
        for (JsonNode row : rows) {
            files.add(row.path("file").asText());
            assertEquals("pending", row.path("verification").asText());
            ObjectNode original = ((ObjectNode) row).deepCopy();
            original.remove(List.of("head_name", "tail_name"));
            boolean found = false;
            for (JsonNode edge : graph.path("edges")) { found |= original.equals(edge); }
            assertTrue(found, "条件、出处、置信分及扩展字段必须完整保留");
        }
        assertEquals(2, files.size());
    }

    @Test
    void referencesReportVersionMismatchAndCorrectBackMatterSection() {
        var result = tools.checkReferences("WS-T872", 50, 0);
        assertEquals(4, result.total());
        for (JsonNode row : json(result).path("items")) {
            assertEquals("version_mismatch", row.path("resolution").asText());
            assertEquals("2021", row.path("requested_year").asText());
            assertEquals("REFERENCES", row.path("version_evidence").path("section").asText());
            assertFalse(row.path("sufficient").asBoolean());
        }
    }

    @Test
    void standardNumberFormattingAndUnicodeWhitespaceDoNotCauseFalseMisses() {
        assertEquals(4, tools.checkReferences("WS/T 872", 50, 0).total());
        assertEquals(4, tools.checkReferences("WS/T 872—2025", 50, 0).total());
        assertEquals(2, tools.queryRelations("followUpEvery", "WS/T 872—2025", 50, 0).total());
        assertTrue(tools.lookupClause("参考文献", "WS/T 872—2025", 10, 0).total() > 0);
        assertTrue(GraphRepository.contains("随访\u2003频率", "随访频率"));
    }

    @Test
    void aliasesFindTheSameNodeAndLargeEvidenceListsAreExplicitlyTruncated() {
        var result = tools.findEntities("顽固性高血压", "Disease", 10, 0);
        assertEquals("难治性高血压", json(result).path("items").get(0).path("name").asText());
        JsonNode frequent = json(tools.findEntities("高血压", "Disease", 50, 0)).path("items");
        assertTrue(java.util.stream.StreamSupport.stream(frequent.spliterator(), false)
                .anyMatch(n -> n.path("evidences_truncated").asBoolean() && n.path("evidence_count").asInt() > 3));
    }

    @Test
    void getEvidenceReturnsUnmodifiedOriginalBlock() {
        JsonNode edge = json(tools.queryRelations("followUpEvery", null, 1, 0)).path("items").get(0);
        JsonNode block = json(tools.getEvidence(edge.path("block_id").asText())).path("items").get(0);
        JsonNode original = null;
        for (JsonNode b : graph.path("blocks")) {
            if (b.path("id").equals(block.path("id"))) { original = b; }
        }
        assertEquals(original, block);
        int left = edge.path("start").asInt(), right = edge.path("end").asInt();
        String raw = block.path("raw").asText();
        assertEquals(edge.path("evidence").asText(), raw.substring(
                raw.offsetByCodePoints(0, left), raw.offsetByCodePoints(0, right)));
    }

    @Test
    void originalTextSearchSupportsLineBreaksAndFileFiltering() {
        var result = tools.lookupClause("每3个月随访1次", "国家基层", 10, 0);
        assertTrue(result.total() > 0);
        for (JsonNode block : json(result).path("items")) {
            assertTrue(block.path("file").asText().contains("国家基层"));
            assertFalse(block.path("raw").asText().isBlank());
        }
    }

    @Test
    void inverseTraversalPreservesEdgeDirectionAndNeverClaimsSufficiency() {
        var result = tools.traverseRelations("随访", "followUpEvery", 1, "血压达标患者", 10);
        assertEquals(2, result.paths().size());
        assertFalse(result.sufficient());
        for (var path : result.paths()) {
            assertFalse(path.sufficient());
            assertEquals("evidence_path", path.kind());
            assertFalse(path.steps().getFirst().forward());
            assertEquals("N-血压达标患者", path.steps().getFirst().edge().path("headId").asText());
        }
    }

    @Test
    void traversalIsBoundedAndMarksTruncation() {
        var result = tools.traverseRelations("随访", null, 1, null, 1);
        assertEquals(1, result.paths().size());
        assertTrue(result.truncated());
        assertFalse(result.sufficient());
        assertTrue(tools.traverseRelations("不存在的节点", null, 2, null, 10).paths().isEmpty());
    }

    @Test
    void candidatePaginationRetainsAllOriginalRecords() {
        var first = tools.queryCandidates("", "extraction_candidates", 2, 0);
        var second = tools.queryCandidates("", "extraction_candidates", 2, 2);
        assertEquals(graph.path("extraction_candidates").size(), first.total());
        assertTrue(first.truncated());
        assertEquals(graph.path("extraction_candidates").get(0), json(first).path("items").get(0).path("record"));
        assertEquals(graph.path("extraction_candidates").get(2), json(second).path("items").get(0).path("record"));
        assertThrows(IllegalArgumentException.class, () -> tools.queryCandidates("", "unknown", 10, 0));
    }

    @Test
    void thresholdComparisonRequiresUnitAndNeverUsesNumericCandidates() {
        var result = tools.compareThreshold("血压达标患者", 4.0, "月");
        assertEquals(2, result.total());
        assertFalse(result.sufficient());
        for (JsonNode row : json(result).path("items")) { assertFalse(row.path("matches").asBoolean()); }
        assertEquals(0, tools.compareThreshold("血压达标患者", 4.0, "天").total());
        assertEquals(2, tools.compareThreshold("", 140.0, "mmHg").total());
        assertThrows(IllegalArgumentException.class, () -> tools.compareThreshold("", 1.0, null));
        assertThrows(IllegalArgumentException.class, () -> tools.compareThreshold("", Double.NaN, "月"));
    }

    @Test
    void missingOrInvalidGraphFailsInsteadOfFallingBackOrDeletingAssertions() throws Exception {
        assertThrows(java.io.IOException.class, () -> new GraphRepository(mapper, temp.resolve("absent.json").toString()));
        ObjectNode invalid = graph.deepCopy();
        ((ObjectNode) invalid.path("edges").get(0)).put("headId", "unknown");
        Path file = temp.resolve("invalid.json");
        mapper.writeValue(file.toFile(), invalid);
        assertThrows(java.io.IOException.class, () -> new GraphRepository(mapper, file.toString()));
        assertEquals(invalid, mapper.readTree(file.toFile()));
    }

    @Test
    void numericDifferencesRemainPendingAndDifferentUnitsStaySeparate() throws Exception {
        ObjectNode custom = graph.deepCopy();
        var thresholds = mapper.createArrayNode();
        ObjectNode first = ((ObjectNode) graph.path("thresholds").get(0)).deepCopy();
        first.put("value", 1);
        ObjectNode second = first.deepCopy().put("value", 2).put("file", "another.txt");
        ObjectNode otherUnit = first.deepCopy().put("value", 30).put("unit", "天");
        thresholds.add(first).add(second).add(otherUnit);
        custom.set("thresholds", thresholds);
        Path file = temp.resolve("differences.json");
        mapper.writeValue(file.toFile(), custom);
        var customTools = new KgToolsService(new GraphRepository(mapper, file.toString()));
        var result = customTools.detectConflicts(first.path("subject").asText(), 10, 0);
        assertEquals(1, result.total());
        JsonNode row = json(result).path("items").get(0);
        assertEquals("needs_review", row.path("status").asText());
        assertEquals("pending", row.path("verification").asText());
        assertEquals(2, row.path("items").size());
    }

    @Test
    void dmCompositionHasTwoIndependentEvidenceSectionsAndOneOfSelection() {
        JsonNode result = json(tools.resolveRegimen("高血压合并糖尿病患者"));
        assertEquals(1, result.path("total").asInt());
        JsonNode row = result.path("items").get(0);
        assertEquals("one_of", row.path("components").get(0).path("selection").asText());
        assertEquals(2, row.path("paths").size());
        for (JsonNode path : row.path("paths")) {
            assertEquals(2, path.path("hops").asInt());
            JsonNode first = path.path("steps").get(0).path("edge");
            JsonNode second = path.path("steps").get(1).path("edge");
            assertEquals(first.path("regimen_group"), second.path("regimen_group"));
            assertEquals("5.4.2", second.path("section").asText());
            assertEquals("needs_layout_review", first.path("section_status").asText());
            assertFalse(path.path("steps").get(0).path("forward").asBoolean());
        }
        assertEquals(0, tools.resolveRegimen("高血压合并未知疾病患者").total());
        assertFalse(result.path("sufficient").asBoolean());
    }

    @Test
    void bpUsesInclusiveOrAndNeverDiagnosesFromOneReading() {
        for (double[] pair : new double[][] {{140,90}, {140,89}, {139,90}}) {
            JsonNode row = json(tools.evaluateBloodPressure(pair[0], pair[1], "mmHg", "unknown", null, null));
            assertTrue(row.path("reference_boundary_reached").asBoolean());
            assertEquals("insufficient_or_unmet_conditions", row.path("protocol_status").asText());
            assertFalse(row.path("sufficient").asBoolean());
        }
        assertFalse(json(tools.evaluateBloodPressure(139.0,89.0,"mmHg","office",true,null))
                .path("reference_boundary_reached").asBoolean());
        JsonNode home = json(tools.evaluateBloodPressure(140.0,90.0,"mmHg","home",true,null));
        assertTrue(home.path("reference_boundary_reached").isNull());
        assertEquals("not_applicable", home.path("protocol_status").asText());
        assertThrows(IllegalArgumentException.class, () -> tools.evaluateBloodPressure(140.0,90.0,"kPa","office",true,null));
        assertThrows(IllegalArgumentException.class, () -> tools.evaluateBloodPressure(Double.NaN,90.0,"mmHg",null,null,null));
    }

    private String visits(String middle, String last, double sbp) {
        return "[{\"date\":\"2026-10-01\",\"sbp\":140,\"dbp\":85},{\"date\":\"" + middle
                + "\",\"sbp\":" + sbp + ",\"dbp\":85},{\"date\":\"" + last + "\",\"sbp\":139,\"dbp\":90}]";
    }

    @Test
    void bpChecksSeparateDatesWindowStandardizationAndEveryVisit() {
        String valid = visits("2026-10-05", "2026-10-29", 145);
        JsonNode passed = json(tools.evaluateBloodPressure(139.0,90.0,"mmHg","office",true,valid));
        assertEquals("reported_conditions_match_pending_rule", passed.path("protocol_status").asText());
        assertFalse(passed.path("sufficient").asBoolean());
        for (String bad : List.of(visits("2026-10-01","2026-10-29",145),
                visits("2026-10-05","2026-10-30",145), visits("2026-10-05","2026-10-29",139))) {
            assertEquals("insufficient_or_unmet_conditions", json(tools.evaluateBloodPressure(139.0,90.0,"mmHg","office",true,bad))
                    .path("protocol_status").asText());
        }
        assertEquals("insufficient_or_unmet_conditions", json(tools.evaluateBloodPressure(139.0,90.0,"mmHg","office",null,valid))
                .path("protocol_status").asText());
        assertThrows(IllegalArgumentException.class, () -> tools.evaluateBloodPressure(140.0,90.0,"mmHg","office",true,"bad json"));
    }

    @Test
    void stockAndInitialTherapyHaveDifferentPurposesWithBothSourcesReturned() {
        JsonNode result = json(tools.detectConflicts("β受体阻滞剂", 50, 0));
        assertEquals(2, result.path("total").asInt());
        for (JsonNode row : result.path("items")) {
            assertEquals("not_conflicting_different_purpose", row.path("status").asText());
            assertEquals(2, row.path("items").size());
            assertEquals("pending", row.path("verification").asText());
            assertTrue(java.util.stream.StreamSupport.stream(row.path("source_documents").spliterator(), false)
                    .anyMatch(d -> "clinical".equals(d.path("profile").asText()) && "2024".equals(d.path("year").asText())));
        }
    }

    @Test
    void syntheticSameScopeOppositesAreReviewCandidatesAndMissingScopeIsNotExonerated() throws Exception {
        // 合成夹具只验证分支，绝不写入真实图谱充当指南冲突。
        ObjectNode fixture = graph.deepCopy();
        JsonNode negative = tools.queryRelations("excludedFromFirstLine", null, 10, 0).items().stream()
                .map(mapper::valueToTree).map(n -> (JsonNode) n).findFirst().orElseThrow();
        ObjectNode positive = negative.deepCopy();
        positive.put("id", "SYNTHETIC-POSITIVE").put("relation", "firstLineFor");
        fixture.withArray("edges").add(positive);
        Path file = temp.resolve("synthetic-only.json");
        mapper.writeValue(file.toFile(), fixture);
        JsonNode result = json(new KgToolsService(new GraphRepository(mapper,file.toString())).detectConflicts("β受体阻滞剂",50,0));
        assertTrue(result.path("items").findValuesAsText("status").contains("potential_conflict_same_scope"));
        positive.remove("scope");
        mapper.writeValue(file.toFile(), fixture);
        JsonNode incomplete = json(new KgToolsService(new GraphRepository(mapper,file.toString())).detectConflicts("β受体阻滞剂",50,0));
        assertTrue(incomplete.path("items").findValuesAsText("status").contains("scope_or_condition_requires_review"));
    }
}
