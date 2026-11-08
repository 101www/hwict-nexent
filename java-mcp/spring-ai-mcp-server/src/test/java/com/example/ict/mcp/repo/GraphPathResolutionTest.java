package com.example.ict.mcp.repo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class GraphPathResolutionTest {
    @TempDir Path temp;

    private Path graphAt(Path project) throws IOException {
        Path graph = project.resolve("data/processed/graph.json");
        Files.createDirectories(graph.getParent());
        return Files.writeString(graph, "{}");
    }

    @Test
    void outerWorkspaceLaunchFindsGraphFromClassesLocation() throws Exception {
        Path project = temp.resolve("工作区/领域项目");
        Path graph = graphAt(project);
        Path classes = Files.createDirectories(project.resolve("java-mcp/server/target/classes"));
        assertEquals(graph, GraphRepository.resolvePath("", temp.resolve("工作区"), classes));
    }

    @Test
    void unrelatedWorkingDirectoryFindsGraphFromJarLocation() throws Exception {
        Path project = temp.resolve("project");
        Path graph = graphAt(project);
        Path jar = project.resolve("java-mcp/server/target/server.jar");
        Files.createDirectories(jar.getParent());
        Files.writeString(jar, "fixture");
        assertEquals(graph, GraphRepository.resolvePath("", temp, jar));
    }

    @Test
    void workingDirectoryGraphKeepsPriorityOverModuleGraph() throws Exception {
        Path workingGraph = graphAt(temp.resolve("selected"));
        Path moduleGraph = graphAt(temp.resolve("module"));
        Path classes = Files.createDirectories(moduleGraph.getParent().getParent().getParent().resolve("target/classes"));
        assertEquals(workingGraph, GraphRepository.resolvePath("", temp.resolve("selected/subdir"), classes));
    }

    @Test
    void explicitPathWinsAndMissingExplicitPathNeverFallsBack() throws Exception {
        Path graph = graphAt(temp);
        Path explicit = Files.writeString(temp.resolve("chosen.json"), "{}");
        assertEquals(explicit, GraphRepository.resolvePath("chosen.json", temp, temp));
        assertThrows(IOException.class, () -> GraphRepository.resolvePath("missing.json", temp, temp));
        assertTrue(Files.exists(graph));
    }

    @Test
    void failureReportsLaunchLocationsWithoutSearchingOtherChildProjects() throws Exception {
        graphAt(temp.resolve("unrelated-child-project"));
        Path classes = Files.createDirectories(temp.resolve("module/target/classes"));
        IOException error = assertThrows(IOException.class,
                () -> GraphRepository.resolvePath("", temp, classes));
        assertTrue(error.getMessage().contains(temp.toString()));
        assertTrue(error.getMessage().contains(classes.toString()));
        assertTrue(error.getMessage().contains("KG_GRAPH_PATH"));
    }

    @Test
    void defaultStartupPrefersProductionStoreAndDoesNotTreatHistoryAsProduction() throws Exception {
        Path graph = graphAt(temp);
        assertEquals("", GraphRepository.defaultStore(graph));
        Files.createDirectories(temp.resolve("data/evolution/workbench"));
        assertEquals("", GraphRepository.defaultStore(graph));
        Path production = Files.createDirectories(temp.resolve("data/evolution/production"));
        assertEquals(production.toString(), GraphRepository.defaultStore(graph));
        // 即使正式仓库尚缺state.json，也返回它，交由加载层明确报错，不能悄悄选回旧图谱。
        assertFalse(Files.exists(production.resolve("state.json")));
    }
}
