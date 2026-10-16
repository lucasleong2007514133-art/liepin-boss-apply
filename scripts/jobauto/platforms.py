# -*- coding: utf-8 -*-
"""BOSS直聘 / 猎聘 平台适配 —— 搜索 URL、列表抓取、详情抓取。

★ 重要事实区分（不要混为一谈）：
  BOSS直聘：登录后的「沟通 / 发话术 / 送达核实」全流程本机实测跑通。
  猎聘    ：本机只实测跑通【公开 SEO 列表页 + 详情页】的只读抓取；
            登录后的沟通 UI 未实测，选择器集中在 chatui.py 的 LIEPIN 表，
            首次使用请先跑 `probe` 看真实 DOM，再据此调整。
"""
import json
import re
import time
import urllib.parse

from . import fontmap

# ---------------- 城市码 ----------------
BOSS_CITY = {
    "全国": "100010000", "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "东莞": "101281600", "佛山": "101280800", "江门": "101281100",
    "杭州": "101210100", "成都": "101270100", "武汉": "101200100", "南京": "101190100",
    "苏州": "101190400", "西安": "101110100", "长沙": "101250100", "郑州": "101180100",
    "重庆": "101040100", "天津": "101030100", "青岛": "101120200", "合肥": "101220100",
}

LIEPIN_CITY_SLUG = {
    "全国": "", "北京": "beijing", "上海": "shanghai", "广州": "gz", "深圳": "shenzhen",
    "东莞": "dongguan", "佛山": "foshan", "江门": "jiangmen", "杭州": "hangzhou",
    "成都": "chengdu", "武汉": "wuhan", "南京": "nanjing", "苏州": "suzhou",
    "西安": "xian", "长沙": "changsha", "郑州": "zhengzhou", "重庆": "chongqing",
}

# 猎聘 SEO 列表页需要拼音 slug；未知关键词退回「搜索页」而不是编一个 slug
LIEPIN_KW_SLUG = {
    "城市经理": "chengshijingli", "配送经理": "peisongjingli",
    "配送运营经理": "peisongyunyingjingli", "物流运营经理": "wuliuyunyingjingli",
    "区域经理": "quyujingli", "即时配送": "jishipeisong", "运营经理": "yunyingjingli",
    "供应链经理": "gongyinglianjingli", "仓储经理": "cangchujingli",
}


def boss_search_url(keyword, city="全国", page=1, page_size=30):
    code = BOSS_CITY.get(city, city if str(city).isdigit() else BOSS_CITY["全国"])
    q = urllib.parse.quote(keyword)
    return ("https://www.zhipin.com/web/geek/jobs?query=%s&city=%s"
            "&experience=&degree=&industry=&scale=&stage=&position=&jobType="
            "&salary=&multiBusinessDistrict=&multiSubway=&page=%d&pageSize=%d"
            % (q, code, page, page_size))


def liepin_search_url(keyword, city="全国", page=1):
    """猎聘公开 SEO 列表页（免登录可抓），形如 /city-dongguan/zpchengshijingli/。"""
    slug = LIEPIN_CITY_SLUG.get(city, "")
    kw = LIEPIN_KW_SLUG.get(keyword)
    suffix = "" if page <= 1 else f"p{page}/"
    if kw:
        base = f"https://www.liepin.com/city-{slug}/zp{kw}/" if slug else \
               f"https://www.liepin.com/zp{kw}/"
        return base + suffix
    # 未知关键词：走站内搜索（可能要求登录，抓不到就如实报缺口）
    return ("https://www.liepin.com/zhaopin/?key=%s%s"
            % (urllib.parse.quote(keyword), f"&city={slug}" if slug else ""))


