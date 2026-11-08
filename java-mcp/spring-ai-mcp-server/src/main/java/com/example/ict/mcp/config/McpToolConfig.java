package com.example.ict.mcp.config;

import com.example.ict.mcp.tools.KgToolsService;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 把 {@link KgToolsService} 中标注了 {@code @Tool} 的方法注册为 MCP 工具。
 *
 * <p>这一步是"Java 服务"变成"MCP Server"的关键：注册后 Nexent 连接本服务，
 * 会通过 tools/list 自动发现这些工具及其 JSON Schema。
 */
@Configuration
public class McpToolConfig {

    @Bean
    public ToolCallbackProvider kgTools(KgToolsService kgToolsService) {
        return MethodToolCallbackProvider.builder()
                .toolObjects(kgToolsService)
                .build();
    }
}
