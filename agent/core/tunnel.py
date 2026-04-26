"""Cloudflared 内网穿透隧道管理"""
import subprocess
import config as cfg


class TunnelManager:
    """封装内网穿透隧道的启动与状态查询。"""

    def __init__(self):
        self._tunnel_proc = None
        self._caffeinate_proc = None
        self._tunnel_url = None

    def _send_email(self, url: str):
        if not cfg.NOTIFY_EMAIL or not url:
            return
        try:
            import smtplib
            from email.mime.text import MIMEText
            subject = "Dragon Agent 公网地址已更新"
            body = f"Dragon Agent 新公网地址：\n\n{url}\n\n手机浏览器打开即可使用。\n地址在隧道关闭或重启后失效。"
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = cfg.SMTP_USER
            msg["To"] = cfg.NOTIFY_EMAIL
            with smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT) as smtp:
                smtp.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
                smtp.send_message(msg)
            print(f"[Tunnel] 邮件已发送至 {cfg.NOTIFY_EMAIL}", flush=True)
        except Exception as e:
            print(f"[Tunnel] 邮件发送失败: {e}", flush=True)

    @staticmethod
    def _read_tunnel_url() -> str | None:
        try:
            import re
            url = None
            with open("/tmp/cloudflared.log", "r") as f:
                for line in f:
                    m = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
                    if m:
                        url = m.group(1)
            return url
        except Exception:
            pass
        return None

    def start(self) -> str | None:
        import time
        subprocess.run(["pkill", "-f", "cloudflared tunnel"], capture_output=True)
        self._caffeinate_proc = subprocess.Popen(
            ["caffeinate", "-dis"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("[Tunnel] caffeinate 已启动（防休眠）", flush=True)
        log = open("/tmp/cloudflared.log", "w")
        self._tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{cfg.WEB_PORT}"],
            stdout=log, stderr=log,
        )
        print("[Tunnel] cloudflared 启动中...", flush=True)
        for _ in range(20):
            time.sleep(0.5)
            url = self._read_tunnel_url()
            if url:
                self._tunnel_url = url
                print(f"[Tunnel] 公网地址: {url}", flush=True)
                self._send_email(url)
                return url
        print("[Tunnel] 等待超时，未获取到公网地址", flush=True)
        return None

    @property
    def is_alive(self) -> bool:
        return self._tunnel_proc is not None and self._tunnel_proc.poll() is None

    @property
    def url(self) -> str | None:
        return self._tunnel_url if self.is_alive else None
