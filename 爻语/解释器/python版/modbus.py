"""爻语 Modbus TCP 客户端（自实现，零第三方依赖）。

Modbus TCP 报文（MBAP 头 + PDU）：
  MBAP(7 字节) = 事务号(2) + 协议号(2, 固定0) + 长度(2) + 单元号(1)
  PDU         = 功能码(1) + 数据

实现的功能码：
  0x03  读保持寄存器 (Read Holding Registers)
  0x04  读输入寄存器   (Read Input Registers)
  0x06  写单个寄存器   (Write Single Register)
  0x10  写多个寄存器   (Write Multiple Registers)

寄存器是 16 位无符号整数（0-65535）。爻语里用「数」表示。
Modbus 不支持负数——要传负数用二进制补码（Python 侧调用方自己处理）。
"""

from __future__ import annotations

import socket
import threading
from typing import Any

from .errors import 型误, 值误

_读保持 = 0x03
_读输入 = 0x04
_写单个 = 0x06
_写多个 = 0x10

_默认端口 = 502


def _拼(mbap: bytes, pdu: bytes) -> bytes:
    return mbap + pdu


def _收精确(套: socket.socket, n: int) -> bytes:
    缓冲 = bytearray()
    while len(缓冲) < n:
        块 = 套.recv(n - len(缓冲))
        if not 块:
            break
        缓冲.extend(块)
    return bytes(缓冲)


def _检查寄存器值(值: Any) -> int:
    if not isinstance(值, (int, float)) or isinstance(值, bool):
        raise 型误("寄存器值必须是整数")
    n = int(值)
    if n < 0 or n > 65535:
        raise 值误(f"寄存器值必须在 0-65535 之间，实际是 {n}")
    return n


class 从站:
    """一条 Modbus TCP 连接（长连接复用）。"""

    def __init__(self, 套: socket.socket) -> None:
        self.套 = 套
        self.事务号 = 0

    def 下一事务号(self) -> int:
        self.事务号 = (self.事务号 + 1) & 0xFFFF
        return self.事务号


_连接表: dict[int, 从站] = {}
_下一个句柄 = [1]
_锁 = threading.RLock()


def _取(句柄: Any) -> 从站:
    if not isinstance(句柄, int) or isinstance(句柄, bool):
        raise 型误("连接句柄必须是整数")
    with _锁:
        连 = _连接表.get(句柄)
    if 连 is None:
        raise 值误(f"没有这个 Modbus 连接（句柄 {句柄}）")
    return 连


# ---------------------------------------------------------------------------
# 内置函数实现（一次性短连接，简单可靠）
# ---------------------------------------------------------------------------


def _一次事务(
    主机: str, 端口: int, 单元: int, pdu: bytes, 超时: float
) -> tuple[bytes | None, str]:
    """建立连接、发一个 PDU、读回响应 PDU。返回 (响应PDU, 错误说明)。"""
    try:
        套 = socket.create_connection((主机, 端口), timeout=超时)
        套.settimeout(超时)
    except OSError as e:
        return None, f"连不上 {主机}:{端口} —— {e}"

    try:
        事务号 = 1
        mbap = (
            事务号.to_bytes(2, "big")
            + (0).to_bytes(2, "big")            # 协议号固定 0
            + (len(pdu) + 1).to_bytes(2, "big") # 长度 = 单元号 + PDU
            + bytes([单元 & 0xFF])
        )
        套.sendall(mbap + pdu)

        头 = _收精确(套, 7)
        if len(头) < 7:
            return None, "响应太短（读 MBAP 头失败）"
        长度 = int.from_bytes(头[4:6], "big")
        if 长度 < 2 or 长度 > 260:
            return None, f"响应长度异常：{长度}"
        体 = _收精确(套, 长度 - 1)
        if len(体) < 长度 - 1:
            return None, "响应体不完整"
        return 体, ""
    except OSError as e:
        return None, f"通信失败：{e}"
    finally:
        try:
            套.close()
        except OSError:
            pass


def _解错误(响应: bytes) -> str:
    """如果是异常响应（功能码最高位为 1），翻译异常码。"""
    if not 响应:
        return ""
    功能码 = 响应[0]
    if not (功能码 & 0x80):
        return ""
    码 = 响应[1] if len(响应) > 1 else 0
    说明 = {
        1: "非法功能码",
        2: "非法数据地址",
        3: "非法数据值",
        4: "从站设备故障",
        5: "确认（处理中）",
        6: "从站忙",
        8: "存储奇偶校验错",
        10: "网关路径不可用",
        11: "网关目标设备无响应",
    }.get(码, f"未知异常码 {码}")
    return f"Modbus 异常：{说明}"


