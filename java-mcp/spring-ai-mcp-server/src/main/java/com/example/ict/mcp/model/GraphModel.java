package com.example.ict.mcp.model;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import java.util.Map;

/** 工具返回结构。原始记录使用 JsonNode，保留条件、例外及未来扩展字段。 */
public final class GraphModel {
    private GraphModel() { }

    /** sufficient 不能由“检索命中”自动置为 true。total/offset/truncated 用于继续翻页。 */
    public record QueryResult(List<?> items, int total, int offset, boolean truncated,
                              boolean sufficient, String verification, String message,
                              Map<String, Object> knowledge_version) { }

    /** forward 表示遍历方向；edge 内始终保留原始关系方向。 */
    public record PathStep(String from, String to, boolean forward, JsonNode edge) { }

    public record EvidencePath(List<String> nodes, List<PathStep> steps, int hops,
                               String kind, boolean sufficient, String verification,
                               double confidence, String confidence_basis) { }

    public record TraverseResult(List<EvidencePath> paths, boolean truncated, boolean sufficient,
                                 String verification, String message, Map<String, Object> knowledge_version) { }
}
