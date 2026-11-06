"""爻页求值：状态管理、表达式求值、内置函数。"""

from __future__ import annotations

import datetime
from typing import Any

from . import 语法 as A
from .错误 import 名误, 型误, 值误

# ---------------------------------------------------------------------------
# 值工具
# ---------------------------------------------------------------------------


def 转字(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "真" if v else "假"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return ("%.4f" % v).rstrip("0").rstrip(".")
    if isinstance(v, (int, str)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(转字(x) for x in v) + "]"
    return str(v)


def 转数(v: Any) -> float | int:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        文 = v.strip()
        try:
            return int(文)
        except ValueError:
            try:
                return float(文)
            except ValueError:
                raise 型误(f"「{v}」不是数字")
    if v is None:
        return 0
    raise 型误(f"不能把「{type(v).__name__}」当作数字")


def 真值(v: Any) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, str):
        return v != ""
    if isinstance(v, list):
        return len(v) > 0
    return True


def 相等(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(相等(x, y) for x, y in zip(a, b))
    return a == b


# ---------------------------------------------------------------------------
# 内置函数
# ---------------------------------------------------------------------------


def _串(v: Any) -> str:
    return 转字(v)


def _数(v: Any) -> float | int:
    return 转数(v)


def _整(v: Any) -> int:
    return int(转数(v))


def _长(v: Any) -> int:
    if isinstance(v, (str, list)):
        return len(v)
    raise 型误("「长」需要一个字或列")


def _切(v: Any, 起: Any, 止: Any = None) -> Any:
    if not isinstance(v, (str, list)):
        raise 型误("「切」第一个参数需要字或列")
    起 = int(转数(起))
    止 = None if 止 is None else int(转数(止))
    return v[起:止]


def _含(v: Any, 子: Any) -> bool:
    if isinstance(v, str):
        return 转字(子) in v
    if isinstance(v, list):
        return any(相等(x, 子) for x in v)
    raise 型误("「含」第一个参数需要字或列")


def _并(v: Any, 隔: Any = "") -> str:
    if not isinstance(v, list):
        raise 型误("「并」第一个参数需要列")
    return 转字(隔).join(转字(x) for x in v)


def _分(v: Any, 隔: Any = None) -> list:
    if not isinstance(v, str):
        raise 型误("「分」第一个参数需要字")
    if 隔 is None:
        return v.split()
    return v.split(转字(隔))


def _今() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _请求(网址: Any, 选项: Any = None) -> dict:
    """请求(网址, 选项?) → { 码, 文, 错 }

    选项是表：
        法   —— "GET"（默认）/ "POST" / "PUT" / "DELETE"
        体   —— 要发的值（自动 JSON 序列化）
        头   —— 额外请求头

    自动带上全局存储里的 X-Token 登录令牌。
    """
    import json as _json
    import urllib.error
    import urllib.request
    from urllib.parse import quote, urlsplit, urlunsplit

    if not isinstance(网址, str):
        raise 型误("「请求」需要一个网址")

    选项 = 选项 if isinstance(选项, dict) else {}
    法 = str(选项.get("法", "GET")).upper()
    体 = 选项.get("体")
    额外头 = 选项.get("头") or {}

    头 = {"User-Agent": "YaoPage/0.1", **_令牌头()}
    if isinstance(额外头, dict):
        for k, v in 额外头.items():
            头[str(k)] = 转字(v)

    数据 = None
    if 体 is not None:
        数据 = _json.dumps(体, ensure_ascii=False).encode("utf-8")
        头.setdefault("Content-Type", "application/json; charset=utf-8")

    # 中文路径编码
    try:
        拆 = urlsplit(网址)
        真址 = urlunsplit((
            拆.scheme, 拆.netloc,
            quote(拆.path, safe="/%:@&=+$,;~*'()![]"),
            quote(拆.query, safe="=&%:@+$,;~*'()![]/?"),
            拆.fragment,
        ))
    except Exception:
        真址 = 网址

    try:
        req = urllib.request.Request(真址, data=数据, headers=头, method=法)
        with urllib.request.urlopen(req, timeout=20) as r:
            原始 = r.read()
            类型 = (r.headers.get("Content-Type") or "").lower()
            编码 = "utf-8"
            if "charset=" in 类型:
                编码 = 类型.split("charset=")[-1].split(";")[0].strip() or "utf-8"
            return {"码": r.status, "文": 原始.decode(编码, errors="replace"), "错": ""}
    except urllib.error.HTTPError as e:
        原始 = e.read()
        try:
            文 = 原始.decode("utf-8", errors="replace")
        except Exception:
            文 = ""
        return {"码": e.code, "文": 文, "错": ""}
    except Exception as e:
        return {"码": 0, "文": "", "错": f"{type(e).__name__}: {e}"}


def _析(文: Any) -> Any:
    """JSON 解析。失败返回空值而不抛异常（界面渲染要容错）。"""
    import json as _json

    if not isinstance(文, str):
        return None
    try:
        return _json.loads(文)
    except Exception:
        return None


def _构(值: Any) -> str:
    """JSON 序列化。"""
    import json as _json

    try:
        return _json.dumps(值, ensure_ascii=False)
    except Exception:
        return ""


def _令牌头() -> dict:
    """从全局存储取登录令牌，拼成请求头。"""
    令牌 = _全局存储.get("令牌", "")
    if 令牌:
        return {"X-Token": str(令牌)}
    return {}


def _抓(网址: Any) -> dict:
    """抓取一个网址，返回 {码, 文, 头}。失败不抛异常。"""
    import json as _json
    import urllib.error
    import urllib.request
    from urllib.parse import quote, urlsplit, urlunsplit

    if not isinstance(网址, str):
        raise 型误("「抓」需要一个网址")
    # 中文路径自动编码
    try:
        拆 = urlsplit(网址)
        真址 = urlunsplit(
            (拆.scheme, 拆.netloc,
             quote(拆.path, safe="/%:@&=+$,;~*'()![]"),
             quote(拆.query, safe="=&%:@+$,;~*'()![]/?"), 拆.fragment)
        )
    except Exception:
        真址 = 网址
    try:
        req = urllib.request.Request(
            真址, headers={"User-Agent": "YaoPage/0.1", **_令牌头()}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            原始 = r.read()
            类型 = (r.headers.get("Content-Type") or "").lower()
            编码 = "utf-8"
            if "charset=" in 类型:
                编码 = 类型.split("charset=")[-1].split(";")[0].strip() or "utf-8"
            return {
                "码": r.status,
                "文": 原始.decode(编码, errors="replace"),
                "头": {k.lower(): v for k, v in r.headers.items()},
            }
    except urllib.error.HTTPError as e:
        原始 = e.read() if hasattr(e, "read") else b""
        return {"码": e.code, "文": 原始.decode("utf-8", errors="replace"), "头": {}}
    except Exception as e:
        return {"码": 0, "文": "", "头": {}, "错": f"{type(e).__name__}: {e}"}


def _取字段(数据: Any, 键: Any) -> Any:
    """从表/列里取字段；取不到返回空值而不是报错（界面渲染要容错）。"""
    if isinstance(数据, dict):
        return 数据.get(键)
    if isinstance(数据, list):
        try:
            return 数据[int(转数(键))]
        except Exception:
            return None
    return None


def _增(列: Any, 值: Any) -> Any:
    """增(列, 值) —— 追加，与爻语同名。"""
    if isinstance(列, list):
        列.append(值)
    return 列


def _删(容器: Any, 键: Any) -> Any:
    """删(列|表, 键|下标) —— 与爻语同名。"""
    if isinstance(容器, list):
        try:
            i = int(转数(键))
        except Exception:
            return 容器
        if 0 <= i < len(容器):
            容器.pop(i)
    elif isinstance(容器, dict):
        容器.pop(键, None)
    return 容器


def _排(列: Any) -> Any:
    """排(列) —— 排序，返回新列。"""
    if not isinstance(列, list):
        return 列
    try:
        return sorted(列)
    except TypeError:
        return sorted(列, key=lambda x: str(x))


def _倒(列: Any) -> Any:
    """倒(列) —— 反转，返回新列。"""
    if isinstance(列, list):
        return list(reversed(列))
    return 列


#: 跨页面的全局存储（相当于浏览器 localStorage）
_全局存储: dict[str, Any] = {}


def _存(键: Any, 值: Any) -> Any:
    """存(键, 值) —— 写入全局存储，页面切换后仍在。"""
    _全局存储[str(键)] = 值
    return 值


def _载(键: Any, 默认: Any = None) -> Any:
    """载(键, 默认?) —— 读全局存储（同「载入」的载）。"""
    return _全局存储.get(str(键), 默认)


def _清(键: Any = None) -> Any:
    """清(键?) —— 清除一项或全部全局存储。"""
    if 键 is None:
        _全局存储.clear()
    else:
        _全局存储.pop(str(键), None)
    return None


def _删存(键: Any) -> Any:
    _全局存储.pop(str(键), None)
    return None


def _舍(值: Any, 位: Any = 0) -> float:
    """舍(数, 小数位?) —— 与爻语的「舍」同名。"""
    x = 转数(值)
    n = int(转数(位)) if 位 is not None else 0
    return round(x, n)


def _绝(值: Any) -> float:
    return abs(转数(值))


def _极(值们: Any) -> Any:
    """极 —— 取最大（列或多参）"""
    if isinstance(值们, list):
        return max(值们) if 值们 else None
    return 值们


def _取(数据: Any, 键: Any, 默认: Any = None) -> Any:
    """取(表|列|字, 键, 默认?) —— 与爻语的「取」同名同义。

    爻语：取({"甲" ⇒ 1}, "甲", 0) → 1
    爻页：取(快照, "kpi", {}) → 表里的 kpi
    取不到时返回默认值，不报错。
    """
    if isinstance(数据, dict):
        return 数据.get(键, 默认)
    if isinstance(数据, list):
        try:
            i = int(转数(键))
        except Exception:
            return 默认
        if i < 0:
            i += len(数据)
        if 0 <= i < len(数据):
            return 数据[i]
        return 默认
    if isinstance(数据, str):
        try:
            i = int(转数(键))
        except Exception:
            return 默认
        if i < 0:
            i += len(数据)
        if 0 <= i < len(数据):
            return 数据[i]
        return 默认
    return 默认


def _置(容器: Any, 键: Any, 值: Any) -> Any:
    """置(表|列, 键, 值) —— 与爻语同名。就地修改并返回容器。"""
    if isinstance(容器, dict):
        容器[键] = 值
    elif isinstance(容器, list):
        try:
            i = int(转数(键))
        except Exception:
            return 容器
        if 0 <= i < len(容器):
            容器[i] = 值
    return 容器


def _有(数据: Any, 键: Any) -> bool:
    if isinstance(数据, dict):
        return 键 in 数据
    if isinstance(数据, list):
        try:
            return 0 <= int(转数(键)) < len(数据)
        except Exception:
            return False
    return False


def _截断(文: Any, 长: Any = 80) -> str:
    文 = 转字(文)
    长 = int(转数(长))
    return 文 if len(文) <= 长 else 文[:长] + "…"


内置 = {
    "析": (_析, 1, 1),
    "构": (_构, 1, 1),
    "抓": (_抓, 1, 1),
    "取": (_取, 2, 3),
    "置": (_置, 3, 3),
    "取字段": (_取字段, 2, 2),
    "请求": (_请求, 1, 2),
    "存": (_存, 2, 2),
    "载": (_载, 1, 2),
    "清": (_清, 0, 1),
    "增": (_增, 2, 2),
    "删": (_删, 2, 2),
    "排": (_排, 1, 1),
    "倒": (_倒, 1, 1),
    "舍": (_舍, 1, 2),
    "绝": (_绝, 1, 1),
    "有": (_有, 2, 2),
    "截断": (_截断, 1, 2),
    "串": (_串, 1, 1),
    "数": (_数, 1, 1),
    "整": (_整, 1, 1),
    "长": (_长, 1, 1),
    "切": (_切, 2, 3),
    "含": (_含, 2, 2),
    # 注意：不能用「并」「分」——「并」与逻辑关键字冲突，故用「连」「拆」
    "连": (_并, 1, 2),
    "拆": (_分, 1, 2),
    "今": (_今, 0, 0),
}


# ---------------------------------------------------------------------------
# 求值器
# ---------------------------------------------------------------------------


class 求值器:
    def __init__(
        self,
        状态: dict[str, Any] | None = None,
        外部: dict[str, Any] | None = None,
    ) -> None:
        self.状态: dict[str, Any] = dict(状态 or {})
        self.赋值记录: list[str] = []
        #: 动作队列：跳转 / 提交，由浏览器执行
        self.动作: list[tuple] = []
        #: 外部注入的值（如 参数、路径），只在状态里查不到时兜底
        self.外部: dict[str, Any] = dict(外部 or {})
        #: 是否允许赋值时新建变量（始块里为真）
        self.允许新建: bool = False
        #: 调用后端回调（浏览器注入）：(路径, 体) -> 结果
        self.调用后端 = None
        #: 页面内定义的函数：名 -> 函数定义节点
        self.函数表: dict[str, Any] = {}
        #: 「回」语句的返回值（用异常传递）
        self.返回值: Any = None
        self.已返回: bool = False

    # -- 表达式 --

    def 求值(self, n: A.节点) -> Any:
        t = type(n)

        if t is A.数:
            return n.值
        if t is A.字:
            return n.值
        if t is A.真:
            return n.值
        if t is A.空值:
            return None
        if t is A.名:
            return self.取(n.名, n.行, n.列)
        if t is A.一元:
            return self.求一元(n)
        if t is A.二元:
            return self.求二元(n)
        if t is A.调用:
            return self.调函数(n)
        if t is A.列:
            return [self.求值(x) for x in n.元素]
        if t is A.表:
            return {k: self.求值(v) for k, v in n.对}

        raise 型误(f"无法求值的节点 {t.__name__}", getattr(n, "行", 0), getattr(n, "列", 0))

    def 取(self, 名: str, 行: int = 0, 列: int = 0) -> Any:
        if 名 in self.状态:
            return self.状态[名]
        if 名 in self.外部:
            return self.外部[名]
        raise 名误(f"没有这个状态「{名}」", 行, 列)

    def 求一元(self, n: A.一元) -> Any:
        v = self.求值(n.右)
        if n.运算 == "非":
            return not 真值(v)
        if n.运算 == "-":
            return -转数(v)
        raise 型误(f"未知一元运算「{n.运算}」", n.行, n.列)

    def 求二元(self, n: A.二元) -> Any:
        op = n.运算

        if op == "且":
            左 = self.求值(n.左)
            return self.求值(n.右) if 真值(左) else 左
        if op == "或":
            左 = self.求值(n.左)
            return 左 if 真值(左) else self.求值(n.右)

        左 = self.求值(n.左)
        右 = self.求值(n.右)

        if op == "==":
            return 相等(左, 右)
        if op == "!=":
            return not 相等(左, 右)

        if op in ("<", "<=", ">", ">="):
            if isinstance(左, str) and isinstance(右, str):
                a, b = 左, 右
            else:
                a, b = 转数(左), 转数(右)
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]

        if op == "+":
            if isinstance(左, str) or isinstance(右, str):
                return 转字(左) + 转字(右)
            if isinstance(左, list) and isinstance(右, list):
                return 左 + 右
            return 转数(左) + 转数(右)

        a, b = 转数(左), 转数(右)
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise 值误("不能除以零", n.行, n.列)
            return a / b
        if op == "%":
            if b == 0:
                raise 值误("不能对零取余", n.行, n.列)
            return a % b

        raise 型误(f"未知运算「{op}」", n.行, n.列)

    def 调函数(self, n: A.调用) -> Any:
        # 先查页面内定义的函数
        自定 = self.函数表.get(n.被调)
        if 自定 is not None:
            return self._调用户函数(自定, n)

        定义 = 内置.get(n.被调)
        if 定义 is None:
            raise 名误(f"没有这个函数「{n.被调}」", n.行, n.列)
        函数, 最少, 最多 = 定义
        参 = [self.求值(a) for a in n.参]
        if len(参) < 最少 or (最多 is not None and len(参) > 最多):
            raise 型误(f"「{n.被调}」需要 {最少}~{最多} 个参数，实际 {len(参)} 个", n.行, n.列)
        return 函数(*参)

    def _调用户函数(self, 定义: Any, 调用: A.调用) -> Any:
        """调用页面内定义的函数。

        爻页的函数是「闭包共享状态」的语义：函数里能读写页面状态，
        所以不新建作用域，只临时绑定参数。
        """
        参值 = [self.求值(a) for a in 调用.参]
        if len(参值) != len(定义.参数们):
            raise 型误(
                f"「{定义.名}」需要 {len(定义.参数们)} 个参数，实际 {len(参值)} 个",
                调用.行, 调用.列,
            )
        # 保存被覆盖的状态
        旧值: dict[str, Any] = {}
        新键们: list[str] = []
        for 名, 值 in zip(定义.参数们, 参值):
            if 名 in self.状态:
                旧值[名] = self.状态[名]
            else:
                新键们.append(名)
            self.状态[名] = 值

        旧返回 = self.已返回
        旧返回值 = self.返回值
        旧允许 = self.允许新建
        self.允许新建 = True      # 函数体里可以创建局部变量
        self.已返回 = False
        self.返回值 = None
        try:
            循环保护 = 0
            for 语句 in 定义.体.语句:
                self.执行语句(语句)
                循环保护 += 1
                if 循环保护 > 200000:
                    raise 值误("函数执行步数过多（可能死循环）", 调用.行, 调用.列)
                if self.已返回:
                    break
            return self.返回值
        finally:
            for 名, 值 in 旧值.items():
                self.状态[名] = 值
            for 名 in 新键们:
                self.状态.pop(名, None)
            self.已返回 = 旧返回
            self.返回值 = 旧返回值
            self.允许新建 = 旧允许

    # -- 语句 --

    def 执行块(self, 块: A.块节点) -> None:
        for 语句 in 块.语句:
            self.执行语句(语句)

    def 执行语句(self, n: A.节点) -> None:
        if isinstance(n, A.赋值):
            值 = self.求值(n.值)
            if n.名 not in self.状态:
                if self.允许新建:
                    # 始块 / 次块 / 函数体里允许创建局部变量
                    self.状态[n.名] = 值
                    self.赋值记录.append(n.名)
                    return
                raise 名误(f"没有这个状态「{n.名}」", n.行, n.列)
            self.状态[n.名] = 值
            self.赋值记录.append(n.名)
            return
        if isinstance(n, A.调用接口):
            路径 = 转字(self.求值(n.路径))
            体 = self.求值(n.体) if n.体 is not None else None
            if self.调用后端 is None:
                raise 型误("当前环境不支持调用后端", n.行, n.列)
            结果 = self.调用后端(路径, 体)
            if n.结果名:
                self.状态[n.结果名] = 结果
                self.赋值记录.append(n.结果名)
            return
        if isinstance(n, A.函数定义):
            self.函数表[n.名] = n
            return
        if isinstance(n, A.返回):
            self.返回值 = self.求值(n.值) if n.值 is not None else None
            self.已返回 = True
            return
        if isinstance(n, A.调用语句):
            self.求值(n.表达式)
            return
        if isinstance(n, A.分支):
            条件 = 真值(self.求值(n.条件))
            体 = n.真体 if 条件 else n.假体
            if 体 is not None:
                self.执行语句(体)
            return
        if isinstance(n, A.块节点):
            for s in n.语句:
                self.执行语句(s)
            return
        if isinstance(n, A.跳转):
            路径 = 转字(self.求值(n.路径))
            self.动作.append(("跳", 路径))
            return
        if isinstance(n, A.提交):
            路径 = 转字(self.求值(n.路径))
            体 = self.求值(n.体) if n.体 is not None else None
            self.动作.append(("发", 路径, 体))
            return
        raise 型误(f"点击块里不能执行 {type(n).__name__}", n.行, n.列)

    # -- 动作队列（由浏览器消费） --

    def 取动作(self) -> list:
        动作 = self.动作
        self.动作 = []
        return 动作
