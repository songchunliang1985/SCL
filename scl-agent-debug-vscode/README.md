# SCL-Agent-debug-VScode

让 **Claude Code** 通过 MCP 直接驱动 VS Code 的调试器。
你在终端跟 Claude 说一句"调试这个 bug"，它能自己启动调试会话、打断点、
单步、看调用栈、展开嵌套对象、求值表达式、修改变量、捕异常 ——
不用你在 VS Code 里手动操作。

## 它解决什么问题

光让 Claude 读源码，它对**运行时状态**是抓瞎的。React state、ORM 实体、
异步执行顺序——静态分析看不到这些。这个工具把 Claude 的能力从"只会读代码"
升级到"能看 runtime"，对付本地能跑起来的 bug 效率上一个台阶。

## 工程结构

```
vscode-debug-agent/
├── extension/        ← VS Code 扩展（DAP ↔ WebSocket 服务）
│   ├── package.json
│   ├── src/          # extension.ts / debug-bridge.ts / ws-server.ts / setup.ts / types.ts
│   └── bridge/       # 构建期从 MCP-Server/ 同步过来（已 gitignore）
│
└── MCP-Server/       ← MCP 服务器源码（Claude Code 直接 spawn）
    └── mcp-bridge.cjs
```

两个组件职责分明：
- **extension/** 是 VS Code 扩展，负责调用 VS Code Debug API 并暴露
  WebSocket 服务（127.0.0.1:19527 + 一次性 token）
- **MCP-Server/** 是 Claude Code 直接拉起来的 Node 脚本，做 MCP stdio 协议
  ↔ WebSocket 的桥接

## 提供给 Claude 的 25 个工具

**会话** (6)：`start_debug` / `stop_debug` / `restart` / `restart_frame` /
`get_debug_configs` / `get_status`

**断点** (7)：`set_breakpoint` / `set_breakpoints`（批量）/ `set_logpoint`
（命中不暂停只输出）/ `set_exception_breakpoints` / `remove_breakpoint` /
`clear_breakpoints` / `list_breakpoints`

**步进** (5)：`continue` / `step_over` / `step_into` / `step_out` / `pause`

**数据** (7)：`get_stack_trace` / `get_variables`（按 scope 分组）/
`get_variable_children`（展开嵌套对象/数组）/ `set_variable` /
`set_expression` / `evaluate` / `get_threads`

**性能优化**：断点命中时扩展会主动把 top 5 栈帧 + 顶层局部变量打包推给
Claude，省掉它再调 `get_stack_trace` + `get_variables` 的两次往返。

## 工作原理

```
Claude Code (CLI)
   ↕ stdio (MCP)
mcp-bridge.cjs           （部署到 ~/.vscode-debug-agent/，Claude 启动时 spawn）
   ↕ WebSocket           （127.0.0.1:19527 + 每次启动随机 token）
SCL-Agent-debug-VScode   （VS Code 扩展）
   ↕ VS Code Debug API
真正的调试器             （node / python / java / go / ...）
```

- token 在每次 VS Code 启动时随机生成，写到 `~/.vscode-debug-agent/token`，
  权限 0o600
- WS 服务只绑 `127.0.0.1`，不对外暴露
- bridge 自带重连：VS Code 重启后 Claude Code 不用退出

## 安装手顺

### 前置要求

- VS Code ≥ 1.85
- Node.js ≥ 18（npm 自带）
- Claude Code CLI（`claude` 命令在 PATH 里）
- 想调试什么语言，就装相应的 VS Code 调试扩展（Java/Python/Go/...）

### Step 1. 克隆仓库

```bash
git clone https://github.com/songchunliang1985/SCL.git
cd SCL/scl-agent-debug-vscode    # 视实际放置路径调整
```

### Step 2. 编译并打包 .vsix

```bash
cd extension
npm install
npm run package    # 自动 sync-bridge → tsc → vsce package
```

完成后在 `extension/` 下生成 `scl-agent-debug-vscode-1.1.0.vsix`。

### Step 3. 安装 VS Code 扩展

```bash
code --install-extension scl-agent-debug-vscode-1.1.0.vsix
```

或在 VS Code 里：`Cmd+Shift+P` → `Extensions: Install from VSIX…`。

### Step 4. 注册到 Claude Code（任选其一）

#### 方式 A — 在 VS Code 里点一下（推荐）

打开任意 VS Code 窗口（扩展会自动激活），右下角弹窗点 **Setup**，
或 `Cmd+Shift+P` → `SCL-Agent-debug: Setup Claude Code Integration`。

它会把下面这段写到 `~/.claude.json` 顶层 `mcpServers`：

```json
"scl-agent-debug-vscode": {
  "type": "stdio",
  "command": "node",
  "args": ["/Users/<you>/.vscode-debug-agent/mcp-bridge.cjs"],
  "env": {}
}
```

#### 方式 B — 命令行（不开 VS Code 也能配）

```bash
claude mcp add --scope user scl-agent-debug-vscode \
  node "$HOME/.vscode-debug-agent/mcp-bridge.cjs"
```

**注意**：方式 B 的前提是扩展至少在某个 VS Code 窗口跑过一次，这样
`~/.vscode-debug-agent/mcp-bridge.cjs` 才存在。第一次装扩展后建议先开
VS Code 让它自动 deploy bridge，再用方式 B 跑命令。

### Step 5. 重启 Claude Code 验证

```bash
# 在终端 claude 会话里
/exit
claude
/mcp
```

应该看到：

```
scl-agent-debug-vscode: node /Users/<you>/.vscode-debug-agent/mcp-bridge.cjs - ✓ Connected
```

最小冒烟测试：
```
请调用 scl-agent-debug-vscode 的 get_status 工具
```
返回 `{"sessionActive": false, "state": "inactive"}` 即代表整条链路通了。

## 卸载

```bash
# 1. 移除 MCP 注册
claude mcp remove scl-agent-debug-vscode

# 2. 卸载 VS Code 扩展
code --uninstall-extension scl.scl-agent-debug-vscode

# 3. 删除运行时目录（可选）
rm -rf ~/.vscode-debug-agent
```

## 命令 / 状态栏 / 约定

| 命令面板 | 作用 |
|---|---|
| `SCL-Agent-debug: Setup Claude Code Integration`   | 写入 MCP 配置 |
| `SCL-Agent-debug: Remove Claude Code Integration`  | 移除 MCP 配置 |
| `SCL-Agent-debug: Toggle (pause/resume)`           | 暂停 / 恢复 |
| `SCL-Agent-debug: Show Log`                        | 打开扩展日志面板 |

| 状态栏图标 | 含义 |
|---|---|
| `▶ SCL-Agent-debug`（绿） | 已就绪 |
| `⏸ SCL-Agent-debug`     | 已暂停（点击恢复）|
| `⊘ SCL-Agent-debug`     | 未配置（点击运行 Setup）|

**约定**：
- 所有工具的 `line` 参数是 **0-based**（编辑器看到的"第 42 行"对应 `line: 41`）
- 文件路径必须是绝对路径

## 故障排查

| 现象 | 处理 |
|---|---|
| `/mcp` 看不到 `scl-agent-debug-vscode` | 没点 Setup，或 Setup 后没重启 Claude Code |
| 调用工具报 `Not connected` | VS Code 没开，或扩展被 toggle 暂停 |
| 状态栏没出现 | 扩展没装上，或激活失败 → `SCL-Agent-debug: Show Log` 看错误 |
| 端口 19527 冲突 | 老进程没退干净，`lsof -tiTCP:19527 \| xargs kill` 重启 VS Code |
| 设了断点不命中 | 行号没传 0-based，或断点所在文件不在调试器加载范围 |
| Java 调试启不动 | 等右下角"Java: Ready"再 `start_debug`（语言服务器要 indexing）|

`SCL-Agent-debug: Show Log` 是排错首选，里面会列每个请求和 WS 连接事件。

## 支持的语言

凡 VS Code 能调的，这个工具都能驱动 —— 它走 DAP，与具体语言无关：

- Node.js / TypeScript / JavaScript（VS Code 内置）
- Python（`ms-python.python`）
- Java（`redhat.java` + `vscjava.vscode-java-debug`）
- Go（`golang.go`）
- C/C++（`ms-vscode.cpptools`）
- Rust（`vadimcn.codelldb`）
- C#/.NET、PHP、Ruby、Kotlin、Scala、Swift、Dart 等

## 开发

修改源代码后：
```bash
cd extension
npm run compile    # 编译 + 同步 bridge
npm run package    # 重打 .vsix
```

如果只改了 `MCP-Server/mcp-bridge.cjs`，跑 `npm run sync-bridge` 把它同步
到 `extension/bridge/` 即可。

## License

MIT
