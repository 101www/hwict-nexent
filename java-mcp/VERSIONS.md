# Java 侧依赖版本核对清单

> **本文件中的版本号已实测验证**（两个模块均 `BUILD SUCCESS`），不是估算值。
> 若日后构建报 `Could not resolve dependencies`，说明版本已迭代，到下表链接查新版。

| 组件 | 本项目版本 | 状态 | 查最新版 |
|---|---|---|---|
| JDK | 21.0.5 LTS | ✅ 已验证 | — |
| Spring Boot | 3.4.1 | ✅ 已验证 | https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent |
| Spring AI BOM | 1.0.0 | ✅ 已验证（artifact 名 `spring-ai-starter-mcp-server-webmvc` 存在） | https://central.sonatype.com/artifact/org.springframework.ai/spring-ai-bom |
| MCP Java SDK | 0.17.0 | ✅ 已验证（artifact 名 `io.modelcontextprotocol.sdk:mcp` 存在） | https://central.sonatype.com/artifact/io.modelcontextprotocol.sdk/mcp |

## 已踩过的坑（别重复踩）

### 1. Spring AI 1.0.0 的注解属性很有限
```java
// @ToolParam 只有两个属性，没有 name！
public @interface ToolParam {
    boolean required();
    String description();
}
```
**参数名靠 Java 反射从形参名取**，所以想让 LLM 看到 `start_entity` 这样的 snake_case 名字，
就得把 Java 形参直接命名成 `start_entity`（编译需保留 `-parameters`，Spring Boot 父 POM 默认已开）。

### 2. MCP Java SDK 0.17.0 的注册 API
```java
// ✗ 这样写编译不过（toolCall 要的是 Tool + BiFunction，不是 SyncToolSpecification）
McpServer.sync(transport).toolCall(spec)

// ✓ 正确：用 .tools(...) 批量注册，或 .tool(Tool, BiFunction)
McpServer.sync(transport)
    .capabilities(McpSchema.ServerCapabilities.builder().tools(true).build())
    .tools(spec1, spec2)
    .build();

// ✓ SyncToolSpecification 的 builder 方法名
McpServerFeatures.SyncToolSpecification.builder()
    .tool(McpSchema.Tool.builder().name("x").description("y").inputSchema(schema).build())
    .callHandler((exchange, request) -> result)   // 注意不是 .call(...)
    .build();
```

### 3. `.build()` 返回的是 `McpSyncServer` 不是 `McpServer`
Bean 方法签名要写 `McpSyncServer`，否则报"无法转换"。

### 4. 传输层选择
`HttpServletStreamableServerTransportProvider` 继承 `jakarta.servlet.http.HttpServlet`，
配合 Spring Boot 的 `ServletRegistrationBean` 挂载即可，**不需要 Reactor/WebFlux**。


## 若构建失败的排查顺序

1. **先只保留 Spring Boot 依赖跑通 `mvn -q compile`**，再加 MCP 相关依赖 —— 隔离问题
2. Spring AI 报找不到 artifact → 去上面链接确认该版本是否存在，以及 artifact 名（`webmvc` / `webflux` / `core`）
3. MCP SDK API 不匹配（`McpSchema` / `McpServer` 方法签名）→ 查 https://java.sdk.modelcontextprotocol.io/latest-snapshot/
4. 网络问题 → 在 `~/.m2/settings.xml` 配阿里云镜像：
   ```xml
   <mirror>
     <id>aliyun</id>
     <mirrorOf>central</mirrorOf>
     <url>https://maven.aliyun.com/repository/public</url>
   </mirror>
   ```

## 保底方案（不依赖任何 MCP 库）

如果 Maven 一直拉不下来，直接用**方式①「API 转 MCP」**：
只写 Spring Boot Web + `springdoc-openapi-starter-webmvc-ui`，把 `/v3/api-docs` 的 JSON 粘到 Nexent，
**同样算完成了"MCP 集成"这个评分点**，只是答辩时讲不了协议细节。
