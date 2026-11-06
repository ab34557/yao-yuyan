"""爻页浏览器：原生窗口，从零实现的「浏览器」。

界面：地址栏 + 前进/后退/刷新 + 渲染区 + 状态栏。
不使用任何 Web 技术（无 HTML/CSS/JS），渲染全部由 渲染.py 手工绘制。
"""

from __future__ import annotations

import os
import time
import tkinter as tk
import urllib.error
import urllib.parse
from tkinter import filedialog
from typing import Any

from . import __version__, 名称, 后缀
from .错误 import 爻页误
from .布局 import 布局, 命中最上层, 找盒, 遍历
from .渲染 import 画布渲染器
from .求值 import 求值器, 转字
from .语法 import 分析文本
from .词法 import 切分

# 默认示例目录（相对项目根；打包后由启动器指定绝对路径）
示例目录 = "爻页/示例"
默认页 = 示例目录 + "/使用说明" + 后缀


class 浏览器:
    def __init__(self, 根窗口: tk.Tk | None = None, 初始页: str | None = None) -> None:
        self.根 = 根窗口 or tk.Tk()
        self.根.title(f"{名称} 浏览器 v{__version__}")
        self.根.geometry("1000x760")
        self.根.minsize(560, 420)
        self.根.configure(bg="#0b1020")

        # 状态
        self.当前路径: str = ""
        self.历史: list[str] = []
        self.历史位: int = -1
        self.页面对象 = None
        self.求值器: 求值器 | None = None
        self.根盒: dict | None = None
        self.渲染器: 画布渲染器 | None = None
        self.输入焦点标识: int | None = None
        self.悬停盒: dict | None = None
        self.图片缓存: dict = {}
        self.渲染耗时: float = 0.0
        #: 远程页面的源码缓存（本地页面时为 None）
        self._远程源码: str | None = None
        # ---- 滚动 ----
        #: 垂直/水平滚动偏移（像素，>=0）
        self.滚动Y: float = 0.0
        self.滚动X: float = 0.0
        #: 可滚动范围（内容总尺寸 - 视口尺寸，>=0 才可滚）
        self.可滚高: float = 0.0
        self.可滚宽: float = 0.0
        #: 滚动条拖动状态
        self._拖滚动条 = False
        self._拖起点Y = 0.0
        self._拖起始滚动 = 0.0

        #: 定时刷新用的 after 句柄（页面切换时要取消）
        self._定时句柄: list[str] = []
        self._定时运行中 = False

        self._建界面()
        if 初始页:
            self.打开(初始页)
        else:
            self.打开(默认页)

    # ---------- 界面 ----------

    def _建界面(self) -> None:
        顶 = tk.Frame(self.根, bg="#111827", height=46)
        顶.pack(side="top", fill="x")
        顶.pack_propagate(False)

        钮式 = {
            "bg": "#1e293b", "fg": "#e2e8f0", "activebackground": "#334155",
            "activeforeground": "#ffffff", "relief": "flat", "bd": 0,
            "font": ("Microsoft YaHei UI", 11), "width": 3, "cursor": "hand2",
        }

        self.后退钮 = tk.Button(顶, text="←", command=self.后退, **钮式)
        self.后退钮.pack(side="left", padx=(10, 3), pady=8)
        self.前进钮 = tk.Button(顶, text="→", command=self.前进, **钮式)
        self.前进钮.pack(side="left", padx=3, pady=8)
        self.刷新钮 = tk.Button(顶, text="↻", command=self.重载, **钮式)
        self.刷新钮.pack(side="left", padx=3, pady=8)

        self.地址框 = tk.Entry(
            顶, bg="#0b1220", fg="#e2e8f0", insertbackground="#7ee787",
            relief="flat", bd=0, font=("Cascadia Code", 11),
        )
        self.地址框.pack(side="left", fill="x", expand=True, padx=8, pady=8, ipady=6)
        self.地址框.bind("<Return>", lambda e: self._地址跳转())

        开钮 = tk.Button(顶, text="打开", command=self._地址跳转,
                        **{**钮式, "width": 5, "bg": "#7ee787", "fg": "#06210f",
                           "activebackground": "#a7f3b9"})
        开钮.pack(side="left", padx=(0, 6), pady=8)

        选钮 = tk.Button(顶, text="选文件", command=self._选文件,
                        **{**钮式, "width": 7})
        选钮.pack(side="left", padx=(0, 10), pady=8)

        # 渲染区
        self.画布 = tk.Canvas(
            self.根, bg="#070b16", highlightthickness=0, bd=0,
        )
        self.画布.pack(side="top", fill="both", expand=True)
        self.渲染器 = 画布渲染器(self.画布, self.图片缓存)

        self.画布.bind("<Button-1>", self._点击)
        self.画布.bind("<Motion>", self._移动)
        self.画布.bind("<Leave>", lambda e: self._设悬停(None))
        self.画布.bind("<Configure>", self._窗口改变)

        # 滚轮：Windows 上 <MouseWheel> 的 event.delta 是 ±120 的倍数
        self.画布.bind("<MouseWheel>", self._滚轮)
        self.画布.bind("<Button-4>", lambda e: self._滚动(-1))   # Linux
        self.画布.bind("<Button-5>", lambda e: self._滚动(1))
        # 拖动滚动条
        self.画布.bind("<ButtonPress-1>", self._按下, add="+")
        self.画布.bind("<B1-Motion>", self._拖动, add="+")
        self.画布.bind("<ButtonRelease-1>", self._松开, add="+")
        self.根.bind("<Key>", self._按键)
        self.根.bind("<BackSpace>", self._退格)
        self.根.bind("<Control-l>", lambda e: self.地址框.focus_set())
        self.根.bind("<F5>", lambda e: self.重载())

        # 状态栏
        底 = tk.Frame(self.根, bg="#111827", height=28)
        底.pack(side="bottom", fill="x")
        底.pack_propagate(False)
        self.状态 = tk.Label(
            底, text="就绪", bg="#111827", fg="#8b9ab8", anchor="w",
            font=("Microsoft YaHei UI", 10), padx=12,
        )
        self.状态.pack(side="left", fill="x", expand=True)

    # ---------- 打开与历史 ----------

    def _地址跳转(self) -> None:
        址 = self.地址框.get().strip()
        if 址:
            self.打开(址, 记录历史=True)

    def _选文件(self) -> None:
        路径 = filedialog.askopenfilename(
            title="打开爻页文件",
            initialdir=os.path.join(os.getcwd(), 示例目录),
            filetypes=[("爻页文件", "*" + 后缀), ("所有文件", "*.*")],
        )
        if 路径:
            self.打开(路径, 记录历史=True)

    def 打开(self, 路径: str, 记录历史: bool = True) -> None:
        """打开一个地址。

        支持三种形式：
            * `页面.页`                 本地文件
            * `页面.页#键=值`           本地文件 + 参数
            * `http://主机:端口/路径`   远程（返回爻页源码）
        """
        # 支持 "页面.页#键=值&键=值" 形式的参数
        参数: dict[str, Any] = {}
        if "#" in 路径:
            路径, 查询 = 路径.split("#", 1)
            for 段 in 查询.split("&"):
                if "=" in 段:
                    k, v = 段.split("=", 1)
                    参数[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
        self.待传入参数 = 参数

        # ---- 远程地址 ----
        if 路径.startswith("http://") or 路径.startswith("https://"):
            self._打开远程(路径, 记录历史)
            return

        # ---- 本地文件 ----
        真路径 = 路径
        if not os.path.isabs(真路径):
            真路径 = os.path.join(os.getcwd(), 路径)
        if not os.path.isfile(真路径) and os.path.isfile(真路径 + 后缀):
            真路径 += 后缀

        self.当前路径 = 真路径
        self._远程源码 = None      # 清掉远程缓存
        self.地址框.delete(0, "end")
        self.地址框.insert(0, self._显示路径(真路径))

        if 记录历史:
            # 截断前进历史
            if self.历史位 >= 0 and self.历史位 < len(self.历史) - 1:
                self.历史 = self.历史[: self.历史位 + 1]
            if not self.历史 or self.历史[-1] != 真路径:
                self.历史.append(真路径)
            self.历史位 = len(self.历史) - 1

        self._更新导航钮()
        self.重载()

    def _打开远程(self, 网址: str, 记录历史: bool = True) -> None:
        """从 http(s) 地址取回爻页源码并渲染。"""
        self.当前路径 = 网址
        self._远程源码 = ""
        self.地址框.delete(0, "end")
        self.地址框.insert(0, 网址)

        if 记录历史:
            if self.历史位 >= 0 and self.历史位 < len(self.历史) - 1:
                self.历史 = self.历史[: self.历史位 + 1]
            if not self.历史 or self.历史[-1] != 网址:
                self.历史.append(网址)
            self.历史位 = len(self.历史) - 1

        self._更新导航钮()
        self.重载()

    def _显示路径(self, 路径: str) -> str:
        根 = os.getcwd()
        try:
            if os.path.abspath(路径).startswith(os.path.abspath(根)):
                return os.path.relpath(路径, 根).replace("\\", "/")
        except Exception:
            pass
        return 路径

    def 后退(self) -> None:
        if self.历史位 > 0:
            self.历史位 -= 1
            self.打开(self.历史[self.历史位])
            self._更新导航钮()

    def 前进(self) -> None:
        if self.历史位 < len(self.历史) - 1:
            self.历史位 += 1
            self.打开(self.历史[self.历史位])
            self._更新导航钮()

    def _更新导航钮(self) -> None:
        self.后退钮.configure(state="normal" if self.历史位 > 0 else "disabled")
        self.前进钮.configure(
            state="normal" if self.历史位 < len(self.历史) - 1 else "disabled"
        )

    # ---------- 渲染 ----------

    def 重载(self) -> None:
        self.重载并渲染()

    def _取源码(self) -> tuple[str, str] | None:
        """取页面源码。返回 (源码, 显示名)；失败返回 None。"""
        路径 = self.当前路径

        # ---- 远程 ----
        if 路径.startswith("http://") or 路径.startswith("https://"):
            try:
                import urllib.request
                from urllib.parse import quote, urlsplit, urlunsplit

                # 中文路径要百分号编码
                try:
                    拆 = urlsplit(路径)
                    址 = urlunsplit((
                        拆.scheme, 拆.netloc,
                        quote(拆.path, safe="/%:@&=+$,;~*'()![]"),
                        quote(拆.query, safe="=&%:@+$,;~*'()![]/?"),
                        拆.fragment,
                    ))
                except Exception:
                    址 = 路径

                req = urllib.request.Request(
                    址, headers={"User-Agent": "YaoPage-Browser/0.1"}
                )
                with urllib.request.urlopen(req, timeout=15) as r:
                    原始 = r.read()
                    类型 = (r.headers.get("Content-Type") or "").lower()
                    编码 = "utf-8"
                    if "charset=" in 类型:
                        编码 = 类型.split("charset=")[-1].split(";")[0].strip() or "utf-8"
                    文 = 原始.decode(编码, errors="replace")
                self._远程源码 = 文
                self.状态.configure(text=f"已从 {路径} 取回页面", fg="#7ee787")
                return 文, 路径
            except Exception as e:
                self._显示错误(f"无法打开网址：{e}\n\n{路径}")
                return None

        # ---- 本地 ----
        try:
            with open(路径, "r", encoding="utf-8") as f:
                文 = f.read()
            self._远程源码 = None
            return 文, 路径
        except OSError as e:
            self._显示错误(f"无法打开文件：{e}")
            return None

    def 重载并渲染(self) -> None:
        """重新解析 + 重新布局 + 重新绘制。"""
        起 = time.perf_counter()
        取出 = self._取源码()
        if 取出 is None:
            return
        源, 显示名 = 取出

        try:
            页面 = 分析文本(源, 显示名)
            self.页面对象 = 页面

            # 状态初始化（保留已有状态值，以支持重绘时不丢输入）
            旧状态 = dict(self.求值器.状态) if self.求值器 else {}
            外部 = getattr(self, "待传入参数", {}) or {}
            状态 = {}
            for 声明 in 页面.态:
                if 声明.名 in 外部:
                    状态[声明.名] = 外部[声明.名]
                    continue
                求 = 求值器({**旧状态, **状态}, 外部)
                状态[声明.名] = 求.求值(声明.值)
            外部 = {**外部, "响应": getattr(self, "最近响应", None)}
            self.求值器 = 求值器(状态, 外部)
            self.求值器.调用后端 = self._调后端

            # 注册页面内定义的函数（必须在执行「始」之前）
            for 函数 in (getattr(页面, "函数们", None) or []):
                self.求值器.函数表[函数.名] = 函数

            # 执行「始」块（取数据、初始化）
            if 页面.始 is not None:
                self.求值器.允许新建 = True
                try:
                    self.求值器.执行块(页面.始)
                except 爻页误 as ex:
                    self.状态.configure(text=f"始块出错：{ex.格式化()}", fg="#ff6b6b")
                finally:
                    self.求值器.允许新建 = False

            self.根.title(f"{页面.标题} — {名称} 浏览器")
            self._重绘()
            self.渲染耗时 = (time.perf_counter() - 起) * 1000
            self._更新状态栏()
            self._启动定时()
        except 爻页误 as e:
            self._显示错误(e.格式化())
        except Exception as e:  # 兜底，绝不让浏览器崩
            import traceback
            末 = traceback.format_exc().strip().splitlines()[-1]
            self._显示错误(f"内误：{type(e).__name__}: {e}\n{末}")

    def _取消定时(self) -> None:
        """取消所有已排队的定时刷新。"""
        for 句柄 in self._定时句柄:
            try:
                self.根.after_cancel(句柄)
            except Exception:
                pass
        self._定时句柄.clear()
        self._定时运行中 = False

    def _启动定时(self) -> None:
        """按页面里声明的「次」块排定定时刷新。"""
        self._取消定时()
        if self.页面对象 is None or self.求值器 is None:
            return
        定时们 = getattr(self.页面对象, "定时们", None) or []
        if not 定时们:
            return

        for 块 in 定时们:
            try:
                间隔 = float(self.求值器.求值(块.间隔))
            except 爻页误:
                continue
            except Exception:
                continue
            if 间隔 < 16:
                间隔 = 16.0
            if 间隔 > 3_600_000:
                间隔 = 3_600_000.0
            self._排一次(块, 间隔)

    def _排一次(self, 块, 间隔: float) -> None:
        """排下一次执行。"""
        def 触发() -> None:
            if self.求值器 is None or self.页面对象 is None:
                return
            # 页面已换掉就停
            if 块 not in (getattr(self.页面对象, "定时们", None) or []):
                return
            try:
                self.求值器.允许新建 = True
                try:
                    self.求值器.执行块(块.体)
                finally:
                    self.求值器.允许新建 = False
                self._重绘()
                self._更新状态栏()
            except 爻页误 as ex:
                self.状态.configure(text=f"定时块出错：{ex.格式化()}", fg="#ff6b6b")
            except Exception as ex:
                self.状态.configure(text=f"定时块出错：{ex}", fg="#ff6b6b")
            # 继续排下一次（除非页面已换）
            if self.页面对象 is not None and 块 in (getattr(self.页面对象, "定时们", None) or []):
                self._排一次(块, 间隔)

        try:
            句柄 = self.根.after(int(间隔), 触发)
            self._定时句柄.append(句柄)
            self._定时运行中 = True
        except Exception:
            pass

    def _重绘(self) -> None:
        """只重算布局与绘制，不重新解析。"""
        if self.页面对象 is None or self.求值器 is None:
            return
        宽 = max(1, self.画布.winfo_width())
        高 = max(1, self.画布.winfo_height())
        self.根盒 = 布局(self.页面对象, self.求值器, 宽, 高)

        # ---- 计算可滚动范围 ----
        if self.根盒 is not None:
            内容宽 = float(self.根盒.get("宽") or 0)
            内容高 = float(self.根盒.get("高") or 0)
            self.可滚宽 = max(0.0, 内容宽 - 宽)
            self.可滚高 = max(0.0, 内容高 - 高)
        else:
            self.可滚宽 = self.可滚高 = 0.0

        # 偏移越界时夹回来（切页面后内容可能变短）
        self.滚动Y = max(0.0, min(self.滚动Y, self.可滚高))
        self.滚动X = max(0.0, min(self.滚动X, self.可滚宽))

        self.渲染器.渲染(self.根盒, self.滚动X, self.滚动Y)
        self._画滚动条()

    # ---------- 滚动 ----------

    def _滚动(self, 方向: int) -> None:
        """方向：-1 上，1 下。每次滚 3 行左右。"""
        if self.可滚高 <= 0:
            return
        self.滚动Y = max(0.0, min(self.滚动Y + 方向 * 60.0, self.可滚高))
        self._重绘()

    def _滚轮(self, 事件) -> None:
        """鼠标滚轮。Windows 上 delta = ±120 的倍数。"""
        if self.可滚高 <= 0 and self.可滚宽 <= 0:
            return
        步 = 60.0
        if getattr(事件, "state", 0) & 0x0001:      # Shift 按住 → 横向
            if self.可滚宽 <= 0:
                return
            方向 = -1 if 事件.delta > 0 else 1
            self.滚动X = max(0.0, min(self.滚动X + 方向 * 步, self.可滚宽))
        else:
            if self.可滚高 <= 0:
                return
            方向 = -1 if 事件.delta > 0 else 1
            self.滚动Y = max(0.0, min(self.滚动Y + 方向 * 步, self.可滚高))
        self._重绘()

    def _滚动条区域(self) -> tuple[float, float, float, float] | None:
        """返回滚动条的 (x, y, 宽, 高)，不可滚时返回 None。"""
        if self.可滚高 <= 0:
            return None
        宽 = max(1, self.画布.winfo_width())
        高 = max(1, self.画布.winfo_height())
        条宽 = 14.0
        return (宽 - 条宽 - 3, 4.0, 条宽, 高 - 8.0)

    def _滚动条滑块(self) -> tuple[float, float, float, float] | None:
        """返回滑块的 (x, y, 宽, 高)，不可滚时返回 None。"""
        区域 = self._滚动条区域()
        if 区域 is None:
            return None
        x, y, 宽, 高 = 区域
        内容高 = 高 + self.可滚高
        滑块高 = max(28.0, 高 * (高 / 内容高))
        最大位移 = 高 - 滑块高
        比例 = (self.滚动Y / self.可滚高) if self.可滚高 > 0 else 0.0
        滑块y = y + 最大位移 * 比例
        return (x, 滑块y, 宽, 滑块高)

    def _画滚动条(self) -> None:
        """在画布上画垂直滚动条（画在最上层）。"""
        self.画布.delete("滚动条")
        区域 = self._滚动条区域()
        if 区域 is None:
            return
        x, y, 宽, 高 = 区域
        # 轨道（比背景稍亮，能看出范围）
        self._圆角条(x, y, x + 宽, y + 高, 宽 / 2, "#24304d")
        滑块 = self._滚动条滑块()
        if 滑块:
            sx, sy, s宽, s高 = 滑块
            # 滑块（亮色，一眼能看到）
            self._圆角条(sx + 2, sy, sx + s宽 - 2, sy + s高, (s宽 - 4) / 2, "#7ee787")

    def _圆角条(self, x1: float, y1: float, x2: float, y2: float,
                半径: float, 填充: str) -> None:
        """画一个圆角长条（用矩形+两端圆近似）。"""
        半径 = max(0.0, min(半径, (x2 - x1) / 2, (y2 - y1) / 2))
        if 半径 < 1:
            self.画布.create_rectangle(x1, y1, x2, y2, fill=填充,
                                       outline="", tags="滚动条")
            return
        self.画布.create_rectangle(x1 + 半径, y1, x2 - 半径, y2,
                                   fill=填充, outline="", tags="滚动条")
        self.画布.create_oval(x1, y1, x1 + 2 * 半径, y2,
                              fill=填充, outline="", tags="滚动条")
        self.画布.create_oval(x2 - 2 * 半径, y1, x2, y2,
                              fill=填充, outline="", tags="滚动条")

    def _按下(self, 事件) -> None:
        """点在滑块上 → 开始拖动。"""
        滑块 = self._滚动条滑块()
        if 滑块 is None:
            return
        sx, sy, s宽, s高 = 滑块
        if sx <= 事件.x <= sx + s宽 and sy <= 事件.y <= sy + s高:
            self._拖滚动条 = True
            self._拖起点Y = 事件.y
            self._拖起始滚动 = self.滚动Y

    def _拖动(self, 事件) -> None:
        if not self._拖滚动条:
            return
        区域 = self._滚动条区域()
        滑块 = self._滚动条滑块()
        if 区域 is None or 滑块 is None:
            return
        _, _, _, 高 = 区域
        _, _, _, 滑块高 = 滑块
        最大位移 = 高 - 滑块高
        if 最大位移 <= 0:
            return
        位移 = 事件.y - self._拖起点Y
        self.滚动Y = max(0.0, min(
            self._拖起始滚动 + (位移 / 最大位移) * self.可滚高,
            self.可滚高,
        ))
        self._重绘()

    def _松开(self, 事件) -> None:
        self._拖滚动条 = False

    def _更新状态栏(self) -> None:
        if self.根盒 is None:
            return
        数 = sum(1 for _ in 遍历(self.根盒))
        标题 = self.页面对象.标题 if self.页面对象 else ""
        态数 = len(self.求值器.状态) if self.求值器 else 0
        self.状态.configure(
            text=f"就绪 · {标题} · 元素 {数} 个 · 状态 {态数} 个 · 渲染 {self.渲染耗时:.1f} ms",
            fg="#8b9ab8",
        )

    def _显示错误(self, 文: str) -> None:
        self.画布.delete("all")
        宽 = max(1, self.画布.winfo_width())
        self.画布.create_text(
            宽 / 2, 60,
            text="页面出错了",
            fill="#ff6b6b", font=("Microsoft YaHei UI", 18, "bold"), anchor="n",
        )
        self.画布.create_text(
            30, 120, text=文, fill="#ffb3b3",
            font=("Cascadia Code", 11), anchor="nw", width=宽 - 60,
        )
        self.状态.configure(text="出错：" + 文.splitlines()[0], fg="#ff6b6b")

    # ---------- 事件 ----------

    def _窗口改变(self, e) -> None:
        self._重绘()

    def _命中(self, x: float, y: float) -> dict | None:
        if self.根盒 is None:
            return None
        # 鼠标坐标是视口坐标，加上滚动偏移才是内容坐标
        return 命中最上层(self.根盒, x + self.滚动X, y + self.滚动Y)

    def _点击(self, e) -> None:
        if self.根盒 is None or self.求值器 is None:
            return
        盒 = self._命中(e.x, e.y)
        if 盒 is None:
            self.输入焦点标识 = None
            self._重绘()
            return

        if 盒["类"] == "输":
            self.输入焦点标识 = 盒["标识"]
            self.状态.configure(text=f"输入中：{盒.get('绑定', '')}", fg="#7ee787")
            self._重绘()
            return

        self.输入焦点标识 = None
        if 盒["类"] == "钮" and 盒.get("点") is not None:
            try:
                # 恢复「列」展开时的项变量（贴 / 项序 / 该项键）
                绑定 = 盒.get("项绑定") or {}
                for k, v in 绑定.items():
                    self.求值器.状态[k] = v
                self.求值器.执行块(盒["点"])
                self._重绘()
                self._更新状态栏()
                self._执行动作()
            except 爻页误 as ex:
                self._显示错误(ex.格式化())

    def _调后端(self, 路径: str, 体) -> dict:
        """爻页 `调` 语句的实现：向爻语后端发请求，返回解析后的 JSON。"""
        import json as _json
        import urllib.error
        import urllib.request

        # 路径里的中文必须百分号编码（HTTP 请求行只能是 ASCII）
        from urllib.parse import quote

        def _编码(u: str) -> str:
            try:
                from urllib.parse import urlsplit, urlunsplit
                拆 = urlsplit(u)
                return urlunsplit((
                    拆.scheme, 拆.netloc,
                    quote(拆.path, safe="/%:@&=+$,;~*'()![]"),
                    quote(拆.query, safe="=&%:@+$,;~*'()![]/?"),
                    拆.fragment,
                ))
            except Exception:
                return u

        if 路径.startswith("http"):
            址 = _编码(路径)
        else:
            址 = _编码(f"http://127.0.0.1:8793{路径}")
        令牌 = ""
        if isinstance(体, dict) and "_令牌" in 体:
            令牌 = 转字(体.pop("_令牌"))
        elif self.求值器 is not None:
            令牌 = 转字(self.求值器.状态.get("令牌", "") or "")

        数据 = _json.dumps(体, ensure_ascii=False).encode("utf-8") if 体 is not None else None
        头 = {"Content-Type": "application/json; charset=utf-8"}
        if 令牌:
            头["X-Token"] = 令牌

        req = urllib.request.Request(
            址, data=数据, headers=头, method="POST" if 数据 else "GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                结果 = _json.loads(r.read().decode("utf-8") or "null")
                self.最近响应 = 结果
                return 结果
        except urllib.error.HTTPError as e:
            try:
                结果 = _json.loads(e.read().decode("utf-8") or "null")
            except Exception:
                结果 = {"错": f"HTTP {e.code}"}
            self.最近响应 = 结果
            return 结果
        except Exception as e:
            self.最近响应 = {"错": f"{type(e).__name__}: {e}"}
            return self.最近响应

    def _解析跳转目标(self, 目标: str) -> str:
        """把「跳」的目标解析成可打开的地址。

        分两种情况：
          * 当前页面来自 http(s) → 拼成 URL（页面名去 .页 后缀，走 /页/名）
          * 当前页面是本地文件   → 相对当前文件目录解析（原行为）
        """
        if not isinstance(目标, str):
            目标 = str(目标)

        # 目标本身已经是绝对地址
        if 目标.startswith(("http://", "https://")) or os.path.isabs(目标):
            return 目标

        当前 = self.当前路径 or ""

        # ---- 当前是远程页面 ----
        if 当前.startswith(("http://", "https://")):
            import urllib.parse as _up

            # 去掉 .页 后缀 —— 后端的 /页/:名 接口自己会补
            页名 = 目标
            if 页名.endswith(后缀):
                页名 = 页名[: -len(后缀)]

            拆 = _up.urlsplit(当前)

            # 目标里带子目录（如 "页面/总览.页"）就按相对路径拼
            if "/" in 页名 or "\\" in 页名:
                基路径 = 拆.path.rsplit("/", 1)[0] + "/"
                新路径 = _up.urljoin(基路径, 页名.replace("\\", "/"))
            else:
                # 简单页面名 → /页/名
                前缀 = 拆.path.rsplit("/", 1)[0]  # "" 或 "/页"
                if 前缀.endswith("/页"):
                    新路径 = f"{前缀}/{页名}"
                else:
                    新路径 = f"/页/{页名}"

            # 保留 #hash 形式的参数
            片 = ""
            if "#" in 目标:
                页名2, 片 = 目标.split("#", 1)
                if "/" not in 页名2 and "\\" not in 页名2:
                    新路径 = f"/页/{页名2[:-len(后缀)] if 页名2.endswith(后缀) else 页名2}"
                片 = "#" + 片

            return _up.urlunsplit((拆.scheme, 拆.netloc, 新路径, 拆.query, 片))

        # ---- 当前是本地文件 ----
        if not os.path.isfile(os.path.join(os.getcwd(), 目标)):
            候选 = os.path.join(os.path.dirname(当前), 目标)
            if os.path.isfile(候选) or os.path.isfile(候选 + 后缀):
                return 候选
        return 目标

    def _执行动作(self) -> None:
        """处理点块里产生的「跳」「发」动作。"""
        import json as _json

        for 动作 in self.求值器.取动作():
            if 动作[0] == "跳":
                目标 = self._解析跳转目标(动作[1])
                self.打开(目标, 记录历史=True)
                return
            if 动作[0] == "发":
                _, 接口, 体 = 动作
                try:
                    import urllib.request

                    令牌 = ""
                    if isinstance(体, dict) and "_令牌" in 体:
                        令牌 = 转字(体.pop("_令牌"))
                    址 = 接口 if 接口.startswith("http") else "http://127.0.0.1:8793" + 接口
                    数据 = _json.dumps(体, ensure_ascii=False).encode("utf-8") if 体 is not None else None
                    头 = {"Content-Type": "application/json; charset=utf-8"}
                    if 令牌:
                        头["X-Token"] = 令牌
                    req = urllib.request.Request(
                        址, data=数据, headers=头,
                        method="POST" if 数据 else "GET",
                    )
                    with urllib.request.urlopen(req, timeout=15) as r:
                        self.最近响应 = _json.loads(r.read().decode("utf-8") or "null")
                    self.状态.configure(text="已提交，正在刷新…", fg="#7ee787")
                    self.重载并渲染()
                except urllib.error.HTTPError as e:
                    try:
                        self.最近响应 = _json.loads(e.read().decode("utf-8") or "null")
                    except Exception:
                        self.最近响应 = None
                    self.状态.configure(text=f"提交被拒：{e.code}", fg="#ff6b6b")
                    self.重载并渲染()
                except Exception as e:
                    self.状态.configure(text=f"提交失败：{e}", fg="#ff6b6b")
                return

    def _移动(self, e) -> None:
        盒 = self._命中(e.x, e.y)
        新 = 盒 if (盒 is not None and 盒["类"] in ("钮", "输")) else None
        if 新 is not self.悬停盒:
            self.悬停盒 = 新
            self.画布.configure(cursor="hand2" if (新 and 新.get("手")) else "")
            if self.根盒 is not None:
                self._重绘()

    def _设悬停(self, 盒: dict | None) -> None:
        self.悬停盒 = 盒

    def _按键(self, e) -> None:
        """输入框获得焦点时接收键盘输入。"""
        if self.输入焦点标识 is None or self.求值器 is None or self.根盒 is None:
            return
        if e.keysym in ("BackSpace", "Return", "Escape", "Tab",
                        "Left", "Right", "Up", "Down", "Control_L", "Control_R",
                        "Shift_L", "Shift_R", "Alt_L", "Alt_R"):
            return
        ch = e.char
        if not ch or ord(ch) < 32:
            return
        self._追加输入(ch)

    def _退格(self, e) -> None:
        if self.输入焦点标识 is None or self.求值器 is None or self.根盒 is None:
            return
        盒 = 找盒(self.根盒, self.输入焦点标识)
        if 盒 is None or 盒["类"] != "输":
            return
        绑定 = 盒.get("绑定", "")
        if not 绑定:
            return
        原 = str(self.求值器.状态.get(绑定, ""))
        self.求值器.状态[绑定] = 原[:-1]
        self._重绘()

    def _追加输入(self, ch: str) -> None:
        if self.根盒 is None or self.求值器 is None:
            return
        盒 = 找盒(self.根盒, self.输入焦点标识)
        if 盒 is None or 盒["类"] != "输":
            return
        绑定 = 盒.get("绑定", "")
        if not 绑定:
            return
        原 = str(self.求值器.状态.get(绑定, ""))
        self.求值器.状态[绑定] = 原 + ch
        self._重绘()

    # ---------- 运行 ----------

    def 运行(self) -> None:
        self.根.protocol("WM_DELETE_WINDOW", self._关闭)
        self.根.mainloop()

    def _关闭(self) -> None:
        self._取消定时()
        try:
            self.根.destroy()
        except Exception:
            pass


def 启动(路径: str | None = None) -> int:
    浏 = 浏览器(初始页=路径)
    浏.运行()
    return 0
