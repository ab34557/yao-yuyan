"""爻语运行时值模型。

爻语的值：
* 数   —— Python int / float
* 字   —— Python str
* 真/假 —— Python bool
* 空   —— None
* 列   —— Python list
* 表   —— Python dict（键可为字/数/真/假/空）
* 匠   —— 函数（具名或匿名），带定义环境
* 应   —— 响应对象
* 请   —— 请求对象
* 原生 —— 内置函数包装
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class _空类:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "空"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, 他: object) -> bool:
        return isinstance(他, _空类)

    def __hash__(self) -> int:
        return hash("<空>")


空 = _空类()


@dataclass(slots=True)
class 匠:
    """爻语函数：具名函数或匿名函数。"""

    名: str
    参: list[str]
    体: Any  # 块节点
    环境: Any  # 环境对象（定义处作用域）
    行: int = 0
    列: int = 0
    文件名: str = "<输入>"

    def 显示(self) -> str:
        if self.名:
            return f"匠 {self.名}({len(self.参)} 参)"
        return f"节({len(self.参)} 参)"


@dataclass(slots=True)
class 原生:
    """内置函数。"""

    名: str
    函数: Callable[..., Any]
    最小参: int = 0
    最大参: int | None = None
    沙箱禁用: bool = False

    def 显示(self) -> str:
        return f"内置 {self.名}"


@dataclass(slots=True)
class 应:
    """响应对象（SPEC 4.5）。"""

    码: int = 200
    头: dict[str, str] = field(default_factory=lambda: {"Content-Type": "text/html; charset=utf-8"})
    体: Any = 空

    def 显示(self) -> str:
        return f"应({self.码})"


@dataclass(slots=True)
class 请:
    """请求对象（SPEC 4.5.1）。"""

    法: str = "GET"
    径: str = "/"
    参: dict[str, str] = field(default_factory=dict)
    体: Any = 空
    头: dict[str, str] = field(default_factory=dict)
    原: str = ""
    查询: str = ""
    路径参: dict[str, str] = field(default_factory=dict)

    字段名 = ("法", "径", "参", "体", "头", "原", "查询", "路径参")

    def 取字段(self, 名: str) -> Any:
        if 名 in self.字段名:
            return getattr(self, 名)
        from .errors import 键误

        raise 键误(f"请求对象没有字段「{名}」")

    def 显示(self) -> str:
        return f"请({self.法} {self.径})"


# ---------------------------------------------------------------------------
# 类型与显示
# ---------------------------------------------------------------------------

类型名: dict[type, str] = {
    bool: "真",
    int: "数",
    float: "数",
    str: "字",
    list: "列",
    dict: "表",
}


def 取类型名(值: Any) -> str:
    if 值 is 空 or 值 is None or isinstance(值, _空类):
        return "空"
    if isinstance(值, bool):
        return "真"
    if isinstance(值, (int, float)):
        return "数"
    if isinstance(值, str):
        return "字"
    if isinstance(值, list):
        return "列"
    if isinstance(值, dict):
        return "表"
    if isinstance(值, 匠):
        return "匠"
    if isinstance(值, 原生):
        return "匠"
    if isinstance(值, 应):
        return "应"
    if isinstance(值, 请):
        return "请"
    return type(值).__name__


def 化空(值: Any) -> Any:
    """把 Python None 递归替换为爻语「空」（JSON null → 空）。"""
    if 值 is None:
        return 空
    if isinstance(值, list):
        return [化空(v) for v in 值]
    if isinstance(值, dict):
        return {k: 化空(v) for k, v in 值.items()}
    return 值


def 数字串(值: float | int) -> str:
    if isinstance(值, bool):  # 防御
        return "真" if 值 else "假"
    if isinstance(值, int):
        return str(值)
    if 值 == int(值) and abs(值) < 1e16:
        return str(int(值))
    return repr(值)


def 转字(值: Any, _路径: frozenset[int] | None = None) -> str:
    """爻语展示样式（`显` 用）：列/表显示为 `[甲, 乙]` / `{键 ⇒ 值}`。

    原生 Python 的容器 repr 自带环检测（显示 `[...]`），这里也必须做，
    否则自引用结构（例如解释器的作用域链 `{变量 ⇒ …, 父 ⇒ 上层}`）会让
    `显(环境)` 直接爆栈。
    """
    if 值 is 空 or 值 is None or isinstance(值, _空类):
        return "空"
    if isinstance(值, bool):
        return "真" if 值 else "假"
    if isinstance(值, (int, float)):
        return 数字串(值)
    if isinstance(值, str):
        return 值

    # 只有容器才需要环检测
    if isinstance(值, (list, dict)):
        路径 = _路径 or frozenset()
        标识 = id(值)
        if 标识 in 路径:
            return "[…]" if isinstance(值, list) else "{…}"
        路径 = 路径 | {标识}
        if isinstance(值, list):
            return "[" + ", ".join(转字(项, 路径) for 项 in 值) + "]"
        return "{" + ", ".join(
            f"{转字(k, 路径)} ⇒ {转字(v, 路径)}" for k, v in 值.items()
        ) + "}"

    if isinstance(值, 匠):
        return 值.显示()
    if isinstance(值, 原生):
        return 值.显示()
    if isinstance(值, 应):
        return 值.显示()
    if isinstance(值, 请):
        return 值.显示()
    return str(值)


def 真值(值: Any) -> bool:
    """SPEC 3.6 真值规则。"""
    if 值 is 空 or 值 is None or isinstance(值, _空类):
        return False
    if isinstance(值, bool):
        return 值
    if isinstance(值, (int, float)):
        return 值 != 0
    if isinstance(值, str):
        return len(值) > 0
    if isinstance(值, (list, dict)):
        return len(值) > 0
    return True


def 相等(甲: Any, 乙: Any) -> bool:
    """SPEC 3.7 相等规则。"""
    if 甲 is 乙:
        return True
    空甲 = 甲 is 空 or 甲 is None or isinstance(甲, _空类)
    空乙 = 乙 is 空 or 乙 is None or isinstance(乙, _空类)
    if 空甲 or 空乙:
        return 空甲 and 空乙
    # 数与数
    if isinstance(甲, bool) or isinstance(乙, bool):
        if isinstance(甲, bool) and isinstance(乙, bool):
            return 甲 is 乙
        return False
    if isinstance(甲, (int, float)) and isinstance(乙, (int, float)):
        return 甲 == 乙
    if isinstance(甲, str) and isinstance(乙, str):
        return 甲 == 乙
    if isinstance(甲, list) and isinstance(乙, list):
        return len(甲) == len(乙) and all(相等(a, b) for a, b in zip(甲, 乙))
    if isinstance(甲, dict) and isinstance(乙, dict):
        if len(甲) != len(乙):
            return False
        for k, v in 甲.items():
            if k not in 乙:
                return False
            if not 相等(v, 乙[k]):
                return False
        return True
    return False


def 是否为数(值: Any) -> bool:
    return isinstance(值, (int, float)) and not isinstance(值, bool)
