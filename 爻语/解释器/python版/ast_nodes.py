"""爻语抽象语法树（dataclass 定义）。

所有节点都带 `行`/`列`，用于中文报错定位。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class 节点:
    行: int = 0
    列: int = 0


# -- 表达式 -----------------------------------------------------------------


@dataclass(slots=True)
class 数节点(节点):
    值: Any = 0


@dataclass(slots=True)
class 字节点(节点):
    值: str = ""


@dataclass(slots=True)
class 真节点(节点):
    值: bool = True


@dataclass(slots=True)
class 空节点(节点):
    pass


@dataclass(slots=True)
class 列节点(节点):
    元素: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 表节点(节点):
    对: list[tuple[节点, 节点]] = field(default_factory=list)


@dataclass(slots=True)
class 名节点(节点):
    名: str = ""


@dataclass(slots=True)
class 一元节点(节点):
    运算: str = "-"
    右: 节点 | None = None


@dataclass(slots=True)
class 二元节点(节点):
    运算: str = "+"
    左: 节点 | None = None
    右: 节点 | None = None


@dataclass(slots=True)
class 管道节点(节点):
    左: 节点 | None = None
    右: 节点 | None = None


@dataclass(slots=True)
class 调用节点(节点):
    被调: 节点 | None = None
    参: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 成员节点(节点):
    对象: 节点 | None = None
    名: str = ""


@dataclass(slots=True)
class 索引节点(节点):
    对象: 节点 | None = None
    键: 节点 | None = None


@dataclass(slots=True)
class 切片节点(节点):
    对象: 节点 | None = None
    起: 节点 | None = None
    止: 节点 | None = None


@dataclass(slots=True)
class 匠节点(节点):
    名: str = ""
    参: list[str] = field(default_factory=list)
    体: 节点 | None = None


@dataclass(slots=True)
class 节节点(节点):
    参: list[str] = field(default_factory=list)
    体: 节点 | None = None


# -- 语句 -------------------------------------------------------------------


@dataclass(slots=True)
class 块节点(节点):
    语句: list[节点] = field(default_factory=list)


@dataclass(slots=True)
class 表达式语句(节点):
    表达式: 节点 | None = None


@dataclass(slots=True)
class 绑定(节点):
    名: str = ""
    值: 节点 | None = None


@dataclass(slots=True)
class 赋值(节点):
    名: str = ""
    值: 节点 | None = None


@dataclass(slots=True)
class 函数定义(节点):
    名: str = ""
    参: list[str] = field(default_factory=list)
    体: 块节点 | None = None


@dataclass(slots=True)
class 臂:
    模式: 节点 | None  # None 表示兜底 `它`
    体: 节点 | None


@dataclass(slots=True)
class 分支(节点):
    值: 节点 | None = None
    臂们: list[臂] = field(default_factory=list)


@dataclass(slots=True)
class 遍历(节点):
    键名: str = ""
    值名: str | None = None
    来源: 节点 | None = None
    体: 块节点 | None = None


@dataclass(slots=True)
class 计数循环(节点):
    变量: str = ""
    起: 节点 | None = None
    至: 节点 | None = None
    步: 节点 | None = None
    体: 块节点 | None = None


@dataclass(slots=True)
class 条件循环(节点):
    条件: 节点 | None = None
    体: 块节点 | None = None


@dataclass(slots=True)
class 试捕(节点):
    试体: 块节点 | None = None
    捕名: str | None = None
    捕体: 块节点 | None = None
    终体: 块节点 | None = None


@dataclass(slots=True)
class 抛出(节点):
    值: 节点 | None = None


@dataclass(slots=True)
class 引入(节点):
    路径: 节点 | None = None
    名: str | None = None


@dataclass(slots=True)
class 导出(节点):
    名们: list[str] = field(default_factory=list)


@dataclass(slots=True)
class 归(节点):
    值: 节点 | None = None


@dataclass(slots=True)
class 断(节点):
    pass


@dataclass(slots=True)
class 续(节点):
    pass


@dataclass(slots=True)
class 程序(节点):
    语句: list[节点] = field(default_factory=list)
