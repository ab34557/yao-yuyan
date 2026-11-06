"""爻语词法分析器。

要点：
* 标识符首字符可以是汉字、字母、下划线；后续可含数字。
* 语句分隔：换行只在括号深度为 0 时生效；`；`/`;` 永远生效。
* 块由 `【`/`】` 界定；`[`/`]` 是 ASCII 方括号，只用于索引与列表。
* `注` 行注释到行尾；`注【 … 】` 块注释，可嵌套。
"""

from __future__ import annotations

import unicodedata

from .errors import 词误
from .tokens import (
    保留字,
    单字符符,
    多字符符,
    符号映射,
    词,
    转义表,
    关键字别名,
)


def 是汉字(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF  # 基本汉字
        or 0x3400 <= o <= 0x4DBF  # 扩展 A
        or 0xF900 <= o <= 0xFAFF  # 兼容汉字
        or 0x3000 <= o <= 0x303F  # 中文标点（会被单独处理，不进入标识符）
    )


def 标识符首(ch: str) -> bool:
    if not ch:
        return False
    if ch == "_" or ch.isalpha():
        return True
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF


def 标识符续(ch: str) -> bool:
    return 标识符首(ch) or ch.isdigit()


class 词法器:
    def __init__(self, 源: str, 文件名: str = "<输入>") -> None:
        self.源 = 源.replace("\r\n", "\n").replace("\r", "\n")
        if self.源.startswith("\ufeff"):
            self.源 = self.源[1:]
        self.文件名 = 文件名
        self.位 = 0
        self.行 = 1
        self.列 = 1
        self.深度 = 0  # ( [ { 嵌套深度
        self.块深 = 0  # 【 嵌套深度
        self.块基准: list[int] = []  # 每个【 开始时的括号深度
        self.词表: list[词] = []

    # -- 基础 ---------------------------------------------------------------

    def 当前(self) -> str:
        return self.源[self.位] if self.位 < len(self.源) else ""

    def 预看(self, 偏移: int = 1) -> str:
        位 = self.位 + 偏移
        return self.源[位] if 位 < len(self.源) else ""

    def 前进(self, 步: int = 1) -> None:
        for _ in range(步):
            if self.位 < len(self.源):
                if self.源[self.位] == "\n":
                    self.行 += 1
                    self.列 = 1
                else:
                    self.列 += 1
                self.位 += 1

    def 加词(self, 类: str, 文, 行: int, 列: int, 原: str = "") -> None:
        self.词表.append(词(类, 文, 行, 列, 原 or str(文)))

    def 错(self, 文: str, 行: int | None = None, 列: int | None = None) -> 词误:
        return 词误(文, self.行 if 行 is None else 行, self.列 if 列 is None else 列)

    # -- 主循环 -------------------------------------------------------------

    def 切分(self) -> list[词]:
        源 = self.源
        while self.位 < len(源):
            ch = 源[self.位]

            # 空白
            if ch in " \t\f\v\u00a0\u3000":
                self.前进()
                continue

            # 换行：在括号内是续行，在块内与顶层都是语句分隔
            if ch == "\n":
                行, 列 = self.行, self.列
                self.前进()
                基准 = self.块基准[-1] if self.块基准 else 0
                if self.深度 <= 基准:
                    if not self.词表 or self.词表[-1].类 != "换行":
                        self.加词("换行", "\n", 行, 列)
                continue

            # 注释：只有「注」后跟空白、行尾或「【」时才是注释；
            # 否则它是标识符的一部分（如 `注册`、`注意`），不能吞掉整行。
            if ch == "注":
                下一 = self.预看()
                if 下一 == "【" or 下一 == "" or 下一 in " \t\u3000\n;；":
                    行, 列 = self.行, self.列
                    if 下一 == "【":
                        self.前进(2)
                        self.块注释(行, 列)
                    else:
                        self.前行注释()
                    continue

            # 分号
            if ch in ";；":
                行, 列 = self.行, self.列
                self.前进()
                self.加词("换行", ";", 行, 列)
                # 分号后紧跟的换行不再重复产生分隔符，但要消费
                while self.位 < len(self.源) and self.源[self.位] in " \t\u3000":
                    self.前进()
                if self.位 < len(self.源) and self.源[self.位] == "\n":
                    self.前进()
                continue

            # 块括号（记录进入时的括号深度，块内换行始终是语句分隔）
            if ch in "【〖":
                self.前进()
                self.块深 += 1
                self.块基准.append(self.深度)
                self.加词("块起", "【", self.行, self.列 - 1)
                continue
            if ch in "】〗":
                self.前进()
                self.块深 = max(0, self.块深 - 1)
                if self.块基准:
                    self.块基准.pop()
                self.加词("块止", "】", self.行, self.列 - 1)
                continue

            # 数字
            if ch.isdigit() or (ch == "." and self.预看().isdigit() and not self._前是值()):
                self.数字()
                continue

            # 字符串
            if ch in "\"'“”‘’":
                self.字符串()
                continue

            # 反引号标识符
            if ch == "`":
                self.反引号名字()
                continue

            # 标识符 / 关键字
            if 标识符首(ch):
                self.名字()
                continue

            # 中文标点归一
            if ch in 符号映射:
                规范 = 符号映射[ch]
                # “ ” 作为字符串开引号已被上面处理；这里只处理括号类
                if 规范 in ("(", "[", "{", ")", "]", "}", ":", ".", "=", "+", "-", "*", "/", "%", "<", ">"):
                    行, 列 = self.行, self.列
                    原 = ch
                    self.前进()
                    自增 = 1 if 规范 in "([{" else 0
                    自减 = 1 if 规范 in ")]}" else 0
                    self.深度 = max(0, self.深度 + 自增 - 自减)
                    self.加词("符", 规范, 行, 列, 原)
                    continue
                self.前进()
                self.加词("符", 规范, self.行, self.列 - 1, ch)
                continue

            # 多字符运算符
            匹配 = None
            for op in 多字符符:
                if 源.startswith(op, self.位):
                    匹配 = op
                    break
            if 匹配:
                行, 列 = self.行, self.列
                # ** 与 // 归一为 ^ 与 除()
                if 匹配 == "**":
                    self.前进(2)
                    self.加词("符", "^", 行, 列, "**")
                    continue
                self.前进(2)
                self.加词("符", 匹配, 行, 列, 匹配)
                continue

            if ch in 单字符符:
                行, 列 = self.行, self.列
                self.前进()
                if ch in "([{":
                    self.深度 += 1
                elif ch in ")]}":
                    self.深度 = max(0, self.深度 - 1)
                self.加词("符", ch, 行, 列, ch)
                continue

            raise self.错(f"无法识别的字符「{ch}」（U+{ord(ch):04X}）")

        self.加词("文件止", "", self.行, self.列)
        return self.词表

    # -- 各种词 -------------------------------------------------------------

    def _前是值(self) -> bool:
        if not self.词表:
            return False
        t = self.词表[-1]
        if t.类 in ("数", "字", "名"):
            return True
        if t.类 == "符" and t.文 in (")", "]"):
            return True
        return False

    def 前行注释(self) -> None:
        while self.位 < len(self.源) and self.源[self.位] != "\n":
            self.前进()

    def 块注释(self, 行: int, 列: int) -> None:
        层 = 1
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
        raise self.错("块注释没有闭合的「】」", 行, 列)

    def 数字(self) -> None:
        行, 列 = self.行, self.列
        起 = self.位
        有小数 = 有指数 = False
        while self.位 < len(self.源):
            ch = self.源[self.位]
            if ch.isdigit():
                self.前进()
            elif ch == "_" and self.位 > 起:
                self.前进()
            elif ch == "." and not 有小数 and not 有指数 and self.预看().isdigit():
                有小数 = True
                self.前进()
            elif ch in "eE" and not 有指数 and (self.预看().isdigit() or (self.预看() in "+-" and self.预看(2).isdigit())):
                有指数 = True
                self.前进()
                if self.当前() in "+-":
                    self.前进()
            else:
                break
        if self.位 < len(self.源) and 标识符续(self.源[self.位]):
            raise self.错("数字后面紧接了非法字符", 行, 列)
        文 = self.源[起:self.位].replace("_", "")
        try:
            值 = float(文) if (有小数 or 有指数) else int(文)
        except ValueError:  # pragma: no cover - 理论不可达
            raise self.错(f"非法数字「{文}」", 行, 列)
        self.加词("数", 值, 行, 列, 文)

    def 字符串(self) -> None:
        行, 列 = self.行, self.列
        开 = self.当前()
        闭 = {"“": "”", "‘": "’"}.get(开, 开)
        self.前进()
        buf: list[str] = []
        while True:
            ch = self.当前()
            if ch == "":
                raise self.错("字符串没有闭合", 行, 列)
            if ch == "\\":
                下一 = self.预看()
                if 下一 in 转义表:
                    buf.append(转义表[下一])
                    self.前进(2)
                    continue
                if 下一 == "u":
                    self.前进(2)
                    十六 = self.源[self.位:self.位 + 4]
                    if len(十六) < 4 or any(c not in "0123456789abcdefABCDEF" for c in 十六):
                        raise self.错("\\u 转义需要 4 位十六进制", self.行, self.列)
                    buf.append(chr(int(十六, 16)))
                    self.前进(4)
                    continue
                # 未知转义：保留反斜杠
                buf.append("\\")
                self.前进()
                continue
            if ch == 闭:
                self.前进()
                break
            buf.append(ch)
            self.前进()
        self.加词("字", "".join(buf), 行, 列, "\u0000" + "".join(buf))

    def 反引号名字(self) -> None:
        行, 列 = self.行, self.列
        self.前进()
        buf: list[str] = []
        while True:
            ch = self.当前()
            if ch == "":
                raise self.错("反引号名字没有闭合", 行, 列)
            if ch == "`":
                self.前进()
                break
            buf.append(ch)
            self.前进()
        名 = "".join(buf).strip()
        if not 名:
            raise self.错("反引号里不能为空", 行, 列)
        self.加词("名", 名, 行, 列, f"`{名}`")

    def 名字(self) -> None:
        行, 列 = self.行, self.列
        起 = self.位
        while self.位 < len(self.源) and 标识符续(self.源[self.位]):
            self.前进()
        文 = self.源[起:self.位]
        # 全角字母/数字归一为半角，方便 `显（…）` 这类写法
        正规 = unicodedata.normalize("NFKC", 文)
        if 正规 in 保留字:
            self.加词("键", 正规, 行, 列, 正规)
            return
        # 兼容「真」「假」「空」等已在上表；其余保持原样
        self.加词("名", 正规, 行, 列, 文)


def 切分(源: str, 文件名: str = "<输入>") -> list[词]:
    return 词法器(源, 文件名).切分()
