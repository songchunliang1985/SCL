"""Gunicorn 生产部署配置。安装：pip install gunicorn gevent"""
workers = 2
worker_class = "gevent"
worker_connections = 50
bind = "0.0.0.0:5050"
timeout = 180          # SSE 长连接需要较长超时
keepalive = 5
accesslog = "-"        # 访问日志输出到 stdout
errorlog = "-"
loglevel = "info"
