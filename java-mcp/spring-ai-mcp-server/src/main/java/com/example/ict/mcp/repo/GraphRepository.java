package com.example.ict.mcp.repo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.system.ApplicationHome;
import org.springframework.stereotype.Repository;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.security.MessageDigest;
import java.util.HexFormat;

/** 固定文件模式或发布仓库模式。每次工具调用先取得一个完整快照，单次调用不混用版本。 */
@Repository
public class GraphRepository {
    private static final Logger LOG = LoggerFactory.getLogger(GraphRepository.class);
    private final Path source;
    private final JsonNode graph;
    private final Map<String, JsonNode> nodes = new LinkedHashMap<>();
    private final Map<String, JsonNode> blocks = new LinkedHashMap<>();
    private final Map<String, List<JsonNode>> adjacency = new LinkedHashMap<>();
    private Path store;
    private Path followedStore;
    private final ObjectMapper mapper;
    private String manifestHash = "";
    private String graphHash;
    private GraphRepository currentSnapshot;

    public GraphRepository(ObjectMapper mapper, String configuredPath) throws IOException {
        this.mapper = mapper;
        source = resolvePath(configuredPath);
        byte[] payload = Files.readAllBytes(source);
        graphHash = sha256(payload);
        graph = mapper.readTree(payload);
        if (graph == null || !graph.path("meta").isObject()) {
            throw new IOException("图谱缺少 meta 对象: " + source);
        }
        for (String key : List.of("nodes", "edges", "thresholds", "blocks")) {
            if (!graph.path(key).isArray()) {
                throw new IOException("图谱缺少数组 " + key + ": " + source);
            }
        }
        index(graph.path("nodes"), nodes, "node");
        index(graph.path("blocks"), blocks, "block");
        for (JsonNode edge : graph.path("edges")) {
            String head = edge.path("headId").asText(), tail = edge.path("tailId").asText();
            if (!nodes.containsKey(head) || !nodes.containsKey(tail)) {
                // 不删除异常断言，也不默默跳过。候选集合允许保留未解决端点。
                throw new IOException("关系端点不存在: " + edge.path("id").asText());
            }
            adjacency.computeIfAbsent(head, ignored -> new ArrayList<>()).add(edge);
            if (!head.equals(tail)) {
                adjacency.computeIfAbsent(tail, ignored -> new ArrayList<>()).add(edge);
            }
        }
        LOG.info("Loaded real graph: {} (nodes={}, edges={}, blocks={}); no demo fallback",
                source, nodes.size(), graph.path("edges").size(), blocks.size());
    }

    @Autowired
    public GraphRepository(ObjectMapper mapper, @Value("${kg.graph-path:}") String configuredPath,
                           @Value("${kg.evolution-store:}") String configuredStore) throws IOException {
        this(mapper, selectSource(configuredPath, configuredStore));
    }

    private GraphRepository(ObjectMapper mapper, SourceSelection selection) throws IOException {
        this(mapper, initialPath(mapper, selection.graphPath(), selection.storePath()));
        if (selection.storePath() != null && !selection.storePath().isBlank()) {
            store = Path.of(selection.storePath()).toAbsolutePath().normalize();
            LOG.info("Following published knowledge store: {}", store);
            snapshot(); // 启动时也验证发布清单；坏指针不能退回旧文件。
        }
    }

    private record SourceSelection(String graphPath, String storePath) { }

    private static SourceSelection selectSource(String graphPath, String configuredStore) throws IOException {
        if ((graphPath != null && !graphPath.isBlank()) || (configuredStore != null && !configuredStore.isBlank())) {
            return new SourceSelection(graphPath, configuredStore);
        }
        Path defaultGraph = resolvePath("");
        String detected = defaultStore(defaultGraph);
        return new SourceSelection(detected.isBlank() ? defaultGraph.toString() : "", detected);
    }

    /** IDEA、Maven、JAR默认启动使用同一正式仓库；已有仓库损坏时让加载报错，不能静默退回旧图。 */
    static String defaultStore(Path defaultGraph) {
        Path candidate = defaultGraph.toAbsolutePath().normalize().getParent().getParent().resolve("evolution/production");
        return Files.exists(candidate) ? candidate.toString() : "";
    }

