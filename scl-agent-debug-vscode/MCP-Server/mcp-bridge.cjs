#!/usr/bin/env node
/**
 * MCP Bridge — Claude Code ↔ VS Code Debug Agent
 *
 * stdin: JSON-RPC (MCP), Claude Code 启动时自动 spawn
 * 内部: WebSocket 连 VS Code 扩展（127.0.0.1:19527 + token）
 */

const { randomUUID } = require('crypto');
const { createInterface } = require('readline');
const { readFileSync, existsSync } = require('fs');
const { join } = require('path');
const { homedir } = require('os');

const AGENT_DIR = join(homedir(), '.vscode-debug-agent');
const TOKEN_FILE = join(AGENT_DIR, 'token');
const WS_URL = 'ws://127.0.0.1:19527';

// ═══ 工具定义 ═══
// 行号约定：line 参数都是 0-based（VS Code 内部 Position 用 0-based）
// 用户层面看到的"第 42 行"对应 line=41
const TOOLS = [
  // 会话控制
  {
    name: 'start_debug',
    description: '启动 VS Code 调试。传入 launch.json 中的配置对象。',
    inputSchema: {
      type: 'object',
      properties: { config: { type: 'object', description: 'launch.json 配置' } },
      required: ['config'],
    },
  },
  { name: 'stop_debug', description: '停止当前调试会话。', inputSchema: { type: 'object', properties: {} } },
  { name: 'restart', description: '重启当前调试会话（保留所有断点）。', inputSchema: { type: 'object', properties: {} } },
  {
    name: 'restart_frame',
    description: '回到指定栈帧的开头重新执行。少数语言不支持。',
    inputSchema: { type: 'object', properties: { frameId: { type: 'number' } }, required: ['frameId'] },
  },
  { name: 'get_debug_configs', description: '列出工作区 launch.json 中可用的调试配置。', inputSchema: { type: 'object', properties: {} } },
  { name: 'get_status', description: '获取当前调试状态：是否有活动会话、是否在断点处暂停、当前文件和行号。', inputSchema: { type: 'object', properties: {} } },

  // 断点
  {
    name: 'set_breakpoint',
    description: '设置普通断点。line 是 0-based（VS Code 显示的第 N 行对应 line=N-1）。',
    inputSchema: {
      type: 'object',
      properties: {
        file: { type: 'string', description: '文件绝对路径' },
        line: { type: 'number', description: '行号（0-based）' },
        condition: { type: 'string', description: '可选条件表达式' },
      },
      required: ['file', 'line'],
    },
  },
  {
    name: 'set_breakpoints',
    description: '一次设置同一文件的多个断点。',
    inputSchema: {
      type: 'object',
      properties: {
        file: { type: 'string' },
        lines: { type: 'array', items: { type: 'number' }, description: '行号数组（0-based）' },
      },
      required: ['file', 'lines'],
    },
  },
  {
    name: 'set_logpoint',
    description: '设置日志断点：命中时不暂停，只在 Debug Console 输出 logMessage。'
      + ' logMessage 中可用 {expr} 内插表达式（如 "user={user.id}, count={items.length}"）。'
      + ' 适合在不打断执行的前提下追踪状态，避免 heisenbug。',
    inputSchema: {
      type: 'object',
      properties: {
        file: { type: 'string' },
        line: { type: 'number', description: '行号（0-based）' },
        logMessage: { type: 'string', description: '日志消息，支持 {expr} 内插' },
        condition: { type: 'string', description: '可选条件' },
      },
      required: ['file', 'line', 'logMessage'],
    },
  },
  {
    name: 'set_exception_breakpoints',
    description: '设置异常断点。filters 取决于调试器；常见：["uncaught"]、["all"]、Java: ["uncaught", "caught"]。',
    inputSchema: {
      type: 'object',
      properties: { filters: { type: 'array', items: { type: 'string' } } },
      required: ['filters'],
    },
  },
  {
    name: 'remove_breakpoint',
    description: '移除指定文件和行的断点。',
    inputSchema: {
      type: 'object',
      properties: { file: { type: 'string' }, line: { type: 'number' } },
      required: ['file', 'line'],
    },
  },
  {
    name: 'clear_breakpoints',
    description: '清除断点。不传 file 清全部；传 file 只清该文件的。',
    inputSchema: { type: 'object', properties: { file: { type: 'string' } } },
  },
  { name: 'list_breakpoints', description: '列出所有断点（含 logpoint）。', inputSchema: { type: 'object', properties: {} } },

  // 步进
  { name: 'continue', description: '继续执行（从断点恢复）。', inputSchema: { type: 'object', properties: {} } },
  { name: 'step_over', description: '单步步过（不进入函数）。', inputSchema: { type: 'object', properties: {} } },
  { name: 'step_into', description: '单步进入（进入函数内部）。', inputSchema: { type: 'object', properties: {} } },
  { name: 'step_out', description: '单步跳出（执行到函数返回）。', inputSchema: { type: 'object', properties: {} } },
  { name: 'pause', description: '暂停正在运行的程序。', inputSchema: { type: 'object', properties: {} } },

  // 数据查看
  {
    name: 'get_stack_trace',
    description: '获取当前线程的调用栈。',
    inputSchema: {
      type: 'object',
      properties: {
        threadId: { type: 'number', description: '线程 ID，不传则用当前暂停线程' },
        levels: { type: 'number', description: '最大栈帧数，默认 20' },
      },
    },
  },
  {
    name: 'get_variables',
    description: '获取指定栈帧的变量，按 scope 分组（Local / Closure / Global 等）。'
      + ' 嵌套对象的 variablesReference > 0 表示可展开 —— 用 get_variable_children 拿子项。',
    inputSchema: {
      type: 'object',
      properties: { frameId: { type: 'number' } },
      required: ['frameId'],
    },
  },
  {
    name: 'get_variable_children',
    description: '展开嵌套对象/数组的子变量。传 get_variables 返回的某个变量的 variablesReference。',
    inputSchema: {
      type: 'object',
      properties: { variablesReference: { type: 'number' } },
      required: ['variablesReference'],
    },
  },
  {
    name: 'set_variable',
    description: '修改变量的值。需要 variablesReference（来自 get_variables 的 scope）和变量名。',
    inputSchema: {
      type: 'object',
      properties: {
        variablesReference: { type: 'number' },
        name: { type: 'string' },
        value: { type: 'string' },
      },
      required: ['variablesReference', 'name', 'value'],
    },
  },
  {
    name: 'set_expression',
    description: '通过表达式赋值，如设置 user.name = "Alice"。frameId 不传用当前帧。',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string' },
        value: { type: 'string' },
        frameId: { type: 'number' },
      },
      required: ['expression', 'value'],
    },
  },
  {
    name: 'evaluate',
    description: '在调试上下文中求值表达式。可读变量、调函数、做计算。',
    inputSchema: {
      type: 'object',
      properties: { expression: { type: 'string' }, frameId: { type: 'number' } },
      required: ['expression'],
    },
  },
  { name: 'get_threads', description: '获取当前调试会话的所有线程。', inputSchema: { type: 'object', properties: {} } },
];

