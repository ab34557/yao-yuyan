"""登录流程真实键鼠测试。

这个 bug 曾出现过两次，都是同一个模式：
    判 条件 【 真 ⇒ 【...回 0】 它 ⇒ 回 0 】
「它 ⇒ 回 0」在条件为假时也返回，导致后面的业务逻辑永远不执行
—— 用户点登录按钮后什么都没发生。

本测试用真实键盘输入 + 真实鼠标点击走完整流程，确保：
  1. 点登录按钮真的会调用登录函数
  2. 正确密码能跳转到总览
  3. 错误密码显示明确提示且不跳转
  4. 空账号有提示
  5. 跳转后能拿到数据
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

根目录 = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(根目录))

页面目录 = 根目录 / "examples" / "分拣监控" / "页面"


@pytest.fixture(scope="module")
def 后端在跑():
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8795/api/健康", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.fixture
def 浏览器():
    tk = pytest.importorskip("tkinter")
    from 爻页.浏览器 import 浏览器 as 浏类

    根窗 = tk.Tk()
    根窗.geometry("1200x900")
    try:
        实例 = 浏类(根窗, 初始页="http://127.0.0.1:8795/")
        根窗.update()
        截止 = time.time() + 3
        while time.time() < 截止 and 实例.页面对象 is None:
            根窗.update()
            time.sleep(0.05)
        yield 根窗, 实例
    finally:
        根窗.destroy()


def 带坐标(盒, 父x=0.0, 父y=0.0):
    x, y = 盒["x"] + 父x, 盒["y"] + 父y
    出 = [(盒, x, y)]
    for 子 in 盒.get("子", []):
        出.extend(带坐标(子, x, y))
    return 出


def 点(浏, 根窗, x, y):
    浏.画布.event_generate("<Button-1>", x=int(x), y=int(y))
    根窗.update()
    time.sleep(0.12)
    浏.画布.event_generate("<ButtonRelease-1>", x=int(x), y=int(y))
    根窗.update()
    time.sleep(0.15)


def 打字(浏, 根窗, 文字):
    """走浏览器真实的 _按键 处理入口。"""
    from types import SimpleNamespace

    for 字 in 文字:
        浏._按键(SimpleNamespace(keysym=字, char=字, widget=浏.画布))
        根窗.update()
        time.sleep(0.06)
    time.sleep(0.12)


def 填账号密码(浏, 根窗, 账号, 密码):
    框 = [(b, x, y) for b, x, y in 带坐标(浏.根盒) if b["类"] == "输"]
    assert len(框) >= 2, f"应该有 2 个输入框，实际 {len(框)}"

    b, x, y = 框[0]
    点(浏, 根窗, x + b["宽"] / 2, y + b["高"] / 2)
    打字(浏, 根窗, 账号)

    框 = [(b, x, y) for b, x, y in 带坐标(浏.根盒) if b["类"] == "输"]
    b, x, y = 框[1]
    点(浏, 根窗, x + b["宽"] / 2, y + b["高"] / 2)
    打字(浏, 根窗, 密码)


def 点登录(浏, 根窗):
    钮 = [(b, x, y) for b, x, y in 带坐标(浏.根盒)
           if b["类"] == "钮" and b.get("文本") == "登 录"]
    assert 钮, "找不到「登 录」按钮"
    b, x, y = 钮[0]
    点(浏, 根窗, x + b["宽"] / 2, y + b["高"] / 2)


def 等到(根窗, 条件, 秒=5.0):
    截 = time.time()
    while time.time() - 截 < 秒:
        根窗.update()
        if 条件():
            return True
        time.sleep(0.05)
    return 条件()


# ---------------------------------------------------------------------------
# 静态检查：不能有「它 ⇒ 回 0」这种致命写法
# ---------------------------------------------------------------------------


def test_登录页没有致命逻辑() -> None:
    """`它 ⇒ 回 0` 会让函数无条件返回，后面的逻辑永远不执行。"""
    源 = (页面目录 / "登录.页").read_text(encoding="utf-8")
    行们 = 源.splitlines()
    坏行 = [
        (i + 1, 行.strip())
        for i, 行 in enumerate(行们)
        if "它 ⇒ 回 0" in 行 and "真 ⇒" not in 行
    ]
    assert not 坏行, f"登录页有致命逻辑（条件为假时也返回）：{坏行}"


def test_所有页面都没有致命逻辑() -> None:
    """全量扫描：所有 .页 文件都不该出现单独的 `它 ⇒ 回 0`。"""
    坏 = []
    for pf in 页面目录.glob("*.页"):
        源 = pf.read_text(encoding="utf-8")
        for i, 行 in enumerate(源.splitlines(), 1):
            剥 = 行.strip()
            if 剥.startswith("它 ⇒ 回 0") or 剥 == "它 ⇒ 回 0":
                坏.append(f"{pf.name}:{i}")
    assert not 坏, f"以下位置有致命逻辑：{坏}"


# ---------------------------------------------------------------------------
# 真实键鼠流程
# ---------------------------------------------------------------------------


def test_空账号有提示(浏览器, 后端在跑) -> None:
    if not 后端在跑:
        pytest.skip("后端未运行")
    根窗, 浏 = 浏览器
    点登录(浏, 根窗)
    等到(根窗, lambda: bool(浏.求值器.状态.get("提示")), 2)
    assert 浏.求值器.状态.get("提示") == "请输入账号", 浏.求值器.状态.get("提示")


def test_错误密码显示明确提示(浏览器, 后端在跑) -> None:
    if not 后端在跑:
        pytest.skip("后端未运行")
    根窗, 浏 = 浏览器
    填账号密码(浏, 根窗, "admin", "错误的密码")
    assert 浏.求值器.状态.get("账号") == "admin"
    assert 浏.求值器.状态.get("密码") == "错误的密码"

    点登录(浏, 根窗)
    等到(根窗, lambda: "✗" in str(浏.求值器.状态.get("提示", "")), 4)

    提示 = 浏.求值器.状态.get("提示", "")
    assert "✗" in 提示, f"应显示错误标记，实际：{提示!r}"
    assert "错误" in 提示, f"应说明错误原因，实际：{提示!r}"
    # 不该跳转
    assert "登录" in 浏.页面对象.标题, 浏.页面对象.标题


def test_正确密码跳转到总览(浏览器, 后端在跑) -> None:
    if not 后端在跑:
        pytest.skip("后端未运行")
    根窗, 浏 = 浏览器
    填账号密码(浏, 根窗, "admin", "admin123")
    assert 浏.求值器.状态.get("账号") == "admin"
    assert 浏.求值器.状态.get("密码") == "admin123"

    点登录(浏, 根窗)
    跳到 = 等到(根窗, lambda: "总览" in 浏.页面对象.标题, 6)

    assert 跳到, f"点登录后应跳转到总览，实际仍在：{浏.页面对象.标题}"
    assert "/页/总览" in 浏.地址框.get(), 浏.地址框.get()


def test_跳转后能拿到实时数据(浏览器, 后端在跑) -> None:
    if not 后端在跑:
        pytest.skip("后端未运行")
    根窗, 浏 = 浏览器
    填账号密码(浏, 根窗, "admin", "admin123")
    点登录(浏, 根窗)
    if not 等到(根窗, lambda: "总览" in 浏.页面对象.标题, 6):
        pytest.skip("未能跳转，前置测试已覆盖")

    等到(根窗, lambda: 浏.求值器.状态.get("总到达", 0) > 0, 5)
    态 = 浏.求值器.状态
    assert 态.get("总到达", 0) > 0, "总览应取到实时数据"
    assert isinstance(态.get("设备们"), list), "应有设备列表"
    assert len(态["设备们"]) == 6, f"应有 6 台设备，实际 {len(态['设备们'])}"


def test_跳转后点导航能切页(浏览器, 后端在跑) -> None:
    if not 后端在跑:
        pytest.skip("后端未运行")
    根窗, 浏 = 浏览器
    填账号密码(浏, 根窗, "admin", "admin123")
    点登录(浏, 根窗)
    if not 等到(根窗, lambda: "总览" in 浏.页面对象.标题, 6):
        pytest.skip("未能跳转")

    钮 = [(b, x, y) for b, x, y in 带坐标(浏.根盒)
           if b["类"] == "钮" and b.get("文本") == "分析"]
    assert 钮, "总览页应该有「分析」导航按钮"
    b, x, y = 钮[0]
    点(浏, 根窗, x + b["宽"] / 2, y + b["高"] / 2)

    换页 = 等到(根窗, lambda: "分析" in 浏.页面对象.标题, 6)
    assert 换页, f"点导航应切到分析页，实际：{浏.页面对象.标题}"
    assert "/页/分析" in 浏.地址框.get(), 浏.地址框.get()
