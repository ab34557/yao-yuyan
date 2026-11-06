"""爻语 MQTT 3.1.1 客户端（自实现，零第三方依赖）。

实现的报文：
  CONNECT / CONNACK
  PUBLISH（QoS 0 与 QoS 1）
  PUBACK
  SUBSCRIBE / SUBACK
  PINGREQ / PINGRESP
  DISCONNECT

不实现：TLS、QoS 2、遗嘱消息、保留消息的服务端处理。

协议要点（容易踩坑的地方，都在这里注释清楚）：
* 每个报文头 = 固定头(1 字节类型+标志) + 剩余长度(变长编码) + 可变头 + 载荷
* 剩余长度变长编码：每字节低 7 位是数据，最高位表示「后面还有」
* 字符串是「2 字节大端长度 + UTF-8 字节」
* CONNECT 的协议名是 "MQTT"（MQTT 3.1.1，level 4），不是 "MQIsdp"（3.1）
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from .errors import 型误, 值误

# 报文类型
_CONNECT = 1
_CONNACK = 2
_PUBLISH = 3
_PUBACK = 4
_SUBSCRIBE = 8
_SUBACK = 9
_PINGREQ = 12
_PINGRESP = 13
_DISCONNECT = 14


# ---------------------------------------------------------------------------
# 编解码
# ---------------------------------------------------------------------------


def _编剩余长度(n: int) -> bytes:
    """剩余长度变长编码。最多 4 字节，最大 268435455。"""
    出 = bytearray()
    while True:
        字节 = n % 128
        n //= 128
        if n > 0:
            字节 |= 0x80
        出.append(字节)
        if n == 0:
            break
    return bytes(出)


def _编字串(s: str) -> bytes:
    """MQTT 字符串：2 字节大端长度 + UTF-8 内容。"""
    原 = s.encode("utf-8")
    if len(原) > 65535:
        raise 值误("MQTT 字符串长度不能超过 65535 字节")
    return len(原).to_bytes(2, "big") + 原


def _拼报文(首字节: int, 可变头: bytes, 载荷: bytes = b"") -> bytes:
    内容 = 可变头 + 载荷
    return bytes([首字节]) + _编剩余长度(len(内容)) + 内容


def _收精确(套: socket.socket, n: int) -> bytes:
    """读满 n 字节，读不满返回已读部分。"""
    缓冲 = bytearray()
    while len(缓冲) < n:
        块 = 套.recv(n - len(缓冲))
        if not 块:
            break
        缓冲.extend(块)
    return bytes(缓冲)


#: 「读超时」与「连接断开」要区分开（sentinel 对象）
读超时 = object()


def _收报文(套: socket.socket) -> tuple[int, bytes] | None | object:
    """读一个完整报文，返回 (首字节, 剩余内容)。

    * 连接断开 → None
    * 读超时   → 读超时（sentinel）
    """
    try:
        头 = _收精确(套, 1)
    except socket.timeout:
        return 读超时
    if not 头:
        return None
    首位 = 头[0]

    # 剩余长度
    倍数 = 1
    剩余 = 0
    for _ in range(4):
        try:
            字节们 = _收精确(套, 1)
        except socket.timeout:
            return 读超时
        if not 字节们:
            return None
        字节 = 字节们[0]
        剩余 += (字节 & 0x7F) * 倍数
        倍数 *= 128
        if (字节 & 0x80) == 0:
            break

    try:
        内容 = _收精确(套, 剩余) if 剩余 > 0 else b""
    except socket.timeout:
        return 读超时
    if len(内容) < 剩余:
        return None
    return 首位, 内容


def _读字串(数据: bytes, 位: int) -> tuple[str, int]:
    """从数据里读一个 MQTT 字符串，返回 (字, 新位置)。"""
    if 位 + 2 > len(数据):
        return "", 位
    长度 = int.from_bytes(数据[位:位 + 2], "big")
    位 += 2
    if 位 + 长度 > len(数据):
        return "", len(数据)
    内容 = 数据[位:位 + 长度].decode("utf-8", errors="replace")
    return 内容, 位 + 长度


def _转字节(值: Any) -> bytes:
    if isinstance(值, str):
        return 值.encode("utf-8")
    if isinstance(值, (bytes, bytearray)):
        return bytes(值)
    if isinstance(值, list):
        出 = bytearray()
        for 项 in 值:
            if not isinstance(项, (int, float)) or isinstance(项, bool):
                raise 型误("消息内容里的每一项都必须是 0-255 的数")
            n = int(项)
            if n < 0 or n > 255:
                raise 值误(f"字节值必须在 0-255 之间，实际是 {n}")
            出.append(n)
        return bytes(出)
    raise 型误("消息内容必须是字或字节列")


def _转数(数据: bytes) -> list[int]:
    return list(数据)


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class 联接:
    """一条 MQTT 连接。"""

    def __init__(self, 套: socket.socket, 客户名: str) -> None:
        self.套 = 套
        self.客户名 = 客户名
        self.已收 = bytearray()      # 收讯时缓冲的载荷
        #: (主题, 内容bytes) 队列
        self.队列: list[tuple[str, bytes]] = []
        self.锁 = threading.RLock()
        self.下次包号 = 1
        self.存活 = True

    def 取包号(self) -> int:
        with self.锁:
            n = self.下次包号
            self.下次包号 = (self.下次包号 % 65535) + 1
            return n

    def 发(self, 数据: bytes) -> None:
        self.套.sendall(数据)

    def 收一个(self, 超时: float | None) -> tuple[str, bytes] | None:
        """读一个报文；如果是 PUBLISH 返回 (主题, 载荷)，其它类型吞掉继续读。"""
        原超时 = self.套.gettimeout()
        if 超时 is not None:
            self.套.settimeout(超时)
        截止 = time.monotonic() + 超时 if 超时 else None
        try:
            while True:
                if 截止 is not None:
                    剩 = 截止 - time.monotonic()
                    if 剩 <= 0:
                        return None
                    self.套.settimeout(剩)
                报文 = _收报文(self.套)
                if 报文 is 读超时:
                    return 读超时
                if 报文 is None:
                    self.存活 = False
                    return None
                首位, 内容 = 报文
                类型 = 首位 >> 4

                if 类型 == _PUBLISH:
                    qos = (首位 >> 1) & 0x03
                    主题, 位 = _读字串(内容, 0)
                    if qos > 0:
                        包号 = int.from_bytes(内容[位:位 + 2], "big")
                        位 += 2
                        # QoS 1 要回 PUBACK
                        self.发(bytes([_PUBACK << 4, 2]) + 包号.to_bytes(2, "big"))
                    载荷 = 内容[位:]
                    return 主题, 载荷

                if 类型 == _PINGRESP:
                    continue
                if 类型 == _PUBACK:
                    continue
                if 类型 == _CONNACK:
                    if len(内容) >= 2 and 内容[1] != 0:
                        self.存活 = False
                        return None
                    continue
                if 类型 == _SUBACK:
                    continue
                # 其它报文忽略
        finally:
            try:
                self.套.settimeout(原超时)
            except OSError:
                pass

    def 关闭(self) -> None:
        with self.锁:
            if not self.存活:
                return
            self.存活 = False
        try:
            self.发(bytes([_DISCONNECT << 4, 0]))
        except OSError:
            pass
        try:
            self.套.close()
        except OSError:
            pass


#: 句柄 → 联接
_连接表: dict[int, 联接] = {}
_下一个句柄 = [1]
_锁 = threading.RLock()


def _取(句柄: Any) -> 联接:
    if not isinstance(句柄, int) or isinstance(句柄, bool):
        raise 型误("连接句柄必须是整数")
    with _锁:
        联 = _连接表.get(句柄)
    if 联 is None:
        raise 值误(f"没有这个 MQTT 连接（句柄 {句柄}）")
    return 联


# ---------------------------------------------------------------------------
# 内置函数实现
# ---------------------------------------------------------------------------


def 联(主机: Any, 端口: Any, 客户名: Any, 超时: Any = 5) -> dict:
    """联(主机, 端口, 客户名, 超时?) → { 号, 错 }

    建立 MQTT 连接并完成 CONNECT/CONNACK 握手。
    """
    if not isinstance(主机, str):
        raise 型误("「联」的主机必须是字")
    if not isinstance(端口, int) or isinstance(端口, bool):
        raise 型误("「联」的端口必须是整数")
    if not isinstance(客户名, str):
        raise 型误("「联」的客户名必须是字")
    超时秒 = float(超时) if isinstance(超时, (int, float)) else 5.0

    try:
        套 = socket.create_connection((主机, 端口), timeout=超时秒)
        套.settimeout(超时秒)
    except OSError as e:
        return {"号": 0, "错": f"连不上 MQTT 服务器 {主机}:{端口} —— {e}"}

    # CONNECT 报文
    可变头 = (
        _编字串("MQTT")          # 协议名（3.1.1 是 "MQTT"，3.1 才是 "MQIsdp"）
        + bytes([4])              # 协议级别 4
        + bytes([0x02])           # 连接标志：clean session
        + (30).to_bytes(2, "big") # keepalive 30 秒
    )
    载荷 = _编字串(客户名)
    try:
        套.sendall(_拼报文(_CONNECT << 4, 可变头, 载荷))
        报文 = _收报文(套)
    except OSError as e:
        try:
            套.close()
        except OSError:
            pass
        return {"号": 0, "错": f"MQTT 握手失败：{e}"}

    if 报文 is 读超时 or 报文 is None:
        try:
            套.close()
        except OSError:
            pass
        return {"号": 0, "错": "MQTT 握手失败：服务器无响应或断开"}

    首位, 内容 = 报文
    类型 = 首位 >> 4
    if 类型 != _CONNACK:
        try:
            套.close()
        except OSError:
            pass
        return {"号": 0, "错": f"MQTT 握手失败：期望 CONNACK，收到类型 {类型}"}
    if len(内容) < 2:
        try:
            套.close()
        except OSError:
            pass
        return {"号": 0, "错": "MQTT 握手失败：CONNACK 太短"}
    返回码 = 内容[1]
    if 返回码 != 0:
        说明 = {
            1: "协议版本不被接受",
            2: "客户标识被拒绝",
            3: "服务器不可用",
            4: "用户名或密码错误",
            5: "未授权",
        }.get(返回码, f"未知错误码 {返回码}")
        try:
            套.close()
        except OSError:
            pass
        return {"号": 0, "错": f"MQTT 连接被拒绝：{说明}"}

    联 = 联接(套, 客户名)
    with _锁:
        句柄 = _下一个句柄[0]
        _下一个句柄[0] += 1
        _连接表[句柄] = 联
    return {"号": 句柄, "错": ""}


def 订(句柄: Any, 主题: Any) -> dict:
    """订(连接, 主题) → { 成, 错 }"""
    联 = _取(句柄)
    if not isinstance(主题, str):
        raise 型误("「订」的主题必须是字")
    包号 = 联.取包号()
    可变头 = 包号.to_bytes(2, "big")
    载荷 = _编字串(主题) + bytes([1])   # QoS 1
    try:
        联.发(_拼报文((_SUBSCRIBE << 4) | 0x02, 可变头, 载荷))
    except OSError as e:
        return {"成": False, "错": f"订阅失败：{e}"}

    # 等 SUBACK
    try:
        联.套.settimeout(5.0)
        for _ in range(8):
            报文 = _收报文(联.套)
            if 报文 is 读超时:
                continue
            if 报文 is None:
                return {"成": False, "错": "订阅失败：连接断开"}
            首位, _内容 = 报文
            if (首位 >> 4) == _SUBACK:
                return {"成": True, "错": ""}
    except OSError as e:
        return {"成": False, "错": f"订阅失败：{e}"}
    return {"成": False, "错": "订阅失败：没收到 SUBACK"}


def 播(句柄: Any, 主题: Any, 内容: Any, 保留: Any = False) -> dict:
    """播(连接, 主题, 内容, 保留?) → { 成, 错 }"""
    联 = _取(句柄)
    if not isinstance(主题, str):
        raise 型误("「播」的主题必须是字")
    原 = _转字节(内容)
    首 = _PUBLISH << 4
    if 保留:
        首 |= 0x01
    try:
        联.发(_拼报文(首, _编字串(主题), 原))
        return {"成": True, "错": ""}
    except OSError as e:
        return {"成": False, "错": f"发布失败：{e}"}


def 收讯(句柄: Any, 超时: Any = 2) -> dict:
    """收讯(连接, 超时?) → { 主题, 内容, 字节, 超时, 错 }

    「内容」是字（按 UTF-8 解码）；「字节」是原始字节列。
    超时时「错」非空但不算异常，调用方据此决定是否继续循环。
    """
    联 = _取(句柄)
    超时秒 = float(超时) if isinstance(超时, (int, float)) else 2.0
    try:
        结果 = 联.收一个(超时秒)
    except OSError as e:
        return {"主题": "", "内容": "", "字节": [], "超时": False,
                "错": f"接收失败：{e}"}

    if 结果 is 读超时:
        return {"主题": "", "内容": "", "字节": [], "超时": True, "错": ""}

    if 结果 is None:
        if not 联.存活:
            return {"主题": "", "内容": "", "字节": [], "超时": False,
                    "错": "连接已断开"}
        return {"主题": "", "内容": "", "字节": [], "超时": True, "错": ""}

    主题, 载荷 = 结果
    return {
        "主题": 主题,
        "内容": 载荷.decode("utf-8", errors="replace"),
        "字节": _转数(载荷),
        "超时": False,
        "错": "",
    }


def 离联(句柄: Any) -> Any:
    """离联(连接) → 空"""
    if not isinstance(句柄, int) or isinstance(句柄, bool):
        raise 型误("连接句柄必须是整数")
    with _锁:
        联 = _连接表.pop(句柄, None)
    if 联 is not None:
        联.关闭()
    return None


def 关闭全部() -> None:
    with _锁:
        句柄们 = list(_连接表.keys())
    for 句柄 in 句柄们:
        try:
            离联(句柄)
        except Exception:
            pass


def 活动连接数() -> int:
    with _锁:
        return len(_连接表)