    private static String initialPath(ObjectMapper mapper, String graphPath, String storePath) throws IOException {
        if (storePath == null || storePath.isBlank()) { return graphPath; }
        if (graphPath != null && !graphPath.isBlank()) {
            throw new IOException("kg.graph-path和kg.evolution-store不能同时设置，避免数据源歧义");
        }
        Path root = Path.of(storePath).toAbsolutePath().normalize();
        JsonNode state = mapper.readTree(Files.readAllBytes(root.resolve("state.json")));
        return releasePath(root, state).resolve("graph.json").toString();
    }

    private static Path releasePath(Path root, JsonNode state) throws IOException {
        String id = state.path("current").asText();
        if (!id.matches("[A-Za-z0-9_-]+")) { throw new IOException("当前知识版本ID无效"); }
        boolean listed = false;
        for (JsonNode release : state.path("releases")) { listed |= id.equals(release.asText()); }
        if (!listed) { throw new IOException("当前指针不是已发布版本"); }
        Path folder = root.resolve("releases").resolve(id).normalize();
        if (!folder.toRealPath().startsWith(root.toRealPath())) { throw new IOException("版本路径越出仓库"); }
        return folder;
    }

    /** 每次工具调用只调用一次，后续查询委托给返回的固定快照。发布或回滚下次调用生效。 */
    public synchronized GraphRepository snapshot() {
        if (store == null) { return this; }
        try {
            JsonNode state = mapper.readTree(Files.readAllBytes(store.resolve("state.json")));
            Path folder = releasePath(store, state);
            byte[] manifestBytes = Files.readAllBytes(folder.resolve("manifest.json"));
            JsonNode manifest = mapper.readTree(manifestBytes);
            String nextManifestHash = sha256(manifestBytes);
            String kind = manifest.path("kind").asText();
            if (!List.of("imported_baseline", "release").contains(kind)) { throw new IOException("不能加载未发布提案"); }
            if ("release".equals(kind) && !"approve".equals(manifest.path("review").path("decision").asText())) {
                throw new IOException("发布版本缺少批准记录");
            }
            if ("release".equals(kind) && !"human".equals(manifest.path("review").path("actor_kind").asText())
                    && !Boolean.getBoolean("kg.allowTestReleases")) {
                throw new IOException("正式服务不能加载自动测试审核版本");
            }
            Path file = folder.resolve("graph.json");
            String expected = manifest.path("files").path("graph.json").asText();
            if (expected.isBlank() || !sha256(Files.readAllBytes(file)).equals(expected)) {
                throw new IOException("已发布图谱与清单哈希不一致");
            }
            if (currentSnapshot == null || !manifestHash.equals(nextManifestHash)
                    || !currentSnapshot.source.equals(file)) {
                var names = manifest.path("files").fieldNames();
                while (names.hasNext()) {
                    String name = names.next();
                    if (name.contains("/") || name.contains("\\") || name.equals("..")) {
                        throw new IOException("快照清单路径无效");
                    }
                    Path artifact = folder.resolve(name);
                    if (!artifact.toRealPath().startsWith(folder.toRealPath())
                            || !sha256(Files.readAllBytes(artifact)).equals(manifest.path("files").path(name).asText())) {
                        throw new IOException("发布快照校验失败: " + name);
                    }
                }
                GraphRepository loaded = new GraphRepository(mapper, file.toString());
                loaded.followedStore = store;
                if (!loaded.graphHash.equals(expected)
                        || !loaded.meta().path("evolution").path("release_id").asText().equals(state.path("current").asText())) {
                    throw new IOException("发布版本标识不一致");
                }
                currentSnapshot = loaded;
                manifestHash = nextManifestHash;
            }
            return currentSnapshot;
        } catch (IOException | RuntimeException exc) {
            throw new IllegalStateException("知识版本加载失败；未使用旧版本冒充当前结果: " + exc.getMessage(), exc);
        }
    }

    public Map<String, Object> version() {
        return Map.of("release_id", meta().path("evolution").path("release_id").asText("unversioned"),
                "ontology_version", meta().path("ontology_version").asText(),
                "graph_sha256", graphHash, "built_at", meta().path("built_at").asText(),
                "verification", "pending", "load_mode", followedStore == null ? "fixed_file" : "published_store",
                "version_store", followedStore == null ? "" : followedStore.toString());
    }

    private static String sha256(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (java.security.NoSuchAlgorithmException exc) { throw new IllegalStateException(exc); }
    }

