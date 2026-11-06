"""爻页布局引擎：把抽象节点树变成「盒树」。

盒模型是自己定义的，不依赖任何 Web 布局概念：

    盒子外框 = 内边距(填) + 内容区
    容器高  = 上内边距 + Σ子高 + 缝×(子数-1) + 下内边距
    竖：子元素自上而下；横：自左而右；层：全部叠在左上角

文本测量用「字符宽度估算」：中文按字号计宽，ASCII 按 0.55×字号。
这样不依赖字体度量也能得到稳定的换行结果。
"""

from __future__ import annotations

from typing import Any

from . import 语法 as A
from .求值 import 求值器, 转字, 转数, 真值

# 默认样式
默认式 = {
    "填": 0.0,
    "缝": 0.0,
    "大": 15.0,
    "色": "#e2e8f0",
    "底": None,
    "粗": False,
    "圆": 0.0,
    "边": 0.0,
    "边色": "#24304d",
    "齐": "左",
    "悬底": None,
    "手": False,
    "横排": False,
    # 图线专用
    "底线": "#1e293b",
    "点色": None,
    "线宽": 2.0,
}

# 行高系数
行高系数 = 1.45
# 按钮内边距
钮横填 = 18.0
钮纵填 = 10.0
# 输入框默认宽
输默认宽 = 200.0


def 字宽(ch: str, 字号: float) -> float:
    """字符宽度估算：CJK 与全角符号按 1.0em，其余按 0.55em。"""
    o = ord(ch)
    if o < 128:
        return 字号 * 0.55
    if 0xFF01 <= o <= 0xFF60:      # 全角 ASCII
        return 字号 * 1.0
    if 0x3000 <= o <= 0x303F:      # 中文标点
        return 字号 * 1.0
    return 字号 * 1.0


def 文本宽(文: str, 字号: float) -> float:
    return sum(字宽(c, 字号) for c in 文)


def 可断点(文: str, 起: int, 止: int) -> list[int]:
    """返回可以换行的位置（在空格后、或任意 CJK 字符前后）。"""
    点: list[int] = []
    for i in range(起, 止):
        c = 文[i]
        if c == " ":
            点.append(i + 1)
        elif ord(c) >= 0x2E80:      # CJK 及标点，任意处可断
            点.append(i)
    return 点


def 折行(文: str, 字号: float, 可用宽: float) -> list[str]:
    """按可用宽度折行，返回行列表。"""
    if not 文:
        return [""]
    行们: list[str] = []
    剩余 = 文
    while 剩余:
        宽 = 0.0
        断处 = 0
        for i, c in enumerate(剩余):
            w = 字宽(c, 字号)
            if 宽 + w > 可用宽 and i > 0:
                break
            宽 += w
            断处 = i + 1
        else:
            断处 = len(剩余)

        if 断处 == len(剩余):
            行们.append(剩余)
            break

        # 在断处之前找最后一个可断点（优先空格）
        段 = 剩余[:断处]
        最后空 = 段.rfind(" ")
        if 最后空 > 0 and 最后空 > len(段) * 0.5:
            行们.append(剩余[:最后空])
            剩余 = 剩余[最后空 + 1:]
        else:
            行们.append(段.rstrip())
            剩余 = 剩余[断处:].lstrip()

    return 行们 or [""]


