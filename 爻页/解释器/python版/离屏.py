"""无头渲染：不开窗口，把 .页 渲染成 PNG + 结构摘要。

用途：
1. 自动化测试（验证布局数值）
2. 导出页面预览图
3. CI 里检查页面是否可渲染

它复用同一套 求值 → 布局 → 渲染 管线，只是把 Canvas 换成离屏绘制。
"""

from __future__ import annotations

import io
import os
from typing import Any

from .错误 import 爻页误
from .布局 import 布局, 遍历, 命中最上层
from .求值 import 求值器
from .语法 import 分析文本


def 加载(
    路径: str, 参数: dict | None = None
) -> tuple[Any, 求值器, str]:
    """解析并初始化状态（含执行「始」块）。返回 (页面, 求值器, 源文本)。"""
    with open(路径, "r", encoding="utf-8") as f:
        源 = f.read()
    页面 = 分析文本(源, 路径)
    外部 = dict(参数 or {})
    状态: dict[str, Any] = {}
    for 声明 in 页面.态:
        if 声明.名 in 外部:
            # URL 参数优先于声明的默认值
            状态[声明.名] = 外部[声明.名]
            continue
        求 = 求值器(状态, 外部)
        状态[声明.名] = 求.求值(声明.值)
    求值 = 求值器(状态, 外部)
    # 注册页面内定义的函数
    for 函数 in (getattr(页面, "函数们", None) or []):
        求值.函数表[函数.名] = 函数
    if 页面.始 is not None:
        求值.允许新建 = True
        try:
            求值.执行块(页面.始)
        finally:
            求值.允许新建 = False
    return 页面, 求值, 源


def 布局文件(
    路径: str, 宽: float = 900, 高: float = 700, 参数: dict | None = None
) -> dict:
    """布局一个 .页 文件（会执行始块取数据），返回盒树。"""
    页面, 求, _ = 加载(路径, 参数)
    return 布局(页面, 求, 宽, 高)


def 结构摘要(盒: dict, 缩进: int = 0) -> str:
    """把盒树变成可读的缩进文本，便于测试断言。"""
    行们: list[str] = []
    式 = 盒.get("式", {})
    描述 = f"{盒['类']}"
    if 盒["类"] == "块":
        描述 += f"({盒.get('布局', '?')})"
    if 盒["类"] in ("文", "钮"):
        描述 += f" «{盒.get('文本', '')[:20]}»"
    if 盒["类"] == "输":
        描述 += f" [{盒.get('绑定', '')}]"
    描述 += f" @({盒['x']:.0f},{盒['y']:.0f}) {盒['宽']:.0f}x{盒['高']:.0f}"
    if 式.get("底"):
        描述 += f" 底={式['底']}"
    行们.append("  " * 缩进 + 描述)
    for 子 in 盒.get("子", []):
        行们.append(结构摘要(子, 缩进 + 1))
    return "\n".join(行们)


def _字体候选(粗: bool = False) -> list[str]:
    """返回可用的中文字体路径候选（绝对路径优先）。

    打包成 exe 后工作目录会变，按裸文件名查找会失败，
    所以显式查系统字体目录。
    """
    import os
    from pathlib import Path as _P

    名们: list[str] = []
    if 粗:
        名们 += ["msyhbd.ttc", "msyhbd.ttf", "simhei.ttf"]
    名们 += ["msyh.ttc", "msyhl.ttc", "simsun.ttc", "simhei.ttf",
             "Deng.ttf", "arialuni.ttf", "arial.ttf"]

    目录们: list[_P] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    目录们.append(_P(windir) / "Fonts")
    # 用户字体目录
    本地 = os.environ.get("LOCALAPPDATA")
    if 本地:
        目录们.append(_P(本地) / "Microsoft" / "Windows" / "Fonts")

    出: list[str] = []
    for 目录 in 目录们:
        for 名 in 名们:
            候选 = 目录 / 名
            if 候选.is_file():
                出.append(str(候选))
    # 兜底：让 Pillow 自己找（某些环境可能能搜到）
    出.extend(名们)
    return 出


