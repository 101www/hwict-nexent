package com.example.ict.sdk;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 赛题3 · Java 侧 MCP 工具服务（MCP Java SDK 原生实现）。
 *
 * <p>相比 Spring AI 封装版，本实现的代码里能直接看到 MCP 协议的三个关键动作：
 * <ol>
 *   <li><b>能力协商</b>：服务端声明 {@code tools} 能力（capabilities）</li>
 *   <li><b>工具发现</b>：{@code tools/list} 返回工具名、描述与输入 JSON Schema</li>
 *   <li><b>工具调用</b>：{@code tools/call} 按工具名分发并返回结构化结果</li>
 * </ol>
 * 答辩被问到"MCP 协议核心机制"时，可以指着 {@link McpServerConfig} 讲。
 */
@SpringBootApplication
public class NativeMcpApplication {

    public static void main(String[] args) {
        SpringApplication.run(NativeMcpApplication.class, args);
    }
}