def 读寄(
    主机: Any, 端口: Any, 单元: Any, 起址: Any, 个数: Any, 超时: Any = 3
) -> dict:
    """读寄(主机, 端口, 单元号, 起始地址, 个数, 超时?) → { 值们, 错 }"""
    if not isinstance(主机, str):
        raise 型误("「读寄」的主机必须是字")
    for 名, 值 in (("端口", 端口), ("单元号", 单元), ("起始地址", 起址), ("个数", 个数)):
        if not isinstance(值, int) or isinstance(值, bool):
            raise 型误(f"「读寄」的{名}必须是整数")
    if 个数 < 1 or 个数 > 125:
        raise 值误("「读寄」的个数必须在 1-125 之间")

    超时秒 = float(超时) if isinstance(超时, (int, float)) else 3.0
    pdu = bytes([_读保持]) + 起址.to_bytes(2, "big") + 个数.to_bytes(2, "big")
    响应, 错 = _一次事务(主机, 端口, 单元, pdu, 超时秒)
    if 响应 is None:
        return {"值们": [], "错": 错}

    异常 = _解错误(响应)
    if 异常:
        return {"值们": [], "错": 异常}
    if not 响应 or 响应[0] != _读保持:
        return {"值们": [], "错": f"功能码不匹配：{响应[0] if 响应 else '?'}"}
    if len(响应) < 2:
        return {"值们": [], "错": "响应太短"}
    字节数 = 响应[1]
    数据 = 响应[2:2 + 字节数]
    if len(数据) < 字节数:
        return {"值们": [], "错": "寄存器数据不完整"}
    值们 = [
        int.from_bytes(数据[i:i + 2], "big")
        for i in range(0, 字节数, 2)
    ]
    return {"值们": 值们, "错": ""}


def 写寄(
    主机: Any, 端口: Any, 单元: Any, 地址: Any, 值: Any, 超时: Any = 3
) -> dict:
    """写寄(主机, 端口, 单元号, 地址, 值, 超时?) → { 成, 错 }"""
    if not isinstance(主机, str):
        raise 型误("「写寄」的主机必须是字")
    for 名, 址 in (("端口", 端口), ("单元号", 单元), ("地址", 地址)):
        if not isinstance(址, int) or isinstance(址, bool):
            raise 型误(f"「写寄」的{名}必须是整数")
    寄存器值 = _检查寄存器值(值)

    超时秒 = float(超时) if isinstance(超时, (int, float)) else 3.0
    pdu = bytes([_写单个]) + 地址.to_bytes(2, "big") + 寄存器值.to_bytes(2, "big")
    响应, 错 = _一次事务(主机, 端口, 单元, pdu, 超时秒)
    if 响应 is None:
        return {"成": False, "错": 错}

    异常 = _解错误(响应)
    if 异常:
        return {"成": False, "错": 异常}
    if not 响应 or 响应[0] != _写单个:
        return {"成": False, "错": "功能码不匹配"}
    return {"成": True, "错": ""}


def 批量写(
    主机: Any, 端口: Any, 单元: Any, 起址: Any, 值们: Any, 超时: Any = 3
) -> dict:
    """批量写(主机, 端口, 单元号, 起始地址, 值的列, 超时?) → { 成, 错 }"""
    if not isinstance(主机, str):
        raise 型误("「批量写」的主机必须是字")
    for 名, 址 in (("端口", 端口), ("单元号", 单元), ("起始地址", 起址)):
        if not isinstance(址, int) or isinstance(址, bool):
            raise 型误(f"「批量写」的{名}必须是整数")
    if not isinstance(值们, list) or not 值们:
        raise 型误("「批量写」的值必须是非空的列")
    if len(值们) > 123:
        raise 值误("「批量写」一次最多写 123 个寄存器")

    原 = bytearray()
    for 值 in 值们:
        寄存器值 = _检查寄存器值(值)
        原.extend(寄存器值.to_bytes(2, "big"))

    超时秒 = float(超时) if isinstance(超时, (int, float)) else 3.0
    pdu = (
        bytes([_写多个])
        + 起址.to_bytes(2, "big")
        + len(值们).to_bytes(2, "big")
        + bytes([len(原)])
        + bytes(原)
    )
    响应, 错 = _一次事务(主机, 端口, 单元, pdu, 超时秒)
    if 响应 is None:
        return {"成": False, "错": 错}

    异常 = _解错误(响应)
    if 异常:
        return {"成": False, "错": 异常}
    if not 响应 or 响应[0] != _写多个:
        return {"成": False, "错": "功能码不匹配"}
    return {"成": True, "错": ""}


def 探活(主机: Any, 端口: Any, 单元: Any = 1, 超时: Any = 1) -> dict:
    """探活(主机, 端口, 单元?, 超时?) → { 在线, 错 }"""
    try:
        结果 = 读寄(主机, 端口, 单元, 0, 1, 超时)
    except Exception as e:  # 参数错误也当离线
        return {"在线": False, "错": str(e)}
    在线 = 结果.get("错") == ""
    return {"在线": 在线, "错": 结果.get("错", "")}
