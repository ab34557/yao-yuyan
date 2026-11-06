"""爻语网页运行时（SPEC 4.5）。

用标准库 `http.server` 提供：
* 路由注册（`路`）：方法 + 路径，支持 `:名` 路径参数。
* 静态目录（`共`）。
* 请求对象 `请`、响应对象 `应`。
* 返回值自动协商：字 → HTML；表/列/数/真/假 → JSON；空 → 204；应 → 按对象输出。
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import threading
import urllib.parse
from typing import Any

from .errors import 爻误, 网误
from .values import (
    应,
    请,
    空,
    取类型名,
    转字,
)

#: 全局解释器锁：爻语路由处理函数共享一个解释器，必须串行化。
锁 = threading.RLock()


def 解析路径(模式: str, 路径: str) -> dict[str, str] | None:
    """匹配 `/事项/:编号` 形式的路由，返回路径参数。"""
    模段 = 模式.strip("/").split("/")
    路段 = 路径.strip("/").split("/")
    if len(模段) != len(路段):
        return None
    参: dict[str, str] = {}
    for m, s in zip(模段, 路段):
        if m.startswith(":") and len(m) > 1:
            名 = m[1:]
            if s == "":
                return None
            参[名] = urllib.parse.unquote(s)
        elif m != s:
            return None
    return 参


def 构建请(法: str, 路径: str, 头: dict[str, str], 体: bytes) -> 请:
    拆 = urllib.parse.urlsplit(路径)
    径 = urllib.parse.unquote(拆.path) or "/"
    查 = urllib.parse.parse_qs(拆.query, keep_blank_values=True)
    参: dict[str, str] = {k: v[-1] for k, v in 查.items()}
    原 = 体.decode("utf-8", errors="replace")
    体值: Any = 空
    类 = 头.get("content-type", "")
    if 原:
        if "application/json" in 类:
            try:
                体值 = json.loads(原)
            except json.JSONDecodeError:
                体值 = 原
        elif "application/x-www-form-urlencoded" in 类:
            对 = urllib.parse.parse_qs(原, keep_blank_values=True)
            体值 = {k: v[-1] for k, v in 对.items()}
        else:
            体值 = 原
    return 请(法=法, 径=径, 参=参, 体=体值, 头=头, 原=原, 查询=拆.query)


def 构建响应(解释器, 请对象: 请, 结果: Any) -> tuple[int, dict[str, str], bytes]:
    """把处理函数返回值转成 (状态码, 头, 体)。"""
    from .builtins import _爻转json

    if isinstance(结果, 应):
        码 = 结果.码
        头表 = dict(结果.头)
        体值 = 结果.体
        if isinstance(体值, str):
            头表.setdefault("Content-Type", "text/html; charset=utf-8")
            体 = 体值.encode("utf-8")
        elif 体值 is 空 or 体值 is None:
            体 = b""
            if 码 == 200:
                码 = 204
        else:
            头表.setdefault("Content-Type", "application/json; charset=utf-8")
            体 = json.dumps(_爻转json(体值), ensure_ascii=False).encode("utf-8")
        return 码, 头表, 体

    if 结果 is 空 or 结果 is None:
        return 204, {"Content-Type": "application/json; charset=utf-8"}, b""

    if isinstance(结果, str):
        return 200, {"Content-Type": "text/html; charset=utf-8"}, 结果.encode("utf-8")

    if isinstance(结果, (dict, list, int, float, bool)):
        体 = json.dumps(_爻转json(结果), ensure_ascii=False).encode("utf-8")
        return 200, {"Content-Type": "application/json; charset=utf-8"}, 体

    # 其它对象按 JSON 处理失败时退回字符串
    try:
        体 = json.dumps(_爻转json(结果), ensure_ascii=False).encode("utf-8")
        return 200, {"Content-Type": "application/json; charset=utf-8"}, 体
    except 爻误:
        return (
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
            转字(结果).encode("utf-8"),
        )


def 找到静态文件(解释器, 路径: str) -> str | None:
    径 = urllib.parse.unquote(路径)
    for 前缀, 目录 in 解释器.静态目录:
        if 径.startswith(前缀):
            余 = 径[len(前缀):]
            if not 余 or ".." in 余.split("/"):
                continue
            候选 = os.path.realpath(os.path.join(目录, 余))
            基 = os.path.realpath(目录)
            if 候选 == 基 or not 候选.startswith(基 + os.sep) and 候选 != 基:
                continue
            if os.path.isfile(候选):
                return 候选
    return None


def 做处理器(解释器):
    class 处理器(http.server.BaseHTTPRequestHandler):
        服务名 = "爻语"
        协议版本 = "HTTP/1.1"

        def log_message(self, 格式, *参):  # 静默
            pass

        def _读体(self) -> bytes:
            长文 = self.headers.get("Content-Length")
            if not 长文:
                return b""
            try:
                n = int(长文)
            except ValueError:
                return b""
            return self.rfile.read(n)

        def _发(self, 码: int, 头: dict[str, str], 体: bytes) -> None:
            头 = dict(头)
            头.setdefault("Content-Length", str(len(体)))
            头.setdefault("Cache-Control", "no-store")
            # HTTP 头只能是 latin-1；中文头名/头值先做校验，转成中文 500 而不是掐断连接
            问题 = _检查头(头)
            if 问题 is not None:
                体 = json.dumps({"错": 问题}, ensure_ascii=False).encode("utf-8")
                码 = 500
                头 = {
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(体)),
                    "Cache-Control": "no-store",
                }
            try:
                self.send_response(码)
                for k, v in 头.items():
                    self.send_header(k, v)
                self.end_headers()
            except (UnicodeEncodeError, ValueError) as e:
                # 最后兜底：绝不把 Python 异常泄漏给客户端或 stderr
                try:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {"错": f"网误：响应头无法写出：{e}"}, ensure_ascii=False
                        ).encode("utf-8")
                    )
                except OSError:
                    pass
                return
            if self.command != "HEAD":
                try:
                    self.wfile.write(体)
                except OSError:
                    pass

        def _发json(self, 码: int, 对象: Any) -> None:
            体 = json.dumps(对象, ensure_ascii=False).encode("utf-8")
            self._发(码, {"Content-Type": "application/json; charset=utf-8"}, 体)

        def _处理(self) -> None:
            法 = self.command
            路径 = self.path
            头 = {k.lower(): v for k, v in self.headers.items()}
            try:
                体原文 = self._读体()
            except OSError:
                体原文 = b""

            拆 = urllib.parse.urlsplit(路径)
            径 = urllib.parse.unquote(拆.path) or "/"

            # 1) 路由
            for 路由 in list(解释器.路由表):
                if 路由["法"] != 法 and not (法 == "HEAD" and 路由["法"] == "GET"):
                    continue
                路径参 = 解析路径(路由["径"], 径)
                if 路径参 is None:
                    continue
                with 锁:
                    请对象 = 构建请(法, 路径, 头, 体原文)
                    请对象.路径参 = 路径参
                    请对象.参 = {**请对象.参, **路径参}
                    旧请 = 解释器.全局.表.get("请")
                    解释器.全局.表["请"] = 请对象
                    try:
                        处理 = 路由["处理"]
                        if isinstance(处理, 匠类):
                            # 0 参 / 1 参都支持
                            if len(处理.参) == 0:
                                结果 = 解释器.调匠(处理, [])
                            elif len(处理.参) == 1:
                                结果 = 解释器.调匠(处理, [请对象])
                            else:
                                raise 网误(
                                    f"路由处理函数最多接受 1 个参数，实际定义了 {len(处理.参)} 个"
                                )
                        else:
                            结果 = 解释器.调用(处理, [请对象], _节点())
                    except 爻误 as e:
                        self._发json(500, {"错": e.格式化()})
                        return
                    finally:
                        解释器.全局.表["请"] = 旧请
                码, 应头, 应体 = 构建响应(解释器, 请对象, 结果)
                self._发(码, 应头, 应体)
                return

            # 2) 静态目录
            静态 = 找到静态文件(解释器, 径)
            if 静态 is not None and 法 in ("GET", "HEAD"):
                try:
                    with open(静态, "rb") as f:
                        内容 = f.read()
                except OSError:
                    self._发json(500, {"错": "静态文件读取失败"})
                    return
                类型, _ = mimetypes.guess_type(静态)
                if 类型 is None:
                    类型 = "application/octet-stream"
                if 类型.startswith("text/") or 类型 in ("application/javascript", "application/json"):
                    类型 += "; charset=utf-8"
                self._发(200, {"Content-Type": 类型}, 内容)
                return

            # 3) 404
            self._发json(404, {"错": "无此路由"})

        def do_GET(self) -> None:
            self._处理()

        def do_POST(self) -> None:
            self._处理()

        def do_PUT(self) -> None:
            self._处理()

        def do_PATCH(self) -> None:
            self._处理()

        def do_DELETE(self) -> None:
            self._处理()

        def do_HEAD(self) -> None:
            self._处理()

        def do_OPTIONS(self) -> None:
            self._发(200, {"Allow": "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"}, b"")

    return 处理器


def _节点():
    from .ast_nodes import 调用节点

    return 调用节点()


def _可latin1(文: str) -> bool:
    try:
        文.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def _检查头(头: dict[str, str]) -> str | None:
    """HTTP 头必须是 latin-1；不合格时返回中文错误说明。"""
    for k, v in 头.items():
        K = str(k)
        V = str(v)
        if not _可latin1(K):
            return f"网误：响应头名「{K}」含非 ASCII 字符（HTTP 头必须用 ASCII，例如 X-Token）"
        if not _可latin1(V):
            return f"网误：响应头「{K}」的值含非 ASCII 字符（HTTP 头必须是 ASCII；中文内容请放进响应体）"
        if "\r" in K or "\n" in K:
            return f"网误：响应头名「{K}」含换行符"
        if "\r" in V or "\n" in V:
            return f"网误：响应头「{K}」的值含换行符"
    return None


# 延迟导入以避免循环
from .values import 匠 as 匠类  # noqa: E402


class 服务器:
    """可编程启停的 HTTP 服务（测试与 `听` 共用）。"""

    def __init__(self, 解释器, 端口: int = 8788, 地址: str = "0.0.0.0") -> None:
        self.解释器 = 解释器
        self.端口 = 端口
        self.地址 = 地址
        self.httpd: http.server.ThreadingHTTPServer | None = None
        self.线程: threading.Thread | None = None

    def 启动(self, 后台: bool = False) -> "服务器":
        self.httpd = http.server.ThreadingHTTPServer((self.地址, self.端口), 做处理器(self.解释器))
        self.httpd.daemon_threads = True
        if 后台:
            self.线程 = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.线程.start()
        return self

    def 服务(self) -> None:
        assert self.httpd is not None
        self.httpd.serve_forever()

    def 停止(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.线程 is not None:
            self.线程.join(timeout=2)
            self.线程 = None


def 启动(解释器, 端口: int) -> int:
    """`听` 的实现：阻塞运行 HTTP 服务。"""
    from . import 版本
    import sys

    服 = 服务器(解释器, 端口)
    try:
        服.启动(后台=False)
    except OSError as e:
        raise 网误(f"端口 {端口} 无法监听：{e}")
    sys.stdout.write(f"爻语 {版本} 网页服务已启动：http://127.0.0.1:{端口}/\n")
    sys.stdout.flush()
    try:
        服.服务()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        服.停止()
    return 0
