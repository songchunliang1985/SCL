import * as http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { randomBytes } from 'crypto';
import { writeFileSync, existsSync, mkdirSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';
import type { Message, Request, Response, AgentEvent } from './types';

const PORT = 19527;
const AGENT_DIR = join(homedir(), '.vscode-debug-agent');

type MessageHandler = (msg: Request) => Promise<unknown>;

export class WsServer {
  private wss: WebSocketServer | null = null;
  private token: string = '';
  private enabled = true;
  private handler: MessageHandler | null = null;
  private eventSender: ((event: string, data: unknown) => void) | null = null;
  private log: (line: string) => void;

  constructor(log: (line: string) => void = () => {}) {
    this.token = randomBytes(16).toString('hex');
    this.log = log;
  }

  /** 设置请求处理器 */
  onRequest(handler: MessageHandler): void {
    this.handler = handler;
  }

  /** 设置事件发送回调，由 extension.ts 注入 */
  onSendEvent(cb: (event: string, data: unknown) => void): void {
    this.eventSender = cb;
  }

  /** 启动 WS 服务 */
  async start(): Promise<void> {
    if (!existsSync(AGENT_DIR)) {
      mkdirSync(AGENT_DIR, { recursive: true, mode: 0o700 });
    }

    // 写入 token
    writeFileSync(join(AGENT_DIR, 'token'), this.token, { mode: 0o600 });

    const server = http.createServer((_req, res) => {
      res.writeHead(200);
      res.end('vscode-debug-agent');
    });

    this.wss = new WebSocketServer({ server });

    this.wss.on('connection', (ws: WebSocket, req: http.IncomingMessage) => {
      const url = new URL(req.url || '/', 'http://127.0.0.1');
      const tok = url.searchParams.get('token');
      if (tok !== this.token) {
        this.log('[ws] rejected connection (bad token)');
        ws.close(4001, 'Unauthorized');
        return;
      }
      this.log('[ws] client connected');

      ws.on('message', async (raw: Buffer) => {
        let msg: Message;
        try {
          msg = JSON.parse(raw.toString()) as Message;
        } catch {
          return;
        }

        if ('method' in msg && this.handler) {
          if (!this.enabled) {
            this.send(ws, { id: msg.id, error: { code: -1, message: 'Agent paused' } });
            return;
          }
          this.log(`[req] ${(msg as Request).method}`);
          try {
            const result = await this.handler(msg as Request);
            this.send(ws, { id: msg.id, result });
          } catch (err: any) {
            this.log(`[req] ${(msg as Request).method} ERROR: ${err.message}`);
            this.send(ws, { id: msg.id, error: { code: -1, message: err.message } });
          }
        }
      });

      ws.on('close', () => this.log('[ws] client disconnected'));
    });

    return new Promise<void>((resolve, reject) => {
      server.on('error', (err) => {
        this.log(`[ws] listen error: ${err.message}`);
        reject(err);
      });
      server.listen(PORT, '127.0.0.1', () => resolve());
    });
  }

  /** 推送事件到所有连接的客户端 */
  sendEvent(event: string, data: unknown): void {
    if (!this.wss) return;
    const msg: AgentEvent = { event, data };
    const raw = JSON.stringify(msg);
    this.wss.clients.forEach((c: WebSocket) => {
      if (c.readyState === WebSocket.OPEN) c.send(raw);
    });
    this.eventSender?.(event, data);
  }

  /** 暂停/恢复 */
  setEnabled(v: boolean): void {
    this.enabled = v;
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  /** 停止服务 */
  stop(): void {
    this.wss?.close();
    this.wss = null;
  }

  /** 获取 port */
  getPort(): number {
    return PORT;
  }

  /** 获取 agent 目录 */
  getAgentDir(): string {
    return AGENT_DIR;
  }

  private send(ws: WebSocket, msg: Response): void {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }
}
