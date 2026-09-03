#!/usr/bin/env bash
# G10 验收一键编排：机械前置 → 起验收服务 → HTTP 面 → UI 面
# （Playwright 自动操作 + 截图存证）→ 人工面提示。
#
# 用法：  bash acceptance/run.sh [port]     （缺省 8000）
# 收尾：  bash acceptance/stop.sh
# 人工面：服务保持运行；浏览器打开提示的 URL 做视觉判定
#         （docs/v2/gates/G10-test-acceptance-plan.md Step 4）。
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${1:-8000}"
LOG="acceptance/server.log"
PIDFILE="acceptance/server.pid"
rm -f "$LOG"

echo "== [1/5] 机械前置（preflight：环境 + 3205 套件 + 纪律面）=="
PYTHONPATH=. .venv/bin/python acceptance/preflight.py || {
  echo "preflight 红——停（详见 acceptance/preflight-report.json）"; exit 1;
}

echo "== [2/5] 启动验收服务（port $PORT；galgame 样例世界源）=="
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "已有验收服务运行（pid $(cat "$PIDFILE")）——复用"; 
else
  PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py \
    --port "$PORT" >"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
fi

SID=""
for _ in $(seq 1 60); do
  SID="$(sed -n 's/^SESSION_ID=//p' "$LOG" 2>/dev/null | head -1)"
  [ -n "$SID" ] && break
  sleep 0.5
done
if [ -z "$SID" ]; then
  echo "服务未就绪——停（$LOG 尾部）"; tail -5 "$LOG"; exit 1;
fi

.venv/bin/python - "$PORT" "$SID" <<'EOF'
import socket, sys, time
port = int(sys.argv[1])
sid = sys.argv[2]
for _ in range(60):
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            break
    time.sleep(0.5)
else:
    raise SystemExit(f"端口 {port} 未监听")
print(f"  服务监听中 http://127.0.0.1:{port}  session={sid[:12]}…")
EOF

echo "== [3/5] HTTP 面检查（路由 / 信封 / 推进 / 图像确定性）=="
.venv/bin/python acceptance/http_check.py --port "$PORT" --session "$SID" \
  || echo "HTTP 面有红项（继续 UI 面；详见 http-report.json）"

echo "== [4/5] UI 面自动检查（Playwright headless + 截图存证）=="
.venv-acceptance/bin/python acceptance/ui_check.py --port "$PORT" \
  --session "$SID" || echo "UI 面有红项（详见 ui-report.json）"

echo
echo "== [5/5] 自动化完成 —— 人工面（S11，判定人 = 你）=="
echo "  浏览器打开:  http://127.0.0.1:$PORT/"
echo "  会话 ID:     $SID"
echo "  操作步骤与判定点见 docs/v2/gates/G10-test-acceptance-plan.md"
echo "  Step 3.2–3.4（G10-5/6/7 判定）+ 3.5 记录格式。"
echo "  自动截图存证: docs/v2/gates/evidence-g10/ui-*.png"
echo "  停止服务:     bash acceptance/stop.sh"
