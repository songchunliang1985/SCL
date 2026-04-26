import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';

const HOME = homedir();
// Claude Code 2.x 真正读取的位置（顶层 mcpServers）
const CLAUDE_JSON = join(HOME, '.claude.json');
// 老版本可能写到这里 —— 装/卸时顺手清理，避免双份
const LEGACY_SETTINGS = join(HOME, '.claude', 'settings.json');

const AGENT_DIR = join(HOME, '.vscode-debug-agent');
const BRIDGE_DEST = join(AGENT_DIR, 'mcp-bridge.cjs');

const MCP_KEY = 'scl-agent-debug-vscode';
// 重命名前的旧 key，安装/卸载时一起清理
const LEGACY_MCP_KEYS = ['vscode-debug'];

const MCP_ENTRY = {
  type: 'stdio' as const,
  command: 'node',
  args: [BRIDGE_DEST],
  env: {} as Record<string, string>,
};

function readJson(path: string): any {
  if (!existsSync(path)) return null;
  try { return JSON.parse(readFileSync(path, 'utf-8')); } catch { return null; }
}

function writeJson(path: string, obj: any): void {
  writeFileSync(path, JSON.stringify(obj, null, 2) + '\n', { mode: 0o600 });
}

/** 把 bridge 拷贝到 ~/.vscode-debug-agent/ */
export function deployBridge(bridgeSourcePath: string): void {
  if (!existsSync(AGENT_DIR)) mkdirSync(AGENT_DIR, { recursive: true, mode: 0o700 });
  copyFileSync(bridgeSourcePath, BRIDGE_DEST);
}

/** 检查 ~/.claude.json 中是否已注册当前 MCP，且指向当前 bridge 路径 */
export function isMcpConfigured(): boolean {
  const j = readJson(CLAUDE_JSON);
  return j?.mcpServers?.[MCP_KEY]?.args?.[0] === BRIDGE_DEST;
}

function purgeLegacy(j: any): boolean {
  if (!j?.mcpServers) return false;
  let changed = false;
  for (const k of LEGACY_MCP_KEYS) {
    if (j.mcpServers[k]) {
      delete j.mcpServers[k];
      changed = true;
    }
  }
  if (changed && Object.keys(j.mcpServers).length === 0) delete j.mcpServers;
  return changed;
}

/** 一键写入 ~/.claude.json，并清理老 key + 老版 settings.json 中的残留 */
export function setupClaudeConfig(): { ok: boolean; message: string } {
  const j = readJson(CLAUDE_JSON) ?? {};
  j.mcpServers = j.mcpServers || {};
  // 清掉旧 key（重命名前的 vscode-debug）
  for (const k of LEGACY_MCP_KEYS) delete j.mcpServers[k];
  j.mcpServers[MCP_KEY] = MCP_ENTRY;
  writeJson(CLAUDE_JSON, j);

  // 老版 settings.json 中的所有相关 key 也清掉（含旧 key 和当前 key）
  const legacy = readJson(LEGACY_SETTINGS);
  if (legacy) {
    let touched = purgeLegacy(legacy);
    if (legacy?.mcpServers?.[MCP_KEY]) {
      delete legacy.mcpServers[MCP_KEY];
      if (Object.keys(legacy.mcpServers).length === 0) delete legacy.mcpServers;
      touched = true;
    }
    if (touched) writeJson(LEGACY_SETTINGS, legacy);
  }

  return { ok: true, message: `MCP configured at ${CLAUDE_JSON} as "${MCP_KEY}"` };
}

/** 反向操作：从两处配置都把当前 key 和老 key 全部清除 */
export function removeClaudeConfig(): { ok: boolean; message: string } {
  let removed = 0;
  for (const path of [CLAUDE_JSON, LEGACY_SETTINGS]) {
    const j = readJson(path);
    if (!j) continue;
    let touched = purgeLegacy(j);
    if (j?.mcpServers?.[MCP_KEY]) {
      delete j.mcpServers[MCP_KEY];
      if (Object.keys(j.mcpServers).length === 0) delete j.mcpServers;
      touched = true;
    }
    if (touched) {
      writeJson(path, j);
      removed++;
    }
  }
  return { ok: true, message: removed > 0 ? `Cleaned ${removed} config file(s)` : 'No config to clean' };
}
