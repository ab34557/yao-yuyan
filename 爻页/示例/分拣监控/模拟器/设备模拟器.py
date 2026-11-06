"""智能物料分拣线 —— 外置设备模拟器（独立进程）。

这是一个**完全独立**的程序，模拟一条真实分拣线上的 6 台设备。
上位机通过标准物联网协议（MQTT / Modbus TCP）与它通信，
就像对接真实 PLC 一样 —— 上位机不知道它是模拟器。

启动：
    python 设备模拟器.py                  # 默认：MQTT broker 1883 + Modbus 15020
    python 设备模拟器.py --mqtt 1884      # 改端口
    python 设备模拟器.py --no-modbus      # 只开 MQTT

模拟的物理过程：
    进料传送带 → 视觉识别 → 称重 → 分拣气缸1（大件）/ 气缸2（小件）→ 出料传送带

每 500ms 推进一次仿真，产生真实感的遥测数据：
    · 物料以泊松流到达
    · 传送带按设定速度运行，速度影响到达率
    · 视觉识别有 3% 误判率
    · 称重有 ±5g 噪声
    · 气缸动作耗时随负载波动
    · 偶尔产生堵料（物料堆积）
"""

from __future__ import annotations

import argparse
import json
import math
import random
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# MQTT 迷你 broker（内嵌，让整条链路可以独立运行）
# ---------------------------------------------------------------------------

MQTT_CONNECT = 1
MQTT_CONNACK = 2
MQTT_PUBLISH = 3
MQTT_PUBACK = 4
MQTT_SUBSCRIBE = 8
MQTT_SUBACK = 9
MQTT_PINGREQ = 12
MQTT_PINGRESP = 13
MQTT_DISCONNECT = 14


def _编长(n: int) -> bytes:
    出 = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        出.append(b)
        if n == 0:
            break
    return bytes(出)


def _读满(套: socket.socket, n: int) -> bytes:
    缓 = bytearray()
    while len(缓) < n:
        块 = 套.recv(n - len(缓))
        if not 块:
            break
        缓.extend(块)
    return bytes(缓)


def _读字串(数据: bytes, 位: int) -> tuple[str, int]:
    长 = int.from_bytes(数据[位:位 + 2], "big")
    位 += 2
    return 数据[位:位 + 长].decode("utf-8", errors="replace"), 位 + 长


def _匹配主题(订阅: str, 主题: str) -> bool:
    """MQTT 通配符：+ 匹配一级，# 匹配剩余全部。"""
    if 订阅 == 主题:
        return True
    订段 = 订阅.split("/")
    主段 = 主题.split("/")
    i = 0
    while i < len(订段):
        if 订段[i] == "#":
            return True
        if i >= len(主段):
            return False
        if 订段[i] != "+" and 订段[i] != 主段[i]:
            return False
        i += 1
    return i == len(主段)


