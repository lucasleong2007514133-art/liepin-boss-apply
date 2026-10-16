# -*- coding: utf-8 -*-
"""送达核实 + 收件箱盘点。

★ 纪律：发完消息后不要靠页面提示判断真假，回消息中心看会话列表里的
   「最后一条消息 + 投递状态」才是证据（本机实测靠这一步抓到过多次假成功）。
"""
import time

CHAT_URL = {"boss": "https://www.zhipin.com/web/geek/chat",
            "liepin": "https://www.liepin.com/im/"}

BOSS_CONV_JS = r"""
(() => {
  const lis = Array.prototype.slice.call(document.querySelectorAll('li'));
  const rows = [];
  for (let i = 0; i < lis.length; i++) {
    const li = lis[i];
    const nm = li.querySelector('.name-text, .geek-name, [class*="name-text"]');
    if (!nm) continue;
    const msg = li.querySelector('.last-msg-text, [class*="last-msg"]');
    const st = li.querySelector('.message-status, [class*="status"]');
    const txt = (li.innerText || '').replace(/\s+/g, ' ').trim();
    if (!txt) continue;
    rows.push({
      hr: (nm.textContent || '').trim(),
      lastMsg: msg ? (msg.textContent || '').trim() : '',
      status: st ? (st.textContent || '').trim() : '',
      text: txt.slice(0, 160)
    });
  }
  return JSON.stringify({count: rows.length, rows: rows,
                         url: location.href, title: document.title.slice(0, 60)});
})()
"""

LIEPIN_CONV_JS = r"""
(() => {
  const nodes = Array.prototype.slice.call(
    document.querySelectorAll('[class*="conversation"], [class*="session"], [class*="chat-item"], li'));
  const rows = [];
  for (let i = 0; i < nodes.length; i++) {
    const li = nodes[i];
    const nm = li.querySelector('[class*="name"], .name, [class*="title"]');
    if (!nm) continue;
    const txt = (li.innerText || '').replace(/\s+/g, ' ').trim();
    if (!txt || txt.length < 4) continue;
    rows.push({ hr: (nm.textContent || '').trim().slice(0, 24), text: txt.slice(0, 160) });
  }
  return JSON.stringify({count: rows.length, rows: rows, url: location.href});
})()
"""

CONV_JS = {"boss": BOSS_CONV_JS, "liepin": LIEPIN_CONV_JS}


def inbox(d, site="boss", index=None, settle=3.5, sleep=2.5):
    ok, info = d.nav(CHAT_URL[site], settle=settle, index=index)
    if not ok:
        return {"ok": False, "error": str(info)[:150]}
    time.sleep(sleep)
    r = d.js(CONV_JS[site], index=index)
    if not isinstance(r, dict) or "__js_error__" in r:
        return {"ok": False, "error": (r or {}).get("__js_error__", "会话列表解析失败")
                if isinstance(r, dict) else "会话列表解析失败", "raw": str(r)[:200]}
    r["ok"] = True
    r["site"] = site
    return r


def verify_one(d, site, hr, expect_msg, index=None):
    """在会话列表里找该 HR，看最后一条消息是否为我刚发的内容。"""
    inv = inbox(d, site=site, index=index)
    if not inv.get("ok"):
        return {"ok": False, "hr": hr, "error": inv.get("error")}
    key = "".join((expect_msg or "")[:16].split())
    for row in inv.get("rows", []):
        if hr and hr.strip() and hr.strip() not in (row.get("hr") or ""):
            continue
        tail = "".join((row.get("lastMsg") or row.get("text") or "").split())
        hit = bool(key) and key in tail
        return {"ok": hit, "hr": hr, "status": row.get("status", ""),
                "last_msg": row.get("lastMsg") or row.get("text", ""),
                "found": True}
    return {"ok": False, "hr": hr, "found": False, "error": "会话列表里找不到该 HR"}


def verify_batch(d, site, sent_rows, index=None, sleep=1.2):
    """逐条核实一批发送结果，输出可归档的对账表。"""
    out = []
    for r in sent_rows:
        v = verify_one(d, site, r.get("hr", ""), r.get("msg", ""), index=index)
        out.append({**{k: r.get(k) for k in ("hr", "company", "position")}, **v})
        time.sleep(sleep)
    good = sum(1 for x in out if x.get("ok"))
    return {"site": site, "total": len(out), "verified": good, "rows": out}
