import * as vscode from 'vscode';
import { WsServer } from './ws-server';
import { DebugBridge } from './debug-bridge';
import { deployBridge, isMcpConfigured, setupClaudeConfig, removeClaudeConfig } from './setup';

let server: WsServer;
let bridge: DebugBridge | null;
let statusBar: vscode.StatusBarItem;
let output: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  output = vscode.window.createOutputChannel('SCL-Agent-debug-VScode');
  context.subscriptions.push(output);
  output.appendLine('[activate] SCL-Agent-debug-VScode starting');

  // 1. 部署 bridge 到 ~/.vscode-debug-agent/mcp-bridge.cjs
  const bridgeSrc = context.asAbsolutePath('bridge/mcp-bridge.cjs');
  try {
    deployBridge(bridgeSrc);
    output.appendLine(`[deploy] bridge from ${bridgeSrc}`);
  } catch (e: any) {
    output.appendLine(`[deploy] FAILED: ${e.message}`);
    vscode.window.showErrorMessage(`SCL-Agent-debug: failed to deploy bridge — ${e.message}`);
  }

  // 2. 启动 WS 服务
  server = new WsServer((line) => output.appendLine(line));
  bridge = new DebugBridge((event, data) => server.sendEvent(event, data));
  server.onRequest((req) => bridge!.handle(req));
  await server.start();
  output.appendLine(`[ws] listening on 127.0.0.1:${server.getPort()}`);

  // 3. 状态栏
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.command = 'sclAgentDebug.toggle';
  context.subscriptions.push(statusBar);
  updateStatusBar();

  // 4. 命令
  context.subscriptions.push(
    vscode.commands.registerCommand('sclAgentDebug.setup', handleSetup),
    vscode.commands.registerCommand('sclAgentDebug.remove', handleRemove),
    vscode.commands.registerCommand('sclAgentDebug.toggle', handleToggle),
    vscode.commands.registerCommand('sclAgentDebug.showLog', () => output.show()),
  );

  // 5. 首次激活引导
  if (!isMcpConfigured()) {
    const action = await vscode.window.showInformationMessage(
      'Claude Code debug integration is not configured. Setup now?',
      'Setup', 'Later'
    );
    if (action === 'Setup') handleSetup();
  }
}

export async function deactivate(): Promise<void> {
  server?.stop();
  bridge?.dispose();
  statusBar?.dispose();
}

async function handleSetup(): Promise<void> {
  const result = setupClaudeConfig();
  if (result.ok) {
    updateStatusBar();
    vscode.window.showInformationMessage(
      `Claude Code debug integration ready. Restart Claude Code (CLI: /exit then claude again) to load 25 debug tools.`
    );
  } else {
    vscode.window.showErrorMessage(result.message);
  }
}

async function handleRemove(): Promise<void> {
  const result = removeClaudeConfig();
  if (result.ok) {
    updateStatusBar();
    vscode.window.showInformationMessage('Claude Code debug integration removed.');
  } else {
    vscode.window.showErrorMessage(result.message);
  }
}

async function handleToggle(): Promise<void> {
  const current = server.isEnabled();
  server.setEnabled(!current);
  updateStatusBar();
  vscode.window.showInformationMessage(`SCL-Agent-debug: ${!current ? 'enabled' : 'paused'}`);
}

function updateStatusBar(): void {
  if (!isMcpConfigured()) {
    statusBar.text = '$(debug-disconnect) SCL-Agent-debug';
    statusBar.tooltip = 'Not configured — click to setup';
    statusBar.backgroundColor = undefined;
  } else if (!server.isEnabled()) {
    statusBar.text = '$(debug-pause) SCL-Agent-debug';
    statusBar.tooltip = 'Paused — click to resume';
    statusBar.backgroundColor = undefined;
  } else {
    statusBar.text = '$(debug-start) SCL-Agent-debug';
    statusBar.tooltip = 'Active — Claude Code can debug';
  }
  statusBar.show();
}
