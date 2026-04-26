#!/bin/bash
cd "$(dirname "$0")"

# 如果已在运行，直接打开浏览器
if lsof -i :5050 -sTCP:LISTEN -t &>/dev/null; then
    echo "Agent 已经在运行，正在打开浏览器..."
    open "http://localhost:5050"
    exit 0
fi

echo "正在启动 Agent..."
python3 app.py &
APP_PID=$!

# 等待服务就绪
for i in {1..20}; do
    sleep 0.5
    if curl -s http://localhost:5050 &>/dev/null; then
        echo "Agent 已启动 (PID: $APP_PID)"
        break
    fi
done

open "http://localhost:5050"

# 关闭终端窗口时自动杀掉 app
trap "echo '正在关闭 Agent...'; kill $APP_PID 2>/dev/null; exit" EXIT INT TERM

# 保持前台运行，关窗口即停止
wait $APP_PID