class 迷你broker:
    """一个够用的 MQTT 3.1.1 broker。支持 CONNECT/SUBSCRIBE/PUBLISH/PING。"""

    def __init__(self, 端口: int = 1883) -> None:
        self.端口 = 端口
        self.套 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.套.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.套.bind(("0.0.0.0", 端口))
        self.套.listen(16)
        self.停 = threading.Event()
        self.客户们: list[dict] = []
        self.锁 = threading.RLock()
        self.消息数 = [0]

    def 启动(self) -> None:
        threading.Thread(target=self._接受, daemon=True).start()

    def _接受(self) -> None:
        self.套.settimeout(0.5)
        while not self.停.is_set():
            try:
                连, 址 = self.套.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            客户 = {"套": 连, "址": 址, "订阅": set(), "客户名": ""}
            with self.锁:
                self.客户们.append(客户)
            threading.Thread(target=self._服务, args=(客户,), daemon=True).start()

    def _服务(self, 客户: dict) -> None:
        连: socket.socket = 客户["套"]
        连.settimeout(60.0)
        try:
            while not self.停.is_set():
                头 = _读满(连, 1)
                if not 头:
                    break
                类型 = 头[0] >> 4

                剩余 = 0
                倍数 = 1
                for _ in range(4):
                    b = _读满(连, 1)
                    if not b:
                        return
                    剩余 += (b[0] & 0x7F) * 倍数
                    倍数 *= 128
                    if not (b[0] & 0x80):
                        break
                内容 = _读满(连, 剩余) if 剩余 else b""

                if 类型 == MQTT_CONNECT:
                    协议名, 位 = _读字串(内容, 0)
                    位 += 1                      # 协议级别
                    标志 = 内容[位]
                    位 += 1
                    位 += 2                      # keepalive
                    客户名, _ = _读字串(内容, 位)
                    客户["客户名"] = 客户名
                    连.sendall(bytes([MQTT_CONNACK << 4, 2, 0, 0]))
                elif 类型 == MQTT_SUBSCRIBE:
                    包号 = 内容[:2]
                    位 = 2
                    主题们 = []
                    while 位 < len(内容):
                        主题, 位 = _读字串(内容, 位)
                        位 += 1                  # QoS
                        主题们.append(主题)
                        客户["订阅"].add(主题)
                    QoSn = bytes([1] * len(主题们))
                    连.sendall(
                        bytes([MQTT_SUBACK << 4, 2 + len(QoSn)])
                        + 包号 + QoSn
                    )
                elif 类型 == MQTT_PUBLISH:
                    qos = (头[0] >> 1) & 0x03
                    主题, 位 = _读字串(内容, 0)
                    if qos > 0:
                        包号 = 内容[位:位 + 2]
                        位 += 2
                        连.sendall(bytes([MQTT_PUBACK << 4, 2]) + 包号)
                    载荷 = 内容[位:]
                    self._转发(主题, 载荷)
                elif 类型 == MQTT_PINGREQ:
                    连.sendall(bytes([MQTT_PINGRESP << 4, 0]))
                elif 类型 == MQTT_DISCONNECT:
                    break
        except (OSError, socket.timeout):
            pass
        finally:
            with self.锁:
                self.客户们 = [c for c in self.客户们 if c is not 客户]
            try:
                连.close()
            except OSError:
                pass

    def _转发(self, 主题: str, 载荷: bytes) -> None:
        主原 = 主题.encode("utf-8")
        报文 = (
            bytes([MQTT_PUBLISH << 4])
            + _编长(len(主原) + 2 + len(载荷))
            + len(主原).to_bytes(2, "big")
            + 主原
            + 载荷
        )
        with self.锁:
            客户们 = list(self.客户们)
        for 客 in 客户们:
            if any(_匹配主题(订, 主题) for 订 in 客["订阅"]):
                try:
                    客["套"].sendall(报文)
                except OSError:
                    pass
        self.消息数[0] += 1

    def 关(self) -> None:
        self.停.set()
        with self.锁:
            for 客 in self.客户们:
                try:
                    客["套"].close()
                except OSError:
                    pass
        try:
            self.套.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Modbus TCP 从站（把设备寄存器暴露给上位机）
# ---------------------------------------------------------------------------

# 寄存器映射（地址 → 含义），与上位机约定好
寄存器表 = {
    0: "CV01_速度x100",       # 进料传送带速度 (×100，如 150 = 1.50 m/s)
    1: "CV01_运行",           # 1=运行 0=停止
    2: "CV01_电流x10",        # 电机电流 (×10 A)
    3: "VS01_识别总数低",     # 低 16 位
    4: "VS01_识别总数高",
    5: "VS01_成功率x100",     # 识别成功率 (×100)
    6: "WT01_最后重量",       # 最后一件重量 (g)
    7: "WT01_超重件数",
    8: "CY01_动作次数低",
    9: "CY01_动作耗时",       # ms
    10: "CY02_动作次数低",
    11: "CY02_动作耗时",
    12: "CV02_速度x100",
    13: "CV02_出货总数低",
    14: "产出_大件数",
    15: "产出_小件数",
}


