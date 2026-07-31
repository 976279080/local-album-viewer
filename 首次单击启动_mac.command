#!/bin/bash
# 无联网相册 - macOS 启动脚本
# 双击运行，启动后自动关闭终端窗口（快速路径：不检测更新）
# 注意：如果双击提示"来自身份不明的开发者"，请右键选择"打开"一次
#       或在终端执行：xattr -dr com.apple.quarantine "首次单击启动_mac.command"

# 一、自身先移除 macOS quarantine 属性（即使是用户手动双击也能生效）
xattr -dr com.apple.quarantine "$0" 2>/dev/null

# 获取脚本所在目录（即项目根目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# 权限检查：macOS TCC 保护 Downloads/Desktop/Documents 等文件夹
# 若终端无访问权限（用户曾点过"拒绝"），给出明确提示而非 Operation not permitted
# ============================================================
if [ ! -r "$SCRIPT_DIR/.bin/src/main.py" ]; then
    echo "========================================"
    echo "无法访问项目目录（macOS 权限限制）"
    echo "========================================"
    echo ""
    echo "项目路径: $SCRIPT_DIR"
    echo ""
    echo "原因：macOS 对 下载/桌面/文稿 等文件夹有隐私保护，"
    echo "     终端首次访问会弹窗询问，若点了"拒绝"则无法运行。"
    echo ""
    echo "解决方法（任选其一）："
    echo "  1. 把整个项目文件夹从"下载"移动到其他位置（如家目录、应用程序）"
    echo "  2. 打开 系统设置 → 隐私与安全性 → 文件和文件夹 → 终端 → 勾选"下载文件夹""
    echo "  3. 打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 添加 终端"
    echo ""
    echo "按回车键关闭此窗口..."
    read
    exit 1
fi

# ============================================================
# 一、清理无用文件（只删这一个：.release/.bin.zip 下载后解压完就无用
# ============================================================
rm -f "$SCRIPT_DIR/.release/.bin.zip" 2>/dev/null

# ============================================================
# 二、白名单隐藏：根目录只保留：
#   ✅ 首次单击启动_mac.command / data
#   其他所有文件/文件夹一律隐藏（包括 双击启动_windows.vbs / .user_data / .bin / .release / version.json / README.md / .git 等）
# ============================================================
MAC_LAUNCHER="首次单击启动_mac.command"
DATA_DIR_NAME="data"

for item in "$SCRIPT_DIR"/* "$SCRIPT_DIR"/.*; do
    # 跳过 "." 和 ".." 本身
    case "$item" in
        "$SCRIPT_DIR/."|"$SCRIPT_DIR/..") continue ;;
    esac
    [ -e "$item" ] || continue
    name="$(basename "$item")"

    # 白名单判断（用字符串比较，避免 case 模式匹配的歧义）
    # mac 上只保留 mac 启动器和 data 目录；windows 启动器(.vbs)在 mac 上隐藏
    if [ "$name" = "$MAC_LAUNCHER" ] || [ "$name" = "$DATA_DIR_NAME" ]; then
        chflags nohidden "$item" 2>/dev/null
        continue
    fi
    # 其它一律隐藏
    chflags hidden "$item" 2>/dev/null
done

# 每次点击都重启服务：先杀掉旧进程（8089 和备用 8090）
lsof -ti:8089 | xargs kill -9 2>/dev/null
lsof -ti:8090 | xargs kill -9 2>/dev/null
sleep 0.1

# 选择可用的 python3：优先用户安装的（Homebrew 等），最后回退到 /usr/bin
for PY in /usr/local/bin/python3 /opt/homebrew/bin/python3 "$HOME/.pyenv/shims/python3" /usr/bin/python3; do
    if [ -x "$PY" ]; then
        break
    fi
done

# 直接启动服务器（后台运行，脱离终端会话以避免退出终端时被杀）
LOG_FILE="$SCRIPT_DIR/.user_data/album_viewer.log"
mkdir -p "$SCRIPT_DIR/.user_data"
nohup "$PY" "$SCRIPT_DIR/.bin/src/main.py" > "$LOG_FILE" 2>&1 &
disown %1 2>/dev/null

# 轮询端口，就绪后打开浏览器（8089 端口优先，备用 8090）
# 用 /api/summary 作为就绪探针，确保服务完整就绪后再打开浏览器
for p in 8089 8090; do
    first=1
    for i in $(seq 1 50); do
        if [ "$first" = "1" ]; then
            first=0
        else
            sleep 0.15
        fi
        if curl -sfS "http://localhost:$p/api/summary" > /dev/null 2>&1; then
            open "http://localhost:$p"
            # 关闭终端窗口（只关当前启动这个）
            osascript -e 'tell application "Terminal" to close (every window whose name contains "首次单击启动_mac")' > /dev/null 2>&1 &
            exit 0
        fi
    done
done

echo "启动失败，查看日志:"
cat "$LOG_FILE" 2>/dev/null
