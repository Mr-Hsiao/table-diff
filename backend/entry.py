"""表对比工具启动入口。

用法:
  双击 exe / python entry.py        守护模式(Windows 桌面):
      服务未运行 -> 后台静默启动 + 自动打开浏览器
      服务已在运行 -> 直接打开浏览器(不重复启动)
  python entry.py --server          后台服务模式(由守护模式拉起,或手动前台运行)
  python entry.py --stop            停止后台服务(读取 data/server.json)
  容器 / Linux                      直接前台运行服务(TABLE_DIFF_HOST=0.0.0.0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

SERVER_FLAG = "--server"
STOP_FLAG = "--stop"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _data_dir() -> Path:
    from app import db
    return db.DATA_DIR


def _state_file() -> Path:
    return _data_dir() / "server.json"


def _read_state():
    try:
        return json.loads(_state_file().read_text("utf-8"))
    except Exception:
        return None


def _health(port: int, timeout: float = 2.0) -> bool:
    """健康检查:确认该端口上是本服务(而不是别的程序)。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            return r.status == 200 and "table-diff" in r.read().decode("utf-8", "ignore")
    except Exception:
        return False


def _running():
    """返回 (port, is_running)。"""
    st = _read_state()
    if not st or not st.get("port"):
        return None, False
    port = int(st["port"])
    return port, _health(port)


def _open_browser(port: int):
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception:
        pass


def _msg(title: str, text: str):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
            return
        except Exception:
            pass
    print(f"{title}: {text}")


def server_mode():
    """后台服务模式:无控制台时把日志写到 data/server.log,然后前台阻塞运行。"""
    if _frozen() and sys.stdout is None:
        try:
            _data_dir().mkdir(parents=True, exist_ok=True)
            logp = _data_dir() / "server.log"
            sys.stdout = open(logp, "a", encoding="utf-8")
            sys.stderr = sys.stdout
        except Exception:
            pass
    from app.main import run_server
    run_server()


def stop_mode():
    st = _read_state()
    if not st or not st.get("pid"):
        _msg("表对比工具", "服务没有在运行。")
        return
    pid = int(st["pid"])
    import signal
    killed = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
            killed = True
            break
        except Exception:
            continue
    if not killed and os.name == "nt":
        # 兜底:taskkill(不捕获输出,避免管道限制)
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
            killed = True
        except Exception:
            pass
    try:
        _state_file().unlink(missing_ok=True)
    except Exception:
        pass
    if killed:
        _msg("表对比工具", "服务已停止。下次双击 exe 会重新启动。")
    else:
        _msg("表对比工具", "停止服务失败,请在任务管理器中结束 table-diff 进程。")


def launcher_mode():
    """守护模式:服务未启动则后台拉起并自动打开浏览器;已启动则只打开浏览器。"""
    port, running = _running()
    if running:
        _open_browser(port)
        return

    # 拉起后台服务(隐藏窗口)
    try:
        if _frozen():
            cmd = [sys.executable, SERVER_FLAG]
        else:
            cmd = [sys.executable, str(Path(__file__).resolve()), SERVER_FLAG]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    except Exception as e:
        _msg("表对比工具", f"服务启动失败: {e}")
        return

    # 等待服务就绪(最多 20 秒),然后打开浏览器
    for _ in range(40):
        time.sleep(0.5)
        port, running = _running()
        if running:
            _open_browser(port)
            return
    _msg("表对比工具", "服务启动超时,请查看 data/server.log 排查。")


def main():
    args = set(sys.argv[1:])
    if STOP_FLAG in args:
        stop_mode()
        return
    # 容器 / Linux / 显式 --server:直接前台运行服务
    if os.name != "nt" or os.environ.get("TABLE_DIFF_HOST") == "0.0.0.0" or SERVER_FLAG in args:
        server_mode()
        return
    launcher_mode()


if __name__ == "__main__":
    main()
