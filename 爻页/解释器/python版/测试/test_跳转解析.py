"""爻页浏览器「跳」的目标解析测试。

这个 bug 曾出现过：从 http:// 加载的页面，点「跳 总览.页」会当成
本地文件去找，报 "无法打开文件：C:\\...\\总览.页"。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

根目录 = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(根目录))


@pytest.fixture(scope="module")
def 浏览器类():
    pytest.importorskip("tkinter")
    from 爻页.浏览器 import 浏览器

    return 浏览器


@pytest.fixture
def 浏(浏览器类):
    """构造一个不显示窗口的浏览器实例，只测纯逻辑。"""
    import tkinter as tk

    根窗 = tk.Tk()
    根窗.withdraw()
    try:
        实例 = 浏览器类(根窗, 初始页="")
        根窗.update()
        yield 实例
    finally:
        根窗.destroy()


def test_从根URL跳页面名(浏) -> None:
    浏.当前路径 = "http://127.0.0.1:8795/"
    assert 浏._解析跳转目标("总览.页") == "http://127.0.0.1:8795/页/总览"


def test_从根URL跳多个页面(浏) -> None:
    浏.当前路径 = "http://127.0.0.1:8795/"
    for 名 in ("总览", "设备", "分拣", "分析", "告警", "物联", "用户", "参数", "登录"):
        目标 = 浏._解析跳转目标(f"{名}.页")
        assert 目标 == f"http://127.0.0.1:8795/页/{名}", 目标


def test_从页URL跳页面名(浏) -> None:
    浏.当前路径 = "http://127.0.0.1:8795/页/总览"
    assert 浏._解析跳转目标("设备.页") == "http://127.0.0.1:8795/页/设备"


def test_带端口的主机(浏) -> None:
    浏.当前路径 = "http://192.168.1.10:9000/"
    assert 浏._解析跳转目标("分析.页") == "http://192.168.1.10:9000/页/分析"


def test_https也支持(浏) -> None:
    浏.当前路径 = "https://example.com/"
    assert 浏._解析跳转目标("总览.页") == "https://example.com/页/总览"


def test_目标已是URL保持原样(浏) -> None:
    浏.当前路径 = "http://127.0.0.1:8795/"
    原 = "http://other.host:1234/页/某页"
    assert 浏._解析跳转目标(原) == 原


def test_本地文件相对跳转(浏) -> None:
    页面目录 = 根目录 / "examples" / "分拣监控" / "页面"
    浏.当前路径 = str(页面目录 / "总览.页")
    目标 = 浏._解析跳转目标("设备.页")
    assert 目标.endswith("设备.页"), 目标
    assert "examples" in 目标, "本地页面跳转应该解析成文件路径"


def test_本地文件绝不拼成URL(浏) -> None:
    页面目录 = 根目录 / "examples" / "分拣监控" / "页面"
    浏.当前路径 = str(页面目录 / "登录.页")
    目标 = 浏._解析跳转目标("总览.页")
    assert not 目标.startswith("http"), 目标


def test_绝对路径保持原样(浏) -> None:
    浏.当前路径 = "http://127.0.0.1:8795/"
    绝对 = str(根目录 / "examples" / "分拣监控" / "页面" / "总览.页")
    assert 浏._解析跳转目标(绝对) == 绝对


def test_真实URL跳转() -> None:
    """后端在跑时验证端到端跳转，否则跳过。"""
    pytest.importorskip("tkinter")
    import tkinter as tk
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8795/api/健康", timeout=1) as r:
            if r.status != 200:
                pytest.skip("后端未就绪")
    except Exception:
        pytest.skip("后端未运行")

    from 爻页.浏览器 import 浏览器

    根窗 = tk.Tk()
    根窗.withdraw()
    try:
        实 = 浏览器(根窗, 初始页="http://127.0.0.1:8795/")
        根窗.update()
        assert 实.页面对象 is not None, "URL 页面未渲染"
        实.求值器.动作 = [("跳", "总览.页", None)]
        实._执行动作()
        根窗.update()
        assert "总览" in getattr(实.页面对象, "标题", ""), 实.页面对象.标题
        assert 实.地址框.get().endswith("/页/总览"), 实.地址框.get()
    finally:
        根窗.destroy()
