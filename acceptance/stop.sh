#!/usr/bin/env bash
# 停验收服务（scripts/v2_g10_acceptance.py 起的进程）。
set -euo pipefail
cd "$(dirname "$0")/.."
PIDFILE="acceptance/server.pid"
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" && echo "已停 pid $PID"
  else
    echo "进程 $PID 已不在"
  fi
  rm -f "$PIDFILE"
else
  echo "无 server.pid（服务可能未以 run.sh 启动）"
fi
