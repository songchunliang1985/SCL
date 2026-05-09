import * as vscode from 'vscode';
import type {
  Request,
  DebugConfig,
  BreakpointInfo,
  StackFrame,
  Variable,
  VariableScope,
  Thread,
  DebugStatus,
  DebugConfigsResult,
  BreakpointsResult,
  StackTraceResult,
  VariablesResult,
  VariableChildrenResult,
  EvaluateResult,
  ThreadsResult,
  SetVariableResult,
  Watch,
  WatchValue,
  WatchListResult,
  AddWatchResult,
  ClearResult,
  StepMode,
  SmartStepResult,
  WaitForStopResult,
  ScopeDiff,
} from './types';

interface StoppedInfo {
  threadId: number;
  frameId: number;
  reason: string;
  file?: string;
  line?: number;
}

interface WaitResolver {
  resolve: () => void;
  reject: (e: Error) => void;
  timer: NodeJS.Timeout;
}

const MAX_VAR_VALUE_LEN = 200;
const MAX_PIGGYBACK_VARS = 30;
const MAX_PIGGYBACK_FRAMES = 5;

// 路径不属于"用户代码"的启发式特征
const NON_USER_PATH_RE =
  /(node_modules|[\\/]site-packages[\\/]|<frozen |<built-in|[\\/]internal[\\/]|[\\/]jre[\\/]|[\\/]jdk[\\/]|[\\/]\.pyenv[\\/]|[\\/]lib[\\/]python[\d.]+[\\/])/i;

function isUserFrame(path?: string): boolean {
  if (!path) return false;
  return !NON_USER_PATH_RE.test(path);
}

function truncate(s: string, max = MAX_VAR_VALUE_LEN): string {
  if (s == null) return '';
  return s.length <= max ? s : s.slice(0, max) + `… (${s.length} chars)`;
}

function mapVar(v: any): Variable {
  return {
    name: v.name,
    value: truncate(String(v.value ?? '')),
    type: v.type || typeof v.value,
    variablesReference: v.variablesReference || 0,
    indexedVariables: v.indexedVariables,
    namedVariables: v.namedVariables,
  };
}

function diffScopes(prev: VariableScope[] | null, curr: VariableScope[]): ScopeDiff[] | undefined {
  if (!prev) return undefined;
  const out: ScopeDiff[] = [];
  for (const cur of curr) {
    const prevScope = prev.find((s) => s.name === cur.name);
    if (!prevScope) {
      out.push({ name: cur.name, added: cur.variables, removed: [], changed: [] });
      continue;
    }
    const added: Variable[] = [];
    const removed: { name: string }[] = [];
    const changed: { name: string; oldValue: string; newValue: string; type: string }[] = [];
    const prevByName = new Map(prevScope.variables.map((v) => [v.name, v]));
    const curByName = new Map(cur.variables.map((v) => [v.name, v]));
    for (const v of cur.variables) {
      const p = prevByName.get(v.name);
      if (!p) added.push(v);
      else if (p.value !== v.value) changed.push({ name: v.name, oldValue: p.value, newValue: v.value, type: v.type });
    }
    for (const v of prevScope.variables) {
      if (!curByName.has(v.name)) removed.push({ name: v.name });
    }
    if (added.length || removed.length || changed.length) {
      out.push({ name: cur.name, added, removed, changed });
    }
  }
  return out;
}

export class DebugBridge {
  private activeSession: vscode.DebugSession | null = null;
  private stoppedInfo: StoppedInfo | null = null;
  private trackerDisposable: vscode.Disposable | null = null;
  private sendEvent: (event: string, data: unknown) => void;

  // v1.2 状态
  private watches: Watch[] = [];
  private nextWatchId = 1;
  private prevTopScopes: VariableScope[] | null = null;
  private waitResolvers: WaitResolver[] = [];

  constructor(sendEvent: (event: string, data: unknown) => void) {
    this.sendEvent = sendEvent;
    this.registerTracker();
    this.listenSessions();
  }