// ═══ 状态 ═══
let ws = null;
let wsReady = false;
const pending = new Map();
let msgQueue = [];
let reconnectTimer = null;

// ═══ MCP 输出 ═══
function sendMcp(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

function eventToText(event, data) {
  switch (event) {
    case 'stopped': {
      const lineDisplay = (data.line ?? -1) >= 0 ? data.line + 1 : '?';
      let txt = `[Stopped @ ${data.file || '?'}:${lineDisplay}] reason=${data.reason}, thread=${data.threadId}, frameId=${data.frameId}`;
      if (Array.isArray(data.frames) && data.frames.length) {
        txt += '\n\nStack (top ' + data.frames.length + '):';
        for (const f of data.frames) {
          const path = f.source?.path || f.source?.name || '?';
          txt += `\n  #${f.id} ${f.name} @ ${path}:${f.line}`;
        }
      }
      if (Array.isArray(data.topScopes) && data.topScopes.length) {
        txt += '\n\nTop frame variables:';
        for (const sc of data.topScopes) {
          if (!sc.variables?.length) continue;
          txt += `\n  [${sc.name}]`;
          for (const v of sc.variables) {
            const more = v.variablesReference ? ` (ref=${v.variablesReference})` : '';
            txt += `\n    ${v.name}: ${v.type} = ${v.value}${more}`;
          }
        }
      }
      return txt;
    }
    case 'continued': return '[Continued] Program resumed';
    case 'sessionChanged': return data.active ? `[Debug Session Started] type=${data.type}` : '[Debug Session Ended]';
    case 'output': return `[${data.category || 'stdout'}] ${data.output}`.trimEnd();
    case 'terminated': return '[Terminated] Debugged process exited';
    default: return `[${event}] ${JSON.stringify(data)}`;
  }
}

// ═══ WebSocket ═══
function setupWs(wsocket) {
  wsocket.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg && 'id' in msg) {
      const resolve = pending.get(msg.id);
      if (resolve) {
        pending.delete(msg.id);
        resolve(msg.error ? { __error: msg.error.message } : msg.result);
      }
    } else if (msg && 'event' in msg) {
      sendMcp({
        jsonrpc: '2.0',
        method: 'notifications/message',
        params: { level: 'info', message: eventToText(msg.event, msg.data) },
      });
    }
  };
  wsocket.onclose = () => {
    wsReady = false;
    ws = null;
    scheduleReconnect();
  };
  wsocket.onerror = () => { /* 由 onclose 处理 */ };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    tryConnect();
  }, 2000);
}

