# -*- coding: utf-8 -*-
"""BOSS直聘 薪资反混淆 —— 字体私用区字符 → 数字。

原理：BOSS直聘 把薪资数字映射到自定义字体的私用区（PUA）字符，
直接读会显示成空白/方框（例如 '\ue033\ue033-\ue034\ue036K·\ue032\ue037薪'）。

本机实测解出的映射（U+E031..U+E03A → 0..9）：
    \ue031=0  \ue032=1  \ue033=2  \ue034=3  \ue035=4
    \ue036=5  \ue037=6  \ue038=7  \ue039=8  \ue03a=9
即 code - 0xE031 == 数字本身。

站点改版换了字体时怎么重建映射：
  1) 从页面 performance.getEntriesByType('resource') 里找 .ttf/.woff2 字体 URL
  2) 下载字体，用 fontTools 拿 cmap，再用 PIL 把每个字形渲染成图片，
     与 Arial 的 0-9 逐个像素比对，即可恢复映射（顺序不保证，必须比对字形而不是靠顺序猜）
"""
import os
import re
import unicodedata

PUA_START = 0xE031

# 已知字典：即使字体映射整体位移，也能靠这张表兜底
KNOWN = {chr(0xE031 + i): str(i) for i in range(10)}

# 常见拉丁数字（有的岗位薪资没混淆，直接是 '20-35K'）
ASCII = {c: c for c in "0123456789"}

_SALARY_RE = re.compile(r"[\ue000-\uf8ff0-9]+\s*[-~—]\s*[\ue000-\uf8ff0-9]+\s*[Kk万千Ww]?")


def decode_char(ch):
    if ch in ASCII:
        return ch
    if ch in KNOWN:
        return KNOWN[ch]
    cp = ord(ch)
    # 兜底：私用区里若出现连续位移，用「数字区起点」相对解码（本机实测成立）
    if 0xE000 <= cp <= 0xF8FF:
        guess = cp - PUA_START
        if 0 <= guess <= 9:
            return str(guess)
        return ""          # 解不出来宁可丢掉，也不编一个数字
    return ch


def decode_salary(s):
    """把混淆字符串还原成可读薪资，例如 '22-35K·16薪'。"""
    if not s:
        return ""
    return "".join(decode_char(c) for c in s).strip()


def extract_salary(text):
    """从一段卡片文本里抠出薪资段（不依赖具体 class，抗改版）。"""
    if not text:
        return ""
    t = " ".join(str(text).split())
    m = _SALARY_RE.search(t)
    if m:
        return decode_salary(m.group(0))
    # 没有区间（如「薪资面议」）就原样返回
    for kw in ("面议", "薪资面议"):
        if kw in t:
            return "面议"
    return ""


def load_map(path=None):
    """读取外部 fontmap.json（若用户自己重建过映射，优先用它）。"""
    import json
    if not path:
        return dict(KNOWN)
    if not os.path.isfile(path):
        return dict(KNOWN)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if k}


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["\ue033\ue033-\ue034\ue036K·\ue032\ue037薪"]:
        print(f"{s!r} -> {decode_salary(s)}")