    private static Path resolvePath(String configured) throws IOException {
        // Spring Boot处理普通classes目录以及可执行JAR的嵌套URL，避免手工解析路径。
        Path codeLocation = new ApplicationHome(GraphRepository.class).getDir().toPath();
        return resolvePath(configured, Path.of("").toAbsolutePath(), codeLocation);
    }

    /** 分别从工作目录和已编译类/JAR位置向上查找，兼容IDEA从外层工作区启动。 */
    static Path resolvePath(String configured, Path workingDirectory, Path codeLocation) throws IOException {
        Path working = workingDirectory.toAbsolutePath().normalize();
        if (configured != null && !configured.isBlank()) {
            Path result = working.resolve(configured).normalize();
            if (!Files.isRegularFile(result)) {
                throw new IOException("找不到图谱 " + result + "；请先运行 pipeline/build_graph.py 或设置 KG_GRAPH_PATH。");
            }
            return result;
        }
        // 工作目录优先；不递归扫描磁盘、不猜测项目名。显式路径无效时绝不回退。
        Path module = codeLocation == null ? null : codeLocation.toAbsolutePath().normalize();
        if (module != null && !Files.isDirectory(module)) {
            module = module.getParent();
        }
        for (Path root : new Path[] {working, module}) {
            for (Path dir = root; dir != null; dir = dir.getParent()) {
                Path candidate = dir.resolve("data/processed/graph.json");
                if (Files.isRegularFile(candidate)) {
                    return candidate.normalize();
                }
            }
        }
        throw new IOException("找不到 data/processed/graph.json；工作目录=" + working
                + "，Java模块位置=" + module
                + "；请设置 KG_GRAPH_PATH 为图谱绝对路径，或将IDEA运行配置的工作目录设为项目根目录。");
    }

    private static void index(JsonNode records, Map<String, JsonNode> target, String kind) throws IOException {
        for (JsonNode record : records) {
            String id = record.path("id").asText();
            if (id.isBlank() || target.putIfAbsent(id, record) != null) {
                throw new IOException(kind + " id 为空或重复: " + id);
            }
        }
    }

    public Path source() { return source; }
    public JsonNode meta() { return graph.path("meta"); }
    public JsonNode node(String id) { return nodes.get(id); }
    public JsonNode block(String id) { return blocks.get(id); }
    public List<JsonNode> adjacent(String id) { return adjacency.getOrDefault(id, List.of()); }
    public List<JsonNode> records(String key) {
        List<JsonNode> result = new ArrayList<>();
        graph.path(key).forEach(result::add);
        return result;
    }

    public List<JsonNode> find(String keyword, String type) {
        String kw = normalized(keyword);
        return nodes.values().stream().filter(n ->
                (type == null || type.isBlank() || type.equalsIgnoreCase(n.path("type").asText()))
                && (kw.isEmpty() || normalized(n.path("name").asText()).contains(kw)
                || normalized(n.path("id").asText()).equals(kw)
                || aliases(n).stream().anyMatch(a -> normalized(a).contains(kw)))).toList();
    }

    public List<JsonNode> seeds(String keyword) {
        List<JsonNode> matches = find(keyword, null).stream()
                .filter(n -> !List.of("Section", "SourceDoc").contains(n.path("type").asText())).toList();
        String kw = normalized(keyword);
        List<JsonNode> exact = matches.stream().filter(n ->
                normalized(n.path("name").asText()).equals(kw)
                || normalized(n.path("id").asText()).equals(kw)
                || aliases(n).stream().anyMatch(a -> normalized(a).equals(kw))).toList();
        return exact.isEmpty() ? matches.stream().limit(5).toList() : exact;
    }

    private static List<String> aliases(JsonNode node) {
        List<String> result = new ArrayList<>();
        node.path("aliases").forEach(a -> result.add(a.asText()));
        return result;
    }

    public static String normalized(String text) {
        return text == null ? "" : text.replaceAll("(?U)\\s+", "").toLowerCase(Locale.ROOT);
    }

    public static boolean contains(String text, String keyword) {
        return normalized(text).contains(normalized(keyword));
    }

    /** 标准编号的排版差异，例如 WS/T 872—2025 与 WS-T872-2025_重排.txt。 */
    public static boolean fileContains(String file, String keyword) {
        return normalized(file).replaceAll("[-_/‐‑–—－]", "")
                .contains(normalized(keyword).replaceAll("[-_/‐‑–—－]", ""));
    }
}
