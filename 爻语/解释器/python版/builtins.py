"""爻语内置函数（SPEC 第 4 节）。"""

from __future__ import annotations

import datetime
import json
import math
import os
import random
import sys
import threading
import time
from typing import Any

from .errors import 型误, 值误, 核误, 键误, 零误, 引误
from .values import (
    匠,
    原生,
    应,
    请,
    空,
    取类型名,
    数字串,
    相等,
    化空,
    真值,
    转字,
)


def _造(名: str, 函数, 最小参: int = 0, 最大参: int | None = None, 沙箱禁用: bool = False) -> 原生:
    return 原生(名=名, 函数=函数, 最小参=最小参, 最大参=最大参, 沙箱禁用=沙箱禁用)


#: 采集线程表：编号 → { 线程, 停止标志 }
_采集线程们: dict[int, dict] = {}
_采集序号 = [0]
_采集锁 = threading.RLock()


def _启采(法: Any, 名: Any = "") -> dict:
    """启采(函数, 名字?) → { 号, 错 }

    在后台线程里反复调用「函数」，直到 停采。函数自己负责每次的间隔
    （通常用 眠(秒) 或阻塞式的 收讯）。这是爻语唯一的并发入口。
    """
    if not isinstance(法, 匠):
        raise 型误("「启采」需要一个无参函数")

    with _采集锁:
        _采集序号[0] += 1
        号 = _采集序号[0]
        停止 = threading.Event()

        def _循环() -> None:
            import sys as _sys

            # 采集线程里出错只打印，不能拖垮整个服务
            while not 停止.is_set():
                try:
                    解释器 = _采集目标解释器[0]
                    if 解释器 is None:
                        break
                    解释器.调用(法, [], _假节点())
                except Exception as e:
                    try:
                        _sys.stderr.write(f"[采集线程 {号}] 出错：{e}\n")
                        _sys.stderr.flush()
                    except Exception:
                        pass
                    # 出错后歇一会儿，避免疯狂刷屏
                    停止.wait(1.0)

        线 = threading.Thread(target=_循环, name=f"爻语采集{号}", daemon=True)
        _采集线程们[号] = {"线程": 线, "停止": 停止, "名": 转字(名) if 名 is not None else ""}
        线.start()

    return {"号": 号, "错": ""}


def _停采(号: Any = None) -> Any:
    """停采(号?) → 空。不给号就停全部。"""
    with _采集锁:
        if 号 is None or 号 == 空:
            目标们 = list(_采集线程们.keys())
        else:
            if not isinstance(号, int) or isinstance(号, bool):
                raise 型误("「停采」的号必须是整数")
            目标们 = [号] if 号 in _采集线程们 else []

        for 编 in 目标们:
            信息 = _采集线程们.pop(编, None)
            if 信息:
                信息["停止"].set()
                线 = 信息["线程"]
                if 线.is_alive():
                    线.join(timeout=2.0)
    return 空


def 关闭采集() -> None:
    """进程退出前停掉所有采集线程。"""
    try:
        _停采(None)
    except Exception:
        pass


def 采集状态() -> dict:
    with _采集锁:
        return {
            "数": len(_采集线程们),
            "名们": [v.get("名", "") for v in _采集线程们.values()],
        }


#: 采集线程要用的解释器（启动时填）
_采集目标解释器: list = [None]


def 绑定解释器(解释器: Any) -> None:
    _采集目标解释器[0] = 解释器


def _整(值: Any) -> int:
    """整(值) —— 转成整数（截断小数）。"""
    if isinstance(值, bool):
        raise 型误("「整」不能用于真假值")
    if isinstance(值, int):
        return 值
    if isinstance(值, float):
        return int(值)
    if isinstance(值, str):
        try:
            return int(float(值.strip()))
        except ValueError:
            raise 型误(f"「整」无法把「{值}」转成整数")
    raise 型误(f"「整」不能用于{取类型名(值)}")


def _字码(字: Any, 位置: Any = 0) -> int:
    """字码(字, 位置?) → 该位置字符的码点（整数）。"""
    if not isinstance(字, str):
        raise 型误("「字码」需要一个字")
    i = int(位置) if isinstance(位置, (int, float)) else 0
    if i < 0:
        i += len(字)
    if not (0 <= i < len(字)):
        raise 键误(f"「字码」位置越界：{位置}（长度 {len(字)}）")
    return ord(字[i])


def _码字(码: Any) -> str:
    """码字(整) → 该码点对应的字符。"""
    if isinstance(码, bool) or not isinstance(码, (int, float)):
        raise 型误("「码字」需要一个整数码点")
    try:
        return chr(int(码))
    except (ValueError, OverflowError):
        raise 值误(f"「码字」码点不合法：{码}")


