#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""jobauto CLI —— 招聘平台投递 / 话术自动化（BOSS直聘 · 猎聘）。

零第三方依赖（纯标准库 + 原生 CDP）。所有命令默认「只读优先」：
先 scan/probe 看清页面，再 apply/send 动手。

用法示例：
  python jobauto.py doctor
  python jobauto.py launch
  python jobauto.py login --site boss
  python jobauto.py tabs
  python jobauto.py probe --site boss
  python jobauto.py scan  --site boss --kw 城市经理 --city 东莞 --pages 2 -o jobs.json
  python jobauto.py detail --site boss --url <职位页URL>
  python jobauto.py decode "\ue033\ue033-\ue034\ue036K"
  python jobauto.py draft --jobs jobs.json --facts my_facts.json -o messages.json
  python jobauto.py send  --site boss --messages messages.json --batch 15          # 默认 dry-run
  python jobauto.py send  --site boss --messages messages.json --execute          # 真发（需显式确认）
  python jobauto.py inbox --site boss
  python jobauto.py verify --site boss --messages messages.json
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ★ Windows 控制台默认 GBK，打印 BOSS直聘 薪资的字体私用区字符（U+E031..）
#   会直接 UnicodeEncodeError 崩掉 —— 所以先强制 stdout/stderr 走 UTF-8。
for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from jobauto import chatui, fontmap, launcher, messages as msgmod, platforms, sender, verify  # noqa: E402
from jobauto.driver import Driver  # noqa: E402

LOGIN_URL = {"boss": "https://www.zhipin.com/web/user/?ka=header-login",
             "liepin": "https://www.liepin.com/"}


def out(obj, path=None):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入 {path}")
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(
        description="招聘平台投递/话术自动化（BOSS直聘 · 猎聘）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--index", type=int, default=0, help="标签页序号（先跑 tabs 看清）")
    ap.add_argument("--site", choices=["boss", "liepin"], default="boss")
    ap.add_argument("--kw", default=None, help="搜索关键词")
    ap.add_argument("--city", default="全国")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--url", default=None)
    ap.add_argument("--jobs", default=None, help="jobs.json")
    ap.add_argument("--messages", default=None, help="messages.json")
    ap.add_argument("--facts", default=None, help="事实库 JSON/MD")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--batch", type=int, default=15)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--execute", action="store_true",
                    help="真的发送（不加则为 dry-run，只打印将要发的内容）")
    ap.add_argument("--verify-each", action="store_true", help="每条发完立刻核实")
    ap.add_argument("--browser", default=None)
    ap.add_argument("--wait", type=int, default=40)
    a = ap.parse_args()
    cmd = a.cmd

    # ---------- 不依赖浏览器的命令 ----------
    if cmd == "doctor":
        out(launcher.doctor(browser=a.browser, port=a.port))
        return 0
    if cmd == "launch":
        out(launcher.launch(browser=a.browser, port=a.port, wait=a.wait))
        return 0
    if cmd == "decode":
        src = a.args[0] if a.args else "\ue033\ue033-\ue034\ue036K·\ue032\ue037薪"
        out({"raw": src, "decoded": fontmap.decode_salary(src)})
        return 0
    if cmd == "draft":
        if not a.jobs:
            print("需要 --jobs jobs.json", file=sys.stderr)
            return 2
        with open(a.jobs, encoding="utf-8") as f:
            jobs = json.load(f)
        if isinstance(jobs, dict):
            jobs = jobs.get("jobs") or []
        path = a.output or "messages.json"
        out(msgmod.to_messages_file(jobs, path, facts_path=a.facts))
        return 0
    if cmd == "liepin-http":
        if not a.kw:
            print("需要 --kw", file=sys.stderr)
            return 2
        r = platforms.liepin_http_search(a.kw, a.city, a.pages)
        if a.output:
            with open(a.output, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        out({k: v for k, v in r.items() if k != "jobs"} | {"jobs_count": len(r.get("jobs", []))})
        return 0

    # ---------- 需要浏览器 ----------
    d = Driver(port=a.port, index=a.index)

    if cmd == "tabs":
        out(d.tabs())
        return 0

    okv, ver = launcher.port_alive(a.port)
    if not okv:
        out({"ok": False, "error": f"调试端口 {a.port} 未就绪，先跑 launch / doctor",
             "hint": "python jobauto.py doctor"})
        return 1

    if cmd == "login":
        ok, info = d.goto(LOGIN_URL[a.site], settle=3.0)
        out({"ok": ok, "url": LOGIN_URL[a.site], "note": "在弹出的独立浏览器窗口里登录一次，登录态会持久化",
             "detail": str(info)[:120]})
        return 0

    if cmd == "probe":
        out(chatui.probe(d, a.site, index=a.index))
        return 0

    if cmd == "scan":
        if not a.kw:
            print("需要 --kw", file=sys.stderr)
            return 2
        r = platforms.search(d, a.site, a.kw, a.city, a.pages, index=a.index)
        if a.output:
            with open(a.output, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        out({k: v for k, v in r.items() if k != "jobs"} | {"jobs_count": len(r["jobs"])})
        if r["jobs"]:
            print("\n前 5 条预览：")
            for j in r["jobs"][:5]:
                print(f"  {j.get('salary', ''):<14} {j.get('area', ''):<8} "
                      f"{j.get('company', '')[:16]:<18} {j.get('title', '')[:30]}")
        return 0

    if cmd == "detail":
        if not a.url:
            print("需要 --url", file=sys.stderr)
            return 2
        r = platforms.detail(d, a.site, a.url, index=a.index)
        if a.output and r.get("ok"):
            with open(a.output, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        out({k: v for k, v in r.items() if k != "jd"} | ({"jd_len": len(r.get("jd") or "")}
                                                         if r.get("ok") else {}))
        return 0

    if cmd == "inbox":
        r = verify.inbox(d, a.site, index=a.index)
        if a.output and r.get("ok"):
            with open(a.output, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        out({k: v for k, v in r.items() if k != "rows"}
            | ({"rows_count": len(r.get("rows") or [])} if r.get("ok") else {}))
        return 0

    if cmd == "apply":
        if not (a.url and a.args):
            print('用法：apply --url <职位页> "<话术>"', file=sys.stderr)
            return 2
        r = chatui.apply_via_detail(d, a.site, a.url, a.args[0],
                                    index=a.index, dry_run=not a.execute)
        out(r)
        return 0 if r.get("ok") else 1

    if cmd == "send":
        if not a.messages:
            print("需要 --messages messages.json", file=sys.stderr)
            return 2
        rows = sender.load_messages(a.messages)
        r = sender.send_batch(d, a.site, rows, index=a.index, start=a.start, end=a.end,
                              batch=a.batch, dry_run=not a.execute,
                              verify_each=a.verify_each,
                              out_dir=os.path.dirname(os.path.abspath(a.messages)))
        out(r["summary"] | {"files": r["files"]})
        return 0

    if cmd == "verify":
        if not a.messages:
            print("需要 --messages messages.json", file=sys.stderr)
            return 2
        rows = sender.load_messages(a.messages)
        out(verify.verify_batch(d, a.site, rows[a.start:(a.end or len(rows))], index=a.index))
        return 0

    print(f"未知命令：{cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