  async handle(msg: Request): Promise<unknown> {
    const p = msg.params as any;
    switch (msg.method) {
      case 'startDebug':              return this.startDebug(p);
      case 'stopDebug':               return this.stopDebug();
      case 'restart':                 return this.restart();
      case 'restartFrame':            return this.restartFrame(p);
      case 'getDebugConfigs':         return this.getDebugConfigs();
      case 'getStatus':                return this.getStatus();
      case 'setBreakpoint':           return this.setBreakpoint(p);
      case 'setBreakpoints':          return this.setBreakpoints(p);
      case 'setLogpoint':             return this.setLogpoint(p);
      case 'setExceptionBreakpoints': return this.setExceptionBreakpoints(p);
      case 'removeBreakpoint':        return this.removeBreakpoint(p);
      case 'clearBreakpoints':        return this.clearBreakpoints(p);
      case 'listBreakpoints':         return this.listBreakpoints();
      case 'continue':                return this.doContinue();
      case 'stepOver':                return this.stepOver();
      case 'stepInto':                return this.stepInto();
      case 'stepOut':                 return this.stepOut();
      case 'pause':                   return this.pause();
      case 'getStackTrace':           return this.getStackTrace(p);
      case 'getVariables':            return this.getVariables(p);
      case 'getVariableChildren':     return this.getVariableChildren(p);
      case 'setVariable':             return this.setVariable(p);
      case 'setExpression':           return this.setExpression(p);
      case 'evaluate':                return this.evaluate(p);
      case 'getThreads':              return this.getThreads();
      // ═══ v1.2 新方法 ═══
      case 'smartStepUntil':          return this.smartStepUntil(p);
      case 'waitForStop':             return this.waitForStop(p);
      case 'addWatch':                return this.addWatch(p);
      case 'removeWatch':             return this.removeWatch(p);
      case 'listWatches':             return this.listWatches();
      case 'clearWatches':            return this.clearWatches();
      default:
        throw new Error(`Unknown method: ${msg.method}`);
    }
  }

  dispose(): void {
    this.trackerDisposable?.dispose();
  }

  // ═══ 行号归一化(line1 1-based → line 0-based) ═══
  private resolveLine(p: { line?: number; line1?: number }): number {
    if (typeof p.line1 === 'number') return Math.max(0, p.line1 - 1);
    if (typeof p.line === 'number') return p.line;
    throw new Error('line or line1 required');
  }

  // ═══ 会话跟踪 ═══
  private listenSessions(): void {
    vscode.debug.onDidStartDebugSession((session) => {
      this.activeSession = session;
      this.sendEvent('sessionChanged', { active: true, type: session.type });
    });
    vscode.debug.onDidTerminateDebugSession(() => {
      this.activeSession = null;
      this.stoppedInfo = null;
      this.prevTopScopes = null;
      this.rejectAllWaiters(new Error('session terminated'));
      this.sendEvent('sessionChanged', { active: false });
    });
  }

  // ═══ DAP 事件捕获 + stopped piggyback ═══
  private registerTracker(): void {
    const self = this;
    this.trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory('*', {
      createDebugAdapterTracker: (session) => ({
        onDidSendMessage: async (msg: any) => {
          if (msg.type === 'event' && msg.event === 'stopped') {
            await self.handleStopped(session, msg.body);
          } else if (msg.type === 'event' && msg.event === 'continued') {
            self.stoppedInfo = null;
            self.sendEvent('continued', {
              threadId: msg.body?.threadId,
              allThreadsContinued: msg.body?.allThreadsContinued,
            });
          } else if (msg.type === 'event' && msg.event === 'output') {
            self.sendEvent('output', { category: msg.body?.category, output: msg.body?.output });
          } else if (msg.type === 'event' && msg.event === 'terminated') {
            self.rejectAllWaiters(new Error('session terminated'));
            self.sendEvent('terminated', {});
          }
        },
      }),
    });
  }

