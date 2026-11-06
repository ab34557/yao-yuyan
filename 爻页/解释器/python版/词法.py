"""爻页词法分析。

与爻语（.yao）不同，爻页是**界面描述语言**：关键字是元素名与属性名，
没有函数定义、循环、模块等语句。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .错误 import 词误

# ---------------------------------------------------------------------------
# 关键字
# ---------------------------------------------------------------------------

#: 结构容器
结构 = frozenset({"页", "竖", "横", "层"})
#: 元素
元素 = frozenset({"文", "钮", "输", "图", "线", "空", "列", "图线"})
#: 属性修饰
修饰 = frozenset({
    "填", "缝", "宽", "高", "大", "色", "底", "粗", "圆",
    "边", "边色", "齐", "悬底", "隐", "手", "横排",
    # 图线专用
    "底线", "点色", "线宽",
})
#: 语句关键字（始=页面初始化，判=条件分支，归=始块内赋值，它=分支兜底）
语句键 = frozenset({
    "态", "置", "点", "跳", "发", "始", "判", "归", "它", "调",
    "次",       # 定时刷新
    "毫秒",     # 定时单位
    "匠",       # 页面内定义函数
    "易",       # 修改已有状态
    "行",       # 调用函数（语句位置）
    "回",       # 函数返回
})
#: 逻辑与字面量
逻辑 = frozenset({"且", "或", "非", "真", "假", "空值"})
#: 对齐值
对齐 = frozenset({"左", "中", "右"})

#: 「于」用于「列 项 于 数据源」
介词 = frozenset({"于"})

保留字 = 结构 | 元素 | 修饰 | 语句键 | 逻辑 | 对齐 | 介词 | frozenset({"满"})

#: 全角符号 → 半角
符号映射 = {
    "（": "(", "）": ")", "，": ",", "：": ":",
    "；": ";", "＝": "=", "＋": "+", "－": "-",
    "＊": "*", "／": "/", "％": "%", "＜": "<", "＞": ">",
    "！": "!", "“": '"', "”": '"', "‘": "'", "’": "'",
    "。": ".", "［": "[", "］": "]", "｛": "{", "｝": "}", "｟": "{", "｠": "}",
    "⇒": "=>",   # 与爻语一致的箭头
}

转义 = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


@dataclass(slots=True)
class 词:
    类: str          # 数 / 字 / 名 / 键 / 符 / 块起 / 块止 / 换行 / 文件止
    文: Any
    行: int
    列: int


def 是汉字(ch: str) -> bool:
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF


def 名首(ch: str) -> bool:
    return ch == "_" or ch.isalpha() or 是汉字(ch)


def 名续(ch: str) -> bool:
    return 名首(ch) or ch.isdigit()


class 词法器:
    def __init__(self, 源: str, 文件名: str = "<页>") -> None:
        self.源 = 源.replace("\r\n", "\n").replace("\r", "\n")
        if self.源.startswith("\ufeff"):
            self.源 = self.源[1:]
        self.文件名 = 文件名
        self.位 = 0
        self.行 = 1
        self.列 = 1
        self.深度 = 0

    def 当前(self) -> str:
        return self.源[self.位] if self.位 < len(self.源) else ""

    def 预看(self, 偏: int = 1) -> str:
        p = self.位 + 偏
        return self.源[p] if p < len(self.源) else ""

    def 前进(self, 步: int = 1) -> None:
        for _ in range(步):
            if self.位 < len(self.源):
                if self.源[self.位] == "\n":
                    self.行 += 1
                    self.列 = 1
                else:
                    self.列 += 1
                self.位 += 1

    def 错(self, 文: str, 行: int | None = None, 列: int | None = None) -> 词误:
        return 词误(文, self.行 if 行 is None else 行, self.列 if 列 is None else 列)

    def 切分(self) -> list[词]:
        出: list[词] = []

        def 加(类: str, 文: Any, 行: int, 列: int) -> None:
            出.append(词(类, 文, 行, 列))

        源 = self.源
        while self.位 < len(源):
            ch = 源[self.位]

            if ch in " \t\f\v\u00a0\u3000":
                self.前进()
                continue

            # 换行：括号内是续行，否则是语句分隔
            if ch == "\n":
                行, 列 = self.行, self.列
                self.前进()
                if self.深度 == 0 and (not 出 or 出[-1].类 != "换行"):
                    加("换行", "\n", 行, 列)
                continue

            # 注释：注 后跟空白/行尾/【 才是注释
            if ch == "注":
                下一 = self.预看()
                if 下一 == "【" or 下一 == "" or 下一 in " \t\u3000\n;；":
                    if 下一 == "【":
                        self.块注释()
                    else:
                        while self.位 < len(源) and 源[self.位] != "\n":
                            self.前进()
                    continue

            # 分号
            if ch in ";；":
                行, 列 = self.行, self.列
                self.前进()
                加("换行", ";", 行, 列)
                continue

            # 块
            if ch in "【〖":
                行, 列 = self.行, self.列
                self.前进()
                self.深度 += 1
                加("块起", "【", 行, 列)
                continue
            if ch in "】〗":
                行, 列 = self.行, self.列
                self.前进()
                self.深度 = max(0, self.深度 - 1)
                加("块止", "】", 行, 列)
                continue

            # 字符串
            if ch in "\"'“”‘’":
                行, 列 = self.行, self.列
                闭 = {"“": "”", "‘": "’"}.get(ch, ch)
                self.前进()
                缓: list[str] = []
                while True:
                    c = self.当前()
                    if c == "":
                        raise self.错("字符串没有闭合", 行, 列)
                    if c == "\\":
                        nxt = self.预看()
                        if nxt in 转义:
                            缓.append(转义[nxt])
                            self.前进(2)
                            continue
                        缓.append("\\")
                        self.前进()
                        continue
                    if c == 闭:
                        self.前进()
                        break
                    缓.append(c)
                    self.前进()
                加("字", "".join(缓), 行, 列)
                continue

            # 数字
            if ch.isdigit() or (ch == "." and self.预看().isdigit()):
                行, 列 = self.行, self.列
                起 = self.位
                有小数 = False
                while self.位 < len(源):
                    c = 源[self.位]
                    if c.isdigit():
                        self.前进()
                    elif c == "." and not 有小数 and self.预看().isdigit():
                        有小数 = True
                        self.前进()
                    else:
                        break
                文 = 源[起:self.位]
                加("数", float(文) if 有小数 else int(文), 行, 列)
                continue

            # 标识符 / 关键字
            if 名首(ch):
                行, 列 = self.行, self.列
                起 = self.位
                while self.位 < len(源) and 名续(源[self.位]):
                    self.前进()
                文 = 源[起:self.位]
                if 文 in 保留字:
                    加("键", 文, 行, 列)
                else:
                    加("名", 文, 行, 列)
                continue

            # 全角符号
            if ch in 符号映射:
                nxt = 符号映射[ch]
                if nxt == "=>":
                    行, 列 = self.行, self.列
                    self.前进()
                    加("符", "=>", 行, 列)
                    continue
                if nxt in "()[]":
                    行, 列 = self.行, self.列
                    self.前进()
                    加("符", nxt, 行, 列)
                    continue
                if nxt in ",:+-*/%<>!=.":
                    行, 列 = self.行, self.列
                    self.前进()
                    加("符", nxt, 行, 列)
                    continue

            # 多字符运算符
            命中 = None
            for op in ("==", "!=", "<=", ">=", "=>"):
                if 源.startswith(op, self.位):
                    命中 = op
                    break
            if 命中:
                行, 列 = self.行, self.列
                self.前进(2)
                加("符", 命中, 行, 列)
                continue

            if ch in "{}":
                行, 列 = self.行, self.列
                self.前进()
                加("符", ch, 行, 列)
                continue

            if ch in "+-*/%<>()[],=!":
                行, 列 = self.行, self.列
                self.前进()
                if ch in "([":
                    self.深度 += 1
                elif ch in ")]":
                    self.深度 = max(0, self.深度 - 1)
                加("符", ch, 行, 列)
                continue

            raise self.错(f"无法识别的字符「{ch}」（U+{ord(ch):04X}）")

        加("文件止", "", self.行, self.列)
        return 出

    def 块注释(self) -> None:
        行, 列 = self.行, self.列
        层 = 0
        while self.位 < len(self.源):
            if self.源.startswith("注【", self.位):
                层 += 1
                self.前进(2)
                continue
            if self.当前() == "】":
                层 -= 1
                self.前进()
                if 层 == 0:
                    return
                continue
            self.前进()
        raise self.错("块注释没有闭合", 行, 列)


def 切分(源: str, 文件名: str = "<页>") -> list[词]:
    return 词法器(源, 文件名).切分()
