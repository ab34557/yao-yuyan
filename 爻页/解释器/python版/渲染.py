"""爻页渲染器：把盒树画到 tkinter Canvas 上。

不使用任何 Web 技术：文字、圆角矩形、边框、图片全部用 Canvas 图元手工绘制。
圆角矩形用「多边形 + 平滑」近似，稳定且不依赖平台 API。
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any

from .布局 import 遍历


class 画布渲染器:
    def __init__(self, canvas: tk.Canvas, 图片缓存: dict | None = None) -> None:
        self.c = canvas
        self.图片缓存 = 图片缓存 if 图片缓存 is not None else {}
        self._图对象 = {}

    def 清空(self) -> None:
        self.c.delete("all")
        self._图对象.clear()

    # -- 基础图元 --

    def 圆角矩形(self, x1: float, y1: float, x2: float, y2: float, r: float,
                填充: str | None, 边色: str | None = None, 边宽: float = 0) -> int:
        if x2 <= x1 or y2 <= y1:
            return 0
        r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        if r <= 0.5:
            return self.c.create_rectangle(
                x1, y1, x2, y2,
                fill=填充 if 填充 else "",
                outline=边色 if (边宽 > 0 and 边色) else "",
                width=边宽 if 边宽 > 0 else 0,
            )
        # 用平滑多边形近似圆角矩形
        点们 = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.c.create_polygon(
            点们,
            smooth=True,
            splinesteps=12,
            fill=填充 if 填充 else "",
            outline=边色 if 边宽 > 0 and 边色 else "",
            width=边宽 if 边宽 > 0 else 0,
        )

    def _字体(self, 式: dict) -> tuple:
        大 = int(round(式.get("大", 15)))
        粗 = "bold" if 式.get("粗") else "normal"
        return ("Microsoft YaHei UI", 大, 粗)

    # -- 绘制一个盒 --

    def 画盒(self, 盒: dict, 偏移x: float = 0.0, 偏移y: float = 0.0) -> None:
        """绘制一个盒。

        布局阶段盒的 x/y 是**相对父容器**的坐标；渲染时逐层累加父偏移，
        所以这里把 (偏移x, 偏移y) 加上去，并以 绝对位置 作为子元素的父偏移。
        """
        类 = 盒["类"]
        x = 盒["x"] + 偏移x
        y = 盒["y"] + 偏移y
        宽 = 盒["宽"]
        高 = 盒["高"]
        式 = 盒["式"]

        if 类 == "块":
            底 = 式.get("底")
            边 = 式.get("边", 0) or 0
            圆 = 式.get("圆", 0) or 0
            if 底 or 边 > 0:
                self.圆角矩形(
                    x, y, x + 宽, y + 高, 圆,
                    填充=底, 边色=式.get("边色"), 边宽=边,
                )
            for 子 in 盒.get("子", []):
                self.画盒(子, x, y)
            return

        if 类 == "文":
            底 = 式.get("底")
            边 = 式.get("边", 0) or 0
            圆 = 式.get("圆", 0) or 0
            if 底 or 边 > 0:
                self.圆角矩形(x, y, x + 宽, y + 高, 圆, 填充=底,
                              边色=式.get("边色"), 边宽=边)
            字体 = self._字体(式)
            色 = 式.get("色") or "#e2e8f0"
            填 = 盒.get("填", 0)
            齐 = 式.get("齐", "左")
            行们 = 盒.get("行们") or [盒.get("文本", "")]
            大 = 式.get("大", 15)
            行高 = 大 * 1.45
            内宽 = 盒.get("内宽", 宽 - 2 * 填)
            for i, 行 in enumerate(行们):
                文x, 锚点 = self._对齐(行, 式, 大, 内宽, x + 填, 齐)
                self.c.create_text(
                    文x, y + 填 + 行高 * i + 行高 / 2,
                    text=行, fill=色, font=字体, anchor=锚点,
                )
            return

        if 类 == "钮":
            底 = 式.get("底") or "#1e293b"
            边 = 式.get("边", 0) or 0
            圆 = 式.get("圆", 0) or 0
            self.圆角矩形(x, y, x + 宽, y + 高, 圆, 填充=底,
                          边色=式.get("边色"), 边宽=边)
            大 = 式.get("大", 15)
            self.c.create_text(
                x + 宽 / 2, y + 高 / 2,
                text=盒.get("文本", ""),
                fill=式.get("色") or "#e2e8f0",
                font=self._字体(式),
                anchor="center",
            )
            return

        if 类 == "输":
            底 = 式.get("底") or "#0b1220"
            边 = 式.get("边", 0) or 1
            圆 = 式.get("圆", 0) or 0
            self.圆角矩形(x, y, x + 宽, y + 高, 圆, 填充=底,
                          边色=式.get("边色") or "#334155", 边宽=边)
            大 = 式.get("大", 15)
            self.c.create_text(
                x + 12, y + 高 / 2,
                text=盒.get("值", ""),
                fill=式.get("色") or "#e2e8f0",
                font=self._字体(式),
                anchor="w",
            )
            return

        if 类 == "图":
            self._画图(x, y, 宽, 高, 盒.get("图", ""), 式)
            return

        if 类 == "图线":
            self._画折线(x, y, 宽, 高, 盒)
            return

        if 类 == "线":
            粗 = 盒.get("粗", 1)
            色 = 式.get("边色") or "#24304d"
            self.c.create_rectangle(x, y, x + 宽, y + 粗, fill=色, outline="")
            return

        if 类 == "空":
            return

    def _画折线(self, x: float, y: float, 宽: float, 高: float, 盒: dict) -> None:
        """绘制折线图。

        数据自动按最大值归一化；不足两个点时画一条水平基线。
        """
        式 = 盒["式"]
        数据 = 盒.get("数据") or []
        底 = 式.get("底")
        边 = 式.get("边", 0) or 0
        圆 = 式.get("圆", 0) or 0
        边色 = 式.get("边色")

        # 背景
        if 底 or 边 > 0:
            self.圆角矩形(x, y, x + 宽, y + 高, 圆, 填充=底, 边色=边色, 边宽=边)

        填 = 6.0
        内x1 = x + 填
        内y1 = y + 填
        内宽 = max(1.0, 宽 - 2 * 填)
        内高 = max(1.0, 高 - 2 * 填)

        # 基线（底部）
        底线 = 式.get("底线")
        if 底线:
            self.c.create_line(内x1, 内y1 + 内高, 内x1 + 内宽, 内y1 + 内高,
                               fill=底线, width=1)

        if len(数据) < 2:
            # 数据不足：画个提示
            self.c.create_text(
                x + 宽 / 2, y + 高 / 2,
                text="（数据不足）", fill="#475569",
                font=("Microsoft YaHei UI", 10), anchor="center",
            )
            return

        最大 = max(数据)
        最小 = min(数据)
        幅度 = 最大 - 最小
        if 幅度 <= 0:
            幅度 = max(1.0, abs(最大) if 最大 else 1.0)

        线色 = 式.get("色") or "#7ee787"
        线宽 = 式.get("线宽", 2.0) or 2.0
        点色 = 式.get("点色")

        点们 = []
        n = len(数据)
        for i, 值 in enumerate(数据):
            比例 = (值 - 最小) / 幅度
            px = 内x1 + 内宽 * (i / (n - 1))
            py = 内y1 + 内高 * (1.0 - 比例)
            点们.extend([px, py])

        if 点色:
            # 先画点，免得被线盖住
            for i in range(n):
                px, py = 点们[i * 2], 点们[i * 2 + 1]
                r = 2.5
                self.c.create_oval(px - r, py - r, px + r, py + r,
                                   fill=点色, outline="")

        self.c.create_line(*点们, fill=线色, width=线宽, smooth=False)

    def _对齐(self, 行: str, 式: dict, 大: float, 内宽: float,
              x0: float, 齐: str) -> tuple[float, str]:
        from .布局 import 文本宽

        if 齐 == "中":
            宽 = 文本宽(行, 大)
            return x0 + (内宽 - 宽) / 2, "nw"
        if 齐 == "右":
            宽 = 文本宽(行, 大)
            return x0 + 内宽 - 宽, "nw"
        return x0, "nw"

    def _画图(self, x: float, y: float, 宽: float, 高: float, 路径: str, 式: dict) -> None:
        """加载并绘制图片；失败则画占位框。"""
        if not 路径:
            self._占位(x, y, 宽, 高, "无图片路径")
            return

        真路径 = 路径
        if not os.path.isabs(真路径):
            真路径 = os.path.join(os.getcwd(), 真路径)

        键 = os.path.abspath(真路径)
        if 键 in self.图片缓存:
            图 = self.图片缓存[键]
            if 图 is None:
                self._占位(x, y, 宽, 高, "图片无法加载")
                return
            self.c.create_image(x, y, image=图, anchor="nw")
            return

        try:
            from PIL import Image, ImageTk

            原 = Image.open(真路径)
            原 = 原.resize((max(1, int(宽)), max(1, int(高))), Image.LANCZOS)
            图 = ImageTk.PhotoImage(原)
            self.图片缓存[键] = 图
            self.c.create_image(x, y, image=图, anchor="nw")
        except Exception:
            self.图片缓存[键] = None
            self._占位(x, y, 宽, 高, "图片无法加载")

    def _占位(self, x: float, y: float, 宽: float, 高: float, 文: str) -> None:
        self.c.create_rectangle(
            x, y, x + 宽, y + 高,
            fill="#0b1220", outline="#334155", dash=(4, 4),
        )
        self.c.create_text(
            x + 宽 / 2, y + 高 / 2,
            text=文, fill="#64748b",
            font=("Microsoft YaHei UI", 11), anchor="center",
        )

    # -- 整体 --

    def 渲染(self, 根盒: dict, 滚动x: float = 0.0, 滚动y: float = 0.0) -> None:
        """绘制整棵盒树。滚动x/y 是视口偏移（内容顶部被推上去多少像素）。"""
        self.清空()
        self.画盒(根盒, -滚动x, -滚动y)

    def 高亮悬停(self, 盒: dict | None, 旧盒: dict | None) -> None:
        """用悬底颜色覆盖：简单做法是在盒上再画一层半透明矩形。"""
        if 旧盒 is not None and 旧盒.get("式", {}).get("悬底"):
            x, y = 旧盒["x"], 旧盒["y"]
            self.圆角矩形(
                x, y, x + 旧盒["宽"], y + 旧盒["高"],
                旧盒["式"].get("圆", 0) or 0,
                填充=旧盒["式"].get("底") or "#1e293b",
            )
            if 旧盒["类"] == "钮":
                self.c.create_text(
                    x + 旧盒["宽"] / 2, y + 旧盒["高"] / 2,
                    text=旧盒.get("文本", ""),
                    fill=旧盒["式"].get("色") or "#e2e8f0",
                    font=self._字体(旧盒["式"]), anchor="center",
                )
        if 盒 is not None and 盒.get("式", {}).get("悬底"):
            x, y = 盒["x"], 盒["y"]
            self.圆角矩形(
                x, y, x + 盒["宽"], y + 盒["高"],
                盒["式"].get("圆", 0) or 0,
                填充=盒["式"]["悬底"],
            )
            if 盒["类"] == "钮":
                self.c.create_text(
                    x + 盒["宽"] / 2, y + 盒["高"] / 2,
                    text=盒.get("文本", ""),
                    fill=盒["式"].get("色") or "#e2e8f0",
                    font=self._字体(盒["式"]), anchor="center",
                )
