# -*- coding: utf-8 -*-
"""
webctl2.py —— 网页控制工具（原生 CDP 版，零依赖）

与旧版 webctl.py 的区别：
  * 不走 Playwright → 不用 npm/GitHub，不受 Chrome 101 缺 checkVisibility 影响
  * 用 cdp.py 手写 WebSocket + acts.py 的 JS 动作
  * click 派发完整鼠标事件序列；fill/type 派发 input/change（兼容受控组件）

用法（默认端口 9222，需先用「启动_可控制浏览器.bat」拉起带调试端口的浏览器）：
  python webctl2.py tabs
  python webctl2.py goto "https://example.com"          # 新建标签打开（不覆盖现有标签）
  python webctl2.py nav  "https://example.com" --index 0 # 在指定标签内导航
  python webctl2.py text   --index 0
  python webctl2.py html   --index 0
  python webctl2.py count  "a[href*='/job/']" --index 0
  python webctl2.py cards  "li" "a[href*='/job/']" 40 --index 0
  python webctl2.py read   ".title" --index 0
  python webctl2.py eval   "document.title" --index 0
  python webctl2.py js     script.js --index 0
  python webctl2.py fill   "#kw" "城市经理" --index 0
  python webctl2.py type   "input.ipt-search" "城市经理" --index 0
  python webctl2.py click  "a.btn-startchat" --index 0
  python webctl2.py select "#city" "东莞" --index 0
  python webctl2.py press  Enter --index 0
  python webctl2.py wait   ".job-card-box" 20000 --index 0
  python webctl2.py upload "input[type=file]" "D:/a.pdf" --index 0
  python webctl2.py shot   out.png [full] --index 0
  python webctl2.py scroll-bottom --index 0
  python webctl2.py close  3

退出码：1=连不上端口 2=命令不支持 3=没有标签 4=缺 --index 5=--index 越界
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from cdp import CDP, CDPError          # noqa: E402
import acts                            # noqa: E402

# 必须显式指定 --index 的命令（避免误伤用户正在看的标签）
NEEDS_INDEX = {"nav", "text", "html", "eval", "js", "count", "cards", "read",
               "fill", "type", "click", "select", "press", "wait", "upload",
               "shot", "scroll-bottom", "ce-fill", "ce-send", "send"}

# tables.py 里对应实现直接内联在 main 中


def main():
    ap = argparse.ArgumentParser(description="网页控制（原生 CDP 版）")
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", default="9222")
    ap.add_argument("--index", default=None)
    ap.add_argument("--settle", type=float, default=None, help="动作后等待秒数")
    a = ap.parse_args()

    cmd = a.cmd
    args = a.args

    if cmd in NEEDS_INDEX and a.index is None:
        print("NEED_INDEX: 请先 `webctl2.py tabs` 看清标签，再用 --index N 指定目标。\n"
              "（goto 会自动新建标签，无需 --index）", file=sys.stderr)
        return 4

    try:
        d = CDP(port=int(a.port))
    except Exception as e:
        print(f"[x] 连接调试端口 {a.port} 失败：{e}\n"
              "    请先双击「启动_可控制浏览器.bat」拉起浏览器。", file=sys.stderr)
        return 1

    try:
        # ---------- 不需要附加标签的命令 ----------
        if cmd == "tabs":
            print(json.dumps(acts.cmd_tabs(d), ensure_ascii=False, indent=1))
            return 0

        if cmd == "goto":
            if not args:
                print("USAGE: goto <url>", file=sys.stderr)
                return 2
            r = acts.cmd_goto(d, args[0])
            print(json.dumps(r, ensure_ascii=False, indent=1))
            return 0

        # close 支持位置参数（close 3）或 --index
        if cmd == "close":
            raw = args[0] if args else a.index
            if raw is None:
                print("USAGE: close <index> 或 close --index N", file=sys.stderr)
                return 4
            r = acts.cmd_close(d, int(raw))
            print(f"OK close {raw}")
            return 0

        # ---------- 需要附加标签 ----------
        idx = int(a.index)
        try:
            t = d.attach_index(idx)
        except CDPError as e:
            print(f"标签附加失败：{e}", file=sys.stderr)
            return 5
        print(f"[已附加] index={idx} | {t.get('title','')[:60]} | {t.get('url','')[:80]}",
              file=sys.stderr)

        if cmd == "nav":
            r = acts.cmd_nav(d, args[0], settle=a.settle or 2.5)
            print(json.dumps(r, ensure_ascii=False, indent=1))
        elif cmd == "text":
            print(acts.cmd_text(d))
        elif cmd == "html":
            print(acts.cmd_html(d))
        elif cmd == "eval":
            print(acts.cmd_eval(d, args[0]))
        elif cmd == "js":
            print(acts.cmd_js(d, args[0]))
        elif cmd == "count":
            print(acts.cmd_count(d, args[0]))
        elif cmd == "cards":
            link = args[1] if len(args) > 1 else None
            lim = int(args[2]) if len(args) > 2 else 60
            print(json.dumps(acts.cmd_cards(d, args[0], link, lim), ensure_ascii=False, indent=1))
        elif cmd == "read":
            print(json.dumps(acts.cmd_read(d, args[0]), ensure_ascii=False, indent=1))
        elif cmd == "fill":
            r = acts.cmd_fill(d, args[0], args[1])
            print("OK fill" if r.get("ok") else f"FAIL {r}")
        elif cmd == "type":
            r = acts.cmd_type(d, args[0], args[1])
            print(f"OK type len={r.get('len')}")
        elif cmd == "click":
            r = acts.cmd_click(d, args[0], settle=a.settle or 1.2)
            print(f"OK click {r.get('tag')} {r.get('cls','')}")
        elif cmd == "select":
            r = acts.cmd_select(d, args[0], args[1])
            print(f"OK select value={r.get('value')}")
        elif cmd == "press":
            r = acts.cmd_press(d, args[0])
            print(f"OK press {r.get('key')}")
        elif cmd == "wait":
            ms = int(args[1]) if len(args) > 1 else 15000
            r = acts.cmd_wait(d, args[0], timeout=ms / 1000.0)
            print(f"OK wait {r.get('waited')}s")
        elif cmd == "upload":
            acts.cmd_upload(d, args[0], args[1])
            print("OK upload")
        elif cmd == "shot":
            full = len(args) > 1 and args[1] == "full"
            r = acts.cmd_shot(d, args[0], full=full)
            print(f"OK shot {r['path']} ({r['bytes']} bytes)")
        elif cmd == "scroll-bottom":
            acts.cmd_scroll_bottom(d)
            print("OK scroll-bottom")
        elif cmd == "ce-fill":
            # contenteditable 填值（BOSS直聘 聊天输入框）
            r = acts.cmd_ce_fill(d, args[0], args[1])
            print(f"OK ce-fill len={r.get('len')}" if r.get("ok") else f"FAIL {r}")
        elif cmd == "ce-send":
            # 在 contenteditable 内按 Enter 发送
            inp = args[0] if args else "#chat-input"
            btn = args[1] if len(args) > 1 else ".btn-send"
            r = acts.cmd_ce_send(d, inp, btn)
            print(f"{'OK' if r.get('sent') else 'PARTIAL'} ce-send 剩余={r.get('remaining')} 已发送={r.get('sent')}")
        elif cmd == "send":
            # 通用发送：自动判别 textarea / contenteditable，点常见发送按钮
            sel = args[0] if args else None
            r = acts.cmd_send_auto(d, sel)
            print(f"{'OK' if r.get('sent') else 'PARTIAL'} send via {r.get('via')} 剩余={r.get('remaining')}")
        elif cmd == "close":
            acts.cmd_close(d, idx)
            print(f"OK close {idx}")
        else:
            print(f"[x] 不支持的子命令: {cmd}", file=sys.stderr)
            return 2
        return 0
    except CDPError as e:
        print(f"[x] {e}", file=sys.stderr)
        return 1
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main())
