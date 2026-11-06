"""文件编码自动识别。

Windows 上用户用记事本存文件，可能是 GBK / UTF-8-BOM / UTF-16。
这些都要能读，否则用户会觉得「解释器坏了」。
"""

from __future__ import annotations

from pathlib import Path


def 读文本(路径: str | Path) -> str:
    """读文本文件，自动识别编码。"""
    数据 = Path(路径).read_bytes()

    # 1. UTF-8 BOM
    if 数据[:3] == b"\xef\xbb\xbf":
        return 数据[3:].decode("utf-8")

    # 2. UTF-16 BOM
    if 数据[:2] == b"\xff\xfe":
        return 数据[2:].decode("utf-16-le")
    if 数据[:2] == b"\xfe\xff":
        return 数据[2:].decode("utf-16-be")

    # 3. 尝试 UTF-8
    try:
        return 数据.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 4. 无 BOM 的 UTF-16 启发式：大量 0x00
    if len(数据) >= 4:
        样 = 数据[:400]
        偶零 = sum(1 for i in range(0, len(样) - 1, 2) if 样[i] == 0)
        奇零 = sum(1 for i in range(1, len(样), 2) if 样[i] == 0)
        if 偶零 > len(样) // 4 and 偶零 > 奇零 * 3:
            return 数据.decode("utf-16-be", errors="replace")
        if 奇零 > len(样) // 4 and 奇零 > 偶零 * 3:
            return 数据.decode("utf-16-le", errors="replace")

    # 5. GBK（记事本中文默认）
    for 编码 in ("gbk", "gb18030", "gb2312"):
        try:
            return 数据.decode(编码)
        except UnicodeDecodeError:
            continue

    # 6. 最后兜底
    return 数据.decode("utf-8", errors="replace")


def 写文本(路径: str | Path, 内容: str) -> None:
    """写文本文件（统一 UTF-8 无 BOM）。"""
    Path(路径).write_text(内容, encoding="utf-8", newline="\n")