  /** stopped 时主动拉栈 + 顶层变量 + watches + diff,piggyback 推送给 Claude,省 round trip */
  private async handleStopped(session: vscode.DebugSession, body: any): Promise<void> {
    const threadId: number = body.threadId;
    const reason: string = body.reason;

    let frames: StackFrame[] = [];
    let topVars: VariableScope[] = [];
    let topFrameId = 0;
    let file: string | undefined;
    let line: number | undefined;
    let topScopesDiff: ScopeDiff[] | undefined;
    let watchValues: WatchValue[] | undefined;

    try {
      const stResp: any = await session.customRequest('stackTrace', { threadId, levels: MAX_PIGGYBACK_FRAMES });
      const sf = stResp.stackFrames || [];
      frames = sf.map((f: any) => ({
        id: f.id, name: f.name,
        source: { name: f.source?.name, path: f.source?.path },
        line: f.line, column: f.column,
        isUser: isUserFrame(f.source?.path),
      }));

      // 优先取首个用户帧;若无则回退 frames[0]
      const userIdx = frames.findIndex((f) => f.isUser);
      const piggyFrame = userIdx >= 0 ? frames[userIdx] : frames[0];
      if (piggyFrame) {
        topFrameId = piggyFrame.id;
        file = piggyFrame.source?.path;
        line = piggyFrame.line;

        const scopesResp: any = await session.customRequest('scopes', { frameId: topFrameId });
        const scopes: any[] = (scopesResp.scopes || []).filter((sc: any) => !sc.expensive);

        // 并发抓所有 scope 的 variables
        const varResps = await Promise.all(
          scopes.map(async (sc) => {
            try {
              const r: any = await session.customRequest('variables', { variablesReference: sc.variablesReference });
              return { sc, r };
            } catch {
              return { sc, r: { variables: [] } };
            }
          })
        );
        topVars = varResps.map(({ sc, r }: { sc: any; r: any }) => ({
          name: sc.name,
          variables: (r.variables || []).slice(0, MAX_PIGGYBACK_VARS).map(mapVar),
          expensive: false,
        }));

        // diff 上一次 stopped 的 topScopes
        topScopesDiff = diffScopes(this.prevTopScopes, topVars);

        // 自动 evaluate watches
        if (this.watches.length) {
          watchValues = await Promise.all(
            this.watches.map(async (w): Promise<WatchValue> => {
              try {
                const r: any = await session.customRequest('evaluate', {
                  expression: w.expression, frameId: topFrameId, context: 'watch',
                });
                return {
                  id: w.id,
                  expression: w.expression,
                  value: truncate(String(r.result ?? '')),
                  type: r.type || typeof r.result,
                  variablesReference: r.variablesReference || 0,
                };
              } catch (e: any) {
                return {
                  id: w.id,
                  expression: w.expression,
                  error: String(e?.message || e),
                };
              }
            })
          );
        }

        this.prevTopScopes = topVars;
      }
    } catch {
      // 忽略 piggyback 失败 —— 不影响后续 Claude 主动拉
    }

    this.stoppedInfo = { threadId, frameId: topFrameId, reason, file, line };
    this.sendEvent('stopped', {
      threadId, frameId: topFrameId, reason, file, line,
      frames, topScopes: topVars,
      ...(topScopesDiff ? { topScopesDiff } : {}),
      ...(watchValues ? { watches: watchValues } : {}),
    });

    // 唤醒所有等待 stopped 的 waiter(smart_step_until / wait_for_stop)
    this.resolveAllWaiters();
  }