# ---------------- 列表抓取 JS ----------------
# ★ Chrome 101 兼容纪律（本机实测，务必遵守）：
#   Set 在这个内核上完全不可用 —— `[...set]`、`Array.from(set)`、`for (const x of set)`、
#   `set.forEach()` 全部抛异常，而 webctl2 会把异常只打到 stderr（调用方看到的是 None）。
#   所以这里一律用「数组 + indexOf 去重」和「Array.prototype.slice.call(nodeList)」，
#   绝不使用 Set / for...of。
BOSS_LIST_JS = r"""
(() => {
  // 选择器来自 2026-10-15 真实 DOM 实测（卡片结构）：
  //   li.job-card-box > div.job-info > div.job-title > a.job-name + span.job-salary
  //                                     > ul.tag-list > li
  //                     div.job-card-footer > a.boss-info > span.boss-name（公司）
  //                                        > span.company-location（地点，带前后空格）
  const cards = Array.prototype.slice.call(
    document.querySelectorAll('.job-card-box, li.job-card-wrapper'));
  const out = [];
  for (let i = 0; i < cards.length; i++) {
    const c = cards[i];
    const a = c.querySelector('a.job-name, a[href*="/job_detail/"]');
    const salaryEl = c.querySelector('span.job-salary, .salary, span[class*="salary"]');
    const areaEl = c.querySelector('.company-location, .job-area, span[class*="area"]');
    const comp = c.querySelector('.boss-name, .company-name a, .company-name');
    const tagEls = Array.prototype.slice.call(
      c.querySelectorAll('ul.tag-list li, .tag-list li'));
    const href = a ? a.href : '';
    out.push({
      title: a ? (a.textContent || '').trim() : '',
      url: href,
      jid: href ? ((href.match(/job_detail\/([^.]+)\.html/) || [])[1] || '') : '',
      company: comp ? (comp.textContent || '').trim() : '',
      area: areaEl ? (areaEl.textContent || '').replace(/\s+/g, ' ').trim() : '',
      salary_raw: salaryEl ? (salaryEl.textContent || '') : '',
      tags: tagEls.map(e => (e.textContent || '').trim()).filter(x => x)
    });
  }
  return JSON.stringify({
    count: out.length,
    jobs: out.filter(x => x.title),
    url: location.href
  });
})()
"""

LIEPIN_LIST_JS = r"""
(() => {
  const cards = Array.prototype.slice.call(
    document.querySelectorAll('.job-card-pc-container, .job-card-box, li[class*="job-card"]'));
  const out = [];
  for (let i = 0; i < cards.length; i++) {
    const c = cards[i];
    const a = c.querySelector('a[data-nick="job-detail-job-info"], a[href*="/job/"]');
    const t = c.querySelector('.job-title-box div[title], .job-title-box, [class*="job-title"]');
    const sal = c.querySelector('span.job-salary, [class*="salary"]');
    const comp = c.querySelector('span.company-name, [class*="company-name"]');
    const city = c.querySelector('.job-dq-box span.ellipsis-1, [class*="job-dq"]');
    const tagEls = Array.prototype.slice.call(
      c.querySelectorAll('span.labels-tag, .job-labels-box span'));
    const href = a ? a.href : '';
    out.push({
      title: t ? ((t.getAttribute && t.getAttribute('title')) || t.textContent || '').trim() : '',
      url: href,
      jid: href ? ((href.match(/\/job\/(\d+)\.shtml/) || [])[1] || '') : '',
      company: comp ? (comp.textContent || '').trim() : '',
      area: city ? (city.textContent || '').trim() : '',
      salary_raw: sal ? (sal.textContent || '').trim() : '',
      tags: tagEls.map(e => (e.textContent || '').trim()).filter(x => x)
    });
  }
  return JSON.stringify({
    count: out.length,
    jobs: out.filter(x => x.title),
    url: location.href
  });
})()
"""


