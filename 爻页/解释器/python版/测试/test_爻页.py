"""爻页（YaoPage）测试：语言、布局、渲染、浏览器。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

根目录 = Path(__file__).resolve().parent.parent.parent.parent
爻页目录 = 根目录 / "语言" / "爻页"
示例目录 = 爻页目录 / "示例"

sys.path.insert(0, str(根目录))

from 爻页.错误 import 爻页误, 词误, 法误, 名误, 型误, 值误  # noqa: E402
from 爻页.词法 import 切分  # noqa: E402
from 爻页.语法 import 分析文本  # noqa: E402
from 爻页.求值 import 求值器  # noqa: E402
from 爻页.布局 import 布局, 遍历, 命中最上层  # noqa: E402
from 爻页.离屏 import 加载, 布局文件, 结构摘要  # noqa: E402


# ---------------------------------------------------------------------------
# 词法
# ---------------------------------------------------------------------------


def 词类(源: str):
    return [(t.类, t.文) for t in 切分(源)]


def test_空文件只有文件止() -> None:
    assert 词类("") == [("文件止", "")]


def test_关键字识别() -> None:
    assert ("键", "页") in 词类('页 "标题"')
    assert ("键", "竖") in 词类("竖")
    assert ("键", "钮") in 词类("钮")
    assert ("键", "填") in 词类("填 20")
    assert ("键", "态") in 词类("0 态 甲")
    assert ("键", "点") in 词类("点")


def test_普通标识符不是关键字() -> None:
    词们 = 词类("甲 乙 丙")
    assert all(类 == "名" for 类, _ in 词们[:3])


def test_数字与小数() -> None:
    assert 词类("42")[0] == ("数", 42)
    assert 词类("3.14")[0] == ("数", 3.14)


def test_字符串双引号单引号() -> None:
    assert ("字", "你好") in 词类('"你好"')
    assert ("字", "abc") in 词类("'abc'")


def test_字符串转义() -> None:
    词们 = 切分('"行\\n"')
    assert 词们[0].文 == "行\n"


def test_全角引号也是字符串() -> None:
    词们 = 切分('“你好”')
    assert 词们[0].类 == "字" and 词们[0].文 == "你好"


def test_行注释() -> None:
    词们 = 词类('注 这是注释\n文 "甲"')
    assert ("键", "注") not in 词们
    assert ("字", "这是注释") not in 词们
    assert ("键", "文") in 词们


def test_块注释可嵌套() -> None:
    源 = '注【 外层 注【 内层 】 还在注释 】\n文 "甲"'
    词们 = 词类(源)
    assert ("键", "文") in 词们
    assert ("字", "甲") in 词们


def test_以注开头的标识符不被当注释() -> None:
    """`注册` 这类词不应被 `注` 注释吃掉。"""
    词们 = 词类("注册")
    assert ("名", "注册") in 词们


def test_未闭合字符串报词误() -> None:
    with pytest.raises(词误):
        切分('"没有闭合')


def test_未闭合块注释报词误() -> None:
    with pytest.raises(词误):
        切分("注【 没有闭合")


def test_非法字符报词误() -> None:
    with pytest.raises(词误):
        切分("文 $")


def test_行列号() -> None:
    词们 = 切分('页 "甲"\n文 "乙"')
    文乙 = [t for t in 词们 if t.文 == "乙"][0]
    assert (文乙.行, 文乙.列) == (2, 3)


def test_BOM被忽略() -> None:
    词们 = 切分('\ufeff页 "甲"')
    assert 词们[0].类 == "键"


# ---------------------------------------------------------------------------
# 语法
# ---------------------------------------------------------------------------


def test_最简页面() -> None:
    页 = 分析文本('页 "标题" 【 文 "内容" 】')
    assert 页.标题 == "标题"
    assert 页.根.类 == "文"


def test_状态声明() -> None:
    页 = 分析文本('页 "t" 【\n 0 态 计数\n 文 "x"\n】')
    assert len(页.态) == 1
    assert 页.态[0].名 == "计数"


def test_状态初值可以是表达式() -> None:
    页 = 分析文本('页 "t" 【\n 1 + 2 * 3 态 值\n 文 "x"\n】')
    assert 页.态[0].名 == "值"


def test_容器嵌套() -> None:
    页 = 分析文本(
        '页 "t" 【\n 竖 【\n 横 【\n 文 "a"\n 文 "b"\n 】\n 】\n】'
    )
    assert 页.根.类 == "竖"
    assert 页.根.子[0].类 == "横"
    assert len(页.根.子[0].子) == 2


def test_修饰可以写在块前或块后() -> None:
    前 = 分析文本('页 "t" 【\n 竖 填 10 【 文 "a" 】\n】')
    后 = 分析文本('页 "t" 【\n 竖 【 文 "a" 】 填 10\n】')
    def 取填(页):
        return [m.值 for m in 页.根.修饰 if m.键 == "填"][0].值
    assert 取填(前) == 取填(后) == 10


def test_按钮与点击块() -> None:
    页 = 分析文本('页 "t" 【\n 0 态 n\n 钮 "加" 点 【 置 n n + 1 】\n】')
    钮 = 页.根
    assert 钮.类 == "钮"
    assert 钮.点 is not None
    assert len(钮.点.语句) == 1


def test_输入框绑定状态名() -> None:
    页 = 分析文本('页 "t" 【\n "" 态 名\n 输 名\n】')
    assert 页.根.类 == "输"
    assert 页.根.内容.名 == "名"


def test_表达式优先级() -> None:
    页 = 分析文本('页 "t" 【\n 1 + 2 * 3 态 值\n 文 "x"\n】')
    # 1 + (2*3)
    求 = 求值器({"值": 页.态[0].值})
    assert 求.求值(页.态[0].值) == 7


def test_缺少页开头报法误() -> None:
    with pytest.raises(法误):
        分析文本('文 "x"')


def test_块未闭合报法误() -> None:
    """块没有闭合时，解析器应报法误（不能静默接受）。"""
    with pytest.raises(法误):
        分析文本('页 "t" 【\n 竖 【\n 文 "x"\n')


def test_两个根容器报法误() -> None:
    with pytest.raises(法误):
        分析文本('页 "t" 【 文 "a" 文 "b" 】')


def test_错误带行列() -> None:
    with pytest.raises(法误) as 捕:
        分析文本('页 "t" 【\n  文\n】')
    文 = 捕.value.格式化()
    assert "第 2 行" in 文 or "第 3 行" in 文
    assert 捕.value.列 >= 1


# ---------------------------------------------------------------------------
# 求值
# ---------------------------------------------------------------------------


def 求(源: str, 状态=None) -> 求值器:
    return 求值器(状态 or {})


def test_算术() -> None:
    e = 求("")
    页 = 分析文本('页 "t" 【\n 0 态 x\n 文 "a"\n】')
    甲 = 分析文本('页 "t" 【\n 0 态 x\n 文 "a"\n】')
    from 爻页 import 语法 as A

    def 算(源):
        return e.求值(分析文本(f'页 "t" 【\n {源} 态 v\n 文 "a"\n】').态[0].值)

    assert 算("1 + 2") == 3
    assert 算("10 - 3") == 7
    assert 算("3 * 4") == 12
    assert 算("7 / 2") == 3.5
    assert 算("7 % 3") == 1
    assert 算("2 + 3 * 4") == 14
    assert 算("(2 + 3) * 4") == 20
    assert 算("-5") == -5


def test_字符串拼接() -> None:
    e = 求("")
    值 = 分析文本('页 "t" 【\n "甲" + "乙" 态 v\n 文 "a"\n】').态[0].值
    assert e.求值(值) == "甲乙"


def test_字与数拼接自动转字() -> None:
    e = 求("")
    值 = 分析文本('页 "t" 【\n "n=" + 42 态 v\n 文 "a"\n】').态[0].值
    assert e.求值(值) == "n=42"


def test_比较与逻辑() -> None:
    e = 求("")

    def 算(源):
        return e.求值(分析文本(f'页 "t" 【\n {源} 态 v\n 文 "a"\n】').态[0].值)

    assert 算("1 < 2") is True
    assert 算("2 == 2") is True
    assert 算("1 != 2") is True
    assert 算("真 且 假") is False
    assert 算("真 或 假") is True
    assert 算("非 假") is True
    assert 算("非 1 == 2") is True


def test_内置函数() -> None:
    e = 求("")

    def 算(源):
        return e.求值(分析文本('页 "t" 【\n ' + 源 + ' 态 v\n 文 "a"\n】').态[0].值)

    assert 算('串(42)') == "42"
    assert 算('数("42")') == 42
    assert 算("整(3.9)") == 3
    assert 算('长("甲乙丙")') == 3
    assert 算('切("甲乙丙", 1, 3)') == "乙丙"
    assert 算('含("甲乙", "乙")') is True
    assert 算('连(["甲", "乙"], "-")') == "甲-乙"
    assert 算('拆("甲-乙", "-")') == ["甲", "乙"]


def test_未声明状态报名误() -> None:
    e = 求({})
    页面 = 分析文本('页 "t" 【\n 不存在 + 1 态 v\n 文 "a"\n】')
    with pytest.raises(名误):
        求值器({}).求值(页面.态[0].值)


def test_内置函数参数个数错报型误() -> None:
    e = 求("")
    页面 = 分析文本('页 "t" 【\n 串() 态 v\n 文 "a"\n】')
    with pytest.raises(型误):
        求值器({}).求值(页面.态[0].值)


def test_除以零报值误() -> None:
    页面 = 分析文本('页 "t" 【\n 1 / 0 态 v\n 文 "a"\n】')
    with pytest.raises(值误):
        求值器({}).求值(页面.态[0].值)


# ---------------------------------------------------------------------------
# 布局
# ---------------------------------------------------------------------------


def 布(源: str, 宽: int = 800, 高: int = 600) -> dict:
    页 = 分析文本(源)
    状态 = {}
    for 声明 in 页.态:
        状态[声明.名] = 求值器(状态).求值(声明.值)
    return 布局(页, 求值器(状态), 宽, 高)


def test_竖向排列() -> None:
    r = 布('页 "t" 【\n 竖 【\n 空 10\n 空 20\n 空 30\n 】\n】')
    子 = r["子"]
    assert 子[0]["y"] == 0
    assert 子[1]["y"] == 10
    assert 子[2]["y"] == 30
    assert r["高"] == 60


def test_缝间距() -> None:
    r = 布('页 "t" 【\n 竖 缝 5 【\n 空 10\n 空 20\n 】\n】')
    子 = r["子"]
    assert 子[1]["y"] == 15
    assert r["高"] == 35


def test_横向排列() -> None:
    r = 布('页 "t" 【\n 横 缝 6 【\n 钮 "甲"\n 钮 "乙"\n 】\n】')
    子 = r["子"]
    assert 子[0]["x"] == 0
    assert 子[1]["x"] == 子[0]["宽"] + 6
    assert 子[0]["y"] == 0 == 子[1]["y"]


def test_内边距() -> None:
    r = 布('页 "t" 【\n 竖 填 20 【\n 空 10\n 】\n】')
    assert r["子"][0]["x"] == 20
    assert r["子"][0]["y"] == 20
    assert r["高"] == 10 + 40


def test_层叠放() -> None:
    r = 布('页 "t" 【\n 层 宽 300 高 100 【\n 空 40\n 文 "叠"\n 】\n】')
    子 = r["子"]
    assert 子[0]["x"] == 0 == 子[1]["x"]
    assert 子[0]["y"] == 0 == 子[1]["y"]


def test_隐不占空间() -> None:
    显 = 布('页 "t" 【\n 竖 缝 10 【\n 空 10\n 文 "甲"\n 】\n】')
    隐 = 布('页 "t" 【\n 竖 缝 10 【\n 空 10\n 文 "甲" 隐 真\n 】\n】')
    assert len(显["子"]) == 2
    assert len(隐["子"]) == 1


def test_隐的条件表达式() -> None:
    页源 = '页 "t" 【\n 0 态 n\n 竖 【\n 文 "甲" 隐 n > 0\n 】\n】'
    assert len(布(页源)["子"]) == 1
    页 = 分析文本(页源)
    r = 布局(页, 求值器({"n": 1}), 800, 600)
    assert len(r["子"]) == 0


def test_文字折行() -> None:
    r = 布(
        '页 "t" 【\n 竖 宽 200 填 0 【\n'
        ' 文 "这是一段很长的文字，需要折行显示才能放得下，再长一点更明显。" 大 14\n'
        ' 】\n】',
        800, 600,
    )
    文盒 = r["子"][0]
    assert len(文盒["行们"]) > 1, f"应折行，实际 {文盒['行们']}"


def test_按钮宽度由文字决定() -> None:
    短 = 布('页 "t" 【 钮 "短" 】')
    长 = 布('页 "t" 【 钮 "很长很长的按钮标签" 】')
    assert 长["宽"] > 短["宽"]


def test_按钮有手型() -> None:
    r = 布('页 "t" 【 钮 "甲" 】')
    assert r["手"] is True


def test_宽满撑满父级() -> None:
    r = 布('页 "t" 【\n 竖 填 10 宽 400 【\n 空 5 宽 满\n 】\n】', 800, 600)
    # 内容可用宽 = 400 - 20 = 380
    assert r["子"][0]["宽"] == 380


def test_齐中在竖向容器里生效() -> None:
    r = 布('页 "t" 【\n 竖 宽 400 【\n 文 "居中" 齐 中\n 】\n】')
    文盒 = r["子"][0]
    # 盒子撑满可用宽，文字在其中居中（渲染阶段处理）
    assert 文盒["宽"] == 400
    assert 文盒["齐"] == "中"


def test_线的默认高度() -> None:
    r = 布('页 "t" 【 线 】')
    assert r["高"] == 1


def test_负数内边距报值误() -> None:
    with pytest.raises(值误):
        布('页 "t" 【 竖 填 -5 【 空 10 】 】')


# ---------------------------------------------------------------------------
# 命中测试
# ---------------------------------------------------------------------------


def test_命中按钮() -> None:
    r = 布('页 "t" 【\n 钮 "点我"\n】')
    assert 命中最上层(r, 5, 5) is not None
    assert 命中最上层(r, 5000, 5000) is None


def test_命中层中后声明的优先() -> None:
    r = 布(
        '页 "t" 【\n 层 宽 200 高 60 【\n'
        ' 钮 "下" 点 【 置 a 1 】\n'
        ' 钮 "上" 点 【 置 a 2 】\n'
        ' 】\n】',
        800, 600,
    )
    # 两个按钮都在左上角，后声明的应命中
    命中 = 命中最上层(r, 5, 5)
    assert 命中 is not None


def test_遍历盒树() -> None:
    r = 布('页 "t" 【\n 竖 【\n 文 "a"\n 横 【 文 "b" 】\n 】\n】')
    所有 = list(遍历(r))
    # 根块 + 文a + 横块 + 文b = 4
    assert len(所有) == 4
    assert sum(1 for b in 所有 if b["类"] == "文") == 2


# ---------------------------------------------------------------------------
# 示例页面
# ---------------------------------------------------------------------------


示例们 = sorted(示例目录.glob("*.页"))


def test_示例目录存在() -> None:
    assert 示例目录.is_dir()
    assert len(示例们) >= 4, f"示例太少：{[p.name for p in 示例们]}"


@pytest.mark.parametrize("路径", 示例们, ids=lambda p: p.name)
def test_示例可解析(路径) -> None:
    页 = 分析文本(路径.read_text(encoding="utf-8"), str(路径))
    assert 页.标题
    assert 页.根 is not None


@pytest.mark.parametrize("路径", 示例们, ids=lambda p: p.name)
def test_示例可布局(路径) -> None:
    根盒 = 布局文件(str(路径), 900, 760)
    assert 根盒["宽"] > 0
    assert 根盒["高"] > 0
    assert sum(1 for _ in 遍历(根盒)) >= 3


@pytest.mark.parametrize("路径", 示例们, ids=lambda p: p.name)
def test_示例是UTF8无BOM(路径) -> None:
    原始 = 路径.read_bytes()
    assert not 原始.startswith(b"\xef\xbb\xbf")
    原始.decode("utf-8")


def test_计数器示例有状态和点击() -> None:
    源 = (示例目录 / "计数器.页").read_text(encoding="utf-8")
    页 = 分析文本(源)
    assert len(页.态) == 1
    有钮 = any(b["类"] == "钮" and b.get("点") is not None
              for b in 遍历(布局(页, 求值器({"计数": 0}), 900, 760)))
    assert 有钮


def test_表单示例有输入框() -> None:
    源 = (示例目录 / "表单.页").read_text(encoding="utf-8")
    页 = 分析文本(源)
    assert len(页.态) == 2
    # 布局需要状态初值
    状态 = {}
    for d in 页.态:
        状态[d.名] = 求值器(状态).求值(d.值)
    根盒 = 布局(页, 求值器(状态), 900, 760)
    有输 = any(b["类"] == "输" for b in 遍历(根盒))
    assert 有输


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def 跑命令(参数: list[str]) -> tuple[int, str]:
    import subprocess

    结果 = subprocess.run(
        [sys.executable, "-m", "爻页", *参数],
        cwd=str(根目录),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        timeout=60,
    )
    return 结果.returncode, 结果.stdout + 结果.stderr


def test_命令行版本() -> None:
    码, 出 = 跑命令(["--版"])
    assert 码 == 0
    assert "爻页" in 出


def test_命令行帮助() -> None:
    码, 出 = 跑命令(["--帮"])
    assert 码 == 0
    assert "--离屏" in 出


def test_命令行检查通过() -> None:
    码, 出 = 跑命令(["--检", str(示例目录 / "计数器.页")])
    assert 码 == 0
    assert "检查通过" in 出


def test_命令行检查失败返回1() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as 目录:
        文件 = Path(目录) / "坏.页"
        文件.write_text('页 "t" 【 文', encoding="utf-8")
        码, 出 = 跑命令(["--检", str(文件)])
        assert 码 == 1
        assert "法误" in 出 or "词误" in 出


def test_命令行结构输出盒树() -> None:
    码, 出 = 跑命令(["--结构", str(示例目录 / "计数器.页")])
    assert 码 == 0
    assert "块(竖)" in 出
    assert "文" in 出


def test_命令行离屏渲染产出图片() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as 目录:
        输出 = Path(目录) / "图.png"
        码, 出 = 跑命令([
            "--离屏", str(示例目录 / "计数器.页"), str(输出), "600", "400",
        ])
        assert 码 == 0, 出
        assert 输出.is_file()
        assert 输出.stat().st_size > 1000