class Modbus从站:
    """只读从站：上位机可以读全部寄存器，写只支持控制寄存器。"""

    def __init__(self, 端口: int = 15020, 模拟器引用=None) -> None:
        self.端口 = 端口
        self.模拟器 = 模拟器引用
        self.套 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.套.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.套.bind(("0.0.0.0", 端口))
        self.套.listen(8)
        self.停 = threading.Event()
        self.写次数 = 0

    def 启动(self) -> None:
        threading.Thread(target=self._接受, daemon=True).start()

    def _接受(self) -> None:
        self.套.settimeout(0.5)
        while not self.停.is_set():
            try:
                连, _ = self.套.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._服务, args=(连,), daemon=True).start()

    def _服务(self, 连: socket.socket) -> None:
        连.settimeout(10.0)
        try:
            头 = _读满(连, 7)
            if len(头) < 7:
                return
            事务号 = 头[0:2]
            长度 = int.from_bytes(头[4:6], "big")
            体 = _读满(连, 长度 - 1)
            if not 体:
                return
            功能码 = 体[0]
            寄存器们 = self.模拟器.读寄存器快照() if self.模拟器 else []

            if 功能码 in (0x03, 0x04):
                起址 = int.from_bytes(体[1:3], "big")
                个数 = int.from_bytes(体[3:5], "big")
                值们 = []
                for i in range(个数):
                    址 = 起址 + i
                    值们.append(寄存器们[址] if 址 < len(寄存器们) else 0)
                数据 = b"".join(v.to_bytes(2, "big") for v in 值们)
                响应 = bytes([功能码, len(数据)]) + 数据
            elif 功能码 == 0x06:
                地址 = int.from_bytes(体[1:3], "big")
                值 = int.from_bytes(体[3:5], "big")
                self.写次数 += 1
                if self.模拟器:
                    self.模拟器.写寄存器(地址, 值)
                响应 = 体[:5]
            else:
                响应 = bytes([功能码 | 0x80, 1])

            mbap = (
                事务号
                + (0).to_bytes(2, "big")
                + (len(响应) + 1).to_bytes(2, "big")
                + bytes([头[6]])
            )
            连.sendall(mbap + 响应)
        except (OSError, socket.timeout):
            pass
        finally:
            try:
                连.close()
            except OSError:
                pass

    def 关(self) -> None:
        self.停.set()
        try:
            self.套.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 设备仿真核心
# ---------------------------------------------------------------------------


@dataclass
class 设备:
    位号: str
    名: str
    类: str
    在线: bool = True
    #: 遥测数据（键 → 值）
    遥测: dict = field(default_factory=dict)


