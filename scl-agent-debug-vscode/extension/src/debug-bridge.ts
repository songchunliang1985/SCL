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
} from './types';

interface StoppedInfo {
  threadId: number;
  frameId: number;
  reason: string;
  file?: string;
  line?: number;
}

const MAX_VAR_VALUE_LEN = 200;
const MAX_PIGGYBACK_VARS = 30;
const MAX_PIGGYBACK_FRAMES = 5;

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

export class DebugBridge {
  private activeSession: vscode.DebugSession | null = null;
  private stoppedInfo: StoppedInfo | null = null;
  private trackerDisposable: vscode.Disposable | null = null;
  private sendEvent: (event: string, data: unknown) => void;

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
      default:
        throw new Error(`Unknown method: ${msg.method}`);
    }
  }

  dispose(): void {
    this.trackerDisposable?.dispose();
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
            self.sendEvent('terminated', {});
          }
        },
      }),
    });
  }

  /** stopped 时主动拉栈 + 顶层变量，piggyback 推送给 Claude，省 round trip */
  private async handleStopped(session: vscode.DebugSession, body: any): Promise<void> {
    const threadId: number = body.threadId;
    const reason: string = body.reason;

    let frames: StackFrame[] = [];
    let topVars: VariableScope[] = [];
    let topFrameId = 0;
    let file: string | undefined;
    let line: number | undefined;

    try {
      const stResp: any = await session.customRequest('stackTrace', { threadId, levels: MAX_PIGGYBACK_FRAMES });
      const sf = stResp.stackFrames || [];
      frames = sf.map((f: any) => ({
        id: f.id, name: f.name,
        source: { name: f.source?.name, path: f.source?.path },
        line: f.line, column: f.column,
      }));
      if (frames[0]) {
        topFrameId = frames[0].id;
        file = frames[0].source?.path;
        line = frames[0].line;
        const scopesResp: any = await session.customRequest('scopes', { frameId: topFrameId });
        for (const sc of scopesResp.scopes || []) {
          if (sc.expensive) continue;
          const vresp: any = await session.customRequest('variables', {
            variablesReference: sc.variablesReference,
          });
          topVars.push({
            name: sc.name,
            variables: (vresp.variables || []).slice(0, MAX_PIGGYBACK_VARS).map(mapVar),
            expensive: false,
          });
        }
      }
    } catch {
      // 忽略 piggyback 失败 —— 不影响后续 Claude 主动拉
    }

    this.stoppedInfo = { threadId, frameId: topFrameId, reason, file, line };
    this.sendEvent('stopped', {
      threadId, frameId: topFrameId, reason, file, line,
      frames, topScopes: topVars,
    });
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
  private async setBreakpoint(params: { file: string; line: number; condition?: string }): Promise<{ ok: boolean; bp: BreakpointInfo }> {
    const uri = vscode.Uri.file(params.file);
    const loc = new vscode.Location(uri, new vscode.Position(params.line, 0));
    const bp = new vscode.SourceBreakpoint(loc, true, params.condition, undefined, undefined);
    vscode.debug.addBreakpoints([bp]);
    return {
      ok: true,
      bp: { id: 0, file: params.file, line: params.line, enabled: true, condition: params.condition },
    };
  }

  private async setBreakpoints(params: { file: string; lines: number[] }): Promise<{ ok: boolean; count: number }> {
    const uri = vscode.Uri.file(params.file);
    const bps = params.lines.map((line) =>
      new vscode.SourceBreakpoint(new vscode.Location(uri, new vscode.Position(line, 0)), true)
    );
    vscode.debug.addBreakpoints(bps);
    return { ok: true, count: bps.length };
  }

  private async setLogpoint(params: { file: string; line: number; logMessage: string; condition?: string }): Promise<{ ok: boolean }> {
    const uri = vscode.Uri.file(params.file);
    const loc = new vscode.Location(uri, new vscode.Position(params.line, 0));
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

  private async removeBreakpoint(params: { file: string; line: number }): Promise<{ ok: boolean }> {
    const targetPath = vscode.Uri.file(params.file).fsPath;
    const bps = vscode.debug.breakpoints.filter((b) => {
      if (!(b instanceof vscode.SourceBreakpoint)) return false;
      const loc = (b as vscode.SourceBreakpoint).location;
      return loc.uri.fsPath === targetPath && loc.range.start.line === params.line;
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
        return {
          id: i,
          file: sb.location.uri.fsPath,
          line: sb.location.range.start.line,
          enabled: sb.enabled,
          condition: sb.condition,
          logMessage: sb.logMessage,
        };
      }
      return { id: i, file: '', line: 0, enabled: b.enabled };
    });
    return { breakpoints };
  }

  // ═══ 执行控制 ═══
  // 注意：不在这里清 stoppedInfo —— 让 'stopped'/'continued' DAP 事件去更新
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
  private async getStackTrace(params: { threadId?: number; levels?: number }): Promise<StackTraceResult> {
    if (!this.activeSession) throw new Error('No active debug session');
    const threadId = params.threadId ?? this.stoppedInfo?.threadId;
    if (threadId === undefined) throw new Error('No threadId available');
    const resp: any = await this.activeSession.customRequest('stackTrace', { threadId, levels: params.levels ?? 20 });
    const frames: StackFrame[] = (resp.stackFrames || []).map((sf: any) => ({
      id: sf.id, name: sf.name,
      source: { name: sf.source?.name, path: sf.source?.path },
      line: sf.line, column: sf.column,
    }));
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

  /** 展开嵌套对象/数组：传 variablesReference 拿子变量 */
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
}
