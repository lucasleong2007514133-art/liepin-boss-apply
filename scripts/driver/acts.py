# -*- coding: utf-8 -*-
"""
acts.py —— 基于原生 CDP 的网页动作库（配合 cdp.py 使用）

设计要点：
  * 所有动作走 Runtime.evaluate 执行 JS，不经过 Playwright 的 actionability 检查
    → 规避 Chrome 101 缺 element.checkVisibility() 的问题
  * click 派发完整鼠标事件序列（pointerdown/mousedown/pointerup/mouseup/click）
    → 兼容 React/Vue 等框架的事件委托
  * fill/type 设置 value 后派发 input/change 事件
    → 兼容受控组件与联想框
"""
import json
import time

from cdp import CDP, CDPError

# ---------------------------------------------------------------------------
# 注入页面的工具函数（幂等：重复注入会覆盖）
# ---------------------------------------------------------------------------
HELPERS = r"""
window.__W = (function () {
  function all(sel) { try { return Array.from(document.querySelectorAll(sel)); } catch (e) { return []; } }
  function first(sel) { return all(sel)[0] || null; }
  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    return true;
  }
  function fireMouse(el) {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const base = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0 };
    const seq = ['pointerover', 'mouseover', 'pointerenter', 'mouseenter',
                 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    for (const type of seq) {
      let ev;
      try {
        if (type.startsWith('pointer')) ev = new PointerEvent(type, Object.assign({ pointerId: 1, pointerType: 'mouse', isPrimary: true }, base));
        else ev = new MouseEvent(type, base);
      } catch (e) { ev = new MouseEvent(type.replace('pointer', 'mouse'), base); }
      el.dispatchEvent(ev);
    }
    // 兜底：原生 click（某些框架只监听原生 click）
    try { el.click(); } catch (e) {}
    return true;
  }
  function setValue(el, val) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
                : el instanceof HTMLInputElement ? HTMLInputElement.prototype : null;
    try {
      const setter = proto && Object.getOwnPropertyDescriptor(proto, 'value');
      if (setter && setter.set) setter.set.call(el, val); else el.value = val;
    } catch (e) { el.value = val; }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    // React 16 兼容
    try {
      const tracker = el._valueTracker;
      if (tracker) tracker.setValue(val === '' ? 'x' : '');
    } catch (e) {}
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return el.value;
  }
  return { all, first, visible, fireMouse, setValue };
})();
'__W_INSTALLED__'
"""


def inject(d: CDP):
    """注入工具函数（每个页面导航后需要重新注入）"""
    d.eval(HELPERS)


def _need(d: CDP, selector):
    """注入 + 返回目标元素是否存在"""
    inject(d)
    return d.eval(f"!!document.querySelector({json.dumps(selector)})")


# ---------------------------------------------------------------------------
# 动作实现
# ---------------------------------------------------------------------------
def cmd_tabs(d: CDP):
    out = []
    for i, t in enumerate(d.page_targets()):
        out.append({"index": i, "title": t.get("title", ""), "url": t.get("url", "")})
    return out


def cmd_goto(d: CDP, url, index=None, wait=True, settle=2.5):
    """新建标签页打开 URL（不覆盖现有标签）"""
    tid = d.new_tab(url)
    time.sleep(0.6)
    # 重新枚举以拿到 index
    pages = d.page_targets()
    idx = next((i for i, p in enumerate(pages) if p["id"] == tid), None)
    if idx is None:
        raise CDPError("新标签页创建后未能定位")
    d.attach_index(idx)
    if wait:
        d.wait_load(settle=settle)
    return {"mode": "NEW_TAB", "index": idx, "url": d.eval("location.href"),
            "title": d.eval("document.title")}


def cmd_nav(d: CDP, url, wait=True, settle=2.5):
    """在已附加的标签内导航"""
    d.navigate(url)
    if wait:
        d.wait_load(settle=settle)
    return {"url": d.eval("location.href"), "title": d.eval("document.title")}


def cmd_text(d: CDP):
    inject(d)
    return d.eval("document.body ? document.body.innerText : ''")


def cmd_html(d: CDP):
    return d.eval("document.documentElement.outerHTML")


def cmd_eval(d: CDP, expr):
    inject(d)
    return d.eval(expr)


def cmd_js(d: CDP, path):
    code = open(path, encoding="utf-8").read()
    inject(d)
    return d.eval_async(code)


def cmd_count(d: CDP, selector):
    inject(d)
    return d.eval(f"document.querySelectorAll({json.dumps(selector)}).length")