class 分拣线:
    """一条分拣线的物理仿真。"""

    def __init__(self) -> None:
        # --- 可被上位机控制的参数 ---
        self.进料速度 = 1.5          # m/s
        self.进料运行 = True
        self.出料速度 = 1.4
        self.出料运行 = True
        self.称重阈值 = 500          # g，超过算大件
        self.超重告警阈值 = 2000     # g
        self.视觉启用 = True

        # --- 累计量 ---
        self.到达总数 = 0
        self.识别总数 = 0
        self.识别正确 = 0
        self.大件数 = 0
        self.小件数 = 0
        self.超重件数 = 0
        self.出货总数 = 0
        self.气缸1次数 = 0
        self.气缸2次数 = 0
        self.气缸1耗时 = 120
        self.气缸2耗时 = 115
        self.最后重量 = 0

        # --- 瞬时量 ---
        self.进料电流 = 3.2
        self.堵塞 = False
        self.堵塞计时 = 0.0

        # --- 内部 ---
        self.待处理 = 0.0            # 累积的到达量（小数）
        self.随机 = random.Random(20251030)
        self.锁 = threading.RLock()
        self.已运行秒 = 0.0

    # -- 仿真推进 --

    def 推进(self, dt: float) -> None:
        with self.锁:
            self.已运行秒 += dt

            # 1. 物料到达：到达率正比于进料速度
            if self.进料运行 and not self.堵塞:
                到达率 = self.进料速度 * 4.0      # 每秒到达件数
                self.待处理 += 到达率 * dt
                while self.待处理 >= 1.0:
                    self.待处理 -= 1.0
                    self._到达一件()

            # 2. 堵料：随机发生，或待处理堆积过多
            if self.待处理 > 3.0 and not self.堵塞:
                self.堵塞 = True
                self.堵塞计时 = 0.0
            if self.堵塞:
                self.堵塞计时 += dt
                if self.堵塞计时 > 8.0:
                    self.堵塞 = False
                    self.待处理 = 0.0

            # 3. 电机电流随负载波动
            基 = 3.0 if self.进料运行 else 0.1
            载 = 0.6 if self.堵塞 else 0.0
            self.进料电流 = max(0.0, 基 + 载 + self.随机.gauss(0, 0.15))

            # 4. 气缸耗时波动
            自 = self.随机
            if 自.random() < 0.1:
                self.气缸1耗时 = int(max(80, min(400, 自.gauss(130, 25))))
            if 自.random() < 0.1:
                self.气缸2耗时 = int(max(80, min(400, 自.gauss(125, 25))))

    def _到达一件(self) -> None:
        self.到达总数 += 1
        自 = self.随机

        # 视觉识别（3% 误判）
        if self.视觉启用:
            self.识别总数 += 1
            if 自.random() > 0.03:
                self.识别正确 += 1

        # 称重：150-900g 为主，偶尔超重
        重 = 自.gauss(420, 180)
        if 自.random() < 0.06:
            重 = 自.uniform(1900, 2600)     # 超重件
        重 = max(50, int(重))
        self.最后重量 = 重
        if 重 > self.超重告警阈值:
            self.超重件数 += 1

        # 分拣
        if 重 > self.称重阈值:
            self.大件数 += 1
            self.气缸1次数 += 1
        else:
            self.小件数 += 1
            self.气缸2次数 += 1

        self.出货总数 += 1

    # -- 寄存器映射（供 Modbus 读） --

    def 读寄存器快照(self) -> list[int]:
        with self.锁:
            成功率 = (
                int(100 * self.识别正确 / self.识别总数)
                if self.识别总数 > 0
                else 100
            )
            return [
                # 速度换算用 round 而不是 int：230/100=2.3 存回去，
                # 2.3*100 = 229.99999999999997，int() 截断会变成 229。
                round(self.进料速度 * 100),
                1 if self.进料运行 else 0,
                int(self.进料电流 * 10),
                self.识别总数 & 0xFFFF,
                (self.识别总数 >> 16) & 0xFFFF,
                成功率,
                self.最后重量,
                self.超重件数,
                self.气缸1次数 & 0xFFFF,
                self.气缸1耗时,
                self.气缸2次数 & 0xFFFF,
                self.气缸2耗时,
                round(self.出料速度 * 100),
                self.出货总数 & 0xFFFF,
                self.大件数 & 0xFFFF,
                self.小件数 & 0xFFFF,
            ]

    def 写寄存器(self, 地址: int, 值: int) -> None:
        with self.锁:
            if 地址 == 0:
                self.进料速度 = max(0.0, min(5.0, 值 / 100.0))
            elif 地址 == 1:
                self.进料运行 = 值 != 0
            elif 地址 == 12:
                self.出料速度 = max(0.0, min(5.0, 值 / 100.0))
            # 其它地址只读

    # -- MQTT 遥测 --

    def 遥测表(self) -> dict:
        with self.锁:
            成功率 = (
                round(100 * self.识别正确 / self.识别总数, 1)
                if self.识别总数 > 0
                else 100.0
            )
            return {
                "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
                "运行秒": round(self.已运行秒, 1),
                "进料": {
                    "速度": round(self.进料速度, 2),
                    "运行": self.进料运行,
                    "电流": round(self.进料电流, 2),
                    "堵塞": self.堵塞,
                },
                "视觉": {
                    "启用": self.视觉启用,
                    "识别总数": self.识别总数,
                    "成功率": 成功率,
                },
                "称重": {
                    "最后重量": self.最后重量,
                    "超重件数": self.超重件数,
                    "阈值": self.称重阈值,
                },
                "气缸1": {"次数": self.气缸1次数, "耗时": self.气缸1耗时},
                "气缸2": {"次数": self.气缸2次数, "耗时": self.气缸2耗时},
                "出料": {
                    "速度": round(self.出料速度, 2),
                    "运行": self.出料运行,
                    "出货": self.出货总数,
                },
                "产出": {
                    "大件": self.大件数,
                    "小件": self.小件数,
                    "超重": self.超重件数,
                    "总到达": self.到达总数,
                },
            }


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------


