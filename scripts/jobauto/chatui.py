# -*- coding: utf-8 -*-
"""聊天/沟通 UI 适配层 —— 把「按钮文案会变」这个坑做成显式状态机。

★ 核心事故（本机真实踩过）：
  BOSS直聘 的沟通按钮文案随「是否有沟通记录」变化：
    「立即沟通」 → 点完弹出 modal（含 textarea.input-area + .send-message）
    「继续沟通」 → 点完【不弹窗】，直接跳 /web/geek/chat?id=xxx
  当时误判成「弹窗会自动关闭」，一直等 textarea → 必然超时。
  正确做法：动手前先探测按钮文案，按状态走不同分支（见 apply_via_detail）。

所有按钮/输入框选择器都在这里集中，站点改版时只改这一个文件。
"""

# ---------------- 选择器表 ----------------
BOSS = {
    "chat_btn": "a.btn-startchat, .btn-startchat",
    "modal_input": "textarea.input-area",
    "modal_send": ".send-message",
    "chat_input": "#chat-input, div.chat-input[contenteditable='true']",
    "chat_send": ".btn-send",
    "msg_body": ".im-ui-txt, .dialog-con",
    "conv_dialog": ".dialog-con, .im-ui-txt",
    "chat_url": "https://www.zhipin.com/web/geek/chat",
    "detail_url": "https://www.zhipin.com/job_detail/{jid}.html",
}

LIEPIN = {
    # ⚠️ 猎聘登录后的沟通 UI 未经本机实测，选择器按常见结构给出，站点改版请以此文件为准
    "chat_btn": "a.btn-startchat, .btn-chat, .btn-contact, a[class*='chat']",
    "modal_input": ".im-input textarea, textarea[class*='input'], div[contenteditable='true']",
    "modal_send": ".im-input .btn-send, .btn-send, [class*='send-btn']",
    "chat_input": ".im-input div[contenteditable='true'], #chat-input, div[contenteditable='true']",
    "chat_send": ".btn-send, [class*='send-btn']",
    "msg_body": "[class*='message-item'], [class*='im-msg']",
    "conv_dialog": "[class*='message-item'], [class*='im-msg']",
    "chat_url": "https://www.liepin.com/im/",
    "detail_url": "https://www.liepin.com/job/{jid}.shtml",
}

SITE = {"boss": BOSS, "liepin": LIEPIN}


# ---------------- 探测（一律先探测，再动手） ----------------
PROBE_JS = r"""
(() => {
  const vis = e => e && e.offsetParent !== null && !e.disabled;
  const cfg = __CFG__;
  const pick = sel => Array.prototype.slice.call(document.querySelectorAll(sel)).filter(vis);
  const uniq = arr => { const r = []; for (let i = 0; i < arr.length; i++) if (r.indexOf(arr[i]) < 0) r.push(arr[i]); return r; };
  const btns = pick(cfg.chat_btn);
  const labels = btns.map(b => (b.textContent || '').trim());
  const modalInputs = pick(cfg.modal_input);
  const chatInputs = pick(cfg.chat_input);
  const sendBtns = pick(cfg.modal_send).concat(pick(cfg.chat_send));
  return JSON.stringify({
    url: location.href,
    title: document.title.slice(0, 90),
    is_chat_page: /(geek\/chat|\/im\/|\/chat)/.test(location.pathname),
    chat_btn_labels: labels,
    chat_btn_count: btns.length,
    modal_input_count: modalInputs.length,
    chat_input_count: chatInputs.length,
    send_btn_classes: uniq(sendBtns.map(b => (b.className || '').toString())),
    send_btn_texts: uniq(sendBtns.map(b => (b.textContent || '').trim())),
    has_textarea: document.querySelectorAll('textarea').length
  });
})()
"""

# 沟通状态判定：文案里出现「继续」= 已有沟通记录；「立即/沟通/开聊」= 首次
CONTINUE_WORDS = ("继续沟通", "继续", "已沟通", "查看对话")
START_WORDS = ("立即沟通", "沟通", "开聊", "立即开聊", "马上沟通")