def 造内置(解释器) -> dict[str, 原生]:
    # 采集线程要靠这个引用才能执行爻语函数
    绑定解释器(解释器)

    出: dict[str, 原生] = {}

    def 加(f: 原生) -> None:
        出[f.名] = f

    # -- 4.1 输入输出与类型 ---------------------------------------------

    def _显(*值们) -> Any:
        解释器.输出(" ".join(转字(v) for v in 值们) + "\n")
        return 空

    def _述(*值们) -> Any:
        解释器.输出(" ".join(转字(v) for v in 值们))
        return 空

    def _串(值: Any) -> str:
        """SPEC 4.1：列/表 → JSON 风格；其余按爻语展示。"""
        if isinstance(值, (list, dict)):
            try:
                return json.dumps(_爻转json(值), ensure_ascii=False)
            except 型误:
                return 转字(值)
        if 值 is 空 or 值 is None:
            return "空"
        return 转字(值)

    def _数(值: Any) -> Any:
        if isinstance(值, bool):
            raise 型误("真/假不能转成数")
        if isinstance(值, (int, float)):
            return 值
        if isinstance(值, str):
            文 = 值.strip()
            try:
                return int(文)
            except ValueError:
                try:
                    return float(文)
                except ValueError:
                    raise 型误(f"「{文}」不是数字")
        raise 型误(f"「{取类型名(值)}」不能转成数")

    def _型(值: Any) -> str:
        return 取类型名(值)

    def _版本() -> str:
        from . import 版本

        return 版本

    def _滴() -> float:
        """高精度计时（秒，浮点）。用于性能分析与耗时测量。"""
        return time.perf_counter()

    def _毫秒(起: Any, 止: Any = None) -> float:
        """毫秒数：毫秒(起) 或 毫秒(起, 止)，保留 3 位小数。"""
        for 值 in (起, 止):
            if 值 is not None and (isinstance(值, bool) or not isinstance(值, (int, float))):
                raise 型误("「毫秒」的参数必须是数（来自「滴」）")
        终 = time.perf_counter() if 止 is None else 止
        return round((终 - 起) * 1000.0, 3)

    # -- 4.4.2 账号与安全 -------------------------------------------------

    def _散列(文: Any, 盐: Any = "") -> str:
        """加盐 SHA-256 十六进制摘要。用于密码存储，绝不存明文。"""
        import hashlib
        import secrets

        if not isinstance(文, str):
            raise 型误("「散列」的第一个参数必须是字")
        盐文 = "" if 盐 is 空 or 盐 is None else (盐 if isinstance(盐, str) else 转字(盐))
        料 = (盐文 + "\x00" + 文).encode("utf-8")
        return hashlib.sha256(料).hexdigest()

    def _随机字(长度: Any = 32, 集: Any = 空) -> str:
        """密码学安全随机字符串。默认 32 位 URL 安全字符，适合会话令牌/盐。"""
        import secrets
        import string

        if isinstance(长度, bool) or not isinstance(长度, int):
            raise 型误("「随机字」的长度必须是整数")
        if 长度 < 1 or 长度 > 256:
            raise 值误("「随机字」的长度需在 1 到 256 之间")
        if 集 is 空 or 集 is None:
            return secrets.token_urlsafe(长度)[:长度]
        组 = 集 if isinstance(集, str) else 转字(集)
        if not 组:
            raise 值误("「随机字」的字符集不能为空")
        return "".join(secrets.choice(组) for _ in range(长度))

    def _恒等(甲: Any, 乙: Any) -> bool:
        """恒定时间比较两个字符串（防时序攻击），用于校验令牌/密码摘要。"""
        import hmac

        if not isinstance(甲, str) or not isinstance(乙, str):
            raise 型误("「恒等」的两个参数都必须是字")
        return hmac.compare_digest(甲.encode("utf-8"), 乙.encode("utf-8"))

    def _开覆盖() -> Any:
        """开启函数级覆盖率追踪。"""
        解释器.覆盖追踪 = True
        解释器.覆盖计数.clear()
        解释器.覆盖调用行.clear()
        return 空

    def _取覆盖() -> dict:
        """取覆盖率快照：{调用: 表, 次数: 表, 已覆盖函数数: 数}。"""
        return {
            "调用": dict(解释器.覆盖计数),
            "行": dict(解释器.覆盖调用行),
            "已覆盖函数数": len(解释器.覆盖计数),
            "总调用次数": sum(解释器.覆盖计数.values()),
        }

    def _关覆盖() -> Any:
        解释器.覆盖追踪 = False
        return 空

    def _载模块(路径: Any) -> Any:
        """按路径加载 .yao 模块并返回其导出表（用于测试被测文件）。

        路径解析顺序：绝对路径 → 进程工作目录 → 当前脚本所在目录。
        这样 `载模块("examples/测试台/样例/账务.yao")` 与
        `载模块("样例/账务.yao")` 都能工作。
        """
        if not isinstance(路径, str):
            raise 型误("「载模块」需要一个路径（字）")
        from .ast_nodes import 引入, 字节点

        节点 = 引入(路径=字节点(值=路径), 名=None)
        候选们: list[str] = []
        if os.path.isabs(路径):
            候选们.append(路径)
        else:
            候选们.append(os.path.join(解释器.工作目录, 路径))
            当前目录 = os.path.dirname(解释器.当前文件)
            if 当前目录:
                候选们.append(os.path.join(当前目录, 路径))
        for 候选 in 候选们:
            for p in (候选, 候选 + ".yao"):
                if os.path.isfile(p):
                    return 解释器.载入模块(p, 节点)
        raise 引误(f"「载模块」找不到文件「{路径}」")

    加(_造("显", _显))
    # 别名：用户常写成这些
    加(_造("显示", _显))
    加(_造("打印", _显))
    加(_造("输出", _显))
    加(_造("述", _述))
    加(_造("串", _串, 1, 1))
    加(_造("数", _数, 1, 1))
    加(_造("整", _整, 1, 1))
    加(_造("型", _型, 1, 1))
    加(_造("版本", _版本, 0, 0))
    加(_造("滴", _滴, 0, 0))
    加(_造("毫秒", _毫秒, 1, 2))
    加(_造("开覆盖", _开覆盖, 0, 0))
    加(_造("取覆盖", _取覆盖, 0, 0))
    加(_造("关覆盖", _关覆盖, 0, 0))
    加(_造("散列", _散列, 1, 2))
    加(_造("随机字", _随机字, 0, 2))
    加(_造("恒等", _恒等, 2, 2))
    加(_造("载模块", _载模块, 1, 1, 沙箱禁用=True))

    # -- 4.2 集合 ---------------------------------------------------------

    def _长(值: Any) -> int:
        if isinstance(值, (str, list, dict)):
            return len(值)
        raise 型误(f"「{取类型名(值)}」没有长度")

    def _切(值: Any, 起: int, 止: int | None = None) -> Any:
        if not isinstance(值, (str, list)):
            raise 型误(f"「{取类型名(值)}」不支持切")
        return 值[起:止]

    def _取(容器: Any, 键: Any, 默认: Any = None) -> Any:
        # 在「空」上取键：给了默认值就返回默认值。
        # 这让 `取(取(x, "a", 空), "b", 空)` 这类链式安全访问不会崩。
        if 容器 is 空 or 容器 is None or type(容器).__name__ == "_空类":
            if 默认 is not None:
                return 默认
            raise 键误(f"不能从「空」里取「{转字(键)}」")
        if isinstance(容器, dict):
            try:
                if 键 in 容器:
                    return 容器[键]
            except TypeError:
                raise 型误("表的键必须可散列")
            if 默认 is not None:
                return 默认
            raise 键误(f"表里没有键「{转字(键)}」")
        if isinstance(容器, str):
            # 字符串按字符下标访问（写词法分析器必需）
            if isinstance(键, bool) or not isinstance(键, (int, float)):
                raise 型误("字的索引必须是整数")
            n = len(容器)
            i = int(键)
            if i < 0:
                i += n
            if 0 <= i < n:
                return 容器[i]
            if 默认 is not None:
                return 默认
            raise 键误(f"字的索引越界：{键}（长度 {n}）")

        if isinstance(容器, list):
            if isinstance(键, bool) or not isinstance(键, (int, float)):
                raise 型误("列的索引必须是整数")
            # 整数值的浮点也接受（4.0 就当 4）
            if isinstance(键, float):
                if not 键.is_integer():
                    raise 型误(f"列的索引必须是整数，实际是 {键}")
                键 = int(键)
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                if 默认 is not None:
                    return 默认
                raise 值误(f"列索引越界：{键}（长度 {n}）")
            return 容器[i]
        raise 型误(f"「{取类型名(容器)}」不支持「取」")

    def _含(容器: Any, 值: Any) -> bool:
        if isinstance(容器, dict):
            try:
                return 值 in 容器
            except TypeError:
                return False
        if isinstance(容器, str):
            return 转字(值) in 容器
        if isinstance(容器, list):
            return any(相等(项, 值) for 项 in 容器)
        raise 型误(f"「{取类型名(容器)}」不支持「含」")

    def _增(列: Any, 值: Any) -> Any:
        if not isinstance(列, list):
            raise 型误("「增」的第一个参数必须是列")
        列.append(值)
        return 列

    def _删(容器: Any, 键: Any) -> Any:
        if isinstance(容器, dict):
            try:
                if 键 in 容器:
                    del 容器[键]
                    return True
            except TypeError:
                return False
            return False
        if isinstance(容器, list):
            if not isinstance(键, int) or isinstance(键, bool):
                raise 型误("列的索引必须是整数")
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                raise 值误(f"列索引越界：{键}（长度 {n}）")
            return 容器.pop(i)
        raise 型误(f"「{取类型名(容器)}」不支持「删」")

    def _置(容器: Any, 键: Any, 值: Any) -> Any:
        if isinstance(容器, dict):
            try:
                hash(键)
            except TypeError:
                raise 型误("表的键必须可散列")
            容器[键] = 值
            return 容器
        if isinstance(容器, list):
            if not isinstance(键, int) or isinstance(键, bool):
                raise 型误("列的索引必须是整数")
            n = len(容器)
            i = 键 + n if 键 < 0 else 键
            if i < 0 or i >= n:
                raise 值误(f"列索引越界：{键}（长度 {n}）")
            容器[i] = 值
            return 容器
        raise 型误(f"「{取类型名(容器)}」不支持「置」")

    def _键集(表: Any) -> list:
        if not isinstance(表, dict):
            raise 型误("「键集」需要一个表")
        return list(表.keys())

    def _列(值: Any) -> list:
        if isinstance(值, list):
            return list(值)
        if isinstance(值, str):
            return list(值)
        if isinstance(值, dict):
            return list(值.keys())
        raise 型误(f"「{取类型名(值)}」不能转成列")

    def _映(列: Any, 函: Any) -> list:
        if not isinstance(列, list):
            raise 型误("「映」的第一个参数必须是列")
        return [解释器.调匠(函, [项]) if isinstance(函, 匠) else 解释器.调用(函, [项], _假节点()) for 项 in 列]

    def _筛(列: Any, 函: Any) -> list:
        if not isinstance(列, list):
            raise 型误("「筛」的第一个参数必须是列")
        出列 = []
        for 项 in 列:
            结果 = 解释器.调匠(函, [项]) if isinstance(函, 匠) else 解释器.调用(函, [项], _假节点())
            if 真值(结果):
                出列.append(项)
        return 出列

    def _折(列: Any, 函: Any, 初: Any) -> Any:
        if not isinstance(列, list):
            raise 型误("「折」的第一个参数必须是列")
        累 = 初
        for 项 in 列:
            累 = 解释器.调匠(函, [累, 项]) if isinstance(函, 匠) else 解释器.调用(函, [累, 项], _假节点())
        return 累

    def _排(列: Any, 键函: Any = None) -> list:
        if not isinstance(列, list):
            raise 型误("「排」的第一个参数必须是列")
        if 键函 is None:
            return sorted(列, key=_排序键)
        return sorted(
            列,
            key=lambda 项: _排序键(解释器.调匠(键函, [项]) if isinstance(键函, 匠) else 解释器.调用(键函, [项], _假节点())),
        )

    def _排序键(值: Any):
        if isinstance(值, bool):
            return (0, int(值))
        if isinstance(值, (int, float)):
            return (0, 值)
        if isinstance(值, str):
            return (1, 值)
        return (2, 转字(值))

    def _复(值: Any, 次数: int) -> Any:
        if not isinstance(次数, int) or isinstance(次数, bool):
            raise 型误("「复」的次数必须是整数")
        if 次数 < 0:
            raise 值误("「复」的次数不能为负")
        if isinstance(值, (str, list)):
            return 值 * 次数
        raise 型误(f"「{取类型名(值)}」不支持「复」")

    def _并(列: Any, 分隔: str = "") -> str:
        if not isinstance(列, list):
            raise 型误("「并」的第一个参数必须是列")
        if not isinstance(分隔, str):
            raise 型误("「并」的分隔符必须是字")
        return 分隔.join(转字(项) for 项 in 列)

    def _分(字: Any, 分隔: str | None = None) -> list:
        if not isinstance(字, str):
            raise 型误("「分」的第一个参数必须是字")
        if 分隔 is None:
            return 字.split()
        if not isinstance(分隔, str):
            raise 型误("「分」的分隔符必须是字")
        if 分隔 == "":
            return list(字)
        return 字.split(分隔)

    def _替(字: Any, 旧: Any, 新: Any) -> str:
        if not isinstance(字, str):
            raise 型误("「替」的第一个参数必须是字")
        return 字.replace(转字(旧), 转字(新))

    def _裁(字: Any) -> str:
        if not isinstance(字, str):
            raise 型误("「裁」需要一个字")
        return 字.strip()

    加(_造("长", _长, 1, 1))
    加(_造("字码", _字码, 1, 2))
    加(_造("码字", _码字, 1, 1))
    加(_造("切", _切, 2, 3))
    加(_造("取", _取, 2, 3))
    加(_造("含", _含, 2, 2))
    加(_造("增", _增, 2, 2))
    加(_造("删", _删, 2, 2))
    加(_造("置", _置, 3, 3))
    加(_造("键集", _键集, 1, 1))
    加(_造("列", _列, 1, 1))
    加(_造("映", _映, 2, 2))
    加(_造("筛", _筛, 2, 2))
    加(_造("折", _折, 3, 3))
    加(_造("排", _排, 1, 2))
    加(_造("复", _复, 2, 2))
    加(_造("并", _并, 1, 2))
    加(_造("分", _分, 1, 2))
    加(_造("替", _替, 3, 3))
    加(_造("裁", _裁, 1, 1))

    # -- 4.3 数学 / 杂项 --------------------------------------------------

    def _除(甲: Any, 乙: Any) -> int:
        for 值 in (甲, 乙):
            if isinstance(值, bool) or not isinstance(值, (int, float)):
                raise 型误("「除」需要数")
        if 乙 == 0:
            raise 零误("不能除以零")
        return math.floor(甲 / 乙)

    def _绝(值: Any) -> Any:
        if isinstance(值, bool) or not isinstance(值, (int, float)):
            raise 型误("「绝」需要数")
        return abs(值)

    def _极(列: Any, 键函: Any = None) -> Any:
        if not isinstance(列, list):
            raise 型误("「极」的第一个参数必须是列")
        if not 列:
            raise 值误("「极」不能作用于空列")
        if 键函 is None:
            return max(列, key=_排序键)
        return max(列, key=lambda 项: _排序键(解释器.调匠(键函, [项])))

    def _下(列: Any, 键函: Any = None) -> Any:
        if not isinstance(列, list):
            raise 型误("「下」的第一个参数必须是列")
        if not 列:
            raise 值误("「下」不能作用于空列")
        if 键函 is None:
            return min(列, key=_排序键)
        return min(列, key=lambda 项: _排序键(解释器.调匠(键函, [项])))

    def _舍(值: Any, 位: int = 0) -> Any:
        if isinstance(值, bool) or not isinstance(值, (int, float)):
            raise 型误("「舍」需要数")
        if not isinstance(位, int) or isinstance(位, bool):
            raise 型误("「舍」的小数位必须是整数")
        return round(值, 位)

    def _随(下界: int, 上界: int) -> int:
        for 值 in (下界, 上界):
            if not isinstance(值, int) or isinstance(值, bool):
                raise 型误("「随」的边界必须是整数")
        if 下界 > 上界:
            raise 值误("「随」的下界不能大于上界")
        return random.randint(下界, 上界)

    def _今() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _眠(秒: Any) -> Any:
        if isinstance(秒, bool) or not isinstance(秒, (int, float)):
            raise 型误("「眠」需要数")
        if 秒 < 0 or 秒 > 600:
            raise 值误("「眠」的时长需在 0 到 600 秒之间")
        time.sleep(秒)
        return 空

    def _核(条件: Any, 说明: str = "断言失败") -> Any:
        if not 真值(条件):
            raise 核误(说明 if isinstance(说明, str) else 转字(说明))
        return 空

    def _停(码: int = 0) -> Any:
        if not isinstance(码, int) or isinstance(码, bool):
            raise 型误("「停」的退出码必须是整数")
        raise SystemExit(码)

    加(_造("除", _除, 2, 2))
    加(_造("绝", _绝, 1, 1))
    加(_造("极", _极, 1, 2))
    加(_造("下", _下, 1, 2))
    加(_造("舍", _舍, 1, 2))
    加(_造("随", _随, 2, 2))
    加(_造("今", _今, 0, 0))
    加(_造("眠", _眠, 1, 1))
    加(_造("核", _核, 1, 2))
    加(_造("停", _停, 0, 1, 沙箱禁用=True))

    # -- 4.4 序列化 / 文件 / 环境 -----------------------------------------

    def _析(字: Any) -> Any:
        if not isinstance(字, str):
            raise 型误("「析」需要一个字")
        try:
            return 化空(json.loads(字))
        except json.JSONDecodeError as e:
            raise 值误(f"JSON 解析失败：{e}")

    def _构(值: Any, 缩进: int | None = None) -> str:
        try:
            return json.dumps(
                _爻转json(值),
                ensure_ascii=False,
                indent=缩进,
                separators=(",", ":") if 缩进 is None else None,
            )
        except (TypeError, ValueError) as e:
            raise 型误(f"JSON 序列化失败：{e}")

    def _读(路径: Any) -> str:
        if not isinstance(路径, str):
            raise 型误("「读」需要一个路径（字）")
        try:
            with open(路径, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            raise 值误(f"读取失败「{路径}」：{e}")

    def _写(路径: Any, 字: Any) -> Any:
        if not isinstance(路径, str):
            raise 型误("「写」需要一个路径（字）")
        if not isinstance(字, str):
            字 = 转字(字)
        目 = os.path.dirname(路径)
        if 目 and not os.path.isdir(目):
            try:
                os.makedirs(目, exist_ok=True)
            except OSError as e:
                raise 值误(f"无法创建目录「{目}」：{e}")
        try:
            with open(路径, "w", encoding="utf-8", newline="\n") as f:
                f.write(字)
        except OSError as e:
            raise 值误(f"写入失败「{路径}」：{e}")
        return 空

    def _在(路径: Any) -> bool:
        if not isinstance(路径, str):
            raise 型误("「在」需要一个路径（字）")
        return os.path.exists(路径)

    def _参() -> list:
        return list(解释器.参数)

    def _境(名: Any) -> Any:
        if not isinstance(名, str):
            raise 型误("「境」需要一个变量名（字）")
        值 = os.environ.get(名)
        return 空 if 值 is None else 值

    # -- 4.4.1 HTTP 客户端 -------------------------------------------------
    #: 供「网页测试」用：抓取任意站点、发请求、读状态码/头/正文。

    def _规整网址(网址: str) -> str:
        """把网址里的非 ASCII 字符（如中文路径/查询）自动百分号编码。

        HTTP 请求行只能是 ASCII，浏览器与 requests 都会自动编码；
        「抓」/「请求」也照做，用户可以直接写 https://站点/api/健康。
        """
        from urllib.parse import quote, urlsplit, urlunsplit

        try:
            拆 = urlsplit(网址)
        except ValueError:
            return 网址
        if not 拆.scheme:
            return 网址
        路径 = quote(拆.path, safe="/%:@&=+$,;~*'()![]")
        查询 = quote(拆.query, safe="=&%:@+$,;~*'()![]/?")
        片段 = quote(拆.fragment, safe="")
        主机 = 拆.netloc
        try:
            主机.encode("ascii")
        except UnicodeEncodeError:
            主机 = 主机.encode("idna").decode("ascii")
        return urlunsplit((拆.scheme, 主机, 路径, 查询, 片段))

    def _抓(网址: Any, 超时: Any = 10.0) -> dict:
        """抓取一个网址，返回 {码, 头, 文, 字节, 毫秒, 址, 错}。

        永远不抛异常（网络错误也返回表），方便测试系统统一处理。
        """
        import urllib.error
        import urllib.request

        if not isinstance(网址, str) or not 网址.startswith(("http://", "https://")):
            raise 型误("「抓」需要一个 http:// 或 https:// 开头的网址")
        秒 = 10.0
        if 超时 is not None and 超时 is not 空:
            if isinstance(超时, bool) or not isinstance(超时, (int, float)):
                raise 型误("「抓」的超时必须是数（秒）")
            if 超时 <= 0 or 超时 > 120:
                raise 值误("「抓」的超时需在 0 到 120 秒之间")
            秒 = float(超时)

        开始 = time.perf_counter()
        真址 = _规整网址(网址)
        请求 = urllib.request.Request(真址, headers={"User-Agent": "Yao-TestLab/0.1"})
        try:
            with urllib.request.urlopen(请求, timeout=秒) as r:
                原始 = r.read()
                耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
                类型 = (r.headers.get("Content-Type") or "").lower()
                编码 = "utf-8"
                if "charset=" in 类型:
                    编码 = 类型.split("charset=")[-1].split(";")[0].strip() or "utf-8"
                try:
                    正文 = 原始.decode(编码, errors="replace")
                except LookupError:
                    正文 = 原始.decode("utf-8", errors="replace")
                return {
                    "码": r.status,
                    "头": {k.lower(): v for k, v in r.headers.items()},
                    "文": 正文,
                    "字节": len(原始),
                    "毫秒": 耗,
                    "址": 网址,
                    "错": 空,
                }
        except urllib.error.HTTPError as e:
            原始 = e.read() if hasattr(e, "read") else b""
            耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
            return {
                "码": e.code,
                "头": {k.lower(): v for k, v in (e.headers or {}).items()},
                "文": 原始.decode("utf-8", errors="replace"),
                "字节": len(原始),
                "毫秒": 耗,
                "址": 网址,
                "错": 空,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
            原因 = getattr(e, "reason", None) or e
            return {
                "码": 0,
                "头": {},
                "文": "",
                "字节": 0,
                "毫秒": 耗,
                "址": 网址,
                "错": f"{type(原因).__name__}: {原因}",
            }

    def _请求(网址: Any, 选项: Any = None) -> dict:
        """发一个任意方法的 HTTP 请求。

        `选项` 是表，可含：法（默认 GET）、体（字或表；表自动 JSON）、头（表）、超时（数）。
        """
        import urllib.error
        import urllib.request

        if not isinstance(网址, str) or not 网址.startswith(("http://", "https://")):
            raise 型误("「请求」需要一个 http:// 或 https:// 开头的网址")
        选项表: dict = {}
        if 选项 is not None and 选项 is not 空:
            if not isinstance(选项, dict):
                raise 型误("「请求」的第二参必须是表")
            选项表 = 选项

        法 = str(选项表.get("法", "GET")).upper()
        头 = {str(k): str(v) for k, v in (选项表.get("头") or {}).items()}
        头.setdefault("User-Agent", "Yao-TestLab/0.1")
        体值 = 选项表.get("体", 空)
        数据: bytes | None = None
        if 体值 is not 空 and 体值 is not None:
            if isinstance(体值, (dict, list)):
                数据 = json.dumps(_爻转json(体值), ensure_ascii=False).encode("utf-8")
                头.setdefault("Content-Type", "application/json; charset=utf-8")
            else:
                数据 = 转字(体值).encode("utf-8")

        秒 = 10.0
        超 = 选项表.get("超时", 空)
        if 超 is not 空 and 超 is not None:
            if isinstance(超, bool) or not isinstance(超, (int, float)):
                raise 型误("「请求」的超时必须是数")
            秒 = float(超)

        # HTTP 头只能是 ASCII；不合格时给中文错误，而不是让底层编码异常冒出来
        for 键, 值 in 头.items():
            for 段, 叫法 in ((键, "头名"), (值, "值")):
                try:
                    段.encode("latin-1")
                except UnicodeEncodeError:
                    raise 型误(
                        f"请求头{叫法}「{段}」含非 ASCII 字符"
                        "（HTTP 头必须用 ASCII，中文内容请放进请求体）"
                    )
                if "\r" in 段 or "\n" in 段:
                    raise 型误(f"请求头{叫法}「{段}」含换行符")

        开始 = time.perf_counter()
        真址 = _规整网址(网址)
        请求对象 = urllib.request.Request(真址, data=数据, headers=头, method=法)
        try:
            with urllib.request.urlopen(请求对象, timeout=秒) as r:
                原始 = r.read()
                耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
                类型 = (r.headers.get("Content-Type") or "").lower()
                编码 = "utf-8"
                if "charset=" in 类型:
                    编码 = 类型.split("charset=")[-1].split(";")[0].strip() or "utf-8"
                try:
                    正文 = 原始.decode(编码, errors="replace")
                except LookupError:
                    正文 = 原始.decode("utf-8", errors="replace")
                return {
                    "码": r.status,
                    "头": {k.lower(): v for k, v in r.headers.items()},
                    "文": 正文,
                    "字节": len(原始),
                    "毫秒": 耗,
                    "址": 网址,
                    "法": 法,
                    "错": 空,
                }
        except urllib.error.HTTPError as e:
            原始 = e.read() if hasattr(e, "read") else b""
            耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
            return {
                "码": e.code,
                "头": {k.lower(): v for k, v in (e.headers or {}).items()},
                "文": 原始.decode("utf-8", errors="replace"),
                "字节": len(原始),
                "毫秒": 耗,
                "址": 网址,
                "法": 法,
                "错": 空,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            耗 = round((time.perf_counter() - 开始) * 1000.0, 2)
            原因 = getattr(e, "reason", None) or e
            return {
                "码": 0,
                "头": {},
                "文": "",
                "字节": 0,
                "毫秒": 耗,
                "址": 网址,
                "法": 法,
                "错": f"{type(原因).__name__}: {原因}",
            }

    加(_造("析", _析, 1, 1))
    加(_造("构", _构, 1, 2))
    加(_造("读", _读, 1, 1, 沙箱禁用=True))
    加(_造("写", _写, 2, 2, 沙箱禁用=True))
    加(_造("在", _在, 1, 1, 沙箱禁用=True))
    加(_造("参", _参, 0, 0))
    加(_造("境", _境, 1, 1))
    加(_造("抓", _抓, 1, 2, 沙箱禁用=True))
    加(_造("请求", _请求, 1, 2, 沙箱禁用=True))

    # -- 4.5 网页运行时 ---------------------------------------------------

    def 取请求() -> Any:
        return 解释器.全局.表.get("请", 空)

    def _路(法: Any, 径: Any, 处理: Any) -> Any:
        if not isinstance(法, str) or not isinstance(径, str):
            raise 型误("「路」的前两个参数必须是字")
        if not (isinstance(处理, 匠) or isinstance(处理, 原生)):
            raise 型误("「路」的第三个参数必须是函数")
        法 = 法.upper()
        解释器.路由表 = [
            r for r in 解释器.路由表
            if not (r["法"] == 法 and r["径"] == 径)
        ]
        解释器.路由表.append({"法": 法, "径": 径, "处理": 处理})
        return 空

    def _共(目录: Any, 前缀: str = "/公共/") -> Any:
        if not isinstance(目录, str):
            raise 型误("「共」需要一个目录（字）")
        if not isinstance(前缀, str):
            raise 型误("「共」的前缀必须是字")
        if not 前缀.startswith("/"):
            前缀 = "/" + 前缀
        if not 前缀.endswith("/"):
            前缀 = 前缀 + "/"
        解释器.静态目录.append((前缀, 目录))
        return 空

    def _应(码: Any, 头: Any = None, 体: Any = None) -> 应:
        if not isinstance(码, int) or isinstance(码, bool):
            raise 型误("「应」的状态码必须是整数")
        头表: dict[str, str] = {}
        if 头 is not None and 头 is not 空:
            if not isinstance(头, dict):
                raise 型误("「应」的头必须是表")
            for k, v in 头.items():
                头表[str(k)] = 转字(v)
        return 应(码=码, 头=头表, 体=空 if 体 is None else 体)

    def _听(端口: Any = None) -> Any:
        from .web import 启动

        if 端口 is None:
            默认 = os.environ.get("爻_端口")
            端口 = int(默认) if 默认 and 默认.isdigit() else 8788
        if not isinstance(端口, int) or isinstance(端口, bool):
            raise 型误("「听」需要一个端口（整数）")
        return 启动(解释器, 端口)

    加(_造("路", _路, 3, 3, 沙箱禁用=True))
    加(_造("共", _共, 1, 2, 沙箱禁用=True))
    加(_造("应", _应, 1, 3))
    加(_造("听", _听, 0, 1, 沙箱禁用=True))

    # -- 物联：TCP 原语 ------------------------------------------------
    from . import 物联 as _物联

    加(_造("连", _物联.连, 2, 3, 沙箱禁用=True))
    加(_造("发字", _物联.发字, 2, 2, 沙箱禁用=True))
    加(_造("收字", _物联.收字, 2, 3, 沙箱禁用=True))
    加(_造("断连", _物联.断连, 1, 1, 沙箱禁用=True))

    # -- 物联：MQTT ----------------------------------------------------
    from . import mqtt as _mqtt

    加(_造("联", _mqtt.联, 3, 4, 沙箱禁用=True))
    加(_造("订", _mqtt.订, 2, 2, 沙箱禁用=True))
    加(_造("播", _mqtt.播, 3, 4, 沙箱禁用=True))
    加(_造("收讯", _mqtt.收讯, 1, 2, 沙箱禁用=True))
    加(_造("离联", _mqtt.离联, 1, 1, 沙箱禁用=True))

    # -- 物联：Modbus TCP ----------------------------------------------
    from . import modbus as _modbus

    加(_造("读寄", _modbus.读寄, 5, 6, 沙箱禁用=True))
    加(_造("写寄", _modbus.写寄, 5, 6, 沙箱禁用=True))
    加(_造("批量写", _modbus.批量写, 5, 6, 沙箱禁用=True))
    加(_造("探活", _modbus.探活, 2, 4, 沙箱禁用=True))

    # -- 后台采集线程 ---------------------------------------------------
    加(_造("启采", _启采, 1, 2, 沙箱禁用=True))
    加(_造("停采", _停采, 0, 1, 沙箱禁用=True))

    # 全局请求对象占位（Web 运行时每请求替换）
    解释器.全局.定义("请", 请())
    出["请"] = _造("请", lambda: 取请求(), 0, 0)

    return 出


def _假节点():
    from .ast_nodes import 调用节点

    return 调用节点()


def _json转爻(值: Any) -> Any:
    if isinstance(值, list):
        return [_json转爻(v) for v in 值]
    if isinstance(值, dict):
        return {k: _json转爻(v) for k, v in 值.items()}
    return 值


def _爻转json(值: Any, 见=None) -> Any:
    from .values import 匠 as 匠类, 原生 as 原生类, 应 as 应类, 请 as 请类, 空 as 空值

    if 值 is 空值 or isinstance(值, 空值.__class__):
        return None
    if isinstance(值, bool):
        return 值
    if isinstance(值, (int, float, str)):
        return 值
    if isinstance(值, list):
        return [_爻转json(v) for v in 值]
    if isinstance(值, dict):
        return {str(k): _爻转json(v) for k, v in 值.items()}
    if isinstance(值, 应类):
        return _爻转json(值.体)
    if isinstance(值, 请类):
        return {"法": 值.法, "径": 值.径, "参": 值.参}
    raise 型误(f"「{取类型名(值)}」不能序列化为 JSON")
