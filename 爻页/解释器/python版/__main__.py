"""爻页入口。

    python -m 爻页                    打开浏览器（默认欢迎页）
    python -m 爻页 示例/计数器.页      打开指定页面
    python -m 爻页 --离屏 页面.页 出.png  无头渲染成图片
    python -m 爻页 --结构 页面.页      打印盒树结构（调试/测试）
    python -m 爻页 --检 页面.页        只做词法+语法检查
"""

from __future__ import annotations

import sys

from . import __version__, 名称, 后缀


def _修编码() -> None:
    for 流名 in ("stdout", "stderr"):
        流 = getattr(sys, 流名, None)
        if 流 is not None and hasattr(流, "reconfigure"):
            try:
                流.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


帮助 = f"""爻页（YaoPage）v{__version__} —— 自创前端语言与浏览器

用法：
  python -m 爻页                    打开浏览器（默认欢迎页）
  python -m 爻页 页面{{suffix}}          打开指定页面
  python -m 爻页 --检 页面{{suffix}}     只做语法检查
  python -m 爻页 --结构 页面{{suffix}}   打印布局盒树
  python -m 爻页 --离屏 页面{{suffix}} 出.png   渲染成图片
  python -m 爻页 --版                打印版本
  python -m 爻页 --帮                打印本帮助
"""

def 主(argv: list[str] | None = None) -> int:
    _修编码()
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        from .浏览器 import 启动
        return 启动(None)

    if argv[0] in ("--版", "--version", "-v"):
        print(f"{名称}（YaoPage）v{__version__}")
        return 0
    if argv[0] in ("--帮", "--help", "-h"):
        print(帮助)
        return 0

    if argv[0] == "--检":
        if len(argv) < 2:
            print("用法：python -m 爻页 --检 页面.页")
            return 2
        from .错误 import 爻页误
        from .语法 import 分析文本

        try:
            with open(argv[1], "r", encoding="utf-8") as f:
                源 = f.read()
            页 = 分析文本(源, argv[1])
        except OSError as e:
            print(f"无法读取文件：{e}")
            return 2
        except 爻页误 as e:
            print(e.格式化())
            return 1
        print(f"检查通过：{argv[1]}（标题「{页.标题}」，状态 {len(页.态)} 个）")
        return 0

    if argv[0] == "--结构":
        if len(argv) < 2:
            print("用法：python -m 爻页 --结构 页面.页")
            return 2
        from .错误 import 爻页误
        from .离屏 import 布局文件, 结构摘要

        try:
            print(结构摘要(布局文件(argv[1], 900, 700)))
        except 爻页误 as e:
            print(e.格式化())
            return 1
        return 0

    if argv[0] == "--离屏":
        if len(argv) < 3:
            print("用法：python -m 爻页 --离屏 页面.页 输出.png [宽 高]")
            return 2
        宽 = int(argv[3]) if len(argv) > 3 else 900
        高 = int(argv[4]) if len(argv) > 4 else 700
        from .错误 import 爻页误
        from .离屏 import 渲染到图片

        try:
            信息 = 渲染到图片(argv[1], argv[2], 宽, 高)
        except 爻页误 as e:
            print(e.格式化())
            return 1
        print(f"已渲染：{argv[2]}（{宽}×{高}，元素 {信息['元素数']} 个）")
        return 0

    # 默认：打开页面
    路径 = argv[0]
    from .错误 import 爻页误
    from .浏览器 import 启动

    try:
        return 启动(路径)
    except 爻页误 as e:
        print(e.格式化())
        return 1


if __name__ == "__main__":
    sys.exit(主())
