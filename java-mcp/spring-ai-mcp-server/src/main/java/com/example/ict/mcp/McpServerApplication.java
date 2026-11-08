package com.example.ict.mcp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 赛题3 · Java 侧 MCP 工具服务入口。
 *
 * <p>启动后：
 * <ul>
 *   <li>SSE 端点：http://localhost:8081/sse</li>
 *   <li>Nexent使用Java所在电脑的可达地址；本次为 http://192.168.100.1:8081/sse</li>
 * </ul>
 */
@SpringBootApplication
public class McpServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(McpServerApplication.class, args);
    }
}