def probe(d, site, index=None):
    """探测当前页面状态。返回 dict（失败时带 error）。"""
    cfg = SITE[site]
    import json as _json
    js = PROBE_JS.replace("__CFG__", _json.dumps({
        "chat_btn": cfg["chat_btn"],
        "modal_input": cfg["modal_input"],
        "chat_input": cfg["chat_input"],
        "modal_send": cfg["modal_send"],
        "chat_send": cfg["chat_send"],
    }))
    r = d.js(js, index=index)
    if isinstance(r, dict) and "__js_error__" not in r:
        r["site"] = site
        r["state"] = classify(r)
        return r
    err = (r or {}).get("__js_error__") if isinstance(r, dict) else None
    return {"site": site, "error": err or "probe failed",
            "raw": str(r)[:300], "state": "unknown"}


def classify(p):
    """把探测结果归成一个明确状态，供上层分支。"""
    if not isinstance(p, dict) or p.get("error"):
        return "unknown"
    if p.get("is_chat_page"):
        return "in_chat_page"
    labels = p.get("chat_btn_labels") or []
    if any(any(w in lb for w in CONTINUE_WORDS) for lb in labels):
        return "has_history"      # 已有沟通记录 → 点完不弹窗
    if any(any(w in lb for w in START_WORDS) for lb in labels):
        return "first_contact"    # 首次沟通 → 点完弹 modal
    if p.get("modal_input_count"):
        return "modal_open"
    if p.get("chat_input_count"):
        return "chat_input_ready"
    if p.get("chat_btn_count"):
        return "unknown_btn_text"  # 有按钮但文案不认识 → 打印出来人工看
    return "no_action"


# ---------------- 发送 ----------------
def _input_len(d, site, sel, index=None):
    cfg = SITE[site]
    js = (
        "(() => { const e = document.querySelector(%s); "
        "return e ? ((e.value !== undefined ? e.value : e.innerText) || '').length : -1; })()"
        % _js_str(sel)
    )
    return d.js(js, index=index)


def _last_msg(d, site, index=None):
    cfg = SITE[site]
    js = (
        "(() => { const els = [...document.querySelectorAll(%s)]"
        ".map(e => (e.textContent || '').trim()).filter(x => x.length > 8); "
        "return els.length ? els[els.length - 1].slice(0, 120) : ''; })()"
        % _js_str(cfg["conv_dialog"])
    )
    return d.js(js, index=index)


def _js_str(s):
    import json as _json
    return _json.dumps(s)