def 渲染到图片(路径: str, 输出: str, 宽: int = 900, 高: int = 700,
              背景: str = "#070b16", 参数: dict | None = None) -> dict:
    """渲染 .页 到 PNG（会执行始块取数据）。返回 {元素数, 宽, 高, 盒树}。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise 爻页误("缺少 Pillow，无法离屏渲染")

    页面, 求, _ = 加载(路径, 参数)
    根盒 = 布局(页面, 求, 宽, 高)

    图 = Image.new("RGB", (宽, 高), 背景)
    笔 = ImageDraw.Draw(图)

    def 字体(式: dict):
        大 = int(round(式.get("大", 15)))
        for 候选 in _字体候选(式.get("粗")):
            try:
                return ImageFont.truetype(候选, 大)
            except Exception:
                continue
        return ImageFont.load_default()

    def 颜色(值, 默认=None):
        if not 值:
            return 默认
        try:
            return 值
        except Exception:
            return 默认

    def 画盒(盒: dict, 父x: float = 0.0, 父y: float = 0.0) -> None:
        x, y = 盒["x"] + 父x, 盒["y"] + 父y
        w, h = 盒["宽"], 盒["高"]
        式 = 盒["式"]
        类 = 盒["类"]

        if 式.get("底") or (式.get("边") or 0) > 0:
            圆 = 式.get("圆", 0) or 0
            if 圆 > 0:
                笔.rounded_rectangle(
                    [x, y, x + w, y + h], radius=min(圆, w / 2, h / 2),
                    fill=式.get("底"), outline=式.get("边色") if 式.get("边") else None,
                    width=int(式.get("边") or 1),
                )
            else:
                笔.rectangle(
                    [x, y, x + w, y + h], fill=式.get("底"),
                    outline=式.get("边色") if 式.get("边") else None,
                    width=int(式.get("边") or 1),
                )

        if 类 == "文":
            f = 字体(式)
            色 = 式.get("色") or "#e2e8f0"
            填 = 盒.get("填", 0)
            大 = 式.get("大", 15)
            行高 = 大 * 1.45
            行们 = 盒.get("行们") or [盒.get("文本", "")]
            内宽 = 盒.get("内宽", w)
            齐 = 式.get("齐", "左")
            for i, 行 in enumerate(行们):
                宽行 = 笔.textlength(行, font=f)
                tx = x + 填
                if 齐 == "中":
                    tx = x + 填 + (内宽 - 宽行) / 2
                elif 齐 == "右":
                    tx = x + 填 + 内宽 - 宽行
                笔.text((tx, y + 填 + 行高 * i + (行高 - 大) / 2), 行, font=f, fill=色)

        elif 类 == "钮":
            f = 字体(式)
            文 = 盒.get("文本", "")
            宽文 = 笔.textlength(文, font=f)
            笔.text(
                (x + (w - 宽文) / 2, y + (h - 式.get("大", 15)) / 2 - 2),
                文, font=f, fill=式.get("色") or "#e2e8f0",
            )
        elif 类 == "输":
            f = 字体(式)
            笔.text((x + 12, y + (h - 式.get("大", 15)) / 2 - 2),
                    盒.get("值", ""), font=f, fill=式.get("色") or "#e2e8f0")
        elif 类 == "图线":
            数据 = 盒.get("数据") or []
            笔.rectangle([x, y, x + w, y + h], outline=式.get("边色") or "#24304d")
            if len(数据) >= 2:
                填 = 6.0
                内x1, 内y1 = x + 填, y + 填
                内宽 = max(1.0, w - 2 * 填)
                内高 = max(1.0, h - 2 * 填)
                最大 = max(数据)
                最小 = min(数据)
                幅度 = 最大 - 最小 or max(1.0, abs(最大) if 最大 else 1.0)
                点们 = []
                n = len(数据)
                for i, 值 in enumerate(数据):
                    比例 = (值 - 最小) / 幅度
                    px = 内x1 + 内宽 * (i / (n - 1))
                    py = 内y1 + 内高 * (1.0 - 比例)
                    点们.append((px, py))
                笔.line(点们, fill=式.get("色") or "#7ee787",
                        width=int(式.get("线宽", 2) or 2))
                点色 = 式.get("点色")
                if 点色:
                    for px, py in 点们:
                        笔.ellipse([px - 2.5, py - 2.5, px + 2.5, py + 2.5],
                                   fill=点色)
            else:
                笔.text((x + w / 2 - 30, y + h / 2 - 6), "（数据不足）", fill="#475569")

        elif 类 == "线":
            笔.rectangle([x, y, x + w, y + h], fill=式.get("边色") or "#24304d")
        elif 类 == "图":
            笔.rectangle([x, y, x + w, y + h], outline="#334155")
            笔.text((x + w / 2 - 30, y + h / 2 - 8), "[图片]", fill="#64748b")

        for 子 in 盒.get("子", []):
            画盒(子, x, y)

    画盒(根盒)
    图.save(输出)
    return {
        "元素数": sum(1 for _ in 遍历(根盒)),
        "宽": 宽, "高": 高,
        "标题": 页面.标题,
        "状态": dict(求.状态),
        "盒树": 根盒,
    }
