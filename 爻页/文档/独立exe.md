# 爻页浏览器 · 独立可执行版（exe）

把 **爻页浏览器 + 爻语解释器 + 布局引擎 + 渲染器**打包成单个 exe。
**目标机器不需要安装 Python**，拷过去双击就能用。

---


> **运行方式**（两种都行，exe 不需要装 Python）
>
> ```powershell
> 爻页\浏览器\爻页浏览器.exe 页面.页       # 推荐：单文件，可直接分发
> 爻页\浏览器\爻页浏览器.exe 页面.页            # 备选：开发时用
> ```
>
> `爻页浏览器.exe`（14.9 MB）内嵌 Python 运行时，**不需要目标机器装 Python**，
> 但引擎本身是 Python 实现（tkinter 渲染）。它就是这个语言的解释器 + 浏览器。

## 产物

```
bin\爻页浏览器.exe      14.9 MB    单文件，自包含运行时
```

直接把这一个文件拷给别人即可。没有 DLL、没有依赖目录、没有 Python。

---

## 用法

### 双击运行

双击 `爻页浏览器.exe` → 打开浏览器，默认显示欢迎页。

### 命令行

```powershell
# 打开一个页面
爻页浏览器.exe examples\分拣监控\页面\登录.页

# 只给文件名（会在 exe 目录和内置示例里找）
爻页浏览器.exe 登录.页

# 语法检查
爻页浏览器.exe --检 examples\分拣监控\页面\总览.页

# 打印布局盒树（调试）
爻页浏览器.exe --结构 examples\分拣监控\页面\登录.页

# 离屏渲染成 PNG（不需要显示器）
爻页浏览器.exe --离屏 页面.页 输出.png 1024 768

# 版本 / 帮助
爻页浏览器.exe --版
爻页浏览器.exe --帮
```

### 拖拽

把 `.页` 文件拖到 exe 图标上，即可直接打开。

---

## 内置了什么

| 内容 | 说明 |
|---|---|
| **爻页解释器** | 词法 / 语法 / 求值（3 个模块） |
| **布局引擎** | 自己的 flex 式排版算法 |
| **渲染器** | tkinter Canvas 绘制（不用任何 Web 技术） |
| **离屏渲染器** | Pillow 输出 PNG |
| **示例页面** | `示例/` 下 4 个演示页 |
| **分拣监控页面** | `爻语/示例/分拣监控/页面/` 下 9 个页面 |
| **Python 运行时** | 3.11 解释器 + 标准库 |

---

## 验证：真的不依赖 Python

验证方法是**清空 PATH、删除所有 Python 环境变量**，然后运行：

```python
环境 = {
    "PATH": r"C:\Windows\System32;C:\Windows",   # 没有任何 Python
    "SystemRoot": r"C:\Windows",
    # 不设 PYTHONPATH / PYTHONHOME
}
```

确认这个环境里 `where python` 找不到 Python，然后跑 exe：

| 测试 | 结果 |
|---|---|
| `--版` | ✅ 正常输出 v0.1.0 |
| `--帮` | ✅ 正常输出帮助 |
| `--检 页面.页` | ✅ 检查通过 |
| `--离屏 渲染` | ✅ 生成 27 KB PNG |
| **图形窗口启动** | ✅ 窗口出现，中文正常 |

---

## 打包时踩的坑（都修了）

### 1. 包 shim 导致子模块丢失

项目根目录的 `爻页/__init__.py` 是个 **shim**，只做 `__path__` 转发：

```python
_源 = (真目录 / "__init__.py").read_text(encoding="utf-8")
exec(compile(_源, ...), globals())
```

PyInstaller 静态分析时把它当包，结果 `爻页.__main__` 等子模块没被打进去，
运行时 `No module named '爻页.__main__'`。

**修法**：打包时不走 shim，把 `爻页/解释器/python版/*.py` 复制到一个干净的暂存目录
作为真实包根，让 PyInstaller 直接分析。

### 2. 运行时读源码文件失败

shim 里的 `read_text()` 在打包后找不到文件（资源在 `_MEIPASS` 临时目录/压缩包里）：

```
FileNotFoundError: 'C:\Windows\Temp\_MEI00003af02\语言\爻页\__init__.py'
```

**修法**：把元数据写死在 shim 里，不再运行时读文件。

### 3. 中文全变方块

离屏渲染按裸文件名找字体（`"msyh.ttc"`），依赖当前工作目录：

```python
ImageFont.truetype("msyh.ttc", 大)   # 打包后 cwd 变了 → 找不到
```

找不到就 fallback 到 `load_default()`，中文渲染成 ▯▯▯。

**修法**：显式查 `%WINDIR%\Fonts` 下的绝对路径，按优先级尝试
`msyhbd.ttc → msyh.ttc → simhei.ttf → simsun.ttc → ...`

### 4. 相对路径解析错

启动器 `chdir` 到 exe 目录后，传入的 `examples\...` 被解析成 `bin\examples\...`。

**修法**：打开页面前依次在各候选根里找：
`原 cwd → exe 目录 → 内置示例目录 → 资源目录`

---

## 重新打包

```powershell
python -X utf8 packaging\打包爻页v2.py
```

约需 30–60 秒。产物：`bin\爻页浏览器.exe`

### 打包脚本说明

| 文件 | 作用 |
|---|---|
| `packaging\爻页启动器.py` | exe 入口，处理路径/编码/资源定位 |
| `packaging\打包爻页v2.py` | 打包主脚本（复制模块到暂存目录 + 生成 spec + 调 PyInstaller） |
| `packaging\验证exe.py` | 隔离环境验证命令行功能 |
| `packaging\验证exe路径.py` | 验证各种路径形式 |
| `packaging\验证exe界面.py` | 验证图形窗口能启动 |

### 精简体积

打包时排除了用不到的大模块：

```python
excludes = [
    "numpy", "pandas", "matplotlib", "scipy",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython",
    "pytest", "_pytest", "setuptools", "pip", "wheel",
    "curses", "distutils", "lib2to3", "pydoc", "doctest",
    "yao", "爻语",
]
```

想让体积更小可以开 UPX，但可能被杀软误报，这里默认关闭。

---

## 已知限制

- **只支持 Windows**（PE 格式；要 Linux/macOS 需在对应平台重新打包）
- **首次启动稍慢**（1–2 秒，要做自解压到临时目录）
- **控制台窗口会显示**（`console=True`，方便看错误信息；
  改成窗口模式把 spec 里 `console=True` 改为 `False` 即可）
- 打包后的 exe **不能调用外部 Python 脚本**，只能用内置模块
- 打开需要后端的页面时（如分拣监控登录页），后端仍需单独运行

---

## 与后端配合

分拣监控系统的页面要连后端，所以完整部署需要两份东西：

```
1. bin\爻页浏览器.exe           ← 分发给操作员（前端界面）
2. examples\分拣监控\主.yao      ← 部署在服务器上（爻语后端）
```

后端仍需 Python 环境运行（因为要开 HTTP 服务、连 MQTT/Modbus）。
如果后端也要免 Python，可用同样的方式打包 `爻语\解释器\exe\yao.exe 跑`。
