# -*- coding: utf-8 -*-
"""批量发送执行器 —— 分批 + 逐条回读 + 断点续传。

★ 分批是硬要求，不是保守：
  同一个页面连续操作约 20 次后，ChromeCore 会崩成 about:blank。
  所以默认每批 15 条，做完一批落盘一次，崩了也能续。
"""
import json
import os
import time

from . import chatui, verify


def load_messages(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    if isinstance(rows, dict):
        rows = rows.get("messages") or rows.get("rows") or []
    return rows


def send_batch(d, site, rows, index=None, start=0, end=None, batch=15,
               dry_run=False, verify_each=False, out_dir=".", log=print):
    """发送 rows[start:end]（再切成 batch 大小的批）。

    返回 {sent[], verified[], batch_files[]}
    """
    end = len(rows) if end is None else min(end, len(rows))
    target = rows[start:end]
    sent, files = [], []

    for b0 in range(0, len(target), batch):
        chunk = target[b0:b0 + batch]
        log(f"=== 第 {b0 // batch + 1} 批：{len(chunk)} 条（全局序号 {start + b0 + 1}..{start + b0 + len(chunk)}）===")
        for i, m in enumerate(chunk, start + b0 + 1):
            hr = m.get("hr") or ""
            log(f"--- [{i}] {hr} | {m.get('company', '')} | {m.get('position', '')} ---")
            if dry_run:
                log(f"    (dry-run) 话术 {m.get('chars') or len(m.get('msg', ''))} 字，未发送")
                sent.append({**m, "ok": None, "dry_run": True})
                continue

            url = m.get("url")
            if url:
                r = chatui.apply_via_detail(d, site, url, m["msg"], index=index)
            else:
                # 没有详情页 URL：假定当前已在聊天页/会话里
                r = {"ok": False, "error": "该条目没有 url，且未实现按 HR 名直接会话（请补 url）"}
            ok = bool(r.get("ok"))
            log(f"    {'✓ 已送达' if ok else '✗ ' + str(r.get('error') or r.get('note') or '未确认')[:80]}")
            row = {**m, "ok": ok, "via": (r.get("send") or {}).get("via"),
                   "evidence": (r.get("send") or {}).get("evidence"),
                   "state": r.get("state"), "error": r.get("error")}
            sent.append(row)

            if verify_each and ok:
                v = verify.verify_one(d, site, hr, m["msg"], index=index)
                row["verified"] = bool(v.get("ok"))
                row["verify_detail"] = v
                log(f"    核实: {'✓' if v.get('ok') else '?'} {v.get('status', '') or v.get('error', '')}")
            time.sleep(1.5)

        # 每一批落盘（崩了可续）
        os.makedirs(out_dir, exist_ok=True)
        f = os.path.join(out_dir, f"_sent_batch_{start + b0}_{start + b0 + len(chunk)}.json")
        try:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(sent, fh, ensure_ascii=False, indent=1)
            files.append(f)
            log(f"    批记录已落盘: {f}")
        except Exception as e:
            log(f"    批记录落盘失败: {e}")

    good = sum(1 for s in sent if s.get("ok"))
    return {"sent": sent, "files": files,
            "summary": {"total": len(sent), "ok": good, "failed": len(sent) - good}}
