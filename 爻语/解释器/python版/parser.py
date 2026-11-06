"""爻语语法分析器：递归下降 + Pratt 表达式。

设计要点：
* 语句以换行 / `；` 分隔；块为 `【 … 】`，不依赖缩进。
* 绑定与赋值写作「值在左」：`表达式 名 名字` / `表达式 易 目标`。
* `判` 有两种形态：带被匹配值（`判 值 【 0 ⇒ … 】`）与纯条件
  （`判 【 条件 ⇒ …；它 ⇒ … 】`），后者即传统 if。
"""

from __future__ import annotations

from . import ast_nodes as A
from .errors import 法误
from .tokens import 词


class 语法分析器:
    def __init__(self, 词表: list[词], 文件名: str = "<输入>") -> None:
        self.词表 = 词表
        self.文件名 = 文件名
        self.位 = 0
        self._语句起 = 0

    # -- 基础 ---------------------------------------------------------------

    def 当前(self) -> 词:
        return self.词表[self.位]

    def 预看(self, 偏: int = 1) -> 词:
        位 = min(self.位 + 偏, len(self.词表) - 1)
        return self.词表[位]

    def 前进(self) -> 词:
        词c = self.词表[self.位]
        if self.位 < len(self.词表) - 1:
            self.位 += 1
        return 词c

    def 是键(self, *词们: str) -> bool:
        t = self.当前()
        return t.类 == "键" and t.文 in 词们

    def 是符(self, *符们: str) -> bool:
        t = self.当前()
        return t.类 == "符" and t.文 in 符们

    def 吃键(self, 词文: str) -> 词:
        if not self.是键(词文):
            t = self.当前()
            raise 法误(f"这里需要「{词文}」，实际是「{t.原 or t.文}」", t.行, t.列)
        return self.前进()

    def 吃符(self, 符: str) -> 词:
        if not self.是符(符):
            t = self.当前()
            raise 法误(f"这里需要「{符}」，实际是「{t.原 or t.文}」", t.行, t.列)
        return self.前进()

    def 跳换行(self) -> None:
        while self.当前().类 == "换行":
            self.前进()

    def _跳后位(self) -> int:
        """跳过换行后的位置（不改变当前状态）。"""
        位 = self.位
        while 位 < len(self.词表) and self.词表[位].类 == "换行":
            位 += 1
        return 位

    def _跳后是键(self, *词们: str) -> bool:
        词c = self.词表[self._跳后位()]
        return 词c.类 == "键" and 词c.文 in 词们

    def _跳后是符(self, *符们: str) -> bool:
        词c = self.词表[self._跳后位()]
        return 词c.类 == "符" and 词c.文 in 符们

    def 到语句尾(self) -> int:
        """吃掉语句尾的分隔符数量（换行或 `；`），返回吃了几个。"""
        n = 0
        while self.当前().类 == "换行":
            self.前进()
            n += 1
        return n

    def 错(self, 文: str, 词c: 词 | None = None) -> 法误:
        t = 词c or self.当前()
        return 法误(文, t.行, t.列)

    # -- 入口 ---------------------------------------------------------------

    def 分析程序(self) -> A.程序:
        self.跳换行()
        语句们: list[A.节点] = []
        # 爻语里换行不是语句终止符（块由 【】 界定），
        # 所以同一行可以写多条语句：
        #   循 i < 3 【 显(i) i + 1 易 i 】
        while self.当前().类 != "文件止":
            语句们.append(self.分析语句())
            self.跳换行()
        return A.程序(语句=语句们, 行=1, 列=1)

    # -- 块 ----------------------------------------------------------------

    def 分析块(self) -> A.块节点:
        起 = self._吃块起()
        self.跳换行()
        语句们: list[A.节点] = []
        # 同 分析程序：换行不是语句终止符，同一行可写多条语句
        while self.当前().类 not in ("块止", "文件止"):
            语句们.append(self.分析语句())
            self.跳换行()
        if self.当前().类 == "块止":
            self.前进()
        else:
            t = self.当前()
            raise self.错("块没有闭合的「】」", t)
        return A.块节点(语句=语句们, 行=起.行, 列=起.列)

    def _吃块起(self) -> 词:
        if self.当前().类 == "块起":
            return self.前进()
        t = self.当前()
        raise self.错(f"这里需要块开始「【」，实际是「{t.原 or t.文}」", t)

    # -- 语句 ---------------------------------------------------------------

    def 分析语句(self) -> A.节点:
        t = self.当前()

        if t.类 == "键":
            if t.文 == "匠":
                return self.分析函数定义()
            if t.文 == "判":
                return self.分析分支()
            if t.文 == "遍":
                return self.分析遍()
            if t.文 == "环":
                return self.分析环()
            if t.文 == "循":
                return self.分析循()
            if t.文 == "试":
                return self.分析试()
            if t.文 == "抛":
                return self.分析抛()
            if t.文 == "引":
                return self.分析引()
            if t.文 == "出":
                return self.分析出()
            if t.文 == "归":
                return self.分析归()
            if t.文 == "断":
                self.前进()
                return A.断(行=t.行, 列=t.列)
            if t.文 == "续":
                self.前进()
                return A.续(行=t.行, 列=t.列)

        # 表达式开头的：绑定 / 赋值 / 表达式语句
        return self.分析表达式语句()

    def 分析表达式语句(self) -> A.节点:
        表达式 = self.分析表达式()
        if self.是键("名"):
            k = self.前进()
            名 = self.标识符()
            return A.绑定(名=名, 值=表达式, 行=k.行, 列=k.列)
        if self.是键("易"):
            k = self.前进()
            目标 = self.分析赋值目标()
            return A.赋值(名=目标, 值=表达式, 行=k.行, 列=k.列)
        # 命令式调用（无括号）：`显 "甲" "乙"` / `共 "目录", "/资"` / `路 "GET" "/x" 节(请) 【…】`
        if isinstance(表达式, (A.名节点, A.成员节点, A.索引节点, A.调用节点)) and self._可接参():
            参: list[A.节点] = []
            while self._可接参():
                self.跳换行()
                参.append(self.分析表达式())
                if self.是符(","):
                    self.前进()
                    self.跳换行()
            if 参:
                return A.表达式语句(
                    表达式=A.调用节点(
                        被调=表达式, 参=参, 行=表达式.行, 列=表达式.列
                    ),
                    行=表达式.行,
                    列=表达式.列,
                )
        return A.表达式语句(表达式=表达式, 行=表达式.行, 列=表达式.列)

    def _可接参(self) -> bool:
        """当前位置是否像一个无括号调用的实参开头。

        只接受「自明」的实参，避免与普通语句产生歧义：
        * 字面量（数、字、真、假、空、列、表）
        * 括号表达式、`节 (…) 【…】`、箭头函数
        裸标识符不在此列——因为 `甲 乙 丙` 无法区分是「调用 甲(乙,丙)」
        还是三条紧邻的语句名，必须写括号。
        """
        t = self.当前()
        if t.类 in ("数", "字"):
            return True
        if t.类 == "键":
            return t.文 in ("真", "假", "空", "节")
        if t.类 == "符":
            return t.文 in ("(", "[", "{")
        return False

    def 分析赋值目标(self) -> str | A.节点:
        """赋值目标：名字 / 索引 / 成员（写在「易」右边）。"""
        左 = self.分析原子目标()
        while True:
            if self.是符("["):
                k = self.前进()
                self.跳换行()
                键 = self.分析表达式()
                self.跳换行()
                self.吃符("]")
                左 = A.索引节点(对象=左, 键=键, 行=k.行, 列=k.列)
                continue
            if self.是符("."):
                k = self.前进()
                名 = self.成员名()
                左 = A.成员节点(对象=左, 名=名, 行=k.行, 列=k.列)
                continue
            break
        if isinstance(左, A.名节点):
            return 左.名
        return 左

    def 分析原子目标(self) -> A.节点:
        t = self.当前()
        if t.类 == "名":
            self.前进()
            return A.名节点(名=t.文, 行=t.行, 列=t.列)
        raise self.错(f"赋值目标必须是名字、索引或成员，实际是「{t.原 or t.文}」", t)

    def 标识符(self) -> str:
        t = self.当前()
        if t.类 != "名":
            raise self.错(f"这里需要一个名字，实际是「{t.原 or t.文}」", t)
        self.前进()
        return t.文


    def 分析函数定义(self) -> A.函数定义:
        起 = self.吃键("匠")
        名 = self.标识符()
        参 = self.分析参数表()
        体 = self.分析块()
        return A.函数定义(名=名, 参=参, 体=体, 行=起.行, 列=起.列)

    def 分析参数表(self) -> list[str]:
        self.吃符("(")
        参: list[str] = []
        self.跳换行()
        if not self.是符(")"):
            while True:
                self.跳换行()
                参.append(self.标识符())
                self.跳换行()
                if self.是符(","):
                    self.前进()
                    continue
                break
        self.跳换行()
        self.吃符(")")
        return 参

    def 分析分支(self) -> A.分支:
        起 = self.吃键("判")
        self.跳换行()
        值: A.节点 | None = None
        if self.当前().类 != "块起":
            值 = self.分析表达式()
            self.跳换行()
        臂们 = self.分析臂块()
        return A.分支(值=值, 臂们=臂们, 行=起.行, 列=起.列)

    def 分析臂块(self) -> list[A.臂]:
        self._吃块起()
        self.跳换行()
        臂们: list[A.臂] = []
        while self.当前().类 not in ("块止", "文件止"):
            if self.是键("它"):
                self.前进()
                模式 = None
            else:
                模式 = self.分析表达式()
            self.跳换行()
            self.吃符("=>")
            self.跳换行()
            if self.当前().类 == "块起":
                体: A.节点 = self.分析块()
            else:
                体 = self.分析语句()
            臂们.append(A.臂(模式=模式, 体=体))
            self.跳换行()
            if self.当前().类 == "块止":
                break
            self.跳换行()
        if self.当前().类 == "块止":
            self.前进()
        else:
            raise self.错("分支块没有闭合的「】」", self.当前())
        return 臂们

    def 分析块(self) -> A.块节点:
        起 = self._吃块起()
        self.跳换行()
        语句们: list[A.节点] = []
        # 换行不是语句终止符，同一行可写多条语句
        while self.当前().类 not in ("块止", "文件止"):
            语句们.append(self.分析语句())
            self.跳换行()
        if self.当前().类 == "块止":
            self.前进()
        else:
            t = self.当前()
            raise self.错("块没有闭合的「】」", t)
        return A.块节点(语句=语句们, 行=起.行, 列=起.列)

    def 分析遍(self) -> A.遍历:
        起 = self.吃键("遍")
        键名 = self.标识符()
        值名: str | None = None
        self.跳换行()
        if self.是符(","):
            self.前进()
            self.跳换行()
            值名 = self.标识符()
            self.跳换行()
        self.吃键("于")
        self.跳换行()
        来源 = self.分析表达式()
        self.跳换行()
        体 = self.分析块()
        return A.遍历(键名=键名, 值名=值名, 来源=来源, 体=体, 行=起.行, 列=起.列)

    def 分析环(self) -> A.计数循环:
        起 = self.吃键("环")
        变量 = self.标识符()
        self.跳换行()
        self.吃键("自")
        self.跳换行()
        起值 = self.分析表达式()
        self.跳换行()
        self.吃键("至")
        self.跳换行()
        终值 = self.分析表达式()
        self.跳换行()
        步值: A.节点 | None = None
        if self.是键("步"):
            self.前进()
            self.跳换行()
            步值 = self.分析表达式()
            self.跳换行()
        体 = self.分析块()
        return A.计数循环(变量=变量, 起=起值, 至=终值, 步=步值, 体=体, 行=起.行, 列=起.列)

    def 分析循(self) -> A.条件循环:
        起 = self.吃键("循")
        self.跳换行()
        条件 = self.分析表达式()
        self.跳换行()
        体 = self.分析块()
        return A.条件循环(条件=条件, 体=体, 行=起.行, 列=起.列)

    def 分析试(self) -> A.试捕:
        起 = self.吃键("试")
        self.跳换行()
        试体 = self.分析块()
        self.跳换行()
        捕名: str | None = None
        捕体: A.块节点 | None = None
        终体: A.块节点 | None = None
        if self.是键("捕"):
            self.前进()
            self.跳换行()
            if self.当前().类 == "名":
                捕名 = self.前进().文
            self.跳换行()
            捕体 = self.分析块()
            if self._跳后是键("终"):
                self.跳换行()
        if self.是键("终"):
            self.前进()
            self.跳换行()
            终体 = self.分析块()
        if 捕体 is None and 终体 is None:
            raise self.错("「试」之后需要「捕」或「终」", 起)
        return A.试捕(试体=试体, 捕名=捕名, 捕体=捕体, 终体=终体, 行=起.行, 列=起.列)

    def 分析抛(self) -> A.抛出:
        起 = self.吃键("抛")
        self.跳换行()
        值 = self.分析表达式()
        return A.抛出(值=值, 行=起.行, 列=起.列)

    def 分析引(self) -> A.引入:
        起 = self.吃键("引")
        self.跳换行()
        路径 = self.分析表达式()
        if self._跳后是符("=>"):
            self.跳换行()
        else:
            return A.引入(路径=路径, 名=None, 行=起.行, 列=起.列)
        名: str | None = None
        if self.是符("=>"):
            self.前进()
            self.跳换行()
            名 = self.标识符()
        return A.引入(路径=路径, 名=名, 行=起.行, 列=起.列)

    def 分析出(self) -> A.导出:
        起 = self.吃键("出")
        self.跳换行()
        名们: list[str] = []
        while self.当前().类 == "名":
            名们.append(self.标识符())
            if self._跳后是符(","):
                self.跳换行()
                self.前进()
                self.跳换行()
                continue
            break
        if not 名们:
            raise self.错("「出」后面需要至少一个名字", 起)
        return A.导出(名们=名们, 行=起.行, 列=起.列)

    def 分析归(self) -> A.归:
        起 = self.吃键("归")
        值: A.节点 | None = None
        if self.当前().类 not in ("换行", "块止", "文件止") and not self.是符(";"):
            self.跳换行()
            值 = self.分析表达式()
        return A.归(值=值, 行=起.行, 列=起.列)

    # -- 表达式 -------------------------------------------------------------

    def 分析表达式(self) -> A.节点:
        return self.分析或()

    def 分析或(self) -> A.节点:
        左 = self.分析且()
        while self.是键("或"):
            t = self.前进()
            self.跳换行()
            右 = self.分析且()
            左 = A.二元节点(运算="或", 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析且(self) -> A.节点:
        左 = self.分析非()
        while self.是键("且"):
            t = self.前进()
            self.跳换行()
            右 = self.分析非()
            左 = A.二元节点(运算="且", 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析非(self) -> A.节点:
        if self.是键("非"):
            t = self.前进()
            self.跳换行()
            右 = self.分析非()
            return A.一元节点(运算="非", 右=右, 行=t.行, 列=t.列)
        return self.分析比较()

    def 分析比较(self) -> A.节点:
        左 = self.分析管道()
        运算符 = {"==", "!=", "<", "<=", ">", ">="}
        while self.是符(*运算符):
            t = self.前进()
            self.跳换行()
            右 = self.分析管道()
            左 = A.二元节点(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析管道(self) -> A.节点:
        左 = self.分析加减()
        while self.是符("|>"):
            t = self.前进()
            self.跳换行()
            右 = self.分析加减()
            左 = A.管道节点(左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析加减(self) -> A.节点:
        左 = self.分析乘除()
        while self.是符("+", "-"):
            t = self.前进()
            self.跳换行()
            右 = self.分析乘除()
            左 = A.二元节点(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析乘除(self) -> A.节点:
        左 = self.分析一元()
        while self.是符("*", "/", "%"):
            t = self.前进()
            self.跳换行()
            右 = self.分析一元()
            左 = A.二元节点(运算=t.文, 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析一元(self) -> A.节点:
        if self.是符("-"):
            t = self.前进()
            self.跳换行()
            右 = self.分析一元()
            return A.一元节点(运算="-", 右=右, 行=t.行, 列=t.列)
        if self.是符("+"):
            self.前进()
            return self.分析一元()
        # 类型名不是关键字，无需特判
        return self.分析幂()

    def 分析幂(self) -> A.节点:
        左 = self.分析后缀()
        if self.是符("^"):
            t = self.前进()
            self.跳换行()
            右 = self.分析一元()  # 右结合，且允许 -2 ^ 2
            return A.二元节点(运算="^", 左=左, 右=右, 行=t.行, 列=t.列)
        return 左

    def 分析后缀(self) -> A.节点:
        左 = self.分析原子()
        while True:
            if self.是符("("):
                t = self.前进()
                self.跳换行()
                参: list[A.节点] = []
                if not self.是符(")"):
                    while True:
                        self.跳换行()
                        参.append(self.分析表达式())
                        self.跳换行()
                        if self.是符(","):
                            self.前进()
                            continue
                        break
                self.跳换行()
                self.吃符(")")
                左 = A.调用节点(被调=左, 参=参, 行=t.行, 列=t.列)
                continue
            if self.是符("["):
                t = self.前进()
                self.跳换行()
                if self.是符(":"):
                    self.前进()
                    self.跳换行()
                    if self.是符("]"):
                        止 = None
                    else:
                        止 = self.分析表达式()
                        self.跳换行()
                    self.吃符("]")
                    左 = A.切片节点(对象=左, 起=None, 止=止, 行=t.行, 列=t.列)
                    continue
                起 = self.分析表达式()
                self.跳换行()
                if self.是符(":"):
                    self.前进()
                    self.跳换行()
                    if self.是符("]"):
                        止 = None
                    else:
                        止 = self.分析表达式()
                        self.跳换行()
                    self.吃符("]")
                    左 = A.切片节点(对象=左, 起=起, 止=止, 行=t.行, 列=t.列)
                    continue
                self.吃符("]")
                左 = A.索引节点(对象=左, 键=起, 行=t.行, 列=t.列)
                continue
            if self.是符("."):
                t = self.前进()
                self.跳换行()
                名 = self.成员名()
                左 = A.成员节点(对象=左, 名=名, 行=t.行, 列=t.列)
                continue
            break
        return 左

    def 成员名(self) -> str:
        t = self.当前()
        if t.类 == "名":
            self.前进()
            return t.文
        if t.类 == "键":
            # 允许 obj.真 之类的特殊情况、以及 obj.名 这种误用
            self.前进()
            return t.文
        raise self.错(f"「.」之后需要一个名字，实际是「{t.原 or t.文}」", t)

    def 分析原子(self) -> A.节点:
        t = self.当前()

        if t.类 == "数":
            self.前进()
            return A.数节点(值=t.文, 行=t.行, 列=t.列)
        if t.类 == "字":
            self.前进()
            return A.字节点(值=t.文, 行=t.行, 列=t.列)
        if t.类 == "名":
            self.前进()
            return A.名节点(名=t.文, 行=t.行, 列=t.列)

        if t.类 == "键":
            if t.文 == "真":
                self.前进()
                return A.真节点(值=True, 行=t.行, 列=t.列)
            if t.文 == "假":
                self.前进()
                return A.真节点(值=False, 行=t.行, 列=t.列)
            if t.文 == "空":
                self.前进()
                return A.空节点(行=t.行, 列=t.列)
            if t.文 == "节":
                self.前进()
                self.跳换行()
                参 = self.分析参数表()
                self.跳换行()
                体 = self.分析块()
                return A.节节点(参=参, 体=体, 行=t.行, 列=t.列)
            raise self.错(f"「{t.文}」不能出现在表达式这里", t)

        if t.类 == "符":
            if t.文 == "(":
                # 可能是箭头匿名函数 (a, b) ⇒ 表达式
                箭头 = self._试箭头参数()
                if 箭头 is not None:
                    参, 续位 = 箭头
                    self.位 = 续位
                    self.吃符("=>")
                    self.跳换行()
                    体表达式 = self.分析表达式()
                    return A.节节点(
                        参=参,
                        体=A.块节点(语句=[A.归(值=体表达式, 行=体表达式.行, 列=体表达式.列)]),
                        行=t.行,
                        列=t.列,
                    )
                self.前进()
                self.跳换行()
                内 = self.分析表达式()
                self.跳换行()
                self.吃符(")")
                return 内
            if t.文 == "[":
                self.前进()
                self.跳换行()
                元素: list[A.节点] = []
                if not self.是符("]"):
                    while True:
                        self.跳换行()
                        元素.append(self.分析表达式())
                        self.跳换行()
                        if self.是符(","):
                            self.前进()
                            continue
                        break
                self.跳换行()
                self.吃符("]")
                return A.列节点(元素=元素, 行=t.行, 列=t.列)
            if t.文 == "{":
                self.前进()
                self.跳换行()
                对: list[tuple[A.节点, A.节点]] = []
                if not self.是符("}"):
                    while True:
                        self.跳换行()
                        键 = self.分析表达式()
                        self.跳换行()
                        self.吃符("=>")
                        self.跳换行()
                        值 = self.分析表达式()
                        对.append((键, 值))
                        self.跳换行()
                        if self.是符(","):
                            self.前进()
                            continue
                        break
                self.跳换行()
                self.吃符("}")
                return A.表节点(对=对, 行=t.行, 列=t.列)

        raise self.错(f"这里需要一个表达式，实际是「{t.原 or t.文}」", t)

    def _试箭头参数(self) -> tuple[list[str], int] | None:
        """从当前位置（应为 `(`）尝试识别 `(名, 名) ⇒` 形式的匿名函数参数。"""
        位 = self.位
        参: list[str] = []
        if self.词表[位].类 != "符" or self.词表[位].文 != "(":
            return None
        位 += 1
        while 位 < len(self.词表):
            t = self.词表[位]
            if t.类 == "符" and t.文 == ")":
                位 += 1
                break
            if t.类 == "名":
                参.append(t.文)
                位 += 1
                t2 = self.词表[位] if 位 < len(self.词表) else None
                if t2 and t2.类 == "符" and t2.文 == ",":
                    位 += 1
                    continue
                if t2 and t2.类 == "符" and t2.文 == ")":
                    continue
                return None
            return None
        else:
            return None
        nxt = self.词表[位] if 位 < len(self.词表) else None
        if nxt and nxt.类 == "符" and nxt.文 == "=>":
            return 参, 位
        return None


class 内误占位(Exception):
    """内部哨兵：不应该被触发。"""


def 分析(词表: list[词], 文件名: str = "<输入>") -> A.程序:
    return 语法分析器(词表, 文件名).分析程序()


def 分析文本(源: str, 文件名: str = "<输入>") -> A.程序:
    from .lexer import 切分

    return 分析(切分(源, 文件名), 文件名)
