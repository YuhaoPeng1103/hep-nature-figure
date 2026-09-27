#!/usr/bin/env python3
"""
_console —— 控制台编码兜底：把 stdout / stderr 切成 UTF-8
======================================================================

**为什么需要它（实测踩过的坑，2026-09-27）**

本 skill 的报告里大量使用 ✅ / ❌ / ⚠️ / ✗ 这类符号。中文 Windows 上
Python 只在 **交互式控制台（isatty=True）** 才用 UTF-8 输出；一旦
**stdout 被管道或重定向**（agent 调脚本、CI、`python x.py > log.txt`
全是这种），Python 改用本地编码 gbk(cp936) 去编码 —— 这些字符
GBK 编不出来，于是脚本在**打印报告的中途**崩掉：

    UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'

实测：`python evals/test_tools.py`、`python scripts/check_tools.py`
在管道下 100% 崩，而交互式手敲同一条命令却正常 —— 所以这个坑
**只在自动化里炸**，正是本 skill 的主要使用方式。

**用法**：在脚本（或会被 import 的库模块）顶部调用一次即可，幂等：

    from _console import init_console
    init_console()

★ 只改编码，不改行为：已经是 UTF-8 的流上调用是空操作；
  `errors="replace"` 保证连"编码探不出来"的字符也不会再抛异常
  （宁可显示成 ?，也不要整个脚本崩掉）。
"""
import sys


def init_console() -> None:
    """把标准输出 / 标准错误切到 UTF-8（失败时静默跳过，绝不因此报错）。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:            # pythonw / 被替换掉的流
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


init_console()
