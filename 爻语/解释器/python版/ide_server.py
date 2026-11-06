"""爻语在线 IDE 后端（SPEC 第 7 节）。

* 静态页来自 `webui/`（离线，无 CDN）。
* `POST /api/跑` 用**子进程**执行用户代码：5 秒超时、200 万步上限、
* 200 KB 输出截断、沙箱禁用文件与网络内置函数。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

def _找项目根() -> str:
    """向上找到同时含 爻语/ 和 爻页/ 的目录（项目根）。

    代码在 爻语/解释器/python版/，项目根在三级之上。
    """
    当前 = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(当前, "爻语")) and os.path.isdir(
            os.path.join(当前, "爻页")
        ):
            return 当前
        上级 = os.path.dirname(当前)
        if 上级 == 当前:
            break
        当前 = 上级
    # 兜底：按已知层级上溯三级
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


项目根 = _找项目根()
网页目录 = os.path.join(项目根, "爻语", "工具", "webui")
示例目录 = os.path.join(项目根, "爻语", "示例", "示例")

超时秒 = 5.0
步上限 = 20_000_000
输出上限 = 200 * 1024

_执行锁 = threading.Lock()


# ---------------------------------------------------------------------------
# 运行用户代码（子进程）
# ---------------------------------------------------------------------------


def 运行片段(码: str, 参: list[str] | None = None) -> dict[str, Any]:
    """在子进程中执行一段爻语代码，返回 SPEC 7 约定的响应。"""
    import tempfile

    参 = 参 or []
    开始 = time.time()
    with _执行锁:
        with tempfile.TemporaryDirectory(prefix="yao-ide-") as 临时目录:
            脚本 = os.path.join(临时目录, "片段.yao")
            with open(脚本, "w", encoding="utf-8", newline="\n") as f:
                f.write(码)
            runner = os.path.join(临时目录, "runner.py")
            with open(runner, "w", encoding="utf-8") as f:
                f.write(_运行器源码)
            环境 = dict(os.environ)
            环境["PYTHONIOENCODING"] = "utf-8"
            环境["PYTHONUNBUFFERED"] = "1"
            环境["PYTHONPATH"] = 项目根 + os.pathsep + 环境.get("PYTHONPATH", "")
            try:
                进程 = subprocess.run(
                    [sys.executable, "-X", "utf8", runner, 脚本, *参],
                    cwd=临时目录,
                    capture_output=True,
                    timeout=超时秒,
                    env=环境,
                )
            except subprocess.TimeoutExpired as e:
                出文 = _解码(e.stdout) if e.stdout else ""
                return {
                    "成": False,
                    "出": 出文[:输出上限],
                    "错": {
                        "类": "时误",
                        "文": f"时误：执行超过 {超时秒:g} 秒，已中止",
                        "行": 0,
                        "列": 0,
                        "栈": [],
                    },
                    "耗": int((time.time() - 开始) * 1000),
                }
            耗 = int((time.time() - 开始) * 1000)
            出文 = _解码(进程.stdout)
            错文 = _解码(进程.stderr)
            截断 = len(出文) > 输出上限
            if 截断:
                出文 = 出文[:输出上限] + "\n…（输出超过 200 KB，已截断）"
            if 进程.returncode == 0:
                return {"成": True, "出": 出文, "错": None, "耗": 耗}
            # 运行器把结构化错误以 JSON 打印到 stderr 最后一行
            错对象 = _解析错误(错文)
            return {"成": False, "出": 出文, "错": 错对象, "耗": 耗}


def _解码(数据: bytes | None) -> str:
    if not 数据:
        return ""
    return 数据.decode("utf-8", errors="replace")


def _解析错误(错文: str) -> dict[str, Any]:
    行们 = [l for l in 错文.splitlines() if l.strip()]
    for 行 in reversed(行们):
        if 行.startswith("{") and 行.endswith("}"):
            try:
                对象 = json.loads(行)
                if isinstance(对象, dict) and "类" in 对象:
                    return {
                        "类": 对象.get("类", "误"),
                        "文": 对象.get("文", 错文),
                        "行": 对象.get("行", 0),
                        "列": 对象.get("列", 0),
                        "栈": 对象.get("栈", []),
                    }
            except json.JSONDecodeError:
                continue
    return {"类": "内误", "文": 错文.strip() or "未知错误", "行": 0, "列": 0, "栈": []}


_运行器源码 = r'''
import io, json, os, sys, traceback

sys.stdout.reconfigure(encoding="utf-8", newline="\n")
sys.stderr.reconfigure(encoding="utf-8", newline="\n")

sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(os.pathsep)[0])

from yao.interpreter import 解释器
from yao.errors import 爻误

脚本 = sys.argv[1]
参数 = sys.argv[2:]
缓冲 = io.StringIO()

class 截断输出(io.StringIO):
    def write(self, s):
        if self.tell() > 300 * 1024:
            raise SystemExit(0)
        return super().write(s)

def 主():
    with open(脚本, "r", encoding="utf-8") as f:
        源 = f.read()
    输出 = 截断输出()
    y = 解释器(输出=输出.write, 沙箱=True, 参数=参数, 步上限=20000000)
    y.当前文件 = 脚本
    try:
        y.运行源码(源, 脚本)
    except 爻误 as e:
        sys.stderr.write(json.dumps(e.成表(), ensure_ascii=False) + "\n")
        return 1
    except SystemExit:
        pass
    except RecursionError:
        e = 爻误("递归过深")
        e.类 = "内误"
        sys.stderr.write(json.dumps(e.成表(), ensure_ascii=False) + "\n")
        return 1
    except BaseException as e:
        sys.stderr.write(json.dumps({
            "类": "内误", "文": f"内误：{type(e).__name__}: {e}",
            "行": 0, "列": 0, "栈": [traceback.format_exc().splitlines()[-1]],
        }, ensure_ascii=False) + "\n")
        return 1
    finally:
        sys.stdout.write(输出.getvalue().replace("\r\n", "\n"))
        sys.stdout.flush()
    return 0

sys.exit(主())
'''


# ---------------------------------------------------------------------------
# 静态与 API
# ---------------------------------------------------------------------------


def 取示例() -> list[dict[str, str]]:
    出: list[dict[str, str]] = []
    if not os.path.isdir(示例目录):
        return 出
    for 文件名 in sorted(os.listdir(示例目录)):
        if not 文件名.endswith(".yao"):
            continue
        路径 = os.environ.get("PYTHONIOENCODING")  # noqa: F841 - 仅保持编码意识
        try:
            with open(os.path.join(示例目录, 文件名), "r", encoding="utf-8") as f:
                码 = f.read()
        except OSError:
            continue
        出.append({"名": 文件名[:-4], "码": 码})
    return 出


def 取谱() -> dict[str, Any]:
    from yao.tokens import 关键字

    键 = [{"词": k, "义": v} for k, v in 关键字.items()]
    内置 = [
        {"词": "显", "义": "打印（换行）"},
        {"词": "述", "义": "打印（不换行）"},
        {"词": "串", "义": "转字符串"},
        {"词": "数", "义": "转数字"},
        {"词": "型", "义": "类型名"},
        {"词": "长", "义": "长度"},
        {"词": "切", "义": "切片"},
        {"词": "取", "义": "按键取值（可给默认）"},
        {"词": "置", "义": "写键（返回容器）"},
        {"词": "含", "义": "包含判断"},
        {"词": "增", "义": "追加到列"},
        {"词": "删", "义": "删除键或列项"},
        {"词": "键集", "义": "取表的键列"},
        {"词": "列", "义": "转成列"},
        {"词": "映", "义": "映射"},
        {"词": "筛", "义": "过滤"},
        {"词": "折", "义": "折叠/归约"},
        {"词": "排", "义": "排序（可给键函数）"},
        {"词": "复", "义": "重复"},
        {"词": "并", "义": "拼接为字"},
        {"词": "分", "义": "拆分为列"},
        {"词": "替", "义": "替换"},
        {"词": "裁", "义": "去首尾空白"},
        {"词": "除", "义": "整除（向下取整）"},
        {"词": "绝", "义": "绝对值"},
        {"词": "极", "义": "最大值"},
        {"词": "下", "义": "最小值"},
        {"词": "舍", "义": "四舍五入"},
        {"词": "随", "义": "随机整数"},
        {"词": "今", "义": "当前时间"},
        {"词": "眠", "义": "休眠秒数"},
        {"词": "核", "义": "断言"},
        {"词": "停", "义": "退出进程"},
        {"词": "析", "义": "JSON 解析"},
        {"词": "构", "义": "JSON 序列化"},
        {"词": "读", "义": "读文件"},
        {"词": "写", "义": "写文件"},
        {"词": "在", "义": "路径是否存在"},
        {"词": "参", "义": "命令行参数"},
        {"词": "境", "义": "环境变量"},
        {"词": "路", "义": "注册路由"},
        {"词": "共", "义": "静态目录"},
        {"词": "听", "义": "启动网页服务"},
        {"词": "应", "义": "构造响应"},
        {"词": "请", "义": "当前请求"},
        {"词": "版本", "义": "解释器版本"},
        {"词": "滴", "义": "高精度计时起点"},
        {"词": "毫秒", "义": "算耗时毫秒"},
        {"词": "开覆盖", "义": "开启覆盖率追踪"},
        {"词": "取覆盖", "义": "取覆盖率快照"},
        {"词": "关覆盖", "义": "关闭覆盖率追踪"},
        {"词": "载模块", "义": "按路径加载模块"},
        {"词": "抓", "义": "抓取网址（测试网站用）"},
        {"词": "请求", "义": "发任意 HTTP 请求"},
        {"词": "散列", "义": "加盐 SHA-256 摘要"},
        {"词": "随机字", "义": "密码学安全随机串"},
        {"词": "恒等", "义": "恒定时间比较"},
    ]
    运算 = [
        {"词": "⇒", "义": "绑定 / 分支臂 / 表键值"},
        {"词": "▷", "义": "管道：x ▷ f 等价 f(x)"},
        {"词": "【 】", "义": "语句块"},
        {"词": "；", "义": "语句分隔"},
        {"词": "，", "义": "参数分隔"},
        {"词": ".", "义": "成员访问（表.键 / 成员调用）"},
        {"词": "[]", "义": "索引；[] 也是列表字面量"},
        {"词": "{}", "义": "表字面量"},
        {"词": "==", "义": "相等"},
        {"词": "!=", "义": "不等"},
        {"词": "<", "义": "小于"},
        {"词": "<=", "义": "小于等于"},
        {"词": ">", "义": "大于"},
        {"词": ">=", "义": "大于等于"},
        {"词": "+", "义": "加 / 字拼接 / 列连接"},
        {"词": "-", "义": "减 / 负号"},
        {"词": "*", "义": "乘 / 字与列重复"},
        {"词": "/", "义": "真除（结果为浮点，显示去尾零）"},
        {"词": "%", "义": "取余"},
        {"词": "^", "义": "幂（右结合）"},
        {"词": "且", "义": "逻辑与"},
        {"词": "或", "义": "逻辑或"},
        {"词": "非", "义": "逻辑非"},
        {"词": "注", "义": "注释（行注释或 注【 】 块注释）"},
        {"词": "`名`", "义": "用反引号让保留字当名字"},
    ]
    return {"关键字": 键, "内置": 内置, "运算": 运算}


def 做处理器(地址: tuple[str, int] | None = None):
    class 处理器(BaseHTTPRequestHandler):
        协议版本 = "HTTP/1.1"

        def log_message(self, *参):
            pass

        def _发(self, 码: int, 类型: str, 体: bytes) -> None:
            self.send_response(码)
            self.send_header("Content-Type", 类型)
            self.send_header("Content-Length", str(len(体)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(体)

        def _发json(self, 码: int, 对象: Any) -> None:
            体 = json.dumps(对象, ensure_ascii=False).encode("utf-8")
            self._发(码, "application/json; charset=utf-8", 体)

        def _静态(self, 相对: str) -> None:
            路径 = os.path.realpath(os.path.join(网页目录, 相对))
            if not 路径.startswith(os.path.realpath(网页目录)):
                self._发json(403, {"错": "禁止访问"})
                return
            if not os.path.isfile(路径):
                self._发json(404, {"错": "文件不存在"})
                return
            类型 = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }.get(os.path.splitext(路径)[1], "application/octet-stream")
            with open(路径, "rb") as f:
                体 = f.read()
            self._发(200, 类型, 体)

        def do_GET(self):
            拆 = urllib.parse.urlsplit(self.path)
            径 = urllib.parse.unquote(拆.path)
            if 径 in ("/", "/index.html"):
                self._静态("index.html")
                return
            if 径 == "/api/健康":
                from yao import 版本

                self._发json(200, {"行": True, "版": 版本})
                return
            if 径 == "/api/例":
                self._发json(200, {"例子": 取示例()})
                return
            if 径 == "/api/谱":
                self._发json(200, 取谱())
                return
            if 径.startswith("/api/"):
                self._发json(404, {"错": "无此接口"})
                return
            self._静态(径.lstrip("/"))

        def do_POST(self):
            拆 = urllib.parse.urlsplit(self.path)
            径 = urllib.parse.unquote(拆.path)
            if 径 != "/api/跑":
                self._发json(404, {"错": "无此接口"})
                return
            长度 = int(self.headers.get("Content-Length") or 0)
            if 长度 > 1024 * 1024:
                self._发json(413, {"错": "代码过长（上限 1 MB）"})
                return
            原文 = self.rfile.read(长度) if 长度 else b""
            try:
                请求 = json.loads(原文.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._发json(400, {"错": "请求体必须是 UTF-8 JSON"})
                return
            if not isinstance(请求, dict) or not isinstance(请求.get("码"), str):
                self._发json(400, {"错": "缺少字段「码」"})
                return
            参 = 请求.get("参") or []
            if not isinstance(参, list):
                self._发json(400, {"错": "字段「参」必须是列"})
                return
            结果 = 运行片段(请求["码"], [str(x) for x in 参])
            self._发json(200, 结果)

        def do_HEAD(self):
            self._发(200, "text/html; charset=utf-8", b"")

    return 处理器


class IDEServer:
    def __init__(self, 端口: int = 8787, 地址: str = "127.0.0.1") -> None:
        self.端口 = 端口
        self.地址 = 地址
        self.httpd: ThreadingHTTPServer | None = None
        self.线程: threading.Thread | None = None

    def 启动(self, 后台: bool = False) -> "IDEServer":
        self.httpd = ThreadingHTTPServer((self.地址, self.端口), 做处理器())
        self.httpd.daemon_threads = True
        if 后台:
            self.线程 = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.线程.start()
        return self

    def 停止(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.线程 is not None:
            self.线程.join(timeout=2)
            self.线程 = None


def 启动(端口: int = 8787) -> int:
    from yao import 版本

    服 = IDEServer(端口)
    try:
        服.启动()
    except OSError as e:
        print(f"端口 {端口} 无法监听：{e}")
        return 2
    实际 = 服.httpd.server_address[1]
    print(f"爻语 {版本} 在线 IDE：http://127.0.0.1:{实际}/")
    print("按 Ctrl+C 退出。")
    sys.stdout.flush()
    try:
        服.httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        服.停止()
    return 0

