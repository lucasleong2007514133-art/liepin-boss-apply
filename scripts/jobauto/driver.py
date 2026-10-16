# -*- coding: utf-8 -*-
"""webctl2.py 的 Python 封装 —— 所有页面动作都走这里，便于回读校验。

设计纪律（踩过坑才写下的）：
  * 除 tabs 外所有动作必须显式 --index，强迫先看清标签页再动手（禁止覆盖用户标签）
  * 复杂 JS 一律写临时文件用 `js` 执行 —— PowerShell/命令行会把引号吃掉
  * eval 的返回值可能是 JSON，尽力解析；解析不了就返回原文
  * 每个动作都返回 (ok, payload)，不抛异常，让上层决定怎么处理
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(os.path.dirname(HERE), "driver", "webctl2.py")
PY = sys.executable or "python"

EXIT_HINTS = {
    1: "连不上调试端口（浏览器没起 / 被常驻服务吞了参数）",
    2: "命令不支持",
    3: "没有标签页",
    4: "缺 --index（本工具强制显式指定，避免误伤用户标签）",
    5: "--index 越界",
}


class Driver:
    def __init__(self, port=9222, index=0, timeout=120):
        self.port = str(port)
        self.index = index
        self.timeout = timeout

    # ---------- 底层 ----------
    def raw(self, *args, timeout=None, index=None):
        """跑一条 webctl2 命令，返回 (exitcode, stdout, stderr)。"""
        cmd = [PY, DRIVER] + [str(x) for x in args]
        # 需要 index 的命令自动补 --index（tabs/close 除外）
        if args and args[0] not in ("tabs", "close"):
            if "--index" not in [str(x) for x in args]:
                idx = self.index if index is None else index
                cmd += ["--index", str(idx)]
        if "--port" not in [str(x) for x in args]:
            cmd += ["--port", self.port]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout or self.timeout,
                encoding="utf-8", errors="replace",
            )
            return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            return 124, "", f"TIMEOUT({timeout or self.timeout}s)"

    def _run(self, *args, timeout=None, index=None):
        code, out, err = self.raw(*args, timeout=timeout, index=index)
        if code != 0:
            hint = EXIT_HINTS.get(code, "")
            msg = err or out or f"exit {code}"
            return False, {"error": msg, "exit": code, "hint": hint}
        return True, out

    # ---------- 读 ----------
    def tabs(self):
        """列出标签页。webctl2 tabs 直接输出 JSON 数组（实测），也兼容 'N | 标题 | URL' 文本。"""
        ok, out = self._run("tabs")
        if not ok:
            return out
        rows = _try_json(out)
        if isinstance(rows, list):
            norm = []
            for r in rows:
                if isinstance(r, dict):
                    r.setdefault("index", None)
                    norm.append(r)
                else:
                    norm.append({"raw": str(r)})
            return norm
        # 兜底：文本表格
        parsed = []
        for line in (out or "").splitlines():
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) >= 3:
                parsed.append({"index": int(parts[0]), "title": parts[1], "url": parts[2]})
            else:
                parsed.append({"raw": line})
        return parsed

    def eval(self, expr, index=None, parse=True, timeout=None):
        ok, out = self._run("eval", expr, index=index, timeout=timeout)
        if not ok:
            return None
        if not parse:
            return out
        return _try_json(out)

    def js(self, script, index=None, parse=True, timeout=None):
        """执行 JS 文件内容（自动落临时文件，免转义）。

        ★ 实测坑：webctl2 的 `js` 走的是 **函数体** 语义（acts.cmd_js → CDP.eval_async，
        相当于 `new AsyncFunction(body)`），传一个 IIFE 表达式进去只会求值成函数对象，
        于是输出恒为 None。本封装自动兼容两种写法：
          * 形如 `(() => {...})()` 的 IIFE 表达式 → 包成 `return (...)`
          * 已经是 `return ...;` 的函数体      → 原样透传

        ★ 实测坑：这个内核上页面 JS 抛出异常时，webctl2 只会把错误打到 stderr 并以
        exit 1 结束；本封装把 stderr 里的异常摘要带回来（不再静默变成 None）。
        """
        body = _as_async_body(script)
        fd, path = tempfile.mkstemp(suffix=".js", prefix="jobauto_")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            ok, out = self._run("js", path, index=index, timeout=timeout)
            if not ok:
                return {"__js_error__": _clean_err((out or {}).get("error", ""))}
            return _try_json(out) if parse else out
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def text(self, index=None):
        ok, out = self._run("text", index=index)
        return out if ok else ""

    def count(self, sel, index=None):
        ok, out = self._run("count", sel, index=index)
        if not ok:
            return -1
        try:
            return int(str(out).strip().split()[-1])
        except Exception:
            return -1

    def cards(self, outer, link=None, mx=40, index=None):
        args = ["cards", outer]
        if link:
            args += [link, str(mx)]
        ok, out = self._run(*args, index=index)
        return out if ok else ""

    # ---------- 动 ----------
    def nav(self, url, settle=3.0, index=None, timeout=None):
        ok, out = self._run("nav", url, "--settle", str(settle), index=index, timeout=timeout)
        return ok, out

    def goto(self, url, settle=3.0):
        ok, out = self._run("goto", url, "--settle", str(settle))
        return ok, out

    def click(self, sel, settle=1.5, index=None):
        ok, out = self._run("click", sel, "--settle", str(settle), index=index)
        return ok, out

    def fill(self, sel, value, index=None):
        ok, out = self._run("fill", sel, value, index=index)
        return ok, out

    def type(self, sel, value, index=None):
        ok, out = self._run("type", sel, value, index=index)
        return ok, out

    def ce_fill(self, value, sel="#chat-input", index=None):
        ok, out = self._run("ce-fill", sel, value, index=index)
        return ok, out

    def ce_send(self, sel="#chat-input", btn=".btn-send", index=None):
        ok, out = self._run("ce-send", sel, btn, index=index)
        return ok, out

    def send_auto(self, sel=None, index=None):
        ok, out = self._run("send", *([sel] if sel else []), index=index)
        return ok, out

    def press(self, key="Enter", index=None):
        ok, out = self._run("press", key, index=index)
        return ok, out

    def wait(self, sel, ms=20000, index=None):
        ok, out = self._run("wait", sel, str(ms), index=index)
        return ok, out

    def shot(self, name, full=False, index=None):
        args = ["shot", name] + (["full"] if full else [])
        ok, out = self._run(*args, index=index)
        return ok, out

    def upload(self, sel, path, index=None):
        ok, out = self._run("upload", sel, path, index=index)
        return ok, out

    def scroll_bottom(self, index=None):
        ok, out = self._run("scroll-bottom", index=index)
        return ok, out


def _clean_err(err):
    """从 webctl2 的 stderr 里抠出「页面 JS 异常: ...」这一行（含 stderr 里其他噪音时）。"""
    s = str(err or "").strip()
    for line in s.splitlines():
        if "页面 JS 异常" in line or "Error" in line:
            return line.strip()[:300]
    return s[:300]


def _as_async_body(script):
    """把脚本统一成 `return ...` 形式的函数体。

    ★ 判定必须保守（这里踩过一次坑）：只有当脚本**以 `(` 或箭头函数开头**时，
    才把它当成「待求值的表达式」包一层 `return (...)`。
    绝不能因为「文本里没有 return 字样」就去包裹 ——
    函数体如果有前置语句（如 `const a=[1]; return ...`），
    包起来会变成 `return (const a=[1]; return ...)`，直接 SyntaxError，
    而 webctl2 只会把异常打到 stderr，调用方看到的是 None，极难排查。
    """
    s = (script or "").strip()
    if s.startswith("(") or s.startswith("async") or s.startswith("!function"):
        return "return (" + s.rstrip(";").rstrip() + ");"
    return s


def _is_expr_script(script):
    s = (script or "").strip()
    return s.startswith("(") or s.startswith("async") or s.startswith("!function")


def _try_json(s):
    """把驱动输出解析成 Python 对象。

    ★ `null` 单独处理：驱动把 JS 的 null/undefined 打成字符串 "None"，
    如果原样返回，上层会拿到一个真值字符串 "None"（假成功），
    所以这里明确转成 Python 的 None，让调用方走错误分支。
    """
    if s is None:
        return None
    s = s.strip()
    if s in ("None", "null", "undefined", ""):
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    # 从混杂输出里抠出第一个 JSON 对象/数组
    for a, b in (("{", "}"), ("[", "]")):
        i, j = s.find(a), s.rfind(b)
        if i >= 0 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                pass
    return s


def sleep(sec):
    time.sleep(sec)
