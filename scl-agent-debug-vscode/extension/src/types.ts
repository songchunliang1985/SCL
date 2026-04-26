// ═══ 消息协议 ═══
// 请求: { id, method, params }
// 响应: { id, result? } 或 { id, error? }
// 事件: { event, data }

export interface Request {
  id: string;
  method: string;
  params: Record<string, unknown>;
}

export interface Response {
  id: string;
  result?: unknown;
  error?: { code: number; message: string };
}

export interface AgentEvent {
  event: string;
  data: unknown;
}

export type Message = Request | Response | AgentEvent;

// ═══ 调试配置 ═══
export interface DebugConfig {
  name: string;
  type: string;
  request: string;
  program?: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  [key: string]: unknown;
}

// ═══ 断点 ═══
export interface BreakpointInfo {
  id: number;
  file: string;
  line: number;
  enabled: boolean;
  condition?: string;
  logMessage?: string;
}

// ═══ 栈帧 ═══
export interface StackFrame {
  id: number;
  name: string;
  source: { name?: string; path?: string };
  line: number;
  column: number;
}

// ═══ 变量 ═══
export interface Variable {
  name: string;
  value: string;
  type: string;
  variablesReference: number;
  indexedVariables?: number;
  namedVariables?: number;
}

export interface VariableScope {
  name: string;
  variables: Variable[];
  expensive?: boolean;
}

// ═══ 线程 ═══
export interface Thread {
  id: number;
  name: string;
}

// ═══ 调试状态 ═══
export interface DebugStatus {
  sessionActive: boolean;
  state: 'stopped' | 'running' | 'inactive';
  stoppedReason?: string;
  threadId?: number;
  frameId?: number;
  file?: string;
  line?: number;
}

// ═══ 结果类型 ═══
export interface VariablesResult {
  scopes: VariableScope[];
}

export interface VariableChildrenResult {
  variables: Variable[];
}

export interface StackTraceResult {
  frames: StackFrame[];
}

export interface EvaluateResult {
  value: string;
  type: string;
  variablesReference: number;
}

export interface BreakpointsResult {
  breakpoints: BreakpointInfo[];
}

export interface DebugConfigsResult {
  configs: DebugConfig[];
}

export interface ThreadsResult {
  threads: Thread[];
}

export interface SetVariableResult {
  value: string;
  type?: string;
}
