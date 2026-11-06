"""爻语解释器：树遍历求值。

* 控制流用信号异常实现（归 / 断 / 续）。
* 每次求值可加「步预算」，在线 IDE 借此防止死循环。
* 所有错误都是中文 `爻误` 子类，携带行号列号与调用栈。
"""

from __future__ import annotations

import os
import time
from typing import Any

from . import ast_nodes as A
from .env import 环境
from .errors import (
    内误,
    名误,
    型误,
    值误,
    引误,
    零误,
    键误,
    法误,
    爻误,
    抛误,
)
from .values import (
    匠,
    原生,
    应,
    请,
    空,
    取类型名,
    数字串,
    相等,
    真值,
)


class _归信号(BaseException):
    def __init__(self, 值: Any, 行: int = 0, 列: int = 0) -> None:
        self.值 = 值
        self.行 = 行
        self.列 = 列


class _断信号(BaseException):
    def __init__(self, 行: int = 0, 列: int = 0) -> None:
        self.行 = 行
        self.列 = 列


class _续信号(BaseException):
    def __init__(self, 行: int = 0, 列: int = 0) -> None:
        self.行 = 行
        self.列 = 列


class 中断:
    """外部中断标记（在线 IDE 超时用）。"""

    def __init__(self) -> None:
        self.已中断 = False
        self.原因 = ""


