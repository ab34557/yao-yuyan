"""爻语命令行入口。

    python -m yao 跑 文件.yao [参数…]
    python -m yao 台
    python -m yao 站 [端口]
    python -m yao 检 文件.yao
    python -m yao 版
    python -m yao 帮
"""

from __future__ import annotations

import os
import sys

from . import 版本, 名称, 后缀
from .errors import 爻误


def _修编码() -> None:
    for 流名 in ("stdout", "stderr"):
        流 = getattr(sys, 流名, None)
        if 流 is not None and hasattr(流, "reconfigure"):
            try:
                流.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover
                pass


帮助文 = f"""{名称}（Yao）v{版本} —— 中文单字关键字的编程语言

用法：
  python -m yao 跑 {后缀[1:]}文件{后缀} [参数…]   执行脚本
  python -m yao 台                      交互式解释器
  python -m yao 站 [端口]                启动在线 IDE（默认 8787）
  python -m yao 检 文件{后缀}             只做词法/语法检查
  python -m yao 版                       打印版本
  python -m yao 帮                       打印本帮助

示例：
  python -m yao 跑 examples\\示例\\你好.yao
  python -m yao 站 8787

语言速览：
  42 名 答案            值在左的绑定
  匠 加(甲, 乙) 【 归 甲 + 乙 】
  判 值 【 0 ⇒ 显("零")；它 ⇒ 显("非零") 】
  [1, 2, 3] ▷ 筛((x) ⇒ x > 1) ▷ 显
  python -m yao 站 打开网页版编辑器，内置关键字与内置函数速查。
"""


def _帮助主题(主题: str) -> str:
    """分级帮助（与 C 版一致）。"""
    if 主题 in ("语法", "syntax"):
        return """爻语语法速查
=============

【关键字】29 个单字
  名 易 匠 节 归 判 它 遍 于 环 自 至 步 循 断 续
  试 捕 终 抛 引 出 注 真 假 空 且 或 非

【变量】值在左，名字在右
  42 名 答案           把 42 绑定到「答案」
  答案 + 1 易 答案     把「答案」改成 43

【块】用 【 】 括起来
  匠 加(甲, 乙) 【
    归 甲 + 乙
  】

【条件】
  判 分数 >= 60 【
    真 ⇒ 显("及格")
    它 ⇒ 显("不及格")
  】

【循环】
  0 名 i
  循 i < 5 【 显(i)  i + 1 易 i 】
  环 i 自 0 至 5 【 显(i) 】
  遍 项 于 [1, 2, 3] 【 显(项) 】

【函数】
  匠 平方(x) 【 归 x * x 】
  节 (x) 【 归 x * x 】      匿名函数

【集合】
  [1, 2, 3] 名 列
  { "甲" ⇒ 1 } 名 表
  显(列[0])   显(表["甲"])   显(长(列))

【高阶】
  映([1,2,3], 节 (x) 【 归 x * x 】)
  筛([1,2,3,4], 节 (x) 【 归 x % 2 == 0 】)
  折([1,2,3], 节 (a,b) 【 归 a+b 】, 0)

【异常】
  试 【 1/0 名 危险 】 捕 误 【 显("出错") 】

【注释】
  注 这是注释
"""
    if 主题 in ("命令", "cmd"):
        return """爻语命令行

  python -m yao 跑 文件.yao    运行程序
  python -m yao 台             进入 REPL
  python -m yao 检 文件.yao    只检查语法
  python -m yao 帮             完整帮助
  python -m yao 帮 语法        语法速查
  python -m yao 版             版本
"""
    if 主题 in ("函数", "func"):
        return """常用内置函数

  显(...)        输出（别名：显示 打印 输出）
  述(...)        输出不换行
  串(x) 数(x) 整(x) 型(x)
  长(x) 切(x,a,b) 含(x,v)
  增(列,v) 删(列,i) 取(表,k,默认) 键集(表)
  映(列,f) 筛(列,f) 折(列,f,初) 排(列)
  分(字,sep) 并(列,sep)
  析(字) 构(值)
  读(路径) 写(路径,内容) 在(路径)
  今() 眠(秒) 停(码) 散列(文) 版本()
  除(a,b) 绝(x) 极(列) 下(列) 舍(x,n) 随(a,b)
"""
    if 主题 in ("示例", "example"):
        return """示例程序

  爻语/示例/示例/你好.yao
  爻语/示例/示例/斐波那契.yao
  爻语/示例/示例/词频.yao
  爻语/示例/示例/错误处理.yao
"""
    可选 = "语法  命令  函数  示例"
    return f"没有「{主题}」这个帮助主题。\n\n可选主题：\n  {可选}\n\n或者直接  yao 帮  看总览。"


