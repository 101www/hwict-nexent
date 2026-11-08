package com.example.ict.mcp;

import com.example.ict.mcp.repo.GraphRepository;
import com.example.ict.mcp.tools.KgToolsService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

/** 合成版本元数据只用于验证切版；不生成真实审核或发布记录。 */
class LiveGraphVersionTest {
    Path root;
    @BeforeEach void workspaceTemp() throws Exception {
        root = Files.createTempDirectory(Path.of("target").toAbsolutePath(), "live-graph-test-");
    }
    @AfterEach void cleanFixture() throws Exception {
        if (root != null) {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) { Files.delete(path); }
            }
        }
    }
    final ObjectMapper mapper = new ObjectMapper();

    void release(String id, String kind, String actor) throws Exception {
        Path folder = root.resolve("releases").resolve(id);
        Files.createDirectories(folder);
        ObjectNode graph = (ObjectNode) mapper.readTree(Path.of("../../data/processed/graph.json").toFile());
        graph.withObject("meta").withObject("evolution").put("release_id", id);
        if (id.equals("R-new")) {
            graph.withArray("nodes").addObject().put("id", "SYNTHETIC-new").put("name", "版本测试新增实体")
                    .put("type", "Disease").put("verification", "pending").put("confidence", 0.5);
        }
        Path file = folder.resolve("graph.json");
        mapper.writeValue(file.toFile(), graph);
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
        mapper.writeValue(folder.resolve("manifest.json").toFile(), Map.of("kind", kind,
                "files", Map.of("graph.json", hash), "review", Map.of("actor_kind", actor, "decision", "approve")));
    }

    void point(String id) throws Exception {
        mapper.writeValue(root.resolve("state.json").toFile(), Map.of("current", id,
                "releases", List.of("R-old", "R-new")));
    }

    GraphRepository live() throws Exception {
        release("R-old", "imported_baseline", "none");
        release("R-new", "release", "human");
        point("R-old");
        return new GraphRepository(mapper, "", root.toString());
    }

    @Test void sameServiceFollowsPublishAndRollbackWhilePinnedRequestStaysConsistent() throws Exception {
        GraphRepository repository = live();
        KgToolsService tools = new KgToolsService(repository);
        GraphRepository pinned = repository.snapshot();
        assertEquals(0, tools.findEntities("版本测试新增实体", null, 10, 0).total());
        point("R-new");
        assertEquals(1, tools.findEntities("版本测试新增实体", null, 10, 0).total());
        assertEquals("R-new", tools.resolveRegimen("高血压合并糖尿病患者").knowledge_version().get("release_id"));
        assertEquals("R-old", pinned.version().get("release_id"));
        assertEquals(0, new KgToolsService(pinned).findEntities("版本测试新增实体", null, 10, 0).total());
        point("R-old");
        assertEquals(0, tools.findEntities("版本测试新增实体", null, 10, 0).total());
    }

    @Test void everyToolReportsActualVersionAfterSwitch() throws Exception {
        KgToolsService t = new KgToolsService(live());
        point("R-new");
        List<Object> results = List.of(t.graphStatus(), t.findEntities("", null, 1, 0),
                t.queryRelations("", null, 1, 0), t.lookupClause("随访", null, 1, 0), t.getEvidence("absent"),
                t.checkReferences("", 1, 0), t.queryCandidates("", null, 1, 0),
                t.traverseRelations("随访", null, 1, null, 1), t.compareThreshold("", 140.0, "mmHg"),
                t.resolveRegimen("高血压合并糖尿病患者"),
                t.evaluateBloodPressure(140.0, 90.0, "mmHg", "unknown", null, null), t.detectConflicts("", 1, 0));
        assertEquals(12, results.size());
        for (Object result : results) {
            JsonNode json = mapper.valueToTree(result);
            assertEquals("R-new", json.path("knowledge_version").path("release_id").asText());
            assertEquals("pending", json.path("knowledge_version").path("verification").asText());
        }
    }

    @Test void corruptedPublishedFileFailsRatherThanServingStaleKnowledge() throws Exception {
        KgToolsService t = new KgToolsService(live());
        Files.writeString(root.resolve("releases/R-old/graph.json"), "{}");
        assertThrows(IllegalStateException.class, t::graphStatus);
    }

    @Test void unpublishedOrUnlistedPointerIsRejected() throws Exception {
        GraphRepository repo = live();
        point("P-pending");
        assertThrows(IllegalStateException.class, repo::snapshot);
        release("R-new", "proposal", "human");
        point("R-new");
        assertThrows(IllegalStateException.class, repo::snapshot);
    }

    @Test void automatedReviewCannotEnterProductionAndReviewMustApprove() throws Exception {
        GraphRepository repo = live();
        release("R-new", "release", "automated_test");
        point("R-new");
        assertThrows(IllegalStateException.class, repo::snapshot);
        Path manifest = root.resolve("releases/R-new/manifest.json");
        ObjectNode json = (ObjectNode) mapper.readTree(manifest.toFile());
        json.withObject("review").put("actor_kind", "human").put("decision", "defer");
        mapper.writeValue(manifest.toFile(), json);
        assertThrows(IllegalStateException.class, repo::snapshot);
    }

    @Test void explicitFileAndStoreCannotCompete() throws Exception {
        live();
        assertThrows(java.io.IOException.class, () -> new GraphRepository(mapper, "some-file.json", root.toString()));
    }
}