class 布局器:
    def __init__(self, 求值器: 求值器) -> None:
        self.求 = 求值器
        self._标识 = 0

    def 新标识(self) -> int:
        self._标识 += 1
        return self._标识

    # -- 入口 --

    def 布局页面(self, 页: A.页面, 视口宽: float, 视口高: float) -> dict:
        """把页面根节点布局成盒树。视口宽高是绘制区尺寸。"""
        根元素 = 页.根
        if 根元素 is None:
            return self._空盒()

        根盒 = self._布局节点(根元素, 视口宽, 视口高, 是根=True)
        return 根盒

    def _空盒(self) -> dict:
        return {
            "类": "块", "标识": 0, "x": 0.0, "y": 0.0,
            "宽": 0.0, "高": 0.0, "式": dict(默认式), "子": [], "布局": "竖",
        }

    # -- 样式 --

    def 解析式(self, 元素: A.元素节点) -> dict:
        式 = dict(默认式)
        for m in 元素.修饰:
            键 = m.键
            if m.值 is True:
                式[键] = True
                continue
            if isinstance(m.值, str) and 键 in ("齐", "宽"):
                式[键] = m.值
                continue
            if m.值 is None or isinstance(m.值, (A.节点,)):
                v = self.求.求值(m.值)
            else:
                v = m.值

            if 键 in ("填", "缝", "高", "大", "圆", "边"):
                式[键] = float(转数(v))
                if 式[键] < 0:
                    from .错误 import 值误
                    raise 值误(f"「{键}」不能为负数", m.行, m.列)
            elif 键 in ("色", "底", "边色", "悬底", "底线", "点色"):
                式[键] = 转字(v)
            elif 键 == "线宽":
                式[键] = float(转数(v))
            elif 键 == "齐":
                式[键] = v
            elif 键 == "宽":
                式[键] = "满" if v == "满" else float(转数(v))
            else:
                式[键] = v
        return 式

    def _取修饰(self, 元素: A.元素节点, 键: str) -> Any:
        """取某个修饰的值（不经过样式合并，用于「隐」这种控制项）。"""
        for m in 元素.修饰:
            if m.键 == 键:
                if m.值 is True:
                    return True
                if isinstance(m.值, str):
                    return m.值
                return self.求.求值(m.值)
        return None

    # -- 布局 --

    def _布局节点(self, 元素: A.元素节点, 可用宽: float, 可用高: float, 是根: bool = False) -> dict | None:
        # 隐
        隐值 = self._取修饰(元素, "隐")
        if 隐值 is not None and 真值(隐值):
            return None

        式 = self.解析式(元素)
        类 = 元素.类
        标识 = self.新标识()

        填 = 式["填"]

        # 若自身声明了固定宽度，则内部可用宽以它为准（影响折行与「宽 满」子元素）
        宽修饰 = 式.get("宽")
        自身固定宽 = 宽修饰 if isinstance(宽修饰, (int, float)) else None
        if 自身固定宽 is not None:
            内容可用宽 = max(0.0, 自身固定宽 - 2 * 填)
        else:
            内容可用宽 = max(0.0, 可用宽 - 2 * 填)

        if 类 == "条件":
            选中 = self.求.求值(元素.条件)
            元 = 元素.真元 if 真值(选中) else 元素.假元
            if 元 is None:
                return None
            盒 = self._布局节点(元, 可用宽, 可用高)
            if 盒 is None:
                return None
            # 继承外层修饰（如 隐）
            return 盒

        if 类 == "列":
            return self._布局列表(元素, 式, 填, 内容可用宽, 可用高, 标识)

        if 类 in ("竖", "横", "层"):
            return self._布局容器(元素, 式, 填, 内容可用宽, 可用高, 标识)

        if 类 == "文":
            文 = 转字(self.求.求值(元素.内容)) if 元素.内容 is not None else ""
            大 = 式["大"]
            齐 = 式.get("齐", "左")

            # 显式「宽」优先：文本在给定宽度内折行
            宽修饰2 = 式.get("宽")
            if isinstance(宽修饰2, (int, float)):
                内宽 = max(0.0, float(宽修饰2))
                行们 = 折行(文, 大, 内宽)
                内容高 = len(行们) * 大 * 行高系数
                外宽 = 内宽 + 2 * 填
            elif 宽修饰2 == "满":
                内宽 = 内容可用宽
                行们 = 折行(文, 大, 内宽)
                内容高 = len(行们) * 大 * 行高系数
                外宽 = 内容可用宽 + 2 * 填
            else:
                内宽 = 内容可用宽
                行们 = 折行(文, 大, 内容可用宽)
                内容高 = len(行们) * 大 * 行高系数
                内容宽 = max((文本宽(h, 大) for h in 行们), default=0.0)
                # 居中/右对齐时撑满可用宽度，否则按文本实际宽度收缩
                if 齐 in ("中", "右"):
                    外宽 = 内容可用宽 + 2 * 填
                else:
                    外宽 = min(内容可用宽, 内容宽) + 2 * 填

            return {
                "类": "文", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 外宽, "高": 内容高 + 2 * 填,
                "式": 式, "子": [], "文本": 文, "行们": 行们,
                "内宽": 内宽, "填": 填, "齐": 齐,
            }

        if 类 == "钮":
            标签 = 转字(self.求.求值(元素.内容)) if 元素.内容 is not None else ""
            大 = 式["大"]
            内容宽 = 文本宽(标签, 大)
            宽 = 内容宽 + 2 * 钮横填
            高 = 大 * 1.5 + 2 * 钮纵填
            # 宽修饰可覆盖
            if isinstance(式.get("宽"), (int, float)):
                宽 = float(式["宽"])
            elif 式.get("宽") == "满":
                宽 = 内容可用宽
            return {
                "类": "钮", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 宽, "高": 高, "式": 式, "子": [], "文本": 标签,
                "点": 元素.点, "手": True,
            }

        if 类 == "输":
            名 = 元素.内容.名 if isinstance(元素.内容, A.名) else ""
            值 = 转字(self.求.取(名)) if 名 else ""
            大 = 式["大"]
            宽 = 式.get("宽")
            if isinstance(宽, (int, float)):
                宽 = float(宽)
            elif 宽 == "满":
                宽 = 内容可用宽
            else:
                宽 = 输默认宽
            高 = 大 * 1.5 + 12
            return {
                "类": "输", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 宽, "高": 高, "式": 式, "子": [],
                "绑定": 名, "值": 值, "手": True,
            }

        if 类 == "图":
            路径 = 转字(self.求.求值(元素.内容)) if 元素.内容 is not None else ""
            宽 = 式.get("宽")
            高 = 式.get("高")
            if not isinstance(宽, (int, float)):
                宽 = 160.0
            if not isinstance(高, (int, float)):
                高 = 100.0
            return {
                "类": "图", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": float(宽), "高": float(高), "式": 式, "子": [], "图": 路径,
            }

        if 类 == "图线":
            # 数据源是状态名，取它的值（应为数的列）
            状态名 = 元素.内容.名 if isinstance(元素.内容, A.名) else ""
            数据 = []
            if 状态名:
                try:
                    原 = self.求.取(状态名)
                    if isinstance(原, list):
                        数据 = [float(转数(x)) for x in 原 if isinstance(x, (int, float))]
                except Exception:
                    数据 = []
            宽修饰 = 式.get("宽")
            if isinstance(宽修饰, (int, float)):
                宽 = float(宽修饰)
            else:
                宽 = 内容可用宽
            高 = 式.get("高")
            if not isinstance(高, (int, float)):
                高 = 120.0
            return {
                "类": "图线", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 宽, "高": float(高), "式": 式, "子": [],
                "数据": 数据, "状态名": 状态名,
            }

        if 类 == "线":
            粗 = 式["边"] if 式["边"] > 0 else 1.0
            return {
                "类": "线", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 可用宽, "高": 粗, "式": 式, "子": [], "粗": 粗,
            }

        if 类 == "空":
            高 = float(转数(self.求.求值(元素.内容))) if 元素.内容 is not None else 8.0
            宽修饰 = 式.get("宽")
            if isinstance(宽修饰, (int, float)):
                宽 = float(宽修饰)
            elif 宽修饰 == "满":
                宽 = 可用宽
            else:
                # 显式给了高度但没给宽度时，默认撑满（占位条）
                宽 = 可用宽 if 高 > 0 and 式.get("底") else 可用宽
            return {
                "类": "空", "标识": 标识, "x": 0.0, "y": 0.0,
                "宽": 宽, "高": 高, "式": 式, "子": [],
            }

        # 未知元素：当空盒
        return {
            "类": "块", "标识": 标识, "x": 0.0, "y": 0.0,
            "宽": 可用宽, "高": 0.0, "式": 式, "子": [],
        }

    def _布局列表(
        self, 元素: A.元素节点, 式: dict, 填: float, 内容可用宽: float,
        可用高: float, 标识: int,
    ) -> dict:
        """列 项名 于 数据源 【 子元素… 】：对数据源里每一项，重复布局子元素。

        展开后行为等同竖向容器：每一项的子树依次往下排，项之间用「缝」。
        """
        缝 = 式["缝"]
        数据源 = self.求.求值(元素.数据源) if 元素.数据源 is not None else []

        if isinstance(数据源, dict):
            序列 = list(数据源.values())
            键们 = list(数据源.keys())
        elif isinstance(数据源, list):
            序列 = 数据源
            键们 = list(range(len(数据源)))
        else:
            序列 = []
            键们 = []

        # 每项绑定「项名」与「项序」到临时作用域
        子盒们: list[dict] = []
        旧值 = {}
        有旧 = 元素.项名 in self.求.状态
        if 有旧:
            旧值[元素.项名] = self.求.状态[元素.项名]

        绑定 = {}
        for i, 项 in enumerate(序列):
            self.求.状态[元素.项名] = 项
            self.求.状态["项序"] = i
            self.求.状态["该项键"] = 键们[i]
            本次绑定 = {元素.项名: 项, "项序": i, "该项键": 键们[i]}
            for 子 in 元素.子:
                盒 = self._布局节点(子, 内容可用宽, 可用高)
                if 盒 is not None:
                    # 记录项绑定，供点击时恢复上下文
                    记绑定(盒, 本次绑定)
                    子盒们.append(盒)

        # 恢复状态（避免污染）
        if 有旧:
            self.求.状态[元素.项名] = 旧值[元素.项名]
        else:
            self.求.状态.pop(元素.项名, None)
        self.求.状态.pop("项序", None)
        self.求.状态.pop("该项键", None)

        # 排列：默认竖排，加 横排 修饰则横排
        if 式.get("横排"):
            x = 0.0
            内容高 = 0.0
            for i, 盒 in enumerate(子盒们):
                盒["x"] = x
                盒["y"] = 0.0
                x += 盒["宽"]
                if i < len(子盒们) - 1:
                    x += 缝
                内容高 = max(内容高, 盒["高"])
            内容宽 = x
        else:
            y = 0.0
            内容宽 = 0.0
            for i, 盒 in enumerate(子盒们):
                if 盒["式"].get("宽") == "满":
                    盒["宽"] = 内容可用宽
                盒["x"] = 0.0
                盒["y"] = y
                y += 盒["高"]
                if i < len(子盒们) - 1:
                    y += 缝
                内容宽 = max(内容宽, 盒["宽"])
            内容高 = y
        宽修饰 = 式.get("宽")
        if isinstance(宽修饰, (int, float)):
            外宽 = float(宽修饰)
        else:
            外宽 = 内容可用宽 + 2 * 填

        for 盒 in 子盒们:
            盒["x"] += 填
            盒["y"] += 填

        return {
            "类": "块", "标识": 标识, "x": 0.0, "y": 0.0,
            "宽": 外宽, "高": 内容高 + 2 * 填,
            "式": 式, "子": 子盒们, "布局": "竖", "填": 填,
        }

    def _布局容器(
        self, 元素: A.元素节点, 式: dict, 填: float, 内容可用宽: float,
        可用高: float, 标识: int,
    ) -> dict:
        布局 = 元素.类      # 竖 / 横 / 层
        缝 = 式["缝"]

        # 先递归布局子元素（竖/横 的子元素宽度受容器内容宽约束）
        子盒们: list[dict] = []
        for 子 in 元素.子:
            盒 = self._布局节点(子, 内容可用宽, 可用高)
            if 盒 is not None:
                子盒们.append(盒)

        内容高 = 0.0
        内容宽 = 0.0

        if 布局 == "竖":
            y = 0.0
            for i, 盒 in enumerate(子盒们):
                # 宽 满 的子元素撑满内容宽
                如满 = 盒["式"].get("宽") == "满"
                if 如满:
                    盒["宽"] = 内容可用宽
                # 竖向容器里的子元素可以按自身「齐」在横向定位（容器与普通元素都适用）
                子齐 = 盒["式"].get("齐", "左")
                if 子齐 == "中":
                    盒["x"] = max(0.0, (内容可用宽 - 盒["宽"]) / 2)
                elif 子齐 == "右":
                    盒["x"] = max(0.0, 内容可用宽 - 盒["宽"])
                else:
                    盒["x"] = 0.0
                盒["y"] = y
                y += 盒["高"]
                if i < len(子盒们) - 1:
                    y += 缝
                内容高 = y
                内容宽 = max(内容宽, 盒["宽"] + 盒["x"])
        elif 布局 == "横":
            x = 0.0
            for i, 盒 in enumerate(子盒们):
                盒["x"] = x
                盒["y"] = 0.0
                x += 盒["宽"]
                if i < len(子盒们) - 1:
                    x += 缝
                内容宽 = x
                内容高 = max(内容高, 盒["高"])
        else:  # 层
            for 盒 in 子盒们:
                盒["x"] = 0.0
                盒["y"] = 0.0
                内容宽 = max(内容宽, 盒["宽"])
                内容高 = max(内容高, 盒["高"])

        # 容器自身尺寸
        宽修饰 = 式.get("宽")
        if isinstance(宽修饰, (int, float)):
            外宽 = float(宽修饰)
        elif 宽修饰 == "满":
            外宽 = 内容可用宽 + 2 * 填
        else:
            # 横/层容器：宽度由内容决定；竖容器默认撑满可用宽
            if 布局 == "竖":
                外宽 = 内容可用宽 + 2 * 填
            else:
                外宽 = max(内容宽 + 2 * 填, 0.0)

        高修饰 = 式.get("高")
        if isinstance(高修饰, (int, float)):
            外高 = float(高修饰)
        else:
            外高 = 内容高 + 2 * 填

        # 子元素坐标平移到内边距原点
        for 盒 in 子盒们:
            盒["x"] += 填
            盒["y"] += 填

        return {
            "类": "块", "标识": 标识, "x": 0.0, "y": 0.0,
            "宽": 外宽, "高": 外高, "式": 式, "子": 子盒们,
            "布局": 布局, "填": 填,
        }


