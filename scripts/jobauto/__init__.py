# -*- coding: utf-8 -*-
"""jobauto —— 招聘平台（BOSS直聘 / 猎聘）投递与话术自动化工具包。

子模块：
  launcher  —— 启动/自检「可被脚本控制」的独立浏览器（不动日常 profile）
  driver    —— webctl2.py（原生 CDP）的 Python 封装
  chatui    —— 沟通按钮状态机 + 消息发送（三重兜底 + 回读校验）
  platforms —— 搜索 URL / 列表抓取 / 详情抓取
  fontmap   —— BOSS直聘 薪资字体反混淆
  messages  —— 话术引擎（JD → 定制招呼语）
  sender    —— 分批发送 + 断点续传
  verify    —— 送达核实 + 收件箱盘点

纪律见 SKILL.md。仅供效率提升，使用者须自行遵守各平台用户协议与投放频率限制。
"""

__version__ = "1.0.0"

__all__ = [
    "launcher", "driver", "chatui", "platforms",
    "fontmap", "messages", "sender", "verify",
]