class 解释器:
    #: 步数上限，None 表示不限
    步上限: int | None = None

    def __init__(
        self,
        输出=None,
        沙箱: bool = False,
        工作目录: str | None = None,
        中断标志: 中断 | None = None,
        步上限: int | None = None,
        参数: list[str] | None = None,
    ) -> None:
        import sys

        self.输出 = 输出 or (lambda s: sys.stdout.write(s))
        self.沙箱 = 沙箱
        self.工作目录 = 工作目录 or os.getcwd()
        self.中断标志 = 中断标志 or 中断()
        self.步上限 = 步上限
        self.参数 = 参数 or []
        self.步数 = 0
        self.全局 = 环境(None, 模块名="<主>")
        self.模块缓存: dict[str, dict[str, Any]] = {}
        self.正在引: list[str] = []
        self.路由表: list[dict[str, Any]] = []
        self.静态目录: list[tuple[str, str]] = []
        self.当前文件 = "<输入>"
        #: 覆盖率追踪：调用计数（函数签名 -> 次数）与未覆盖函数集合。
        #: 供自动化测试系统调用 `启用覆盖()` / `取覆盖()` 使用；默认关闭，不影响性能。
        self.覆盖追踪 = False
        self.覆盖计数: dict[str, int] = {}
        self.覆盖调用行: dict[str, int] = {}
        self._安装内置()

    # -- 内置装配 -----------------------------------------------------------

    def _安装内置(self) -> None:
        from .builtins import 造内置

        for 名, 函数 in 造内置(self).items():
            self.全局.定义(名, 函数)

    # -- 步计数 -------------------------------------------------------------

    def _步(self) -> None:
        self.步数 += 1
        if self.步上限 is not None and self.步数 > self.步上限:
            from .errors import 限误

            raise 限误(f"执行步数超过上限 {self.步上限}")
        if self.中断标志.已中断:
            from .errors import 时误

            raise 时误(self.中断标志.原因 or "执行超时")

    # -- 入口 ---------------------------------------------------------------

    def 运行程序(self, 程序: A.程序) -> Any:
        try:
            return self.执行块(程序.语句, self.全局, 新作用域=False)
        except _断信号 as e:
            raise 法误("「断」只能用在循环里", e.行, e.列)
        except _续信号 as e:
            raise 法误("「续」只能用在循环里", e.行, e.列)
        except _归信号 as e:
            raise 法误("「归」只能用在函数里", e.行, e.列)

    def 运行源码(self, 源: str, 文件名: str = "<输入>") -> Any:
        from .lexer import 切分
        from .parser import 分析

        self.当前文件 = 文件名
        程序 = 分析(切分(源, 文件名), 文件名)
        return self.运行程序(程序)

    # -- 语句 ---------------------------------------------------------------

    def 执行块(self, 语句们: list[A.节点], 环境对象: 环境, 新作用域: bool = True) -> Any:
        环 = 环境(环境对象) if 新作用域 else 环境对象
        结果: Any = 空
        for 语句 in 语句们:
            self._步()
            结果 = self.执行语句(语句, 环)
        return 结果

    def 执行语句(self, 语句: A.节点, 环: 环境) -> Any:
        try:
            return self._执行语句(语句, 环)
        except 爻误 as e:
            if not e.行:
                e.行 = getattr(语句, "行", 0)
                e.列 = getattr(语句, "列", 0)
                e.args = (e.格式化(),)
            raise
        except (_归信号, _断信号, _续信号, SystemExit):
            raise

    def _执行语句(self, 语句: A.节点, 环: 环境) -> Any:
        t = type(语句)

        if t is A.表达式语句:
            return self.求值(语句.表达式, 环)

        if t is A.绑定:
            值 = self.求值(语句.值, 环)
            环.定义(语句.名, 值)
            return 值

        if t is A.赋值:
            值 = self.求值(语句.值, 环)
            self.执行赋值(语句.名, 值, 语句, 环)
            return 值

        if t is A.函数定义:
            f = 匠(
                名=语句.名,
                参=list(语句.参),
                体=语句.体,
                环境=环,
                行=语句.行,
                列=语句.列,
                文件名=self.当前文件,
            )
            环.定义(语句.名, f)
            return f

        if t is A.块节点:
            return self.执行块(语句.语句, 环)

        if t is A.分支:
            return self.执行分支(语句, 环)

        if t is A.遍历:
            return self.执行遍历(语句, 环)

        if t is A.计数循环:
            return self.执行计数循环(语句, 环)

        if t is A.条件循环:
            return self.执行条件循环(语句, 环)

        if t is A.试捕:
            return self.执行试捕(语句, 环)

        if t is A.抛出:
            值 = self.求值(语句.值, 环)
            self.执行抛出(值, 语句)

        if t is A.引入:
            return self.执行引入(语句, 环)

        if t is A.导出:
            根 = 环.模块根 if 环.模块根 is not None else 环.顶层()
            if 根.导出限制 is None:
                根.导出限制 = []
            for 名 in 语句.名们:
                if 名 not in 根.导出限制:
                    根.导出限制.append(名)
            return 空

        if t is A.归:
            值 = self.求值(语句.值, 环) if 语句.值 is not None else 空
            raise _归信号(值, 语句.行, 语句.列)

        if t is A.断:
            raise _断信号(语句.行, 语句.列)

        if t is A.续:
            raise _续信号(语句.行, 语句.列)

        raise 内误(f"未知语句节点 {t.__name__}", 语句.行, 语句.列)

    def 执行赋值(self, 目标: Any, 值: Any, 语句: A.节点, 环: 环境) -> None:
        if isinstance(目标, str):
            环.改(目标, 值, 语句.行, 语句.列)
            return
        if isinstance(目标, A.索引节点):
            容器 = self.求值(目标.对象, 环)
            键 = self.求值(目标.键, 环)
            self.写索引(容器, 键, 值, 语句)
            return
        if isinstance(目标, A.成员节点):
            对象 = self.求值(目标.对象, 环)
            if not isinstance(对象, dict):
                raise 型误(
                    f"只能给「表」的字段赋值，实际是「{取类型名(对象)}」",
                    语句.行,
                    语句.列,
                )
            对象[目标.名] = 值
            return
        raise 内误("无法识别的赋值目标", 语句.行, 语句.列)

    def 写索引(self, 容器: Any, 键: Any, 值: Any, 语句: A.节点) -> None:
        if isinstance(容器, list):
            if not isinstance(键, int) or isinstance(键, bool):
                raise 型误("列的索引必须是整数", 语句.行, 语句.列)
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                raise 值误(f"列索引越界：{键}（长度 {n}）", 语句.行, 语句.列)
            容器[i] = 值
            return
        if isinstance(容器, dict):
            try:
                hash(键)
            except TypeError:
                raise 型误("表的键必须可散列（字/数/真/假/空）", 语句.行, 语句.列)
            容器[键] = 值
            return
        raise 型误(f"「{取类型名(容器)}」不支持下标赋值", 语句.行, 语句.列)

    # -- 控制流 -------------------------------------------------------------

    def 执行分支(self, 语句: A.分支, 环: 环境) -> Any:
        值 = self.求值(语句.值, 环) if 语句.值 is not None else None
        选: A.节点 | None = None
        有兜底 = False
        for 臂 in 语句.臂们:
            if 臂.模式 is None:
                有兜底 = True
                选 = 臂.体
                break
            若模式 = self.求值(臂.模式, 环)
            if 值 is not None:
                if 相等(值, 若模式):
                    选 = 臂.体
                    break
            else:
                if 真值(若模式):
                    选 = 臂.体
                    break
        if 选 is None:
            return 空
        return self.执行语句(选, 环)

    def 执行遍历(self, 语句: A.遍历, 环: 环境) -> Any:
        来源 = self.求值(语句.来源, 环)
        结果: Any = 空
        if isinstance(来源, dict):
            项们 = list(来源.items())
        elif isinstance(来源, (list, str)):
            项们 = list(enumerate(来源))
        else:
            raise 型误(
                f"「遍」需要一个列、表或字，实际是「{取类型名(来源)}」",
                语句.行,
                语句.列,
            )
        for k, v in 项们:
            self._步()
            轮 = 环境(环)
            if 语句.值名 is not None:
                if isinstance(来源, dict):
                    轮.定义(语句.键名, k)
                    轮.定义(语句.值名, v)
                else:
                    轮.定义(语句.键名, k)
                    轮.定义(语句.值名, v)
            else:
                轮.定义(语句.键名, v if isinstance(来源, dict) else v)
            try:
                结果 = self.执行块(语句.体.语句, 轮)
            except _续信号:
                continue
            except _断信号:
                break
        return 结果

    def 执行计数循环(self, 语句: A.计数循环, 环: 环境) -> Any:
        起 = self.求值(语句.起, 环)
        至 = self.求值(语句.至, 环)
        步 = self.求值(语句.步, 环) if 语句.步 is not None else 1
        for 名, 值 in (("起点", 起), ("终点", 至), ("步长", 步)):
            if not isinstance(值, (int, float)) or isinstance(值, bool):
                raise 型误(f"「环」的{名}必须是数", 语句.行, 语句.列)
        if 步 == 0:
            raise 值误("「环」的步长不能为 0", 语句.行, 语句.列)
        结果: Any = 空
        i = 起
        若 = (lambda x: x < 至) if 步 > 0 else (lambda x: x > 至)
        while 若(i):
            self._步()
            轮 = 环境(环)
            轮.定义(语句.变量, i)
            try:
                结果 = self.执行块(语句.体.语句, 轮)
            except _续信号:
                i += 步
                continue
            except _断信号:
                break
            i += 步
        return 结果

    def 执行条件循环(self, 语句: A.条件循环, 环: 环境) -> Any:
        结果: Any = 空
        while True:
            self._步()
            if not 真值(self.求值(语句.条件, 环)):
                break
            轮 = 环境(环)
            try:
                结果 = self.执行块(语句.体.语句, 轮)
            except _续信号:
                continue
            except _断信号:
                break
        return 结果

    def 执行试捕(self, 语句: A.试捕, 环: 环境) -> Any:
        结果: Any = 空
        try:
            try:
                结果 = self.执行块(语句.试体.语句, 环)
            except 爻误 as e:
                if 语句.捕体 is None:
                    raise
                if 语句.捕名:
                    环.定义(语句.捕名, e.成表())
                结果 = self.执行块(语句.捕体.语句, 环)
        finally:
            if 语句.终体 is not None:
                self.执行块(语句.终体.语句, 环)
        return 结果

    def 执行抛出(self, 值: Any, 语句: A.节点) -> None:
        if isinstance(值, dict):
            from .errors import 可抛类

            文 = 值.get("文", "")
            if not isinstance(文, str):
                文 = "用户抛出"
            类名 = 值.get("类", "抛误")
            if not isinstance(类名, str):
                类名 = "抛误"
            # 只接受已知的错误类别，未知类别退化为 抛误
            if 类名 not in 可抛类:
                类名 = "抛误"
            e = 抛误(文, 语句.行, 语句.列)
            e.类 = 类名
            raise e
        if isinstance(值, str):
            raise 抛误(值, 语句.行, 语句.列)
        if 值 is 空:
            raise 抛误("用户抛出空值", 语句.行, 语句.列)
        raise 抛误(f"用户抛出「{取类型名(值)}」：{数字串(值) if isinstance(值, (int, float)) else 值}",
               语句.行, 语句.列)

    def 执行引入(self, 语句: A.引入, 环: 环境) -> Any:
        路径值 = self.求值(语句.路径, 环)
        if not isinstance(路径值, str):
            raise 型误("「引」需要一个文件路径（字）", 语句.行, 语句.列)
        if self.沙箱:
            raise 型误("在线环境不可用「引」", 语句.行, 语句.列)
        模块 = self.载入模块(路径值, 语句)
        if 语句.名:
            环.定义(语句.名, 模块)
        return 模块

    def 载入模块(self, 路径: str, 语句: A.节点) -> dict[str, Any]:
        基 = self.工作目录
        候选 = 路径
        if not os.path.isabs(候选):
            候选 = os.path.join(os.path.dirname(self.当前文件) or 基, 路径) if self.当前文件 != "<输入>" else os.path.join(基, 路径)
        for p in (候选, 候选 + ".yao"):
            if os.path.isfile(p):
                真路径 = os.path.realpath(p)
                break
        else:
            raise 引误(f"找不到模块「{路径}」", 语句.行, 语句.列)
        # 循环引入检测必须在缓存命中之前
        if 真路径 in self.正在引:
            raise 引误(f"模块循环引入：「{路径}」", 语句.行, 语句.列)
        if 真路径 in self.模块缓存:
            return self.模块缓存[真路径]
        from .lexer import 切分
        from .parser import 分析

        try:
            from .编码 import 读文本
            源 = 读文本(真路径)
        except OSError as e:
            raise 引误(f"无法读取模块「{路径}」：{e}", 语句.行, 语句.列)
        self.正在引.append(真路径)
        先前文件 = self.当前文件
        self.当前文件 = 真路径
        # 先放占位，避免「A 引 B、B 再引 A」时重复执行；同时保证重复引入只执行一次
        占位: dict[str, Any] = {}
        self.模块缓存[真路径] = 占位
        try:
            程序 = 分析(切分(源, 真路径), 真路径)
            模块环境 = 环境(None, 模块名=真路径)
            模块环境.模块根 = 模块环境
            # 内置可见：模块环境父指向全局环境，但导出只看模块根
            模块环境.父 = self.全局
            self.执行块(程序.语句, 模块环境, 新作用域=False)
            导出 = 模块环境.导出表()
        except BaseException:
            self.模块缓存.pop(真路径, None)
            raise
        finally:
            self.正在引.remove(真路径)
            self.当前文件 = 先前文件
        占位.update(导出)
        模块 = 占位
        return 模块

    # -- 表达式 -------------------------------------------------------------

    def 求值(self, 节点: A.节点, 环: 环境) -> Any:
        t = type(节点)

        if t is A.数节点:
            return 节点.值
        if t is A.字节点:
            return 节点.值
        if t is A.真节点:
            return 节点.值
        if t is A.空节点:
            return 空

        if t is A.名节点:
            return 环.取(节点.名, 节点.行, 节点.列)

        if t is A.列节点:
            return [self.求值(e, 环) for e in 节点.元素]

        if t is A.表节点:
            结果: dict[Any, Any] = {}
            for k, v in 节点.对:
                键 = self.求值(k, 环)
                try:
                    hash(键)
                except TypeError:
                    raise 型误("表的键必须可散列（字/数/真/假/空）", 节点.行, 节点.列)
                结果[键] = self.求值(v, 环)
            return 结果

        if t is A.一元节点:
            return self.求一元(节点, 环)

        if t is A.二元节点:
            return self.求二元(节点, 环)

        if t is A.管道节点:
            值 = self.求值(节点.左, 环)
            右 = 节点.右
            if isinstance(右, A.调用节点):
                参 = [值] + [self.求值(a, 环) for a in 右.参]
                被调 = self.求值(右.被调, 环)
                return self.调用(被调, 参, 节点)
            if isinstance(右, A.名节点):
                被调 = 环.取(右.名, 右.行, 右.列)
                return self.调用(被调, [值], 节点)
            被调 = self.求值(右, 环)
            return self.调用(被调, [值], 节点)

        if t is A.调用节点:
            被调 = 节点.被调
            if isinstance(被调, A.成员节点):
                对象 = self.求值(被调.对象, 环)
                成员 = self.取成员(对象, 被调.名, 被调)
                参 = [self.求值(a, 环) for a in 节点.参]
                # 成员调用：对象是表且值是匠时，把对象作为第一个实参注入
                if isinstance(对象, dict) and isinstance(成员, (匠,)):
                    参 = [对象] + 参
                elif isinstance(成员, 匠) and len(成员.参) == len(参) + 1:
                    参 = [对象] + 参
                return self.调用(成员, 参, 节点)
            被调值 = self.求值(被调, 环)
            参 = [self.求值(a, 环) for a in 节点.参]
            return self.调用(被调值, 参, 节点)

        if t is A.成员节点:
            对象 = self.求值(节点.对象, 环)
            return self.取成员(对象, 节点.名, 节点)

        if t is A.索引节点:
            容器 = self.求值(节点.对象, 环)
            键 = self.求值(节点.键, 环)
            return self.读索引(容器, 键, 节点)

        if t is A.切片节点:
            容器 = self.求值(节点.对象, 环)
            起 = self.求值(节点.起, 环) if 节点.起 is not None else None
            止 = self.求值(节点.止, 环) if 节点.止 is not None else None
            return self.切片(容器, 起, 止, 节点)

        if t is A.节节点:
            return 匠(
                名="",
                参=list(节点.参),
                体=节点.体,
                环境=环,
                行=节点.行,
                列=节点.列,
                文件名=self.当前文件,
            )

        raise 内误(f"未知表达式节点 {t.__name__}", 节点.行, 节点.列)

    # -- 运算 ---------------------------------------------------------------

    def 求一元(self, 节点: A.一元节点, 环: 环境) -> Any:
        右 = self.求值(节点.右, 环)
        if 节点.运算 == "非":
            return not 真值(右)
        if 节点.运算 == "-":
            if isinstance(右, bool) or not isinstance(右, (int, float)):
                raise 型误(f"「-」需要数，实际是「{取类型名(右)}」", 节点.行, 节点.列)
            return -右
        raise 内误(f"未知一元运算「{节点.运算}」", 节点.行, 节点.列)

    def 求二元(self, 节点: A.二元节点, 环: 环境) -> Any:
        运算 = 节点.运算

        if 运算 == "且":
            左 = self.求值(节点.左, 环)
            if not 真值(左):
                return 左 if not isinstance(左, bool) else False
            return self.求值(节点.右, 环)
        if 运算 == "或":
            左 = self.求值(节点.左, 环)
            if 真值(左):
                return 左 if not isinstance(左, bool) else True
            return self.求值(节点.右, 环)

        左 = self.求值(节点.左, 环)
        右 = self.求值(节点.右, 环)

        if 运算 in ("==", "!="):
            等 = 相等(左, 右)
            return 等 if 运算 == "==" else (not 等)

        if 运算 in ("<", "<=", ">", ">="):
            return self.比较(左, 右, 运算, 节点)

        if 运算 == "+":
            return self.加法(左, 右, 节点)

        if 运算 == "-":
            self._要数(左, 右, 运算, 节点)
            return 左 - 右

        if 运算 == "*":
            if isinstance(左, str) and isinstance(右, int) and not isinstance(右, bool):
                return 左 * 右
            if isinstance(右, str) and isinstance(左, int) and not isinstance(左, bool):
                return 右 * 左
            if isinstance(左, list) and isinstance(右, int) and not isinstance(右, bool):
                return 左 * 右
            self._要数(左, 右, 运算, 节点)
            return 左 * 右

        if 运算 == "/":
            self._要数(左, 右, 运算, 节点)
            if 右 == 0:
                raise 零误("不能除以零", 节点.行, 节点.列)
            return 左 / 右

        if 运算 == "%":
            self._要数(左, 右, 运算, 节点)
            if 右 == 0:
                raise 零误("不能对零取余", 节点.行, 节点.列)
            return 左 % 右

        if 运算 == "^":
            self._要数(左, 右, 运算, 节点)
            try:
                return 左 ** 右
            except (OverflowError, ValueError) as e:
                raise 值误(f"幂运算失败：{e}", 节点.行, 节点.列)

        raise 内误(f"未知二元运算「{运算}」", 节点.行, 节点.列)

    def _要数(self, 左: Any, 右: Any, 运算: str, 节点: A.节点) -> None:
        for 值 in (左, 右):
            if isinstance(值, bool) or not isinstance(值, (int, float)):
                raise 型误(
                    f"「{运算}」需要数，实际是「{取类型名(值)}」",
                    节点.行,
                    节点.列,
                )

    def 加法(self, 左: Any, 右: Any, 节点: A.节点) -> Any:
        if isinstance(左, str) and isinstance(右, str):
            return 左 + 右
        if isinstance(左, str) or isinstance(右, str):
            # 允许 字 + 数 之类，自动转字
            return self._转字(左) + self._转字(右)
        if isinstance(左, list) and isinstance(右, list):
            return 左 + 右
        self._要数(左, 右, "+", 节点)
        return 左 + 右

    def _转字(self, 值: Any) -> str:
        from .values import 转字

        return 转字(值)

    def 比较(self, 左: Any, 右: Any, 运算: str, 节点: A.节点) -> bool:
        if isinstance(左, bool) or isinstance(右, bool):
            raise 型误("真/假不能比较大小", 节点.行, 节点.列)
        if isinstance(左, (int, float)) and isinstance(右, (int, float)):
            pass
        elif isinstance(左, str) and isinstance(右, str):
            pass
        else:
            raise 型误(
                f"「{运算}」两边类型不同：{取类型名(左)} 与 {取类型名(右)}",
                节点.行,
                节点.列,
            )
        if 运算 == "<":
            return 左 < 右
        if 运算 == "<=":
            return 左 <= 右
        if 运算 == ">":
            return 左 > 右
        return 左 >= 右

    # -- 调用 ---------------------------------------------------------------

    def 调用(self, 被调: Any, 参: list[Any], 节点: A.节点) -> Any:
        if isinstance(被调, 原生):
            if self.沙箱 and 被调.沙箱禁用:
                raise 型误(f"在线环境不可用「{被调.名}」", 节点.行, 节点.列)
            if len(参) < 被调.最小参:
                raise 型误(
                    f"「{被调.名}」至少需要 {被调.最小参} 个参数，实际传入 {len(参)} 个",
                    节点.行,
                    节点.列,
                )
            if 被调.最大参 is not None and len(参) > 被调.最大参:
                raise 型误(
                    f"「{被调.名}」最多接受 {被调.最大参} 个参数，实际传入 {len(参)} 个",
                    节点.行,
                    节点.列,
                )
            try:
                return 被调.函数(*参)
            except 爻误:
                raise
            except ZeroDivisionError:
                raise 零误("不能除以零", 节点.行, 节点.列)
            except (TypeError, ValueError, KeyError, IndexError, OSError) as e:
                raise 型误(f"「{被调.名}」调用出错：{e}", 节点.行, 节点.列)

        if isinstance(被调, 匠):
            return self.调用匠(被调, 参, 节点)

        raise 型误(
            f"「{取类型名(被调)}」不可调用（这里需要一个函数）",
            节点.行,
            节点.列,
        )

    def 调用匠(self, 匠对象: 匠, 参: list[Any], 节点: A.节点) -> Any:
        if len(参) != len(匠对象.参):
            raise 型误(
                f"{匠对象.显示()}需要 {len(匠对象.参)} 个参数，实际传入 {len(参)} 个",
                节点.行,
                节点.列,
            )
        帧 = 环境(匠对象.环境)
        for 名, 值 in zip(匠对象.参, 参):
            帧.定义(名, 值)
        if self.覆盖追踪:
            签名 = f"{os.path.basename(匠对象.文件名)}:{匠对象.行}:{匠对象.名 or '<匿名>'}"
            self.覆盖计数[签名] = self.覆盖计数.get(签名, 0) + 1
            self.覆盖调用行[签名] = 匠对象.行
        try:
            self.执行块(匠对象.体.语句, 帧, 新作用域=False)
        except _归信号 as r:
            return r.值
        except 爻误 as e:
            定位 = f"{os.path.basename(匠对象.文件名)}:{匠对象.行}"
            e.加栈(f"在 {匠对象.显示()}({定位}) 调用处")
            raise
        return 空

    # -- 成员 / 索引 --------------------------------------------------------

    def 取成员(self, 对象: Any, 名: str, 节点: A.节点) -> Any:
        if isinstance(对象, dict):
            if 名 in 对象:
                return 对象[名]
            raise 键误(f"表里没有键「{名}」（用「取(表, 键, 默认)」可容错）", 节点.行, 节点.列)
        if isinstance(对象, 请):
            return 对象.取字段(名)
        if isinstance(对象, 应):
            if 名 == "码":
                return 对象.码
            if 名 == "头":
                return 对象.头
            if 名 == "体":
                return 对象.体
            raise 键误(f"响应对象没有字段「{名}」", 节点.行, 节点.列)
        if isinstance(对象, str) and 名 in ("长", "长"):
            return len(对象)
        raise 型误(
            f"「{取类型名(对象)}」没有成员「{名}」",
            节点.行,
            节点.列,
        )

    def 读索引(self, 容器: Any, 键: Any, 节点: A.节点) -> Any:
        if isinstance(容器, list):
            if not isinstance(键, int) or isinstance(键, bool):
                raise 型误("列的索引必须是整数", 节点.行, 节点.列)
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                raise 值误(f"列索引越界：{键}（长度 {n}）", 节点.行, 节点.列)
            return 容器[i]
        if isinstance(容器, dict):
            try:
                if 键 in 容器:
                    return 容器[键]
            except TypeError:
                raise 型误("表的键必须可散列", 节点.行, 节点.列)
            raise 键误(f"表里没有键「{self._转字(键)}」", 节点.行, 节点.列)
        if isinstance(容器, str):
            if not isinstance(键, int) or isinstance(键, bool):
                raise 型误("字的索引必须是整数", 节点.行, 节点.列)
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                raise 值误(f"字索引越界：{键}（长度 {n}）", 节点.行, 节点.列)
            return 容器[i]
        raise 型误(f"「{取类型名(容器)}」不支持下标取值", 节点.行, 节点.列)

    def 切片(self, 容器: Any, 起: Any, 止: Any, 节点: A.节点) -> Any:
        if not isinstance(容器, (list, str)):
            raise 型误(f"「{取类型名(容器)}」不支持切片", 节点.行, 节点.列)
        for 值 in (起, 止):
            if 值 is not None and (not isinstance(值, int) or isinstance(值, bool)):
                raise 型误("切片的起止必须是整数", 节点.行, 节点.列)
        return 容器[起:止]

    # -- 辅助 ---------------------------------------------------------------

    def 调匠(self, 函数: 匠, 参: list[Any]) -> Any:
        """内置函数调用爻语函数时用（无节点定位）。"""
        return self.调用匠(函数, 参, A.调用节点())

    def 报错定位(self, e: 爻误, 节点: A.节点) -> 爻误:
        if not e.行:
            e.行 = 节点.行
            e.列 = 节点.列
            e.args = (e.格式化(),)
        return e


def 运行文件(
    路径: str,
    参数: list[str] | None = None,
    输出=None,
    沙箱: bool = False,
) -> int:
    """执行 .yao 文件，返回退出码。"""
    from .errors import 爻误

    解释器实例 = 解释器(输出=输出, 沙箱=沙箱, 参数=参数, 工作目录=os.getcwd())
    解释器实例.当前文件 = os.path.realpath(路径)
    try:
        from .编码 import 读文本
        源 = 读文本(路径)
    except OSError as e:
        print(f"无法读取文件「{路径}」：{e}")
        return 2
    开始 = time.time()
    try:
        解释器实例.运行源码(源, 解释器实例.当前文件)
    except 爻误 as e:
        print(e.格式化())
        return 1
    except RecursionError:
        print("内误：递归过深（超过 Python 栈上限）")
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\n已中断")
        return 130
    _ = 开始
    return 0
