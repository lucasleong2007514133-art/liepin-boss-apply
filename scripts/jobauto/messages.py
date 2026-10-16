# -*- coding: utf-8 -*-
"""话术引擎 —— 把「一份简历 + 一条 JD」变成一条定制招呼语。

实测有效的结构（BOSS直聘 上一条 289 字的话术成功送达并被 HR 回复）：
    称呼 + 我是谁 + 年限标签
    → 看到贵司在招 <岗位名>，逐条对应贵岗要求：
    → 1)2)3)4) 每条 = 「岗位关键词：我的可验证事实（带数字）」
    → 收尾一句（我在本地 / 期待详聊）

为什么必须定制：
  HR 侧每天收到大量模板招呼，「15年经验求关注」这类等于没写。
  带岗位关键词 + 带数字的对应关系，才是能过初筛的信息。

批量纪律：一次 10-20 条，每条发完立刻回读核实；不要一口气发 50 条（浏览器会崩）。
"""
import json
import os
import re

# 事实库：只放「能被追问、能拿出证据」的事实。数字必须真实。
# 占位值仅作格式示例，请替换成你自己的事实（见 references/话术模板.md）。
DEFAULT_FACTS = {
    "years": "{N}年<你的行业>经验",
    "current": "现任<公司/体系><岗位>",
    "scope": "直管<城市数量>个城市",
    "scale": "管理<人数>人、覆盖<站点数>个站点",
    "team": "直接管理<下属岗位><人数>人，培养出<人数>名<岗位>",
    "cost": "主导<指标>由<A>降到<B>（<降幅>%）",
    "rescue": "<某两个落后单元>进驻3个月做到<名次>",
    "data": "日常用<维度>多维数据定位问题并出改善方案",
}


def build(job, facts, max_chars=400, greeting=None):
    """按 JD 生成一条话术。

    job: {position, company, hr, jd, url}
    facts: dict，见 DEFAULT_FACTS
    返回 {msg, chars, used_points}
    """
    hr = (job.get("hr") or "").strip()
    f = {**DEFAULT_FACTS, **(facts or {})}
    name = f.get("name") or "<你的名字>"
    # ★ 称呼必须判空（踩过坑）：hr 为空时若直接拼 "{hr}您好" 会生成「您好您好」
    greet = greeting or (f"{hr}您好" if hr else "您好")
    # 岗位名：列表页字段叫 title，详情页/清单里叫 position，两个都认
    pos = (job.get("position") or job.get("title") or "该岗位").strip()
    f.setdefault("name", name)

    points = _match_points(job, f)
    body = "".join(f"{i}）{p}" for i, p in enumerate(points, 1))
    tail = job.get("tail") or "期待和您详细沟通。"

    head = (f"{greet}，我是{f['name']}，{f['years']}。"
            f"看到贵司在招{pos}，我的匹配点：")
    msg = f"{head}{body}{tail}"

    if len(msg) > max_chars:
        # 超长优先砍掉「附加值」点（数据/兜底那句），保留硬对应
        while len(msg) > max_chars and len(points) > 2:
            points.pop()
            body = "".join(f"{i}）{p}" for i, p in enumerate(points, 1))
            msg = f"{head}{body}{tail}"
    return {"msg": msg, "chars": len(msg), "used_points": len(points)}


# JD 关键词 → 拿哪条事实去接（顺序即优先级）
PATTERNS = [
    (("成本", "费用", "单均", "降本", "利润", "盈亏", "经营"), "cost"),
    (("骑手", "运力", "众包", "调度", "履约", "时效"), "scale"),
    (("团队", "管理", "带团队", "培养", "梯队", "组织"), "team"),
    (("多城市", "区域", "大区", "片区", "跨城", "城市经理"), "scope"),
    (("改善", "优化", "提升", "数据", "指标", "复盘", "分析"), "data"),
    (("代理商", "加盟", "承运商", "三方", "供应商", "招商"), "proxy"),
    (("从0", "0到1", "新项目", "开拓", "搭建", "开城"), "zero2one"),
    (("现场", "直营", "网点", "仓", "分拨"), "site"),
]


def _match_points(job, f):
    """按 JD 命中度排序，取出要写进话术的对应点。"""
    jd = (job.get("jd") or "") + " " + (job.get("position") or "")
    hit, miss = [], []
    for kws, key in PATTERNS:
        val = f.get(key)
        if not val:
            continue
        (hit if any(k in jd for k in kws) else miss).append(val)
    ordered = hit + miss
    # 至少 3 条、最多 4 条 —— 实测 3-4 条最像「认真看过 JD」而不是刷屏
    return ordered[:4] if len(ordered) >= 3 else ordered


def load_facts(path=None):
    """从 JSON / Markdown 里读事实库；找不到就用示例（并明确告知是示例）。"""
    if path and os.path.isfile(path):
        if path.lower().endswith(".json"):
            with open(path, encoding="utf-8") as f:
                return json.load(f), True
        out = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*[-*]?\s*`?([a-zA-Z_]+)`?\s*[:：]\s*(.+?)\s*$", line)
                if m:
                    out[m.group(1)] = m.group(2)
        if out:
            return out, True
    return dict(DEFAULT_FACTS), False


def to_messages_file(jobs, path, facts=None, facts_path=None):
    """生成发送清单（_messages.json），供 send 命令消费。"""
    loaded, real = load_facts(facts_path)
    real = bool(real or facts)
    use = {**loaded, **(facts or {})} if real else dict(DEFAULT_FACTS)
    rows = []
    for j in jobs:
        b = build(j, use)
        rows.append({
            "hr": j.get("hr") or "",
            "company": j.get("company") or "",
            # 列表页叫 title、详情/人工清单叫 position，统一回填成 position 供发送器使用
            "position": j.get("position") or j.get("title") or "",
            "url": j.get("url") or "",
            "jid": j.get("jid") or "",
            "msg": b["msg"],
            "chars": b["chars"],
            "facts_is_example": not real,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return {"path": path, "count": len(rows), "facts_is_example": not real}


if __name__ == "__main__":
    demo = {"hr": "张先生", "company": "某即时配送", "position": "配送副总监",
            "jd": "负责区域配送成本、骑手运力与团队管理，多城市履约时效改善"}
    print(json.dumps(build(demo, {}), ensure_ascii=False, indent=2))
