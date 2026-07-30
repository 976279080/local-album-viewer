#!/bin/bash
# 无联网相册 - macOS 启动脚本
# 双击运行，启动后自动关闭终端窗口
# 注意：本脚本不检测更新，更新由 restart.py 自动处理

# 获取脚本所在目录（即项目根目录）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# ============================================================
# 隐藏不需要用户看到的文件/文件夹
# ============================================================
chflags hidden "$SCRIPT_DIR/README.md" 2>/dev/null
chflags hidden "$SCRIPT_DIR/version.json" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.user_data" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.trae" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.tests" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.pending_update" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.bin_update" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.bin_backup" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.gitignore" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.workflow" 2>/dev/null
chflags hidden "$SCRIPT_DIR/generate_license.html" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.git" 2>/dev/null

# 每次点击都重启服务：先杀掉旧进程
lsof -ti:8089 | xargs kill -9 2>/dev/null
sleep 0.3

# 直接启动服务器（后台运行）
nohup /usr/bin/python3 "$SCRIPT_DIR/.bin/src/main.py" > /tmp/album_viewer.log 2>&1 &

# 轮询端口，就绪后打开浏览器
for i in $(seq 1 50); do
    if curl -s http://localhost:8089/ > /dev/null 2>&1; then
        open http://localhost:8089
        # 关闭终端窗口
        osascript -e 'tell application "Terminal" to close (every window whose name contains "双击启动_mac")' > /dev/null 2>&1 &
        exit 0
    fi
    sleep 0.1
done

echo "启动失败，查看日志:"
cat /tmp/album_viewer.log
