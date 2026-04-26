#!/bin/bash
PID=$(lsof -i :5050 -sTCP:LISTEN -t 2>/dev/null)
if [ -n "$PID" ]; then
    kill -9 $PID
    echo "Agent 已停止 (PID: $PID)"
else
    echo "Agent 未在运行"
fi
