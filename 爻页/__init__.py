"""爻页（YaoPage）包入口 —— 转发到 爻页/解释器/python版/。

这个 shim 让 `import 爻页` 同时兼容开发模式和 PyInstaller 打包模式。
元数据直接写死，不运行时读文件（打包后读不到）。
"""

from pathlib import Path

__version__ = "0.1.0"
名称 = "爻页"
后缀 = ".页"

# 开发模式：把 爻页/解释器/python版 加进包搜索路径
_真目录 = Path(__file__).resolve().parent.parent / "爻页" / "解释器" / "python版"
if _真目录.is_dir():
    __path__ = [str(_真目录)]