def 主(argv: list[str] | None = None) -> int:
    _修编码()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(帮助文)
        return 0

    命令 = argv[0]
    其余 = argv[1:]

    if 命令 in ("版", "版本", "--version", "-v"):
        print(f"{名称}（Yao）v{版本}")
        return 0

    if 命令 in ("帮", "帮助", "help", "--help", "-h"):
        if 其余:
            print(_帮助主题(其余[0]))
        else:
            print(帮助文)
        return 0

    if 命令 == "跑":
        if not 其余:
            print("用法：python -m yao 跑 文件.yao [参数…]")
            return 2
        路径 = 其余[0]
        if not os.path.isfile(路径) and os.path.isfile(路径 + 后缀):
            路径 = 路径 + 后缀
        if not os.path.isfile(路径):
            print(f"文件不存在：{路径}")
            return 2
        from .interpreter import 运行文件

        代码 = 运行文件(路径, 参数=其余[1:])
        return 代码

    if 命令 == "检":
        if not 其余:
            print("用法：python -m yao 检 文件.yao")
            return 2
        路径 = 其余[0]
        if not os.path.isfile(路径) and os.path.isfile(路径 + 后缀):
            路径 = 路径 + 后缀
        from .lexer import 切分
        from .parser import 分析

        try:
            from .编码 import 读文本
            源 = 读文本(路径)
        except OSError as e:
            print(f"无法读取文件「{路径}」：{e}")
            return 2
        try:
            分析(切分(源, os.path.realpath(路径)), os.path.realpath(路径))
        except 爻误 as e:
            print(e.格式化())
            return 1
        print(f"检查通过：{路径}")
        return 0

    if 命令 == "站":
        端口 = 8787
        if 其余:
            try:
                端口 = int(其余[0])
            except ValueError:
                print(f"端口必须是整数：{其余[0]}")
                return 2
        from .ide_server import 启动

        return 启动(端口)

    if 命令 == "台":
        return _交互()

    if 命令 == "自举":
        # 用「爻语自己写的解释器」跑程序（验证自举 / 教学演示）
        if not 其余:
            print("用法：python -m yao 自举 文件.yao")
            print("")
            print("用 爻语/解释器/自举版/解释器.yao（爻语写的解释器）执行文件。")
            print("这是自举验证入口，比 Python 版慢，但完全不依赖 Python 的实现逻辑。")
            return 2
        return _跑自举(其余[0], 其余[1:])

    if 命令.endswith(".yao") or os.path.isfile(命令 + 后缀):
        # 允许 `python -m yao 文件.yao`
        路径 = 命令 if os.path.isfile(命令) else 命令 + 后缀
        from .interpreter import 运行文件

        return 运行文件(路径, 参数=其余)

    print(f"未知命令「{命令}」。用 `python -m yao 帮` 查看用法。")
    return 2


def _跑自举(路径: str, 参数: list[str]) -> int:
    """用爻语写的解释器（自举版）执行一个 .yao 文件。"""
    import sys
    import threading

    真路径 = 路径 if os.path.isfile(路径) else 路径 + 后缀
    if not os.path.isfile(真路径):
        print(f"找不到文件：{路径}")
        return 1

    # 定位自举解释器：项目根/爻语/解释器/自举版/解释器.yao
    这里 = os.path.dirname(os.path.abspath(__file__))          # …/爻语/解释器/python版
    候选们 = [
        os.path.join(这里, "..", "自举版", "解释器.yao"),
        os.path.join(这里, "..", "..", "..", "爻语", "解释器", "自举版", "解释器.yao"),
    ]
    解释器文件 = None
    for c in 候选们:
        c = os.path.normpath(c)
        if os.path.isfile(c):
            解释器文件 = c
            break
    if 解释器文件 is None:
        print("找不到自举解释器（爻语/解释器/自举版/解释器.yao）")
        return 1

    # 大栈：自举解释器递归很深
    try:
        threading.stack_size(64 * 1024 * 1024)
        sys.setrecursionlimit(30000)
    except (ValueError, RuntimeError):
        pass

    from .interpreter import 解释器

    自举源 = open(解释器文件, encoding="utf-8").read()
    i = 自举源.find("注 ---------- 测试 ----------")
    if i > 0:
        自举源 = 自举源[:i]

    程序源 = open(真路径, encoding="utf-8").read()
    转义 = (
        程序源.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )

    print(f"【自举解释器】{真路径}")
    print("")
    结果 = [0]

    def _出(文本: str) -> None:
        sys.stdout.write(文本)

    驱动 = f'{自举源}\n\n注 ===== 驱动 =====\n自举解释("{转义}")\n'
    try:
        解释器(输出=_出).运行源码(驱动, "<自举>")
    except Exception as e:  # noqa: BLE001
        print(f"\n【自举解释器】出错：{e}")
        结果[0] = 1
    print("")
    return 结果[0]


def _交互() -> int:
    from .interpreter import 解释器

    print(f"{名称}（Yao）v{版本} 交互式解释器。输入「退出」或按 Ctrl+D 结束。")
    y = 解释器()
    from .errors import 爻误

    缓冲: list[str] = []
    待续 = False
    while True:
        try:
            提示 = "… " if 缓冲 else "爻> "
            行 = input(提示)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:  # pragma: no cover
            print("\n（用「退出」离开）")
            缓冲.clear()
            待续 = False
            continue
        if not 缓冲 and 行.strip() in ("退出", "exit", "quit", "q"):
            return 0
        # REPL 内置命令：help / 帮助 / ?
        if not 缓冲:
            命令词 = 行.strip()
            纯命令 = 命令词.lstrip("./")
            头词 = 纯命令.split()[0] if 纯命令.split() else ""
            if 头词 in ("help", "h", "?", "帮助", "HELP", "Help"):
                剩余 = 纯命令.split()[1:] if len(纯命令.split()) > 1 else []
                if 剩余:
                    print(_帮助主题(剩余[0]))
                else:
                    print(帮助文)
                continue
        缓冲.append(行)
        源 = "\n".join(缓冲)
        待续 = 源.count("【") > 源.count("】")
        if 待续:
            continue
        缓冲.clear()
        if not 源.strip():
            continue
        try:
            y.运行源码(源, "<交互>")
        except 爻误 as e:
            print(e.格式化())
        except SystemExit:
            return 0
