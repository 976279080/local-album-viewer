#!/bin/bash
# 无联网相册 - macOS 启动脚本
# 双击运行，启动后自动关闭终端窗口

# 获取脚本所在目录（即项目根目录）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# ============================================================
# 一、应用待处理的更新（下载好的 .bin_update → .bin）
# 时机：程序还没启动 → .bin 未被占用 → 可以安全移动/替换
# ============================================================
PENDING_MARKER="$SCRIPT_DIR/.pending_update"
BIN_DIR="$SCRIPT_DIR/.bin"
BIN_UPDATE_DIR="$SCRIPT_DIR/.bin_update"
BIN_BACKUP_DIR="$SCRIPT_DIR/.bin_backup"

if [ -f "$PENDING_MARKER" ] && [ -d "$BIN_UPDATE_DIR" ]; then
    # 先确保 8089 端口（旧进程）被释放，防止目录内文件还在占用
    lsof -ti:8089 | xargs kill -9 2>/dev/null
    sleep 0.5

    # 1. 备份当前版本（保留一份可回退）
    if [ -d "$BIN_DIR" ]; then
        rm -rf "$BIN_BACKUP_DIR"
        mv "$BIN_DIR" "$BIN_BACKUP_DIR"
        if [ $? -ne 0 ]; then
            echo "[更新] 备份 .bin 失败，中止本次更新，继续启动当前版本"
        else
            # 2. 新版本就位
            mv "$BIN_UPDATE_DIR" "$BIN_DIR"
            if [ $? -eq 0 ]; then
                # 3. 成功则清除标记
                rm -f "$PENDING_MARKER"
                echo "[更新] 更新完成，已备份旧版本到 .bin_backup，可手动改回用于回退"
            else
                # 替换失败：回滚备份
                echo "[更新] 新版本替换失败，回滚到备份版本"
                rm -rf "$BIN_UPDATE_DIR"
                if [ -d "$BIN_BACKUP_DIR" ]; then
                    mv "$BIN_BACKUP_DIR" "$BIN_DIR"
                fi
            fi
        fi
    else
        # .bin 居然不存在 → 直接用更新包
        mv "$BIN_UPDATE_DIR" "$BIN_DIR"
        if [ $? -eq 0 ]; then
            rm -f "$PENDING_MARKER"
            echo "[更新] 新版本就位"
        fi
    fi
fi

# ============================================================
# 二、隐藏不需要用户看到的文件/文件夹
# ============================================================
# 点号开头的文件 macOS 默认已隐藏，这里处理非点开头和更新相关目录
chflags hidden "$SCRIPT_DIR/README.md" 2>/dev/null
chflags hidden "$SCRIPT_DIR/version.json" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.user_data" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.trae" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.tests" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.pending_update" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.bin_update" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.bin_backup" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.gitignore" 2>/dev/null
chflags hidden "$SCRIPT_DIR/.release" 2>/dev/null
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
