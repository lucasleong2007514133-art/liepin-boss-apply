# -*- coding: utf-8 -*-
"""
cdp.py —— 纯 Python 原生 Chrome DevTools Protocol 客户端（零依赖）

为什么自己写：
  本机浏览器 ChromeCore 内核为 Chrome 101。新版 Playwright 的动作依赖
  element.checkVisibility()（Chrome 105+），在 101 上直接 TypeError，
  导致 click/fill 超时。纯 CDP 走 Runtime.evaluate，不经过任何
  actionability 检查，彻底绕开该问题。

实现：WebSocket 客户端用标准库手写（socket/base64/struct/hashlib），
      只依赖 http://127.0.0.1:<port>/json* 与 ws 通道。

作者备注：2026-10-15 首次落盘，配合 webctl2.py 使用。
"""
import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.request


class CDPError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# 极简 WebSocket 客户端
# --------------------------------------------------------------------------
class WS:
    def __init__(self, url, timeout=30):
        # ws://host:port/path
        assert url.startswith("ws://"), f"只支持 ws:// : {url}"
        rest = url[5:]
        slash = rest.find("/")
        hostport, path = (rest[:slash], rest[slash:]) if slash >= 0 else (rest, "/")
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
            port = int(port)
        else:
            host, port = hostport, 80
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        # 读握手响应
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("WebSocket 握手失败：连接被关闭")
            buf += chunk
        head, _, rest_bytes = buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise CDPError("WebSocket 握手失败：" + head.decode("utf-8", "replace")[:200])
        self._pending = rest_bytes  # 握手包后面可能已带数据帧
        self._id = 0
        self._buf = b""

    # ---------- 帧编解码 ----------
    def _recv_exact(self, n):
        out = b""
        if self._pending:
            take = self._pending[:n]
            self._pending = self._pending[n:]
            out += take
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise CDPError("连接已关闭")
            out += chunk
        return out

    def send_text(self, text):
        data = text.encode("utf-8")
        hdr = bytearray([0x81])
        n = len(data)
        mask = os.urandom(4)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        hdr += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(hdr) + masked)

    def recv_message(self):
        """返回 (opcode, payload_str)"""
        while True:
            b1, b2 = self._recv_exact(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else None
            payload = self._recv_exact(ln) if ln else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:  # close
                raise CDPError("服务端关闭了 WebSocket")
            if opcode == 0x9:  # ping -> pong
                continue
            if opcode in (0x1, 0x2):
                if not fin:
                    # 简化：不拼接分片（CDP 通常不分片）
                    pass
                return opcode, payload.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# CDP 客户端（HTTP 发现 + WS 命令）
# --------------------------------------------------------------------------
class CDP:
    def __init__(self, port=9222, timeout=30):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        ver = self._http("/json/version")
        self.browser_ws = ver["webSocketDebuggerUrl"]
        self.browser_name = ver.get("Browser", "")
        self.ws = WS(self.browser_ws, timeout=timeout)
        self._msg_id = 0
        self._session = None          # 扁平模式的 sessionId
        self._events = []

    # ---------- HTTP ----------
    def _http(self, path, method="GET"):
        url = self.base + path
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def targets(self):
        return self._http("/json/list")

    # ---------- WS 命令 ----------
    def call(self, method, params=None, session=None, timeout=30):
        self._msg_id += 1
        mid = self._msg_id
        msg = {"id": mid, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send_text(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                _, text = self.ws.recv_message()
            except socket.timeout:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue
            if data.get("id") == mid:
                if "error" in data:
                    raise CDPError(f"{method} 失败: {data['error']}")
                return data.get("result", {})
            else:
                self._events.append(data)
        raise CDPError(f"{method} 超时（{timeout}s）")

    # ---------- 目标（标签页）管理 ----------
    def page_targets(self):
        out = []
        for t in self.targets():
            if t.get("type") == "page":
                out.append(t)
        return out

    def attach(self, target_id):
        r = self.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        self._session = r["sessionId"]
        return self._session

    def attach_index(self, index):
        pages = self.page_targets()
        if not pages:
            raise CDPError("没有可用的页面标签")
        if index < 0 or index >= len(pages):
            raise CDPError(f"标签序号越界：共 {len(pages)} 个（0..{len(pages)-1}），收到 {index}")
        t = pages[index]
        self.attach(t["id"])
        return t

    def new_tab(self, url="about:blank"):
        r = self.call("Target.createTarget", {"url": url})
        return r["targetId"]

    def close_tab(self, target_id):
        return self.call("Target.closeTarget", {"targetId": target_id})

    # ---------- 页面操作 ----------
    def eval(self, expr, await_promise=False, timeout=30):
        r = self.call("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "userGesture": True,
        }, session=self._session, timeout=timeout)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            msg = d.get("exception", {}).get("description") or d.get("text") or str(d)
            raise CDPError("页面 JS 异常: " + str(msg)[:300])
        return r.get("result", {}).get("value")

    def eval_async(self, expr, timeout=60):
        """把表达式包成 async IIFE 并等待 Promise"""
        return self.eval(f"(async () => {{ {expr} }})()", await_promise=True, timeout=timeout)

    def navigate(self, url, timeout=45):
        r = self.call("Page.navigate", {"url": url}, session=self._session, timeout=timeout)
        return r

    def wait_load(self, timeout=30, settle=2.0):
        """等 load 事件 + 额外静默时间"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                st = self.eval("document.readyState")
            except CDPError:
                time.sleep(0.5)
                continue
            if st == "complete":
                time.sleep(settle)
                return True
            time.sleep(0.5)
        return False

    def set_files(self, selector, path):
        """给 file input 设置文件（走 DOM.setFileInputFiles）"""
        doc = self.call("DOM.getDocument", {"depth": 0}, session=self._session)
        root = doc["root"]["nodeId"]
        node = self.call("DOM.querySelector", {"nodeId": root, "selector": selector},
                         session=self._session)
        nid = node.get("nodeId")
        if not nid:
            raise CDPError(f"找不到选择器: {selector}")
        abs_path = os.path.abspath(path)
        return self.call("DOM.setFileInputFiles", {"files": [abs_path], "nodeId": nid},
                         session=self._session)

    def screenshot(self, path, full_page=False):
        params = {"format": "png"}
        if full_page:
            m = self.call("Page.getLayoutMetrics", session=self._session)
            cs = m.get("cssContentSize") or m.get("contentSize") or {}
            w = int(cs.get("width") or 1440)
            h = int(cs.get("height") or 900)
            params["captureBeyondViewport"] = True
            params["clip"] = {"x": 0, "y": 0, "width": w, "height": h, "scale": 1}
        r = self.call("Page.captureScreenshot", params, session=self._session, timeout=40)
        data = base64.b64decode(r["data"])
        with open(path, "wb") as f:
            f.write(data)
        return len(data)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