def cmd_read(d: CDP, selector, limit=200):
    inject(d)
    expr = f"""
      const els = __W.all({json.dumps(selector)}).slice(0, {limit});
      return JSON.stringify(els.map(e => (e.innerText || e.textContent || '').trim()));
    """
    return json.loads(d.eval_async(expr) or "[]")


def cmd_cards(d: CDP, item_sel, link_sel=None, limit=60):
    inject(d)
    expr = f"""
      const items = __W.all({json.dumps(item_sel)}).slice(0, {limit});
      const out = [];
      for (const it of items) {{
        const a = {json.dumps(link_sel)} ? it.querySelector({json.dumps(link_sel)}) : it.querySelector('a[href]');
        out.push({{
          text: (it.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300),
          href: a ? a.href : '',
          title: a ? (a.getAttribute('title') || (a.innerText || '').trim().slice(0, 60)) : ''
        }});
      }}
      return JSON.stringify(out);
    """
    return json.loads(d.eval_async(expr) or "[]")


def cmd_fill(d: CDP, selector, value):
    inject(d)
    expr = f"""
      const el = __W.first({json.dumps(selector)});
      if (!el) return JSON.stringify({{ok: false, err: 'NOT_FOUND'}});
      el.focus();
      const v = __W.setValue(el, {json.dumps(value)});
      return JSON.stringify({{ok: true, len: (v || '').length, tag: el.tagName}});
    """
    return json.loads(d.eval_async(expr))


def cmd_type(d: CDP, selector, value, delay=0.03):
    """逐字输入（先聚焦清空，再模拟按键）
    注意：CDP 的 keyDown 带 text 就会插入字符，**不能再发 char 事件**否则会插入两遍。"""
    inject(d)
    d.eval_async(f"""
      const el = __W.first({json.dumps(selector)});
      if (!el) return 'NOT_FOUND';
      el.focus();
      __W.setValue(el, '');
      return 'FOCUSED';
    """)
    for ch in value:
        d.call("Input.dispatchKeyEvent",
               {"type": "keyDown", "text": ch, "unmodifiedText": ch},
               session=d._session)
        d.call("Input.dispatchKeyEvent",
               {"type": "keyUp", "text": ch, "unmodifiedText": ch},
               session=d._session)
        time.sleep(delay)
    return {"ok": True, "len": d.eval(f"(__W.first({json.dumps(selector)})||{{value:''}}).value.length")}


def cmd_click(d: CDP, selector, settle=1.2):
    inject(d)
    expr = f"""
      const el = __W.first({json.dumps(selector)});
      if (!el) return JSON.stringify({{ok: false, err: 'NOT_FOUND'}});
      el.scrollIntoView({{block: 'center'}});
      __W.fireMouse(el);
      return JSON.stringify({{ok: true, tag: el.tagName, cls: (el.className || '').toString().slice(0, 60)}});
    """
    r = json.loads(d.eval_async(expr))
    if not r.get("ok"):
        raise CDPError(f"点击失败：{r.get('err')} :: {selector}")
    time.sleep(settle)
    return r


def cmd_select(d: CDP, selector, value):
    inject(d)
    expr = f"""
      const el = __W.first({json.dumps(selector)});
      if (!el) return JSON.stringify({{ok: false, err: 'NOT_FOUND'}});
      el.value = {json.dumps(value)};
      el.dispatchEvent(new Event('change', {{bubbles: true}}));
      return JSON.stringify({{ok: true, value: el.value}});
    """
    return json.loads(d.eval_async(expr))