function tryConnect() {
  if (ws || wsReady) return;
  if (!existsSync(TOKEN_FILE)) { scheduleReconnect(); return; }
  let token;
  try { token = readFileSync(TOKEN_FILE, 'utf-8').trim(); }
  catch { scheduleReconnect(); return; }

  try {
    ws = new WebSocket(`${WS_URL}/?token=${encodeURIComponent(token)}`);
  } catch {
    ws = null;
    scheduleReconnect();
    return;
  }

  setupWs(ws);
  ws.onopen = () => {
    wsReady = true;
    const q = msgQueue;
    msgQueue = [];
    for (const { id, method, params, resolve } of q) {
      pending.set(id, resolve);
      ws.send(JSON.stringify({ id, method, params }));
    }
  };
}

function sendWs(method, params) {
  return new Promise((resolve) => {
    const id = randomUUID();
    if (wsReady && ws?.readyState === 1) {
      pending.set(id, resolve);
      ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          resolve({ __error: 'Request timed out (10s)' });
        }
      }, 10000);
    } else {
      msgQueue.push({ id, method, params, resolve });
      tryConnect();
      setTimeout(() => {
        const idx = msgQueue.findIndex((m) => m.id === id);
        if (idx >= 0) {
          msgQueue.splice(idx, 1);
          resolve({ __error: 'Not connected to SCL-Agent-debug-VScode. Open VS Code with the extension installed and run "Setup Claude Code Integration".' });
        }
      }, 5000);
    }
  });
}

// ═══ MCP 路由 ═══
async function handleMcp(msg) {
  const { id, method, params } = msg;
  if (id == null) return;

  switch (method) {
    case 'initialize':
      sendMcp({
        jsonrpc: '2.0', id,
        result: {
          protocolVersion: '2024-11-05',
          serverInfo: { name: 'scl-agent-debug-vscode', version: '1.1.0' },
          capabilities: { tools: {}, logging: {} },
        },
      });
      break;

    case 'tools/list':
      sendMcp({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
      break;

    case 'tools/call': {
      try {
        const wsMethod = params.name.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
        const result = await sendWs(wsMethod, params.arguments || {});
        const isError = result?.__error;
        const text = isError ? `Error: ${result.__error}` : JSON.stringify(result, null, 2);
        sendMcp({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text }], isError: !!isError } });
      } catch (err) {
        sendMcp({
          jsonrpc: '2.0', id,
          result: { content: [{ type: 'text', text: 'Error: ' + err.message }], isError: true },
        });
      }
      break;
    }

    case 'ping':
      sendMcp({ jsonrpc: '2.0', id, result: {} });
      break;

    default:
      sendMcp({ jsonrpc: '2.0', id, error: { code: -32601, message: `Unknown method: ${method}` } });
  }
}

// ═══ 启动 ═══
function main() {
  tryConnect();
  const rl = createInterface({ input: process.stdin });
  rl.on('line', (line) => {
    try { handleMcp(JSON.parse(line)); } catch { /* skip */ }
  });
  process.on('SIGTERM', () => { ws?.close(); process.exit(0); });
  process.on('SIGINT',  () => { ws?.close(); process.exit(0); });
}

main();