def 主() -> int:
    解析器 = argparse.ArgumentParser(description="智能物料分拣线设备模拟器")
    解析器.add_argument("--mqtt", type=int, default=1883, help="MQTT 端口（0=不开）")
    解析器.add_argument("--modbus", type=int, default=15020, help="Modbus TCP 端口（0=不开）")
    解析器.add_argument("--秒", type=float, default=0.5, help="上报间隔（秒）")
    解析器.add_argument("--静默", action="store_true", help="不打印每条遥测")
    参数 = 解析器.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    线 = 分拣线()
    服务们 = []

    print("=" * 68)
    print("  智能物料分拣线 · 设备模拟器")
    print("=" * 68)

    # --- Modbus TCP 从站 ---
    从站 = None
    if 参数.modbus > 0:
        try:
            从站 = Modbus从站(参数.modbus, 线)
            从站.启动()
            服务们.append(从站)
            print(f"  Modbus TCP  0.0.0.0:{参数.modbus}   （16 个寄存器）")
        except OSError as e:
            print(f"  [警告] Modbus 端口 {参数.modbus} 不可用：{e}")

    # --- MQTT broker ---
    broker = None
    if 参数.mqtt > 0:
        try:
            broker = 迷你broker(参数.mqtt)
            broker.启动()
            服务们.append(broker)
            print(f"  MQTT broker 0.0.0.0:{参数.mqtt}")
        except OSError as e:
            print(f"  [警告] MQTT 端口 {参数.mqtt} 不可用：{e}")

    if not 服务们:
        print("\n[错误] 没有任何服务启动成功，请检查端口占用。")
        return 1

    print(f"  上报间隔    {参数.秒} 秒")
    print("=" * 68)
    print("  6 台虚拟设备：CV-01 进料 / VS-01 视觉 / WT-01 称重")
    print("               CY-01 气缸1 / CY-02 气缸2 / CV-02 出料")
    print("=" * 68)
    print("  Ctrl+C 停止")
    print()

    上次 = time.monotonic()
    上报计时 = 0.0
    心跳 = 0

    try:
        while True:
            现在 = time.monotonic()
            dt = 现在 - 上次
            上次 = 现在
            线.推进(min(dt, 0.5))
            上报计时 += dt

            if 上报计时 >= 参数.秒:
                上报计时 = 0.0
                表 = 线.遥测表()
                文 = json.dumps(表, ensure_ascii=False)

                if broker is not None:
                    # 分主题发布（真实物联网常见做法）
                    broker._转发("分拣线/遥测", 文.encode("utf-8"))
                    broker._转发(
                        f"分拣线/设备/CV-01",
                        json.dumps(表["进料"], ensure_ascii=False).encode("utf-8"),
                    )
                    broker._转发(
                        f"分拣线/设备/VS-01",
                        json.dumps(表["视觉"], ensure_ascii=False).encode("utf-8"),
                    )
                    broker._转发(
                        f"分拣线/设备/WT-01",
                        json.dumps(表["称重"], ensure_ascii=False).encode("utf-8"),
                    )
                    broker._转发(
                        f"分拣线/设备/CY-01",
                        json.dumps(表["气缸1"], ensure_ascii=False).encode("utf-8"),
                    )
                    broker._转发(
                        f"分拣线/设备/CY-02",
                        json.dumps(表["气缸2"], ensure_ascii=False).encode("utf-8"),
                    )
                    broker._转发(
                        f"分拣线/设备/CV-02",
                        json.dumps(表["出料"], ensure_ascii=False).encode("utf-8"),
                    )

                心跳 += 1
                if not 参数.静默 and 心跳 % 4 == 1:
                    产 = 表["产出"]
                    print(
                        f"  [{表['时间']}] "
                        f"到达 {产['总到达']:5d}  大件 {产['大件']:5d}  "
                        f"小件 {产['小件']:5d}  出货 {表['出料']['出货']:5d}  "
                        f"进料 {表['进料']['速度']:.2f}m/s  "
                        f"识别率 {表['视觉']['成功率']:.1f}%"
                        + ("  【堵料】" if 表["进料"]["堵塞"] else "")
                    )

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n  正在停止…")

    for 服 in 服务们:
        服.关()
    print("  已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(主())