def 记绑定(盒: dict, 绑定: dict) -> None:
    """把项绑定写进盒及其所有子盒（供事件处理恢复上下文）。"""
    盒["项绑定"] = 绑定
    for 子 in 盒.get("子", []):
        记绑定(子, 绑定)


def 布局(页: A.页面, 求值器: 求值器, 视口宽: float, 视口高: float) -> dict:
    return 布局器(求值器).布局页面(页, 视口宽, 视口高)


# ---------------------------------------------------------------------------
# 盒树工具
# ---------------------------------------------------------------------------


def 遍历(盒: dict):
    """先序遍历盒树。"""
    yield 盒
    for 子 in 盒.get("子", []):
        yield from 遍历(子)


def 找盒(根: dict, 标识: int) -> dict | None:
    for 盒 in 遍历(根):
        if 盒.get("标识") == 标识:
            return 盒
    return None


def 命中最上层(根: dict, x: float, y: float) -> dict | None:
    """返回坐标处最上层的可交互盒。

    盒的 x/y 是**相对父容器**的，所以递归时必须累加父偏移，
    再与鼠标的绝对坐标比较（与渲染器的处理一致）。

    可交互 = 钮 / 输；层容器里后声明的在上，所以逆序遍历子元素。
    """
    可交互类 = ("钮", "输")

    def 递归(盒: dict, 父x: float, 父y: float) -> dict | None:
        绝x = 父x + 盒["x"]
        绝y = 父y + 盒["y"]

        # 先查子（后声明的优先）
        for 子 in reversed(盒.get("子", [])):
            命中 = 递归(子, 绝x, 绝y)
            if 命中 is not None:
                return 命中

        # 再看自己
        if 盒.get("类") in 可交互类:
            if (绝x <= x <= 绝x + 盒["宽"]
                    and 绝y <= y <= 绝y + 盒["高"]):
                return 盒
        return None

    return 递归(根, 0.0, 0.0)