  // ═══ 等待器(供 smart_step_until / wait_for_stop 复用) ═══
  private makeWaitPromise(timeoutMs: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waitResolvers = this.waitResolvers.filter((r) => r.timer !== timer);
        reject(new Error('wait timeout'));
      }, timeoutMs);
      this.waitResolvers.push({ resolve, reject, timer });
    });
  }

  private resolveAllWaiters(): void {
    const resolvers = this.waitResolvers;
    this.waitResolvers = [];
    for (const r of resolvers) {
      clearTimeout(r.timer);
      r.resolve();
    }
  }

  private rejectAllWaiters(err: Error): void {
    const resolvers = this.waitResolvers;
    this.waitResolvers = [];
    for (const r of resolvers) {
      clearTimeout(r.timer);
      r.reject(err);
    }
  }

  // ═══ 调试控制 ═══
  private async startDebug(params: { config: DebugConfig }): Promise<{ ok: boolean }> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) throw new Error('No workspace folder open');
    const ok = await vscode.debug.startDebugging(folder, params.config);
    if (!ok) throw new Error('Failed to start debugging');
    return { ok: true };
  }

  private async stopDebug(): Promise<{ ok: boolean }> {
    await vscode.debug.stopDebugging(this.activeSession ?? undefined);
    return { ok: true };
  }

  private async restart(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await vscode.commands.executeCommand('workbench.action.debug.restart');
    return { ok: true };
  }

  private async restartFrame(params: { frameId: number }): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('restartFrame', { frameId: params.frameId });
    return { ok: true };
  }

  private async getDebugConfigs(): Promise<DebugConfigsResult> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) return { configs: [] };
    const config = vscode.workspace.getConfiguration('launch', folder.uri);
    const configs = config.get<DebugConfig[]>('configurations') || [];
    return { configs };
  }

  private async getStatus(): Promise<DebugStatus> {
    if (!this.activeSession) {
      return { sessionActive: false, state: 'inactive' };
    }
    if (this.stoppedInfo) {
      return {
        sessionActive: true,
        state: 'stopped',
        stoppedReason: this.stoppedInfo.reason,
        threadId: this.stoppedInfo.threadId,
        frameId: this.stoppedInfo.frameId,
        file: this.stoppedInfo.file,
        line: this.stoppedInfo.line,
      };
    }
    return { sessionActive: true, state: 'running' };
  }

  // ═══ 断点 ═══
  private async setBreakpoint(params: { file: string; line?: number; line1?: number; condition?: string }): Promise<{ ok: boolean; bp: BreakpointInfo }> {
    const line = this.resolveLine(params);
    const uri = vscode.Uri.file(params.file);
    const loc = new vscode.Location(uri, new vscode.Position(line, 0));
    const bp = new vscode.SourceBreakpoint(loc, true, params.condition, undefined, undefined);
    vscode.debug.addBreakpoints([bp]);
    return {
      ok: true,
      bp: { id: 0, file: params.file, line, line1: line + 1, enabled: true, condition: params.condition },
    };
  }

  private async setBreakpoints(params: { file: string; lines?: number[]; lines1?: number[] }): Promise<{ ok: boolean; count: number }> {
    let lines: number[];
    if (Array.isArray(params.lines1)) lines = params.lines1.map((n) => Math.max(0, n - 1));
    else if (Array.isArray(params.lines)) lines = params.lines;
    else throw new Error('lines or lines1 required');
    const uri = vscode.Uri.file(params.file);
    const bps = lines.map((line) =>
      new vscode.SourceBreakpoint(new vscode.Location(uri, new vscode.Position(line, 0)), true)
    );
    vscode.debug.addBreakpoints(bps);
    return { ok: true, count: bps.length };
  }

  private async setLogpoint(params: { file: string; line?: number; line1?: number; logMessage: string; condition?: string }): Promise<{ ok: boolean }> {
    const line = this.resolveLine(params);
    const uri = vscode.Uri.file(params.file);
    const loc = new vscode.Location(uri, new vscode.Position(line, 0));
    // SourceBreakpoint(location, enabled, condition, hitCondition, logMessage)
    const bp = new vscode.SourceBreakpoint(loc, true, params.condition, undefined, params.logMessage);
    vscode.debug.addBreakpoints([bp]);
    return { ok: true };
  }

  private async setExceptionBreakpoints(params: { filters: string[] }): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('setExceptionBreakpoints', { filters: params.filters });
    return { ok: true };
  }

  private async removeBreakpoint(params: { file: string; line?: number; line1?: number }): Promise<{ ok: boolean }> {
    const line = this.resolveLine(params);
    const targetPath = vscode.Uri.file(params.file).fsPath;
    const bps = vscode.debug.breakpoints.filter((b) => {
      if (!(b instanceof vscode.SourceBreakpoint)) return false;
      const loc = (b as vscode.SourceBreakpoint).location;
      return loc.uri.fsPath === targetPath && loc.range.start.line === line;
    });
    if (bps.length > 0) vscode.debug.removeBreakpoints(bps);
    return { ok: true };
  }

  private async clearBreakpoints(params: { file?: string }): Promise<{ ok: boolean; count: number }> {
    let bps = vscode.debug.breakpoints as readonly vscode.Breakpoint[];
    if (params.file) {
      const targetPath = vscode.Uri.file(params.file).fsPath;
      bps = bps.filter((b) => b instanceof vscode.SourceBreakpoint && (b as vscode.SourceBreakpoint).location.uri.fsPath === targetPath);
    }
    vscode.debug.removeBreakpoints(bps as vscode.Breakpoint[]);
    return { ok: true, count: bps.length };
  }

  private async listBreakpoints(): Promise<BreakpointsResult> {
    const breakpoints: BreakpointInfo[] = vscode.debug.breakpoints.map((b, i) => {
      if (b instanceof vscode.SourceBreakpoint) {
        const sb = b as vscode.SourceBreakpoint;
        const line = sb.location.range.start.line;
        return {
          id: i,
          file: sb.location.uri.fsPath,
          line,
          line1: line + 1,
          enabled: sb.enabled,
          condition: sb.condition,
          logMessage: sb.logMessage,
        };
      }
      return { id: i, file: '', line: 0, line1: 1, enabled: b.enabled };
    });
    return { breakpoints };
  }

  // ═══ 执行控制 ═══
  // 注意:不在这里清 stoppedInfo —— 让 'stopped'/'continued' DAP 事件去更新
  private async doContinue(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('continue', { threadId: this.stoppedInfo?.threadId ?? 0 });
    return { ok: true };
  }

  private async stepOver(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('next', { threadId: this.stoppedInfo?.threadId ?? 0 });
    return { ok: true };
  }

  private async stepInto(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('stepIn', { threadId: this.stoppedInfo?.threadId ?? 0 });
    return { ok: true };
  }

  private async stepOut(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('stepOut', { threadId: this.stoppedInfo?.threadId ?? 0 });
    return { ok: true };
  }

  private async pause(): Promise<{ ok: boolean }> {
    if (!this.activeSession) throw new Error('No active debug session');
    await this.activeSession.customRequest('pause', { threadId: this.stoppedInfo?.threadId ?? 0 });
    return { ok: true };
  }

  // ═══ 数据查看 ═══
  private async getStackTrace(params: { threadId?: number; levels?: number; userFramesOnly?: boolean }): Promise<StackTraceResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const threadId = params.threadId ?? this.stoppedInfo?.threadId;
    if (threadId === undefined) throw new Error('No threadId available');
    const resp: any = await this.activeSession.customRequest('stackTrace', { threadId, levels: params.levels ?? 20 });
    let frames: StackFrame[] = (resp.stackFrames || []).map((sf: any) => ({
      id: sf.id, name: sf.name,
      source: { name: sf.source?.name, path: sf.source?.path },
      line: sf.line, column: sf.column,
      isUser: isUserFrame(sf.source?.path),
    }));
    if (params.userFramesOnly) frames = frames.filter((f) => f.isUser);
    return { frames };
  }

  /** 按 scope 分组返回顶层变量。嵌套对象用 getVariableChildren 展开。 */
  private async getVariables(params: { frameId: number }): Promise<VariablesResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const scopesResp: any = await this.activeSession.customRequest('scopes', { frameId: params.frameId });
    const scopes = scopesResp.scopes || [];
    const result: VariableScope[] = [];
    for (const scope of scopes) {
      if (scope.expensive) {
        result.push({ name: scope.name, variables: [], expensive: true });
        continue;
      }
      const varsResp: any = await this.activeSession.customRequest('variables', {
        variablesReference: scope.variablesReference,
      });
      result.push({
        name: scope.name,
        variables: (varsResp.variables || []).map(mapVar),
      });
    }
    return { scopes: result };
  }

  /** 展开嵌套对象/数组:传 variablesReference 拿子变量 */
  private async getVariableChildren(params: { variablesReference: number }): Promise<VariableChildrenResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    if (!params.variablesReference) throw new Error('variablesReference required');
    const resp: any = await this.activeSession.customRequest('variables', {
      variablesReference: params.variablesReference,
    });
    return { variables: (resp.variables || []).map(mapVar) };
  }

  private async setVariable(params: { variablesReference: number; name: string; value: string }): Promise<SetVariableResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const resp: any = await this.activeSession.customRequest('setVariable', params);
    return { value: resp.value, type: resp.type };
  }

  private async setExpression(params: { expression: string; value: string; frameId?: number }): Promise<SetVariableResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const frameId = params.frameId ?? this.stoppedInfo?.frameId;
    const resp: any = await this.activeSession.customRequest('setExpression', {
      frameId, expression: params.expression, value: params.value,
    });
    return { value: resp.value, type: resp.type };
  }

  private async evaluate(params: { expression: string; frameId?: number }): Promise<EvaluateResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const frameId = params.frameId ?? this.stoppedInfo?.frameId;
    const resp: any = await this.activeSession.customRequest('evaluate', {
      expression: params.expression, frameId, context: 'repl',
    });
    return {
      value: truncate(String(resp.result ?? '')),
      type: resp.type || typeof resp.result,
      variablesReference: resp.variablesReference || 0,
    };
  }

  private async getThreads(): Promise<ThreadsResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const resp: any = await this.activeSession.customRequest('threads', {});
    const threads: Thread[] = (resp.threads || []).map((t: any) => ({ id: t.id, name: t.name }));
    return { threads };
  }

  // ═══ v1.2 智能化能力 ═══

  /** 谓词式步进:循环 step 直到表达式为 true、超 maxSteps、或超 timeoutMs。 */
  private async smartStepUntil(params: {
    predicate: string;
    mode?: StepMode;
    maxSteps?: number;
    timeoutMs?: number;
  }): Promise<SmartStepResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    if (!this.stoppedInfo) {
      return { matched: false, steps: 0, reason: 'not-stopped' };
    }
    const mode: StepMode = params.mode ?? 'over';
    const maxSteps = params.maxSteps ?? 50;
    const timeoutMs = params.timeoutMs ?? 30000;
    const dapMethod = mode === 'into' ? 'stepIn' : mode === 'out' ? 'stepOut' : 'next';

    const start = Date.now();
    for (let i = 0; i < maxSteps; i++) {
      const remaining = timeoutMs - (Date.now() - start);
      if (remaining <= 0) {
        return { matched: false, steps: i, reason: 'timeout' };
      }
      if (!this.activeSession || !this.stoppedInfo) {
        return { matched: false, steps: i, reason: 'terminated' };
      }
      const tid = this.stoppedInfo.threadId;
      const stopP = this.makeWaitPromise(remaining);
      try {
        await this.activeSession.customRequest(dapMethod, { threadId: tid });
        await stopP;
      } catch (e: any) {
        if (!this.activeSession) {
          return { matched: false, steps: i, reason: 'terminated' };
        }
        return { matched: false, steps: i, reason: 'timeout', errorMessage: String(e?.message || e) };
      }

      if (!this.stoppedInfo) {
        return { matched: false, steps: i + 1, reason: 'terminated' };
      }
      const fid = this.stoppedInfo.frameId;
      try {
        const r: any = await this.activeSession.customRequest('evaluate', {
          expression: params.predicate, frameId: fid, context: 'watch',
        });
        const raw = r.result;
        const lower = String(raw ?? '').toLowerCase().trim();
        const matched = lower === 'true' || raw === true;
        if (matched) {
          return {
            matched: true,
            steps: i + 1,
            reason: 'matched',
            value: truncate(String(raw ?? '')),
            type: r.type || typeof raw,
            frameId: fid,
            threadId: this.stoppedInfo.threadId,
            file: this.stoppedInfo.file,
            line: this.stoppedInfo.line,
          };
        }
      } catch (e: any) {
        return {
          matched: false,
          steps: i + 1,
          reason: 'error',
          errorMessage: String(e?.message || e),
        };
      }
    }
    return { matched: false, steps: maxSteps, reason: 'maxSteps' };
  }

  /** 阻塞等待下一次 stopped 事件,超时或会话结束抛错。 */
  private async waitForStop(params: { timeoutMs?: number }): Promise<WaitForStopResult> {
    const initial = this.stoppedInfo;
    if (initial) return this.stoppedInfoToResult(initial);
    if (!this.activeSession) {
      return { stopped: false, terminated: true };
    }
    const timeoutMs = params.timeoutMs ?? 30000;
    try {
      await this.makeWaitPromise(timeoutMs);
    } catch {
      if (!this.activeSession) return { stopped: false, terminated: true };
      return { stopped: false, timedOut: true };
    }
    const after = this.stoppedInfo;
    if (!after) return { stopped: false, terminated: true };
    return this.stoppedInfoToResult(after);
  }

  private stoppedInfoToResult(info: StoppedInfo): WaitForStopResult {
    return {
      stopped: true,
      reason: info.reason,
      threadId: info.threadId,
      frameId: info.frameId,
      file: info.file,
      line: info.line,
    };
  }

  // ═══ Watches:每次 stopped 自动 evaluate 并 piggyback ═══
  private async addWatch(params: { expression: string }): Promise<AddWatchResult> {
    if (!params.expression) throw new Error('expression required');
    const id = this.nextWatchId++;
    this.watches.push({ id, expression: params.expression });
    return { id };
  }

  private async removeWatch(params: { id: number }): Promise<{ ok: boolean }> {
    const before = this.watches.length;
    this.watches = this.watches.filter((w) => w.id !== params.id);
    return { ok: this.watches.length < before };
  }

  private async listWatches(): Promise<WatchListResult> {
    return { watches: [...this.watches] };
  }

  private async clearWatches(): Promise<ClearResult> {
    const count = this.watches.length;
    this.watches = [];
    return { ok: true, count };
  }
}
