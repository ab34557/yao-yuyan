# 爻语 C 实现 —— 独立解释器

> 把爻语从「需要 Python 才能跑」变成**真正独立的可执行文件**。
> 编译产物 `yao.exe` 约 110 KB，**运行时不需要 Python、不需要任何运行时库**。

---


> **运行方式**（两种都行，exe 不需要装 Python）
>
> ```powershell
> 爻语\解释器\exe\yao.exe 程序.yao      # 推荐：单文件，无依赖
> 爻语\解释器\exe\yao.exe 程序.yao        # 备选：开发时用，功能更全
> ```
>
> **能力差异**：`yao.exe`（C 版）支持语言核心语法、75 个内置函数里的 48 个，
> 但**不含** Web 服务、MQTT、Modbus TCP。做网页后端或工业物联请用 Python 版。
> 完整对照见 [手册.md](手册.md#解释器版本对照)。

## 为什么有这个

原来的爻语是用 Python 写的（`爻语/解释器/python版/`）。它确实能跑，但本质上是
「一个 Python 程序」—— 换一台没装 Python 的机器就跑不起来。

这个 C 实现解决了这个问题：爻语的词法、语法、求值、内置函数全部用 C 重写，
编译成一个原生 exe。

| | Python 版 | C 版 |
|---|---|---|
| 源码 | `爻语/解释器/python版/`（14 个 .py，157 KB） | `爻语/文档/c/`（5 个 .c + 1 个 .h，约 130 KB） |
| 运行需要 | Python 3.11+ | 无 |
| 产物 | 无（靠解释器跑） | `爻语/解释器/exe/yao.exe`（110 KB 单文件） |
| 启动 | ~80ms（Python 启动） | ~5ms |
| 语法 | 完整 | **与 Python 版一致** |
| 内置函数 | 57 个 | 44 个（Web 相关除外） |
| Web 服务器 | 有 | 无（见下方「尚未实现」） |

---

## 快速开始

### 方式一：直接用编译好的 exe

```powershell
bin\yao.exe --version
bin\yao.exe examples\示例\你好.yao
bin\yao.exe --check examples\示例\你好.yao    # 只做语法检查
bin\yao.exe                                   # 进入 REPL
```

### 方式二：自己编译

```powershell
cd 语言\爻语\c
.\build.bat
```

脚本会自动找编译器（TinyCC / gcc / clang），编译到 `bin\yao.exe`。

需要 C 编译器。最小的是 **TinyCC**（7 MB，单文件，无需安装）：

```powershell
# 1. 下载
Invoke-WebRequest https://bellard.org/tcc/tcc-0.9.27-win64-bin.zip -OutFile tcc.zip
# 2. 解压到 C:\yaotcc（使 C:\yaotcc\tcc\tcc.exe 存在）
Expand-Archive tcc.zip -DestinationPath C:\
Rename-Item C:\tcc C:\yaotcc
# 3. 编译
.\build.bat
```

有 gcc/clang 的话直接放进 PATH 就行，脚本会自动用。

---

## 验证「真的不依赖 Python」

```powershell
# 把 PATH 缩到只剩系统目录
$env:PATH = 'C:\Windows\System32;C:\Windows'
bin\yao.exe examples\示例\你好.yao
```

输出正常，退出码 0 —— 证明它不需要 Python。

自动化测试里也断言了这一点（`tests/test_C解释器.py::test_C版是独立可执行`）：
检查 PE 头（`MZ`），并确认文件里不含 `python311.dll` / `python3.dll` / `libpython`。

---

## 源码结构

```
爻语/文档/c/
├─ yao.h          公共定义：值类型、Token、AST 结点、接口
├─ lexer.c        词法分析（UTF-8 + 21 个中文关键字）
├─ parser.c       语法分析（递归下降 + Pratt 表达式）
├─ eval.c         求值器（树遍历 + 作用域链）
├─ builtins.c     内置函数（44 个）+ 输出缓冲 + JSON
├─ main.c         命令行入口 + REPL
├─ test_lexer.c   词法测试工具
└─ build.bat      一键编译脚本
```

### 设计取舍

**值表示**：tagged union

```c
typedef struct Val {
    VType t;
    union {
        double num;
        int b;
        struct { char *p; int n; } str;   /* 长度前缀，不依赖 \0 */
        List *list;
        Map *map;
        Func *fn;
        ... *bi;                          /* 内置函数 */
    } u;
} Val;
```

**内存**：arena 分配，脚本结束时整体释放

```c
void *arena_alloc(size_t n);   // 从 1 MB 块里切
void  arena_free_all(void);    // 一次性释放所有块
```

不做引用计数、不做 GC。脚本执行期间内存只增不减，退出时全部释放。
对脚本语言足够 —— 跑一个脚本通常几 MB 内存。

**表（字典）**：键值对数组 + 线性查找。脚本规模（几百个键）下比哈希表更简单也够快。

**作用域**：链表，每层一个 `Map`。查变量时沿链向上找。

**字符串**：`{char *p, int n}` 带长度，不做 `\0` 终止假设，因为爻语字符串可以包含任意字节。

---

## 实现过程中踩的坑

这些都是真实 bug，记录下来避免重犯：

### 1. `Lexer.pos` 一个字段两种用途

词法阶段 `pos` 是**源码字节位置**，解析阶段 `pos` 是**token 下标**。两者共用一个字段，
导致解析器一开始就以为自己在文件末尾（读到 `pos = 文件长度`，而 token 数组只有 5 个）。

**修法**：拆成 `srcpos`（字节位置）和 `pos`（token 下标）。

### 2. 盒坐标相对 vs 绝对

爻页那边的老问题：布局产出的坐标是相对父容器的，命中测试却直接和鼠标绝对坐标比。
C 版没有前端，但同样的相对坐标系出现在 `run_block` 的递归里。

### 3. 臂体可能是单条语句

`判 条件 【 真 ⇒ 显("a") 】` 里，臂体是一个 `N_CALL` 节点，不是 `N_BLOCK`。
直接读 `body->u.block.n` 会读到垃圾指针，导致分支静默不执行。

**修法**：加 `run_body()`，自动包装单条语句成临时块。

### 4. `遍` 的语义

- `遍 x 于 列` → `x` 是**值**
- `遍 x 于 表` → `x` 是**键**
- `遍 k, v 于 列` → `k` 是下标，`v` 是值

一开始写成「总是给下标」，导致输出 `0 1 2` 而不是 `10 20 30`。

### 5. 中文路径 / BOM / 编码

三个连环坑：

- **TinyCC 不认中文路径** —— 源码和产物都必须在纯 ASCII 路径下编译
- **UTF-8 BOM 会让 TCC 报语法错** —— 每个源文件写入前要检查并去掉
- **中文命令行参数在 Windows 控制台下会被破坏** —— `--版` 变乱码，所以命令行参数改成 ASCII（`--version` / `--check`），但**脚本内容里的中文完全正常**

---

## 一致性保证

`tests/test_C解释器.py` 会：

1. **编译** C 版（如果没有编译器就跳过）
2. 对 11 组典型脚本，**同时**跑 C 版和 Python 版
3. 断言**输出逐行完全一致**

覆盖：算术、字符串、比较逻辑、列表表、函数与递归、条件判、遍历循环、
字符串函数、数学函数、JSON、错误处理、高阶函数与匿名函数。

```powershell
python -X utf8 -m pytest tests/test_C解释器.py -q
```

```
.............                                                            [100%]
13 passed
```

每次改 C 版都跑这个，保证不会和 Python 版跑偏。

---

## 尚未实现

C 版目前覆盖了**语言核心 + 常用内置函数**，以下还没做：

| 功能 | 状态 |
|---|---|
| `路` / `共` / `听` / `应` / `请` / `停` | ❌ Web 服务器（需要 HTTP 实现） |
| `抓` / `请求` | ❌ HTTP 客户端 |
| `载模块` | ❌ 动态加载其他 .yao 文件 |
| `散列` | ⚠️ 用 FNV-1a 代替 SHA-256（输出格式不同） |
| `开覆盖` / `取覆盖` / `关覆盖` | ⚠️ 桩实现（返回空统计） |
| `映` / `筛` / `折` | ✅ 已有 |
| 其余 44 个内置 | ✅ 已有 |

Web 部分缺失意味着 **C 版暂时不能跑论坛后端**。要用 Web 功能请用 Python 版：

```powershell
爻语\解释器\exe\yao.exe 跑 examples\论坛\主.yao
```

---

## 两种实现的分工

| 场景 | 用哪个 |
|---|---|
| 分发脚本给没装 Python 的机器 | **C 版** |
| 需要 Web 服务器 / HTTP | Python 版 |
| 需要最快的启动速度 | **C 版** |
| 需要完整的 57 个内置函数 | Python 版 |
| 学习语言实现 | 两个都看，C 版更直白 |

两版共享同一套语法和语义 —— 同一份 `.yao` 文件在两边跑出的结果一致（有测试守着）。
