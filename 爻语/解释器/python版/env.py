"""爻语环境（作用域链）。"""

from __future__ import annotations

from typing import Any, Iterator

from .errors import 名误


class 环境:
    __slots__ = ("父", "表", "导出限制", "模块名", "模块根")

    def __init__(self, 父: 环境 | None = None, 模块名: str = "") -> None:
        self.父 = 父
        self.表: dict[str, Any] = {}
        self.导出限制: list[str] | None = None
        self.模块名 = 模块名
        #: 模块自己的根环境（用于导出，不包含内置层）
        self.模块根: 环境 | None = None

    # -- 读写 ---------------------------------------------------------------

    def 定义(self, 名: str, 值: Any) -> None:
        """在当前作用域新建/覆盖绑定。"""
        self.表[名] = 值

    def 找(self, 名: str) -> 环境 | None:
        env: 环境 | None = self
        while env is not None:
            if 名 in env.表:
                return env
            env = env.父
        return None

    # 常见误写 → 正确写法（与 C 版一致）
    _常见误写 = {
        "显示": "显", "打印": "显", "输出": "显", "印": "显",
        "输入": "输", "读入": "读",
        "长度": "长", "大小": "长", "个数": "长",
        "类型": "型", "种类": "型",
        "转换": "转", "整数": "整", "实数": "数", "数字": "数",
        "字符串": "串", "文本": "串",
        "随机": "随", "睡眠": "眠", "等待": "眠",
        "退出": "停", "结束": "停",
        "绝对值": "绝", "最大": "极", "最小": "下",
        "最大值": "极", "最小值": "下",
        "求和": "折", "累加": "折", "合计": "折", "总和": "折",
        "反转": "反", "颠倒": "反", "倒序": "反",
        "排序": "排", "比对": "比", "比较": "比",
        "去重": "去", "删除": "删", "增加": "增", "添加": "增",
        "筛选": "筛", "过滤": "筛", "映射": "映", "变换": "映",
        "获取": "取", "设置": "置", "替换": "替", "分割": "分",
        "合并": "并", "重复": "复", "裁剪": "裁", "修剪": "裁",
        "时间": "今", "现在": "今", "当前时间": "今",
        "读取": "读", "写入": "写",
        "四舍五入": "舍",
        "解析": "析", "生成": "构",
        "存在": "在", "包含": "含",
    }

    def _建议(self, 名: str) -> str | None:
        """猜用户想用哪个内置函数。"""
        if 名 in self._常见误写:
            return self._常见误写[名]
        # 退一步：名字里包含某个内置函数名（取最长的）
        最佳 = None
        最佳长 = 0
        env = self
        while env is not None:
            for k in env.表:
                if len(k) < len(名) and k in 名 and len(k) > 最佳长:
                    最佳, 最佳长 = k, len(k)
            env = env.父
        return 最佳

    def 取(self, 名: str, 行: int = 0, 列: int = 0) -> Any:
        env = self.找(名)
        if env is None:
            建议 = self._建议(名)
            if 建议:
                raise 名误(
                    f"没有此名字「{名}」，你是不是想用「{建议}」？", 行, 列
                )
            raise 名误(f"没有此名字「{名}」", 行, 列)
        return env.表[名]

    def 改(self, 名: str, 值: Any, 行: int = 0, 列: int = 0) -> None:
        env = self.找(名)
        if env is None:
            raise 名误(f"无法赋值：没有此名字「{名}」（用「名」新建绑定）", 行, 列)
        env.表[名] = 值

    def 有(self, 名: str) -> bool:
        return self.找(名) is not None

    # -- 模块导出 -----------------------------------------------------------

    def 顶层(self) -> 环境:
        env: 环境 = self
        while env.父 is not None:
            env = env.父
        return env

    def 导出表(self) -> dict[str, Any]:
        """模块导出：只导出模块自身作用域的绑定（不含内置层）。"""
        根 = self.模块根 or self
        若 = 根.导出限制
        if 若 is None:
            return dict(根.表)
        结果: dict[str, Any] = {}
        for 名 in 若:
            if 名 in 根.表:
                结果[名] = 根.表[名]
        return 结果

    def 可见名字(self) -> Iterator[str]:
        env: 环境 | None = self
        见 = set()
        while env is not None:
            for k in env.表:
                if k not in 见:
                    见.add(k)
                    yield k
            env = env.父