# ---------------- 详情抓取 JS ----------------
BOSS_DETAIL_JS = r"""
(() => {
  const t = (document.body.innerText || '').replace(/\s+/g, ' ');
  let s = t.indexOf('职位描述');
  if (s < 0) s = t.indexOf('岗位职责');
  if (s < 0) s = 0;
  const h1 = document.querySelector('h1, .name h1, [class*="job-title"]');
  // 公司名（真实 DOM 实测）：详情页主卡片里是 div.boss-info-attr = "公司·岗位"，
  // 侧栏 .company-info 也可能有；按优先级取第一个非空的，失败再退回标题首行
  let comp = '';
  const compSels = ['.boss-info .boss-name', '.boss-info-attr', '.company-info .company-name',
                    '.sider-company .company-name', 'a[href*="/gongsi/"]'];
  for (let ci = 0; ci < compSels.length && !comp; ci++) {
    const el = document.querySelector(compSels[ci]);
    if (!el) continue;
    let txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (compSels[ci] === '.boss-info-attr') txt = txt.split('·')[0].trim();
    if (txt) comp = txt;
  }
  if (!comp) {
    const nm = document.querySelector('.company-info .name');
    comp = nm ? (nm.textContent || '').replace(/\s+/g, ' ').trim() : '';
  }
  if (!comp) {
    const raw = (h1 ? (h1.textContent || '') : (document.title || ''));
    comp = raw.split('\n')[0].replace(/[\d.]+\s*[-~]\s*[\d.]+\s*[Kk万千Ww].*$/, '').trim();
  }
  const sal = document.querySelector('.salary, .job-salary, [class*="salary"]');
  const btns = Array.prototype.slice.call(
      document.querySelectorAll('a.btn-startchat,.btn-startchat,button'))
    .filter(e => e.offsetParent !== null)
    .map(e => (e.textContent || '').trim()).filter(x => x && x.length < 20);
  const uniq = [];
  for (let i = 0; i < btns.length; i++) if (uniq.indexOf(btns[i]) < 0) uniq.push(btns[i]);
  return JSON.stringify({
    title: h1 ? (h1.textContent || '').trim().slice(0, 90) : document.title.slice(0, 90),
    company: comp.slice(0, 40),
    salary_raw: sal ? (sal.textContent || '').trim() : '',
    buttons: uniq.slice(0, 20),
    jd: t.slice(s, s + 2000),
    url: location.href
  });
})()
"""

LIEPIN_DETAIL_JS = r"""
(() => {
  const t = (document.body.innerText || '').replace(/\s+/g, ' ');
  let s = t.indexOf('职位描述');
  if (s < 0) s = t.indexOf('岗位职责');
  if (s < 0) s = t.indexOf('职位介绍');
  if (s < 0) s = 0;
  const h1 = document.querySelector('.job-title-box, h1, [class*="job-title"]');
  const comp = document.querySelector('[class*="company-name"], .company-info');
  const sal = document.querySelector('.job-salary, [class*="salary"]');
  return JSON.stringify({
    title: h1 ? (h1.textContent || '').trim().slice(0, 90) : document.title.slice(0, 90),
    company: comp ? (comp.textContent || '').trim().slice(0, 40) : '',
    salary_raw: sal ? (sal.textContent || '').trim() : '',
    jd: t.slice(s, s + 2000),
    url: location.href
  });
})()
"""

LIST_JS = {"boss": BOSS_LIST_JS, "liepin": LIEPIN_LIST_JS}
DETAIL_JS = {"boss": BOSS_DETAIL_JS, "liepin": LIEPIN_DETAIL_JS}


def _jserr(r):
    """把 driver 带回的 JS 异常 dict 转成人类可读的错误串（没有则 None）。"""
    if isinstance(r, dict) and "__js_error__" in r:
        return r["__js_error__"]
    return None


