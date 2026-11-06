"""爻语物联网接入层 —— TCP 连接管理。

爻语本体没有 socket 能力，这里提供最小可用的 TCP 原语，
让 MQTT / Modbus TCP 这类真实工业协议能在爻语里实现。

设计：
* 连接用整数句柄表示（1, 2, 3…），爻语里当作「数」传递
* 字节用「数」的列表示（0-255），因为爻语没有原生 bytes 类型
* 所有操作返回表而不是抛异常 —— 网络错误在工业场景是常态，
  让调用方自己判断「错」字段，避免一次超时就把整个服务打挂
* 全局锁保护连接表，因为爻语 HTTP 服务器是多线程的
"""

from __future__ import annotations

import socket
import threading
from typing import Any

from .errors import 型误, 值误

#: 连接句柄 → socket 对象
_连接表: dict[int, socket.socket] = {}
#: 分配句柄用的计数器
_下一个句柄 = [1]
#: 保护 _连接表 的锁
_锁 = threading.RLock()


def _取连接(句柄: Any) -> socket.socket:
    """按句柄取 socket，取不到抛中文错误。"""
    if not isinstance(句柄, int) or isinstance(句柄, bool):
        raise 型误("连接句柄必须是整数")
    with _锁:
        套 = _连接表.get(句柄)
    if 套 is None:
        raise 值误(f"没有这个连接（句柄 {句柄}）")
    return 套


def _转字节列(值: Any) -> bytes:
    """把爻语的「数的列」或「字」转成 bytes。"""
    if isinstance(值, str):
        return 值.encode("utf-8")
    if isinstance(值, (bytes, bytearray)):
        return bytes(值)
    if isinstance(值, list):
        出 = bytearray()
        for 项 in 值:
            if not isinstance(项, (int, float)) or isinstance(项, bool):
                raise 型误("字节列里的每一项都必须是 0-255 的数")
            n = int(项)
            if n < 0 or n > 255:
                raise 值误(f"字节值必须在 0-255 之间，实际是 {n}")
            出.append(n)
        return bytes(出)
    raise 型误("「发字」需要一个字节列（数的列）或字")


def _转数列(数据: bytes) -> list[int]:
    return list(数据)


# ---------------------------------------------------------------------------
# 内置函数实现
# ---------------------------------------------------------------------------


def 连(主机: Any, 端口: Any, 超时: Any = 5) -> dict:
    """连(主机, 端口, 超时?) → { 号, 错 }

    建立 TCP 连接。失败时「号」为 0，「错」里是中文说明。
    """
    if not isinstance(主机, str):
        raise 型误("「连」的主机必须是字")
    if not isinstance(端口, int) or isinstance(端口, bool):
        raise 型误("「连」的端口必须是整数")
    超时秒 = float(超时) if isinstance(超时, (int, float)) else 5.0

    try:
        套 = socket.create_connection((主机, 端口), timeout=超时秒)
        套.settimeout(超时秒)
    except OSError as e:
        return {"号": 0, "错": f"连不上 {主机}:{端口} —— {e}"}

    with _锁:
        句柄 = _下一个句柄[0]
        _下一个句柄[0] += 1
        _连接表[句柄] = 套
    return {"号": 句柄, "错": ""}


def 发字(句柄: Any, 数据: Any) -> dict:
    """发字(连接, 字节列|字) → { 成, 错 }"""
    套 = _取连接(句柄)
    原 = _转字节列(数据)
    try:
        套.sendall(原)
        return {"成": True, "错": ""}
    except OSError as e:
        return {"成": False, "错": f"发送失败：{e}"}


def 收字(句柄: Any, 期望长: Any = 1, 超时: Any = None) -> dict:
    """收字(连接, 期望长, 超时?) → { 字节, 长, 超时, 错 }

    读满期望长度或超时为止。超时时「字节」里是已收到的部分。
    """
    套 = _取连接(句柄)
    if not isinstance(期望长, int) or isinstance(期望长, bool) or 期望长 < 0:
        raise 型误("「收字」的长度必须是正整数")
    if 期望长 > 1_000_000:
        raise 值误("「收字」一次最多读 1000000 字节")

    原超时 = 套.gettimeout()
    if 超时 is not None and isinstance(超时, (int, float)):
        套.settimeout(float(超时))

    缓冲 = bytearray()
    超了 = False
    try:
        while len(缓冲) < 期望长:
            try:
                块 = 套.recv(min(4096, 期望长 - len(缓冲)))
            except socket.timeout:
                超了 = True
                break
            if not 块:
                break
            缓冲.extend(块)
    except OSError as e:
        return {"字节": _转数列(缓冲), "长": len(缓冲), "超时": 超了,
                "错": f"接收失败：{e}"}
    finally:
        if 超时 is not None and isinstance(超时, (int, float)):
            try:
                套.settimeout(原超时)
            except OSError:
                pass

    错 = ""
    if 超了 and len(缓冲) < 期望长:
        错 = f"超时：只收到 {len(缓冲)}/{期望长} 字节"
    return {"字节": _转数列(缓冲), "长": len(缓冲), "超时": 超了, "错": 错}


def 断连(句柄: Any) -> Any:
    """断连(连接) → 空"""
    if not isinstance(句柄, int) or isinstance(句柄, bool):
        raise 型误("连接句柄必须是整数")
    with _锁:
        套 = _连接表.pop(句柄, None)
    if 套 is not None:
        try:
            套.close()
        except OSError:
            pass
    return None


def 可用(句柄: Any) -> bool:
    """给内部用：句柄是否还有效。"""
    if not isinstance(句柄, int):
        return False
    with _锁:
        return 句柄 in _连接表


def 关闭全部() -> None:
    """进程退出前关闭所有连接。"""
    with _锁:
        句柄们 = list(_连接表.keys())
    for 句柄 in 句柄们:
        try:
            断连(句柄)
        except Exception:
            pass


def 活动连接数() -> int:
    with _锁:
        return len(_连接表)
