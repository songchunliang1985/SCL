# MCP-Server

MCP server 源代码。**唯一的 bridge 源**就在这里。

## 文件

- `mcp-bridge.cjs` —— stdio JSON-RPC（MCP 协议）↔ WebSocket 桥接，零外部依赖

## 它是怎么被使用的

不需要手动启动。安装 VS Code 扩展后：

1. 扩展激活时把这个文件**复制**到 `~/.vscode-debug-agent/mcp-bridge.cjs`（部署目录）
2. Claude Code 通过 `~/.claude.json` 的 `mcpServers` 配置启动它
3. 它通过 WebSocket 连到 VS Code 扩展的 `127.0.0.1:19527`，转发命令

## 同步到扩展

每次 `extension/` 编译时，`npm run sync-bridge` 会把这个文件复制到
`extension/bridge/`，保证 vsix 打包时能带上它。`extension/bridge/` 在
`.gitignore` 中，**只有这一份才是源**。

## 单独启动（仅调试 bridge 自身用）

```bash
node mcp-bridge.cjs
```

需要 `~/.vscode-debug-agent/token` 已存在 + VS Code 扩展正在跑，否则 bridge
会持续在重连状态。