def cmd_press(d: CDP, key):
    """发送按键（Enter 等）"""
    keymap = {
        "Enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "text": "\r"},
        "Tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
        "Escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    }
    info = keymap.get(key, {"key": key, "code": key})
    d.call("Input.dispatchKeyEvent", dict({"type": "keyDown"}, **info), session=d._session)
    d.call("Input.dispatchKeyEvent", dict({"type": "keyUp"}, **info), session=d._session)
    return {"ok": True, "key": key}


def cmd_wait(d: CDP, selector, timeout=15.0):
    inject(d)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if d.eval(f"!!document.querySelector({json.dumps(selector)})"):
            return {"ok": True, "waited": round(timeout - (deadline - time.time()), 2)}
        time.sleep(0.4)
    raise CDPError(f"等待超时：{selector}")


def cmd_upload(d: CDP, selector, path):
    return d.set_files(selector, path)


def cmd_shot(d: CDP, path, full=False):
    n = d.screenshot(path, full_page=full)
    return {"ok": True, "path": path, "bytes": n}


def cmd_scroll_bottom(d: CDP, times=4):
    inject(d)
    d.eval_async(f"""
      for (let i = 0; i < {times}; i++) {{
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 900));
      }}
      return 'OK';
    """)
    return {"ok": True}


def cmd_close(d: CDP, index):
    pages = d.page_targets()
    if index < 0 or index >= len(pages):
        raise CDPError(f"标签序号越界：{index}")
    d.close_tab(pages[index]["id"])
    return {"ok": True, "closed": index}


# ---------------------------------------------------------------------------
# contenteditable 支持（BOSS直聘 聊天输入框是 div[contenteditable]，不是 textarea）
# ---------------------------------------------------------------------------
def cmd_ce_fill(d: CDP, selector, value):
    """向 contenteditable 元素写入文本并派发 input 事件"""
    inject(d)
    expr = f"""
      const el = __W.first({json.dumps(selector)});
      if (!el) return JSON.stringify({{ok: false, err: 'NOT_FOUND'}});
      el.focus();
      el.innerHTML = '';
      el.innerText = {json.dumps(value)};
      el.dispatchEvent(new InputEvent('input', {{bubbles: true, cancelable: true}}));
      el.dispatchEvent(new Event('change', {{bubbles: true}}));
      return JSON.stringify({{ok: true, len: (el.innerText || '').length, text: (el.innerText || '').slice(0, 40)}});
    """
    return json.loads(d.eval_async(expr))


def cmd_ce_send(d: CDP, input_selector=None, btn_selector=None, settle=2.0):
    """在 contenteditable 输入框内按 Enter 发送（优先）或点发送按钮"""
    inject(d)
    sel = input_selector or "#chat-input"
    expr = f"""
      const el = __W.first({json.dumps(sel)}) || __W.first('div.chat-input');
      if (!el) return JSON.stringify({{ok: false, err: 'NO_INPUT'}});
      el.focus();
      const before = (el.innerText || '').length;
      return JSON.stringify({{ok: true, before}});
    """
    st = json.loads(d.eval_async(expr))
    if not st.get("ok"):
        raise CDPError("发送失败：" + str(st))

    # 首选：真实 Enter 键
    cmd_press(d, "Enter")
    time.sleep(settle)

    # 检查是否已清空（清空=发送成功）
    left = d.eval(f"(__W.first({json.dumps(sel)}) || __W.first('div.chat-input') || {{innerText:''}}).innerText.length")
    if left and int(left) > 0:
        # 兜底：点发送按钮
        if btn_selector:
            try:
                cmd_click(d, btn_selector, settle=settle)
                left = d.eval(f"(__W.first({json.dumps(sel)}) || {{innerText:''}}).innerText.length")
            except CDPError:
                pass
    return {"ok": True, "remaining": int(left or 0), "sent": int(left or 0) == 0}


def cmd_send_auto(d: CDP, input_selector=None):
    """通用发送：自动判别 textarea / contenteditable，用 Enter 或点发送按钮"""
    inject(d)
    sel = input_selector
    # 自动选输入框
    if not sel:
        probe = d.eval("""
          (() => {
            const ce = document.querySelector('#chat-input, div.chat-input[contenteditable="true"]');
            if (ce && ce.offsetParent !== null) return '#chat-input';
            const ta = [...document.querySelectorAll('textarea')].find(e => e.offsetParent !== null);
            if (ta) return 'textarea';
            return '';
          })()
        """)
        sel = probe or ""
    if not sel:
        raise CDPError("找不到可用的输入框")

    use_ce = sel.startswith("#") or "contenteditable" in sel
    get_len = (f"(__W.first({json.dumps(sel)}) || {{innerText:''}}).innerText.length" if use_ce
               else f"(__W.first({json.dumps(sel)}) || {{value:''}}).value.length")

    before = int(d.eval(get_len) or 0)
    if before == 0:
        raise CDPError("输入框是空的，请先 fill / ce-fill")

    # 聚焦后按 Enter
    focus_js = "var __e = __W.first(%s); if (__e && __e.focus) __e.focus(); 'focused'" % json.dumps(sel)
    d.eval(focus_js)
    cmd_press(d, "Enter")
    time.sleep(2.0)

    left = int(d.eval(get_len) or 0)
    via = "Enter"
    if left > 0:
        # 兜底：点常见发送按钮
        for bsel in [".btn-send", "button.btn-send", ".send-message", ".send-btn",
                     "[class*=send]:not([class*=message])"]:
            try:
                if d.eval(f"!!document.querySelector({json.dumps(bsel)})"):
                    cmd_click(d, bsel, settle=2.0)
                    left = int(d.eval(get_len) or 0)
                    via = f"btn:{bsel}"
                    if left == 0:
                        break
            except CDPError:
                continue
    return {"ok": True, "via": via, "before": before, "remaining": left, "sent": left == 0}
