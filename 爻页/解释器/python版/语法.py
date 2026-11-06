"""爻页语法分析：递归下降 + Pratt 表达式。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .错误 import 法误
from .词法 import 词, 结构, 元素, 修饰, 对齐

# ---------------------------------------------------------------------------
# 抽象节点
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class 节点:
    行: int = 0
    列: int = 0


@dataclass(slots=True)
class 数(节点):
    值: Any = 0


@dataclass(slots=True)
class 字(节点):
    值: str = ""


@dataclass(slots=True)
class 真(节点):
    值: bool = True


@dataclass(slots=True)
class 空值(节点):
    pass


@dataclass(slots=True)
class 名(节点):
    名: str = ""


@dataclass(slots=True)
class 一元(节点):
    运算: str = "-"
    右: 节点 | None = None


@dataclass(slots=True)
class 二元(节点):
    运算: str = "+"
    左: 节点 | None = None
    右: 节点 | None = None


@dataclass(slots=True)
class 调用(节点):
    被调: str = ""
    参: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 表(节点):
    """表字面量 { "键" ⇒ 值, … }"""
    对: list[tuple[str, 节点]] = field(default_factory=list)


@dataclass(slots=True)
class 列(节点):
    """列表字面量 [甲, 乙, 丙]"""
    元素: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 状态声明(节点):
    名: str = ""
    值: 节点 | None = None


@dataclass(slots=True)
class 赋值(节点):
    """置 状态名 表达式"""
    名: str = ""
    值: 节点 | None = None


@dataclass(slots=True)
class 调用接口(节点):
    """调 接口路径 体表达式 归 结果状态"""
    路径: "节点 | None" = None
    体: "节点 | None" = None
    结果名: str = ""


@dataclass(slots=True)
class 返回(节点):
    """回 表达式? —— 从函数返回"""
    值: 节点 | None = None


@dataclass(slots=True)
class 函数定义(节点):
    """匠 名(参数们) 【 … 】"""
    名: str = ""
    参数们: list[str] = field(default_factory=list)
    体: 块节点 | None = None


@dataclass(slots=True)
class 调用语句(节点):
    """行 表达式 —— 在语句位置调用（丢弃返回值）"""
    表达式: 节点 | None = None


@dataclass(slots=True)
class 定时(节点):
    """次 N 毫秒 【 … 】 —— 每 N 毫秒执行一次块"""
    间隔: 节点 | None = None
    体: 块节点 | None = None


@dataclass(slots=True)
class 分支(节点):
    """判 条件 【 真 ⇒ 语句 它 ⇒ 语句 】"""
    条件: "节点 | None" = None
    真体: "节点 | None" = None
    假体: "节点 | None" = None


@dataclass(slots=True)
class 跳转(节点):
    """跳 页面路径 —— 在浏览器里打开另一个 .页 文件"""
    路径: 节点 | None = None


@dataclass(slots=True)
class 提交(节点):
    """发 接口路径 体表达式 —— POST 后重新执行页面初始化"""
    路径: 节点 | None = None
    体: 节点 | None = None


@dataclass(slots=True)
class 修饰项:
    键: str
    值: Any = None       # 节点，或 真/假/字 这种常量
    行: int = 0
    列: int = 0


@dataclass(slots=True)
class 元素节点(节点):
    类: str = ""                    # 文/钮/输/图/线/空/竖/横/层/列
    内容: 节点 | None = None         # 文:文本表达式 钮:标签表达式 输:状态名 图:路径 空:高度
    点: "块节点 | None" = None       # 钮 的点击块
    修饰: list[修饰项] = field(default_factory=list)
    子: list["元素节点"] = field(default_factory=list)   # 容器
    数据源: 节点 | None = None       # 列: 要遍历的表达式
    项名: str = ""                   # 列: 每一项绑定的名字
    条件: 节点 | None = None         # 条件: 条件渲染的表达式
    真元: "元素节点 | None" = None   # 条件: 条件为真时渲染的元素
    假元: "元素节点 | None" = None   # 条件: 条件为假时渲染的元素
    绑定: str = ""                   # 图线: 数据源状态名


@dataclass(slots=True)
class 块节点(节点):
    语句: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 页面(节点):
    标题: str = ""
    态: list[状态声明] = field(default_factory=list)
    根: 元素节点 | None = None
    始: 块节点 | None = None     # 页面加载时执行（取数据、初始化）
    定时们: list["定时"] = field(default_factory=list)   # 定时刷新块
    函数们: list["函数定义"] = field(default_factory=list)  # 页面内函数


# ---------------------------------------------------------------------------
# 分析器
# ---------------------------------------------------------------------------


class 分析器:
    def __init__(self, 词们: list[词]) -> None:
        self.词们 = 词们
        self.位 = 0

    # -- 基础 --

    def 当前(self) -> 词:
        return self.词们[self.位]

    def 前进(self) -> 词:
        t = self.词们[self.位]
        if self.位 < len(self.词们) - 1:
            self.位 += 1
        return t

    def 是键(self, *文: str) -> bool:
        t = self.当前()
        return t.类 == "键" and t.文 in 文

    def 是符(self, *符: str) -> bool:
        t = self.当前()
        return t.类 == "符" and t.文 in 符

    def 吃键(self, 文: str) -> 词:
        if not self.是键(文):
            t = self.当前()
            raise self.错(f"这里需要「{文}」，实际是「{t.文}」", t)
        return self.前进()

    def 吃符(self, 符: str) -> 词:
        if not self.是符(符):
            t = self.当前()
            raise self.错(f"这里需要「{符}」，实际是「{t.文}」", t)
        return self.前进()

    def 跳换行(self) -> None:
        while self.当前().类 == "换行":
            self.前进()

    def 错(self, 文: str, t: 词 | None = None) -> 法误:
        t = t or self.当前()
        return 法误(文, t.行, t.列)

    def 标识符(self) -> str:
        t = self.当前()
        if t.类 != "名":
            raise self.错(f"这里需要一个名字，实际是「{t.文}」", t)
        self.前进()
        return t.文

    # -- 入口 --

    def 分析页面(self) -> 页面:
        self.跳换行()
        if not self.是键("页"):
            t = self.当前()
            raise self.错("爻页文件必须以「页 \"标题\"」开头", t)
        起 = self.前进()
        标题 = self.字符串()
        self.跳换行()
        if self.当前().类 != "块起":
            raise self.错("页标题之后需要块「【 】」")
        self.前进()
        self.跳换行()

        态们: list[状态声明] = []
        根: 元素节点 | None = None

        始块: 块节点 | None = None
        定时们: list[定时] = []
        函数们: list[函数定义] = []

        while self.当前().类 not in ("块止", "文件止"):
            if self.是键("态"):
                raise self.错("「态」应写在「表达式 态 名字」的形式里（值在左）")
            if self.是键("匠"):
                函数们.append(self.分析函数定义())
                self.跳换行()
                continue

            if self.是键("次"):
                t0 = self.前进()
                self.跳换行()
                间隔 = self.分析表达式()
                self.跳换行()
                if not self.是键("毫秒"):
                    t = self.当前()
                    raise self.错("「次」后面需要「毫秒」作单位", t)
                self.前进()
                self.跳换行()
                if self.当前().类 != "块起":
                    raise self.错("「次 … 毫秒」后面需要块「【 】」")
                self.前进()
                定时语句们: list[节点] = []
                while self.当前().类 not in ("块止", "文件止"):
                    定时语句们.append(self.分析内层语句())
                    self.跳换行()
                if self.当前().类 == "块止":
                    self.前进()
                定时们.append(
                    定时(
                        间隔=间隔,
                        体=块节点(语句=定时语句们, 行=t0.行, 列=t0.列),
                        行=t0.行, 列=t0.列,
                    )
                )
                self.跳换行()
                continue

            if self.是键("始"):
                t0 = self.前进()
                self.跳换行()
                if self.当前().类 != "块起":
                    raise self.错("「始」后面需要块「【 】」")
                self.前进()
                语句们: list[节点] = []
                while self.当前().类 not in ("块止", "文件止"):
                    语句们.append(self.分析始语句())
                    self.跳换行()
                if self.当前().类 == "块止":
                    self.前进()
                始块 = 块节点(语句=语句们, 行=t0.行, 列=t0.列)
                self.跳换行()
                continue
            # 先尝试解析「表达式 态 名」
            保存 = self.位
            if self._尝试状态声明(态们):
                self.跳换行()
                continue
            self.位 = 保存
            # 否则必须是布局节点
            if 根 is not None:
                t = self.当前()
                raise self.错("一个页面只能有一个根容器", t)
            根 = self.分析元素()
            self.跳换行()

        if self.当前().类 == "块止":
            self.前进()

        if 根 is None:
            raise self.错("页面里没有内容", 起)

        return 页面(标题=标题, 态=态们, 根=根, 始=始块, 定时们=定时们,
                  函数们=函数们, 行=起.行, 列=起.列)

    def _尝试状态声明(self, 态们: list[状态声明]) -> bool:
        """尝试解析 `<表达式> 态 <名字>`；失败返回 False 并恢复位置。"""
        起词 = self.当前()
        try:
            值 = self.分析表达式()
        except 法误:
            return False
        if not self.是键("态"):
            return False
        self.前进()
        名 = self.标识符()
        态们.append(状态声明(名=名, 值=值, 行=起词.行, 列=起词.列))
        return True

    def 字符串(self) -> str:
        t = self.当前()
        if t.类 != "字":
            raise self.错(f"这里需要一个字符串，实际是「{t.文}」", t)
        self.前进()
        return t.文

    # -- 元素 --

    def 分析元素(self) -> 元素节点:
        t = self.当前()
        if t.类 != "键":
            raise self.错(f"这里需要一个元素（文/钮/输/图/线/空/竖/横/层/列/判），实际是「{t.文}」", t)

        # 元素位置的条件渲染
        if t.文 == "判":
            return self.分析条件元素()

        类 = t.文

        if 类 in 结构:
            if 类 == "页":
                raise self.错("「页」只能出现在文件开头", t)
            self.前进()
            self.跳换行()
            return self.分析容器(类, t)

        if 类 in 元素:
            self.前进()
            return self.分析普通元素(类, t)

        raise self.错(f"「{类}」不能作为元素", t)

    def 分析条件元素(self) -> 元素节点:
        """判 条件 【 真 ⇒ 元素 它 ⇒ 元素 】 —— 元素位置的条件渲染。"""
        t = self.吃键("判")
        条件 = self.分析表达式()
        self.跳换行()
        if self.当前().类 != "块起":
            raise self.错("「判」条件后面需要块「【 】」")
        self.前进()
        self.跳换行()

        真元: 元素节点 | None = None
        假元: 元素节点 | None = None

        while self.当前().类 not in ("块止", "文件止"):
            if self.是键("真"):
                self.前进()
                键 = "真"
            elif self.是键("假"):
                self.前进()
                键 = "假"
            elif self.是键("它"):
                self.前进()
                键 = "它"
            else:
                tt = self.当前()
                raise self.错("分支臂只能是「真」「假」或「它」", tt)
            self.跳换行()
            self.吃符("=>")
            self.跳换行()
            元 = self.分析元素()
            if 键 == "真":
                真元 = 元
            else:
                假元 = 元
            self.跳换行()

        if self.当前().类 == "块止":
            self.前进()
        修饰们 = self.分析修饰()
        return 元素节点(
            类="条件", 条件=条件, 真元=真元, 假元=假元, 修饰=修饰们,
            行=t.行, 列=t.列,
        )

    def 分析容器(self, 类: str, 起词: 词) -> 元素节点:
        # 修饰可以写在块之前，也可以写在块之后（两种都支持，更贴合直觉）
        前修饰 = self.分析修饰()
        if self.当前().类 != "块起":
            t = self.当前()
            raise self.错(
                f"容器「{类}」后面需要块「【 】」，实际是「{t.文}」", t
            )
        self.前进()
        self.跳换行()
        子: list[元素节点] = []
        while self.当前().类 not in ("块止", "文件止"):
            if self.是键("态"):
                raise self.错("「态」只能写在页面顶层")
            子.append(self.分析元素())
            self.跳换行()
        if self.当前().类 == "块止":
            self.前进()
        else:
            raise self.错(f"容器「{类}」的块没有闭合")

        后修饰 = self.分析修饰()
        return 元素节点(
            类=类, 子=子, 修饰=前修饰 + 后修饰, 行=起词.行, 列=起词.列
        )

    def 分析普通元素(self, 类: str, 起词: 词) -> 元素节点:
        内容: 节点 | None = None
        点名: str | None = None
        点块: 块节点 | None = None

        数据源: 节点 | None = None
        项名 = ""

        if 类 == "线":
            pass
        elif 类 == "输":
            内容 = 名(名=self.标识符(), 行=起词.行, 列=起词.列)
        elif 类 == "图线":
            # 图线 状态名 修饰们
            内容 = 名(名=self.标识符(), 行=起词.行, 列=起词.列)

        elif 类 == "列":
            # 列 项名 于 数据源 【 … 】
            项名 = self.标识符()
            self.跳换行()
            self.吃键("于")
            self.跳换行()
            数据源 = self.分析表达式()
            self.跳换行()
            if self.当前().类 != "块起":
                raise self.错("「列」的数据源后面需要块「【 】」")
            self.前进()
            self.跳换行()
            子们: list[元素节点] = []
            while self.当前().类 not in ("块止", "文件止"):
                子们.append(self.分析元素())
                self.跳换行()
            if self.当前().类 == "块止":
                self.前进()
            修饰们 = self.分析修饰()
            return 元素节点(
                类="列", 子=子们, 数据源=数据源, 项名=项名, 修饰=修饰们,
                行=起词.行, 列=起词.列,
            )
        else:
            内容 = self.分析表达式()

        if 类 == "钮" and self.是键("点"):
            self.前进()
            self.跳换行()
            if self.当前().类 != "块起":
                raise self.错("「点」后面需要块")
            self.前进()
            语句们: list[节点] = []
            while self.当前().类 not in ("块止", "文件止"):
                if self.是键("置"):
                    语句们.append(self.分析置())
                elif self.是键("跳"):
                    语句们.append(self.分析跳())
                elif self.是键("调"):
                    语句们.append(self.分析调())
                elif self.是键("行"):
                    t2 = self.前进()
                    self.跳换行()
                    表达式2 = self.分析表达式()
                    nt2 = self.当前()
                    if nt2.类 == "键" and nt2.文 in ("归", "易"):
                        self.前进()
                        名2 = self.标识符()
                        语句们.append(
                            赋值(名=名2, 值=表达式2, 行=t2.行, 列=t2.列)
                        )
                    else:
                        语句们.append(
                            调用语句(表达式=表达式2, 行=t2.行, 列=t2.列)
                        )
                elif self.是键("判"):
                    语句们.append(self.分析判())
                elif self.是键("发"):
                    语句们.append(self.分析发())
                else:
                    语句们.append(self.分析取值赋值())
                self.跳换行()
            if self.当前().类 == "块止":
                self.前进()
            点块 = 块节点(语句=语句们, 行=起词.行, 列=起词.列)

        修饰们 = self.分析修饰()
        return 元素节点(
            类=类, 内容=内容, 点=点块, 修饰=修饰们, 行=起词.行, 列=起词.列,
            数据源=数据源, 项名=项名,
        )

    def 分析置(self) -> 赋值:
        t = self.吃键("置")
        名 = self.标识符()
        值 = self.分析表达式()
        return 赋值(名=名, 值=值, 行=t.行, 列=t.列)

    def 分析函数定义(self) -> 函数定义:
        """匠 名(参数们) 【 … 】"""
        t = self.吃键("匠")
        self.跳换行()
        名 = self.标识符()
        self.跳换行()
        if self.当前().类 != "符" or self.当前().文 != "(":
            raise self.错("函数名后面需要参数列表「( )」")
        self.前进()
        self.跳换行()

        参数们: list[str] = []
        if not (self.当前().类 == "符" and self.当前().文 == ")"):
            while True:
                参数们.append(self.标识符())
                self.跳换行()
                if self.当前().类 == "符" and self.当前().文 == ",":
                    self.前进()
                    self.跳换行()
                    continue
                break
        if not (self.当前().类 == "符" and self.当前().文 == ")"):
            raise self.错("参数列表没有闭合的「)」")
        self.前进()
        self.跳换行()

        if self.当前().类 != "块起":
            raise self.错("函数定义后面需要块「【 】」")
        self.前进()
        语句们: list[节点] = []
        while self.当前().类 not in ("块止", "文件止"):
            语句们.append(self.分析内层语句())
            self.跳换行()
        if self.当前().类 == "块止":
            self.前进()

        return 函数定义(
            名=名, 参数们=参数们,
            体=块节点(语句=语句们, 行=t.行, 列=t.列),
            行=t.行, 列=t.列,
        )

    def 分析判(self) -> 分支:
        """判 条件 【 真 ⇒ 语句 它 ⇒ 语句 】"""
        t = self.吃键("判")
        self.跳换行()
        条件 = self.分析表达式()
        self.跳换行()
        if self.当前().类 != "块起":
            raise self.错("「判」条件后面需要块「【 】」")
        self.前进()
        self.跳换行()

        真体: 节点 | None = None
        假体: 节点 | None = None

        while self.当前().类 not in ("块止", "文件止"):
            if self.是键("真"):
                self.前进()
                键 = "真"
            elif self.是键("假"):
                self.前进()
                键 = "假"
            elif self.是键("它"):
                self.前进()
                键 = "它"
            else:
                tt = self.当前()
                raise self.错("分支臂只能是「真」「假」或「它」", tt)
            self.跳换行()
            if not (self.当前().类 == "符" and self.当前().文 == "=>"):
                raise self.错("这里需要「⇒」")
            self.前进()
            self.跳换行()

            if self.当前().类 == "块起":
                self.前进()
                语句们: list[节点] = []
                while self.当前().类 not in ("块止", "文件止"):
                    语句们.append(self.分析内层语句())
                    self.跳换行()
                if self.当前().类 == "块止":
                    self.前进()
                体 = (
                    语句们[0]
                    if len(语句们) == 1
                    else 块节点(语句=语句们, 行=t.行, 列=t.列)
                )
            else:
                体 = self.分析内层语句()

            if 键 == "真":
                真体 = 体
            else:
                假体 = 体
            self.跳换行()

        if self.当前().类 == "块止":
            self.前进()
        return 分支(条件=条件, 真体=真体, 假体=假体, 行=t.行, 列=t.列)

    def 分析内层语句(self) -> 节点:
        """始块/点块内可用的语句：置 / 发 / 判 / 跳 / 表达式 取 名。"""
        if self.是键("置"):
            return self.分析置()
        if self.是键("发"):
            return self.分析发()
        if self.是键("判"):
            return self.分析判()
        if self.是键("跳"):
            return self.分析跳()
        if self.是键("调"):
            return self.分析调()
        if self.是键("回"):
            t = self.前进()
            self.跳换行()
            值 = None
            if self.当前().类 not in ("换行", "块止", "文件止"):
                值 = self.分析表达式()
            return 返回(值=值, 行=t.行, 列=t.列)
        if self.是键("行"):
            t = self.前进()
            self.跳换行()
            表达式 = self.分析表达式()
            # `行 f() 归 果` / `行 f() 易 果` —— 把返回值写进状态
            nt = self.当前()
            if nt.类 == "键" and nt.文 in ("归", "易"):
                self.前进()
                名 = self.标识符()
                return 赋值(名=名, 值=表达式, 行=t.行, 列=t.列)
            return 调用语句(表达式=表达式, 行=t.行, 列=t.列)
        if self.是键("置"):
            return self.分析置()
        return self.分析取值赋值()

    def 分析始语句(self) -> 节点:
        """「始」块里的语句 —— 与内层语句完全一致。"""
        return self.分析内层语句()

    def 分析取值赋值(self) -> 节点:
        """`表达式 归 状态名` 或 `表达式 易 状态名`。

        * 归：把表达式结果写进状态（可在始块/次块/函数体里新建）
        * 易：修改已有状态
        用「归」作动词，避免与内置函数「取字段」的第一个字冲突。
        """
        起 = self.当前()
        值 = self.分析表达式()
        t = self.当前()
        # 归 / 易 都是保留字（键）
        if t.类 != "键" or t.文 not in ("归", "易"):
            raise self.错(
                "这里需要「归 状态名」或「易 状态名」（把结果写进状态）", t
            )
        self.前进()
        名 = self.标识符()
        return 赋值(名=名, 值=值, 行=起.行, 列=起.列)

    def 分析调(self) -> 调用接口:
        """调 接口路径 体表达式 归 结果名（归 可省略）"""
        t = self.吃键("调")
        路径 = self.分析表达式()
        self.跳换行()
        体: 节点 | None = None
        结果名 = ""
        if self.当前().类 not in ("换行", "块止", "文件止"):
            体 = self.分析表达式()
        if self.是键("归"):
            self.前进()
            结果名 = self.标识符()
        return 调用接口(路径=路径, 体=体, 结果名=结果名, 行=t.行, 列=t.列)

    def 分析跳(self) -> 跳转:
        t = self.吃键("跳")
        路径 = self.分析表达式()
        return 跳转(路径=路径, 行=t.行, 列=t.列)

    def 分析发(self) -> 提交:
        t = self.吃键("发")
        路径 = self.分析表达式()
        体: 节点 | None = None
        if self.当前().类 not in ("换行", "块止", "文件止"):
            体 = self.分析表达式()
        return 提交(路径=路径, 体=体, 行=t.行, 列=t.列)

    def 分析修饰(self) -> list[修饰项]:
        出: list[修饰项] = []
        while True:
            t = self.当前()
            if t.类 != "键" or t.文 not in 修饰:
                break
            键 = t.文
            self.前进()

            if 键 in ("粗", "手", "横排"):
                出.append(修饰项(键=键, 值=True, 行=t.行, 列=t.列))
                continue

            if 键 == "齐":
                v = self.当前()
                if v.类 != "键" or v.文 not in 对齐:
                    raise self.错("「齐」后面需要 左 / 中 / 右", v)
                self.前进()
                出.append(修饰项(键=键, 值=v.文, 行=t.行, 列=t.列))
                continue

            if 键 == "宽":
                if self.是键("满"):
                    self.前进()
                    出.append(修饰项(键=键, 值="满", 行=t.行, 列=t.列))
                    continue
                出.append(修饰项(键=键, 值=self.分析表达式(), 行=t.行, 列=t.列))
                continue

            出.append(修饰项(键=键, 值=self.分析表达式(), 行=t.行, 列=t.列))
        return 出

    # -- 表达式 --

    def 分析表达式(self) -> 节点:
        return self.分析或()

    def 分析或(self) -> 节点:
        左 = self.分析且()
        while self.是键("或"):
            t = self.前进()
            右 = self.分析且()
            左 = 二元(运算="或", 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析且(self) -> 节点:
        左 = self.分析非()
        while self.是键("且"):
            t = self.前进()
            右 = self.分析非()
            左 = 二元(运算="且", 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析非(self) -> 节点:
        if self.是键("非"):
            t = self.前进()
            右 = self.分析非()
            return 一元(运算="非", 右=右, 行=t.行, 列=t.列)
        return self.分析比较()

    def 分析比较(self) -> 节点:
        左 = self.分析加减()
        while self.是符("==", "!=", "<", "<=", ">", ">="):
            t = self.前进()
            右 = self.分析加减()
            左 = 二元(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析加减(self) -> 节点:
        左 = self.分析乘除()
        while self.是符("+", "-"):
            t = self.前进()
            右 = self.分析乘除()
            左 = 二元(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析乘除(self) -> 节点:
        左 = self.分析一元()
        while self.是符("*", "/", "%"):
            t = self.前进()
            右 = self.分析一元()
            左 = 二元(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析一元(self) -> 节点:
        if self.是符("-"):
            t = self.前进()
            return 一元(运算="-", 右=self.分析一元(), 行=t.行, 列=t.列)
        return self.分析后缀()

    def 分析后缀(self) -> 节点:
        左 = self.分析原子()
        while self.是符("("):
            t = self.前进()
            参: list[节点] = []
            if not self.是符(")"):
                while True:
                    参.append(self.分析表达式())
                    if self.是符(","):
                        self.前进()
                        continue
                    break
            self.吃符(")")
            if not isinstance(左, 名):
                raise self.错("只有函数名后面能跟参数", t)
            左 = 调用(被调=左.名, 参=参, 行=t.行, 列=t.列)
        return 左

    def 分析原子(self) -> 节点:
        t = self.当前()

        if t.类 == "数":
            self.前进()
            return 数(值=t.文, 行=t.行, 列=t.列)
        if t.类 == "字":
            self.前进()
            return 字(值=t.文, 行=t.行, 列=t.列)
        if t.类 == "名":
            self.前进()
            return 名(名=t.文, 行=t.行, 列=t.列)
        if t.类 == "键":
            if t.文 == "真":
                self.前进()
                return 真(值=True, 行=t.行, 列=t.列)
            if t.文 == "假":
                self.前进()
                return 真(值=False, 行=t.行, 列=t.列)
            if t.文 == "空值":
                self.前进()
                return 空值(行=t.行, 列=t.列)
        if t.类 == "符" and t.文 == "(":
            self.前进()
            内 = self.分析表达式()
            self.吃符(")")
            return 内

        if t.类 == "符" and t.文 == "{":
            self.前进()
            对们: list[tuple[str, 节点]] = []
            while not self.是符("}"):
                键词 = self.当前()
                if 键词.类 == "字":
                    键 = 键词.文
                    self.前进()
                elif 键词.类 == "名":
                    键 = 键词.文
                    self.前进()
                else:
                    raise self.错("表的键必须是字符串或名字", 键词)
                self.跳换行()
                self.吃符("=>")
                self.跳换行()
                值 = self.分析表达式()
                对们.append((键, 值))
                self.跳换行()
                if self.是符(","):
                    self.前进()
                    self.跳换行()
                    continue
                break
            self.吃符("}")
            return 表(对=对们, 行=t.行, 列=t.列)

        if t.类 == "符" and t.文 == "[":
            self.前进()
            元素们: list[节点] = []
            if not self.是符("]"):
                while True:
                    元素们.append(self.分析表达式())
                    if self.是符(","):
                        self.前进()
                        continue
                    break
            self.吃符("]")
            return 列(元素=元素们, 行=t.行, 列=t.列)

        raise self.错(f"这里需要一个表达式，实际是「{t.文}」", t)


def 分析(词们: list[词]) -> 页面:
    return 分析器(词们).分析页面()


def 分析文本(源: str, 文件名: str = "<页>") -> 页面:
    from .词法 import 切分

    return 分析(切分(源, 文件名))
