# -*- coding: utf-8 -*-
"""启动「可被脚本控制」的浏览器 —— 只用独立 user-data-dir，绝不动日常 profile。

为什么必须独立 profile（真实事故）：
  曾用用户日常 profile + 调试端口启动，导致用户正在编辑的猎聘简历页被覆盖成空白。
  独立 profile 的代价只是「首次要在弹出的窗口里登录一次」，登录态会持久化。

另一个真实坑：ChromeCoreSvr.exe 常驻时会吞掉启动参数，导致端口起不来。
  该进程权限高，Stop-Process 会 Access is denied —— 不要硬杀，让用户从托盘退出。
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

IS_WIN = os.name == "nt"

# 常见浏览器可执行文件（按优先级）。ChromeCore 是本机实测可用的那个；
# 换成标准 Chrome/Edge 同样可用（参数一致）。
CANDIDATES = [
    r"D:\chrome谷歌浏览器\ChromeCore\ChromeCore.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 会吞掉启动参数的常驻服务进程名（只提示，不杀）
HIJACKERS = ["ChromeCoreSvr"]


def find_browser(explicit=None):
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("JOBAUTO_BROWSER")
    if env and os.path.isfile(env):
        return env
    for p in CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def port_alive(port=9222, timeout=1.5):
    """调试端口是否可用，返回 (bool, version_dict|None)。"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ) as r:
            return True, json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return False, None


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def running_hijackers():
    if not IS_WIN:
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        ).stdout or ""
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        name = line.split(",")[0].strip('" ')
        for h in HIJACKERS:
            if name.lower().startswith(h.lower()):
                found.append(name)
    return sorted(set(found))


def launch(browser=None, port=9222, profile=None, wait=40, extra=None):
    """启动带调试端口的独立浏览器实例。

    返回 dict：{ok, browser, port, profile, version, notes[]}
    """
    notes = []
    ok, ver = port_alive(port)
    if ok:
        notes.append(f"端口 {port} 已在服务，无需重复启动")
        return {"ok": True, "browser": None, "port": port,
                "profile": None, "version": ver, "notes": notes}

    exe = find_browser(browser)
    if not exe:
        return {"ok": False, "error": "找不到浏览器可执行文件，请用 --browser 指定",
                "tried": CANDIDATES, "notes": notes}

    if port_in_use(port):
        return {"ok": False,
                "error": f"端口 {port} 被别的程序占用（不是调试端口），换 --port",
                "notes": notes}

    hk = running_hijackers()
    if hk:
        notes.append(
            "检测到常驻服务 " + "/".join(hk) +
            "：它会吞掉调试端口参数。若下面端口起不来，"
            "请让用户从托盘图标右键「退出」后重试（不要用 Stop-Process 硬杀）。"
        )

    profile = profile or os.path.join(
        os.environ.get("JOBAUTO_HOME", os.path.expanduser("~/.jobauto")), "profile"
    )
    os.makedirs(profile, exist_ok=True)

    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
    ] + list(extra or [])

    creation = 0x00000008 if IS_WIN else 0  # DETACHED_PROCESS
    creation |= 0x00000200 if IS_WIN else 0  # CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=creation,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)

    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(1.5)
        ok, ver = port_alive(port)
        if ok:
            notes.append("端口就绪")
            return {"ok": True, "browser": exe, "port": port,
                    "profile": profile, "version": ver, "notes": notes}

    return {"ok": False,
            "error": f"等待 {wait}s 端口 {port} 仍未就绪",
            "browser": exe, "profile": profile, "notes": notes}


def doctor(browser=None, port=9222):
    """只读自检：把「能不能干活」的原因一次性说清。"""
    rep = {"port": port, "python": sys.version.split()[0]}
    ok, ver = port_alive(port)
    rep["port_ok"] = ok
    rep["browser_version"] = (ver or {}).get("Browser")
    rep["browser_exe_found"] = find_browser(browser)
    rep["hijackers_running"] = running_hijackers()
    hints = []
    if not ok:
        hints.append("端口未就绪 → 跑 scripts/启动_可控制浏览器.bat 或 jobauto.py launch")
    if rep["hijackers_running"]:
        hints.append("有常驻服务在跑，端口起不来时让用户从托盘退出它")
    if not rep["browser_exe_found"]:
        hints.append("没找到浏览器，用 --browser 或设 JOBAUTO_BROWSER 环境变量")
    rep["hints"] = hints
    rep["ready"] = bool(ok)
    return rep


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="启动/自检可控制浏览器")
    ap.add_argument("cmd", choices=["launch", "doctor"], nargs="?", default="doctor")
    ap.add_argument("--browser", default=None)
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--wait", type=int, default=40)
    a = ap.parse_args()
    fn = launch if a.cmd == "launch" else doctor
    kw = dict(browser=a.browser, port=a.port)
    if a.cmd == "launch":
        kw.update(profile=a.profile, wait=a.wait)
    print(json.dumps(fn(**kw), ensure_ascii=False, indent=2))