def search(d, site, keyword, city="全国", pages=1, index=None, settle=4.0, sleep=2.0):
    """翻页抓岗位列表。返回 {site, keyword, city, jobs[], pages_meta[]}。"""
    jobs, meta = [], []
    for p in range(1, pages + 1):
        url = boss_search_url(keyword, city, p) if site == "boss" \
            else liepin_search_url(keyword, city, p)
        ok, info = d.nav(url, settle=settle, index=index)
        if not ok:
            meta.append({"page": p, "url": url, "error": str(info)[:120]})
            continue
        time.sleep(sleep)
        # 列表是懒加载的，先滚到底
        d.scroll_bottom(index=index)
        time.sleep(1.2)
        r = d.js(LIST_JS[site], index=index)
        if not isinstance(r, dict) or "__js_error__" in r:
            meta.append({"page": p, "url": url, "error": _jserr(r) or "列表解析失败",
                         "raw": str(r)[:200]})
            continue
        got = r.get("jobs") or []
        for j in got:
            j["salary"] = fontmap.decode_salary(j.get("salary_raw") or "") if site == "boss" \
                else (j.get("salary_raw") or "").strip()
            j["site"] = site
            j["keyword"] = keyword
            j["city"] = city
        jobs.extend(got)
        meta.append({"page": p, "url": url, "count": len(got)})

    # 去重（同 jid 保留先出现的）—— 用 dict 而不是 Set（Chrome 101 上 Set 不可用是页面侧的事，
    # 这里是 Python 侧，用 dict 同样更直观）
    seen, uniq = {}, []
    for j in jobs:
        k = j.get("jid") or j.get("url")
        if k and k in seen:
            continue
        if k:
            seen[k] = True
        uniq.append(j)
    return {"site": site, "keyword": keyword, "city": city, "jobs": uniq, "pages_meta": meta}


def detail(d, site, url, index=None, settle=4.0, sleep=2.0):
    ok, info = d.nav(url, settle=settle, index=index)
    if not ok:
        return {"ok": False, "url": url, "error": str(info)[:150]}
    time.sleep(sleep)
    r = d.js(DETAIL_JS[site], index=index)
    if not isinstance(r, dict) or "__js_error__" in r:
        return {"ok": False, "url": url, "error": _jserr(r) or "详情解析失败",
                "raw": str(r)[:200]}
    r["ok"] = True
    r["salary"] = fontmap.decode_salary(r.get("salary_raw") or "") if site == "boss" \
        else (r.get("salary_raw") or "").strip()
    return r


# ---------------- 猎聘只读抓取（不需要浏览器，走公开页） ----------------
def liepin_http_search(keyword, city="全国", pages=1, timeout=25):
    """不依赖浏览器的兜底通道：requests 抓猎聘公开 SEO 页。

    猎聘公开页可直接 GET；但若无 requests 或页面结构变化，会如实报缺口。
    """
    try:
        import requests
    except ImportError:
        return {"ok": False, "error": "未安装 requests（pip install requests），改用浏览器通道"}
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0")
    head = {"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9"}
    jobs, meta = [], []
    for p in range(1, pages + 1):
        url = liepin_search_url(keyword, city, p)
        try:
            r = requests.get(url, headers=head, timeout=timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text
        except Exception as e:
            meta.append({"page": p, "url": url, "error": repr(e)[:120]})
            continue
        got = _parse_liepin_html(html)
        jobs.extend(got)
        meta.append({"page": p, "url": url, "status": r.status_code, "count": len(got)})
    return {"ok": True, "jobs": jobs, "pages_meta": meta}


def _parse_liepin_html(html):
    """轻量正则解析（不引入 bs4）。结构变了就返回空并让上层报缺口。"""
    out = []
    for m in re.finditer(
        r'<a[^>]+data-nick="job-detail-job-info"[^>]+href="([^"]+)"[^>]*data-jobid="(\d+)"',
        html,
    ):
        href, jid = m.group(1), m.group(2)
        if href.startswith("/"):
            href = "https://www.liepin.com" + href
        out.append({"url": href, "jid": jid, "title": "", "company": "",
                    "salary_raw": "", "tags": [], "site": "liepin"})
    # 标题/公司做一次粗提取（同一卡片块内）
    for j in out:
        blk = re.search(r'href="[^"]*%s[^"]*"(.{0,1200}?)</li>' % re.escape(j["jid"]), html, re.S)
        if not blk:
            continue
        seg = blk.group(1)
        t = re.search(r'title="([^"]{2,60})"', seg)
        c = re.search(r'class="company-name"[^>]*>([^<]{2,40})<', seg)
        s = re.search(r'class="job-salary"[^>]*>([^<]{1,30})<', seg)
        if t:
            j["title"] = t.group(1).strip()
        if c:
            j["company"] = c.group(1).strip()
        if s:
            j["salary_raw"] = s.group(1).strip()
    return [j for j in out if j["title"]]
