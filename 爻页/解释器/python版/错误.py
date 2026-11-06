"""爻页错误。全部中文，带行列定位。"""

from __future__ import annotations


class 爻页误(Exception):
    类 = "误"
    默认文 = "未知错误"

    def __init__(self, 文: str | None = None, 行: int = 0, 列: int = 0) -> None:
        self.文 = 文 or self.默认文
        self.行 = 行
        self.列 = 列
        super().__init__(self.格式化())

    def 头部(self) -> str:
        if self.行:
            return f"第 {self.行} 行 第 {self.列} 列：{self.类}：{self.文}"
        return f"{self.类}：{self.文}"

    def 格式化(self) -> str:
        return self.头部()

    def __str__(self) -> str:
        return self.格式化()


class 词误(爻页误):
    类 = "词误"
    默认文 = "无法识别的字符"


class 法误(爻页误):
    类 = "法误"
    默认文 = "语法错误"


class 名误(爻页误):
    类 = "名误"
    默认文 = "名字不存在"


class 型误(爻页误):
    类 = "型误"
    默认文 = "类型不匹配"


class 值误(爻页误):
    类 = "值误"
    默认文 = "取值非法"


class 图误(爻页误):
    类 = "图误"
    默认文 = "图片无法加载"
