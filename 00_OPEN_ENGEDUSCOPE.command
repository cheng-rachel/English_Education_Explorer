#!/bin/bash
# Double-click in Finder. Uses only macOS tools and the project's existing venv.

fail() {
    printf '\n%s\n' "$1"
    if [ -t 0 ]; then
        printf '按回车键退出；上方错误信息会保留在终端中。'
        read -r _reply
    fi
    exit 1
}

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" || fail '无法定位项目目录。'
cd "$PROJECT_DIR" || fail '无法打开项目目录，请检查文件夹权限。'
URL='http://127.0.0.1:8501'

[ -x '.venv/bin/python' ] || fail '没有找到可用的 .venv 环境。请先按项目 README.md 的 Quick Start 完成环境安装，再双击此文件。'
[ -f '03app/00_app.py' ] || fail '没有找到应用文件，请将此启动文件放在 English Education Explorer 项目根目录。'

healthy() {
    [ "$(/usr/bin/curl --noproxy '*' --fail --silent --max-time 1 "$URL/_stcore/health")" = 'ok' ]
}

open_browser() {
    /usr/bin/open "$URL" || printf '\n浏览器未能自动打开，请手动访问：%s\n' "$URL"
}

# A different service on this port must not be mistaken for this application.
LISTENERS="$(/usr/sbin/lsof -nP -t -iTCP:8501 -sTCP:LISTEN 2>/dev/null)"
if [ -n "$LISTENERS" ]; then
    for pid in $LISTENERS; do
        case "$(/bin/ps -p "$pid" -o command=)" in
            *streamlit*run*03app/00_app.py*) ;;
            *) fail '8501 端口正被其他程序使用。请先关闭占用该端口的程序，再重新启动。' ;;
        esac
    done
    printf 'English Education Explorer · 英探探：英语学习与教育探索器已在运行，正在打开浏览器……\n'
    for ((attempt = 0; attempt < 30; attempt++)); do
        if healthy; then
            open_browser
            exit 0
        fi
        sleep 1
    done
    fail '检测到已有英探探，但尚未正常响应。请查看原启动终端的错误信息，关闭该实例后重试。'
fi

APP_PID=''
cleanup() {
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        kill "$APP_PID" 2>/dev/null
        wait "$APP_PID" 2>/dev/null
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

printf '正在启动 English Education Explorer · 英探探：英语学习与教育探索器……\n项目目录：%s\n' "$PROJECT_DIR"
.venv/bin/python -B -m streamlit run 03app/00_app.py \
    --server.address 127.0.0.1 --server.port 8501 --server.headless true &
APP_PID=$!

for ((attempt = 0; attempt < 30; attempt++)); do
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        wait "$APP_PID"
        code=$?
        APP_PID=''
        fail "英探探启动失败（退出码 $code）。请查看上方错误，并按 README.md 检查环境。"
    fi
    if healthy; then
        printf '\nEnglish Education Explorer · 英探探：英语学习与教育探索器已就绪：%s\n保持此终端窗口打开；关闭窗口或按 Control+C 可停止本次启动的应用。\n' "$URL"
        open_browser
        wait "$APP_PID"
        code=$?
        APP_PID=''
        [ "$code" -eq 0 ] || fail "英探探已停止（退出码 $code），请查看上方错误信息。"
        exit 0
    fi
    sleep 1
done
cleanup
APP_PID=''
fail '启动等待超时。请查看上方错误信息，按 README.md 检查环境后重试。'