def send_message(d, site, msg, index=None, prefer=None):
    """在聊天页/弹窗里发一条消息，带回读校验。

    三重兜底（按实测成功率排序）：
      1. ce-fill + ce-send  —— contenteditable 专用，BOSS直聘 聊天页实测可用
      2. send（自动判别 textarea / contenteditable，自动找发送按钮）
      3. fill + click(发送按钮)
    返回 {ok, via, verify_method, evidence, attempts[]}
    """
    cfg = SITE[site]
    attempts = []
    result = {"ok": False, "via": None, "attempts": attempts}

    chain = [
        ("ce", cfg["chat_input"], cfg["chat_send"]),
        ("send_auto", None, None),
        ("fill_click", cfg["modal_input"], cfg["modal_send"]),
        ("fill_click", cfg["chat_input"], cfg["chat_send"]),
    ]

    for via, inp, btn in chain:
        ok_a, info = False, ""
        try:
            if via == "ce":
                ok1, o1 = d.ce_fill(msg, sel=inp, index=index)
                if not ok1 or "FAIL" in str(o1):
                    attempts.append(("ce-fill", False, str(o1)[:80]))
                    continue
                ok2, o2 = d.ce_send(sel=inp, btn=btn, index=index)
                ok_a, info = bool(ok2 and "已发送=True" in str(o2)), str(o2)[:120]
            elif via == "send_auto":
                ok_s, o_s = d.send_auto(index=index)
                ok_a, info = bool(ok_s and "已发送=True" in str(o_s)), str(o_s)[:120]
                if ok_a:
                    # send_auto 自带填入，跳过后续；若失败尝试下一档
                    pass
                else:
                    attempts.append(("send", False, str(o_s)[:80]))
                    continue
            else:
                ok_f, o_f = d.fill(inp, msg, index=index)
                if not ok_f or "FAIL" in str(o_f):
                    attempts.append((f"fill:{inp}", False, str(o_f)[:80]))
                    continue
                ok_c, o_c = d.click(btn, settle=2.0, index=index)
                ok_a, info = bool(ok_c), str(o_c)[:120]
        except Exception as e:  # 不让单个动作炸掉整批
            attempts.append((via, False, repr(e)[:80]))
            continue

        attempts.append((via, ok_a, info))
        if not ok_a:
            continue

        # ---- 回读校验：输入框应被清空，且末条消息应含我发的内容 ----
        left = _input_len(d, site, cfg["chat_input"] if via != "fill_click" else inp, index=index)
        tail = _last_msg(d, site, index=index)
        key = "".join((msg or "")[:16].split())
        tailc = "".join(str(tail or "").split())
        verified = (isinstance(left, int) and left == 0) or (key and key in tailc)
        result.update({
            "ok": bool(verified), "via": via,
            "verify_method": "输入框清空" if (isinstance(left, int) and left == 0) else "末尾消息匹配",
            "evidence": {"input_left": left, "last_msg": tail},
        })
        if verified:
            return result
        # 发出去了但没校验到 → 继续尝试下一档可能造成重复发送，这里收手并如实上报
        result.update({"ok": False, "via": via, "note": "动作已执行但未校验到送达，请人工看消息中心确认，避免重复发送"})
        return result

    result["error"] = "所有发送通道都失败"
    return result


def apply_via_detail(d, site, url, msg, index=None, wait_modal=6.0, dry_run=False):
    """在职位详情页发起沟通并发第一条话术。★ 按探测到的状态分支。"""
    import time as _t
    cfg = SITE[site]
    out = {"url": url, "site": site, "steps": []}

    ok, info = d.nav(url, settle=4.0, index=index)
    out["steps"].append(("nav", ok, str(info)[:80]))
    if not ok:
        out["ok"] = False
        out["error"] = "导航失败"
        return out

    _t.sleep(2.5)
    p = probe(d, site, index=index)
    out["probe"] = p
    state = p.get("state")
    out["state"] = state

    if state == "no_action":
        out["ok"] = False
        out["error"] = "页面上找不到沟通按钮（可能已下线 / 需登录 / 站点改版）"
        return out

    if state == "unknown_btn_text":
        out["ok"] = False
        out["error"] = "按钮文案不认识，请人工看一下并更新 chatui.py 的关键词表"
        return out

    if dry_run:
        out["ok"] = True
        out["dry_run"] = True
        out["note"] = f"探测到状态 {state}，未执行任何发送"
        return out

    # 点沟通按钮（继续沟通不会弹窗，会直接跳聊天页 —— 这正是当年的坑）
    ok_c, info_c = d.click(cfg["chat_btn"], settle=wait_modal, index=index)
    out["steps"].append(("click_chat", ok_c, str(info_c)[:80]))
    _t.sleep(2.0 if state == "has_history" else 4.0)

    p2 = probe(d, site, index=index)
    out["probe_after"] = p2

    if p2.get("modal_input_count") or p2.get("chat_input_count") or p2.get("is_chat_page"):
        r = send_message(d, site, msg, index=index)
        out["send"] = r
        out["ok"] = bool(r.get("ok"))
        if not out["ok"]:
            out["error"] = r.get("error") or r.get("note") or "发送未校验成功"
        return out

    out["ok"] = False
    out["error"] = ("点了沟通按钮但既没弹窗也没进聊天页 —— "
                    "若是「继续沟通」，确认点击后是否跳转到 chat 页；"
                    "否则检查选择器是否随站点改版失效")
    return out
