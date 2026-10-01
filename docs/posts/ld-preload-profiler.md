---
title: "从函数拦截到调用计时：用 LD_PRELOAD 写一个 API Profiler"
description: "用一个 C++ 动态库实验，理解 LD_PRELOAD 如何拦截 API、函数别名如何保留原始入口，以及怎样测量和解释调用耗时。"
publishedAt: 2026-10-01
updatedAt: 2026-10-01
tags:
  - "C/C++"
  - "调试"
  - "性能优化"
slug: "ld-preload-profiler"
draft: false
---

排查性能问题时，我们经常需要知道：一个 API 被调用了多少次，每次花了多长时间？如果调用来自动态库，可以在应用与库之间插入一层 wrapper，由它记录调用，再把工作交给原始实现。

Linux 的 `LD_PRELOAD` 为这种实验提供了一个入口。应用仍然调用同名 API，运行时加载的另一份实现负责接住调用，因此可以通过启动命令切换是否启用记录。

本文用一个只有加法接口的 C++ demo，把这条链路完整串起来：**拦截 `demoAdd`，通过别名调用原始实现，再用单调时钟记录耗时。** 这个小实验展示的是 API 级插桩 profiler 的基本机制；采样调用栈、生成火焰图等能力，需要另行实现或使用现成工具。

## 实验设计：一个应用，两个动态库

应用每次调用 `demoAdd(10, 20)`，预期返回 30。业务库提供加法实现，profiler 库提供同名包装函数：

| 产物 | 源文件 | 职责 |
| --- | --- | --- |
| `app` | `main.cpp` | 调用接口，并检查返回值 |
| `libdemo.so` | `demo.cpp`、`demo.h` | 提供 `demoAdd` 和原始实现别名 `pdemoAdd` |
| `libprofiler.so` | `profiler.cpp`、`demo.h` | 拦截 `demoAdd`，记录耗时后返回结果 |

两种运行方式对应两条调用路径：

```text
普通运行
app ── demoAdd ──> libdemo.so ──> 返回 30

启用 profiler
app ── demoAdd ──> libprofiler.so
                       │ 开始计时
                       ├── pdemoAdd ──> libdemo.so ──> 返回 30
                       │ 结束计时，更新统计
                       └── 返回 30 ──> app
```

这里最重要的问题是：wrapper 也叫 `demoAdd`，它该怎样调用原来的 `demoAdd`，而不是再次进入自己？本例通过额外导出的函数别名 `pdemoAdd` 解决这个问题。

## 先编译运行，观察调用链

实验使用 **Linux / ELF、GCC 或 Clang，以及 C++17**。CMake 构建要求 3.20+；验证脚本还需要 Bash、Python 3 和 GNU binutils。macOS 使用 Mach-O，需要在 Linux 虚拟机或容器中运行本例。

下载 {download}`完整 demo 源码 <../_static/downloads/test_profiler.zip>`，解压后进入 `test_profiler/`。Debian / Ubuntu 可以这样准备环境和构建：

```bash
sudo apt update
sudo apt install build-essential cmake binutils python3

cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel
```

构建后，`build/` 中会生成应用与两个动态库。先运行对照组：

```bash
./build/app
```

应用直接调用业务库，预期输出：

```text
[app] call demoAdd, iterations = 1
[libdemo] original demoAdd(10, 20)
[app] result = 30, calls = 1, checksum = 30
```

再预加载 profiler：

```bash
LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app
```

预期输出格式如下，**其中时间值仅用于说明格式，不代表实测性能**：

```text
[app] call demoAdd, iterations = 1
[profiler] before demoAdd
[libdemo] original demoAdd(10, 20)
[profiler] after demoAdd, ret = 30, elapsed_ns = 1800
[app] result = 30, calls = 1, checksum = 30
[profiler] summary: calls=1 total_ns=1800 avg_ns=1800.00 min_ns=1800 max_ns=1800
```

阅读这份输出，先确认 `before -> original -> after` 的顺序，再确认结果仍为 30。它说明包装层参与了调用，同时原始函数体也得到了执行。最后一行是正常退出时打印的耗时汇总。

应用接受一个迭代次数参数，范围为 `1..1000000`。例如：

```bash
LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app 3
```

每次调用都会出现一组 before、original、after 日志；最终应用与 profiler 的调用次数都应为 3，返回值累加和 `checksum` 应为 90。

## 同一个函数体，两个符号名

`demo.h` 用 C linkage 声明接口，避免 C++ name mangling，使符号表中的名字保持为 `demoAdd` 和 `pdemoAdd`：

```cpp
extern "C" {
    int demoAdd(int a, int b);
    int pdemoAdd(int a, int b);
}
```

业务库通过 `PROFAPI` 控制是否导出原始入口。开启后，`DEMO_API(int, demoAdd, int a, int b)` 的关键展开结果如下，省略了函数体中的日志：

```cpp
extern "C"
__attribute__((visibility("default")))
__attribute__((alias("demoAdd")))
int pdemoAdd(int a, int b);

extern "C"
__attribute__((visibility("default")))
__attribute__((weak))
int demoAdd(int a, int b) {
    return a + b;
}
```

三个属性各有职责：

| 属性 | 作用 |
| --- | --- |
| `visibility("default")` | 让入口能够被动态库外部引用 |
| `alias("demoAdd")` | 让 `pdemoAdd` 与 `demoAdd` 指向同一个函数体 |
| `weak` | 将业务库中的公开入口 `demoAdd` 标记为弱符号 |

`pdemoAdd` 是符号别名，不是另一个转发函数。GCC 要求 alias 与目标在同一翻译单元中定义，并且类型一致；wrapper 与业务库也必须保持接口签名和 ABI 一致。具体约束可参考 [GCC 函数属性文档](https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html)。

于是，wrapper 可以这样转交调用：

```cpp
const int ret = pdemoAdd(a, b);
```

如果在 wrapper 内再次调用 `demoAdd(a, b)`，就会重新进入自己，造成递归。另一个符号名使 profiler 能够引用业务库里的原始函数体。

这个方案要求能够改动业务库，为它增加别名。如果无法修改库，也可以考虑 `dlsym(RTLD_NEXT, "demoAdd")`，查找当前共享对象之后的同名实现；它还需要处理查找失败、初始化与递归保护。多个预加载库存在时，“下一个实现”也可能是另一层 wrapper。参见 [dlsym 手册](https://man7.org/linux/man-pages/man3/dlsym.3.html)。

## `weak` 与 `LD_PRELOAD` 分别做了什么

看到库里的弱符号和 wrapper 里的普通全局符号，很容易把拦截归因于“强符号覆盖弱符号”。但在这个动态库实验中，还必须考虑运行时查找顺序。

现代 glibc 的动态链接器通常采用首先找到的定义。`LD_PRELOAD` 让指定库处于更靠前的查找位置，因此应用对 `demoAdd` 的引用能够绑定到 profiler。正常导出的强符号同样可能被预加载库拦截；弱符号并不是这种运行方法的必要条件。[ld.so 手册的 `LD_PRELOAD` 与 `LD_DYNAMIC_WEAK` 说明](https://man7.org/linux/man-pages/man8/ld.so.8.html)区分了加载顺序与历史上的弱符号查找行为。

本例保留 `weak`，展示业务库的双入口设计；真正启用 profiler 的动作是运行时设置 `LD_PRELOAD`。两个概念各司其职。

`pdemoAdd` 也仍是可被动态查找的导出符号。如果其他预加载库定义了它，绑定关系可能改变。这个名字是 demo 约定的原始入口，并不是动态链接器提供的不可替换通道。

## 在 wrapper 中加入计时

拦截只是 profiler 的入口，下一步是明确测量范围。下面是 `profiler.cpp` 中的计时核心：

```cpp
const auto begin = std::chrono::steady_clock::now();
const int ret = pdemoAdd(a, b);
const auto end = std::chrono::steady_clock::now();

const auto elapsed = static_cast<std::uint64_t>(
    std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count());
```

`steady_clock` 适合测量时间间隔。这里计时只包围 `pdemoAdd`：profiler 自己的 before/after 打印和统计更新放在区间之外，原始实现内部的操作则全部包含在内。

因此，默认模式测到的既有函数调用和加法，也有业务库内部 `printf` 的成本。为了观察关闭日志后的耗时，可以执行：

```bash
DEMO_QUIET=1 LD_BIND_NOW=1 \
  LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app 10000
```

`DEMO_QUIET` 关闭业务库和 profiler 的逐次日志，只保留应用开始、应用结果与 profiler 汇总三行。该变量按是否存在判断，设置成 `0` 也会关闭日志，并且在首次调用时读取后缓存。

`LD_BIND_NOW=1` 把动态符号的懒绑定提前到启动阶段，减少首次被测调用中的解析影响。它不会消除其他初始化、缓存或调度成本。[ld.so 手册](https://man7.org/linux/man-pages/man8/ld.so.8.html)说明了这一开关。

### 怎样解读统计字段

| 字段 | 含义 |
| --- | --- |
| `elapsed_ns` | 单次原始调用的墙钟耗时，单位纳秒 |
| `calls` | 进入 wrapper 的次数 |
| `total_ns` | 所有被测调用耗时之和 |
| `avg_ns` | `total_ns / calls` |
| `min_ns` / `max_ns` | 最短与最长单次耗时 |

应用另外输出 `result` 和 `checksum`，用于检查业务行为。调用一万次时，两边的次数都应为 10000，最后返回值仍为 30，校验和应为 300000。

需要区分三个范围：`elapsed_ns` 是一次调用的墙钟时间，线程被抢占或等待时也会增长；`total_ns` 是这些时间的累计，不是整个进程的运行时间；`avg_ns` 则是本次记录范围内的平均值，包含首调用的影响。

这个加法函数太短，时钟读取、调用边界和初始化可能占主要成本，因此结果用于理解计时机制，不能当作加法性能基准。换成实际 API 后，应关闭热路径日志，使用代表性输入，并将预热阶段与稳态统计分开。

对于异步 GPU API，类似 wrapper 通常只测到 CPU 提交时间。设备执行耗时需要设备事件或对应的 GPU profiler。

## 手动编译：理解每个构建参数

CMake 负责自动组织依赖。要理解库边界和运行路径，也可以在源码目录手动编译到独立目录：

```bash
mkdir -p build-manual

# 业务库：导出原始实现别名
g++ -std=c++17 -O2 -g -Wall -Wextra -fPIC -shared \
  -DPROFAPI demo.cpp -o build-manual/libdemo.so

# 应用：链接业务库
g++ -std=c++17 -O2 -g -Wall -Wextra main.cpp \
  -Lbuild-manual -ldemo -Wl,-rpath,'$ORIGIN' \
  -o build-manual/app

# profiler：通过 pdemoAdd 依赖业务库
g++ -std=c++17 -O2 -g -Wall -Wextra -fPIC -shared \
  profiler.cpp -Lbuild-manual -ldemo \
  -Wl,-z,defs -Wl,-rpath,'$ORIGIN' \
  -o build-manual/libprofiler.so

LD_PRELOAD="$PWD/build-manual/libprofiler.so" ./build-manual/app
```

| 参数 | 作用 |
| --- | --- |
| `-DPROFAPI` | 业务库开启 `pdemoAdd` 别名与弱公开入口 |
| `-fPIC -shared` | 生成位置无关代码和共享库 |
| `-Lbuild-manual -ldemo` | 在链接阶段找到业务库 |
| `-Wl,-rpath,'$ORIGIN'` | 运行时从程序或共享库所在目录查找依赖 |
| `-Wl,-z,defs` | 构建 profiler 时检查未解析引用 |
| `-O2 -g` | 开启优化，同时保留调试信息 |

`-L` 只解决链接阶段的搜索问题。这里另外设置运行路径，使应用和 profiler 能从同目录找到 `libdemo.so`。`$ORIGIN` 由动态链接器展开，必须使用单引号，避免 shell 提前替换。[ld.so 的动态字符串标记说明](https://man7.org/linux/man-pages/man8/ld.so.8.html)给出了它的含义。

只需要对业务库定义 `PROFAPI`。保持应用、业务库、profiler 三个独立产物，才能观察这套动态绑定过程。

## 用符号表验证原理

日志能观察执行顺序，符号表则能检查两个入口到底如何导出：

```bash
readelf --dyn-syms --wide build/libdemo.so | grep -E 'demoAdd|pdemoAdd'
readelf --dyn-syms --wide build/libprofiler.so | grep -E 'demoAdd|pdemoAdd'
```

预期关系如下，具体地址和索引会随构建变化：

| 产物 | 符号 | 绑定与可见性 | 定义状态 |
| --- | --- | --- | --- |
| `libdemo.so` | `demoAdd` | `WEAK DEFAULT` | 已定义 |
| `libdemo.so` | `pdemoAdd` | `GLOBAL DEFAULT` | 已定义，与 `demoAdd` 地址相同 |
| `libprofiler.so` | `demoAdd` | `GLOBAL DEFAULT` | 已定义，为 wrapper |
| `libprofiler.so` | `pdemoAdd` | `GLOBAL DEFAULT` | `UND`，需要业务库提供 |

两个业务库符号地址相同，体现了 alias 的含义。profiler 中 `pdemoAdd` 为 `UND`，表示当前共享库没有定义它；这个引用可以由依赖的业务库满足。

在 glibc 环境中，还可以查看实际绑定：

```bash
LD_DEBUG=bindings LD_PRELOAD="$PWD/build/libprofiler.so" \
  ./build/app 2>build/bindings.log
grep -E 'demoAdd|pdemoAdd' build/bindings.log
```

应检查应用的 `demoAdd` 是否绑定到 profiler，以及 profiler 的 `pdemoAdd` 是否绑定到业务库。`LD_DEBUG` 用于诊断，不应在性能采集时开启。

源码包还附带自动验证脚本：

```bash
ctest --test-dir build --output-on-failure
```

它检查对照运行、预加载调用顺序、静默模式、业务结果、统计次数与动态符号关系。耗时检查只验证总量与最值的一致性，不固定某个纳秒阈值。

完整验证步骤、Linux 容器运行命令与当前验证记录见源码包中的 `README.md`。文中的日志和符号表用于说明预期行为，实际结果应以目标 Linux 环境的运行与验证为准。

关闭别名可做另一个对照实验：

```bash
cmake -S . -B build-plain -DDEMO_ENABLE_PROFAPI=OFF \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build-plain --parallel
./build-plain/app
```

此时业务库只导出普通的 `demoAdd`，应用仍然可以运行，但不再构建依赖 `pdemoAdd` 的 profiler。不要混用两个构建目录中的库。

## 常见问题与使用边界

| 现象 | 排查方向 |
| --- | --- |
| 构建 profiler 报 `undefined reference to pdemoAdd` | 检查业务库是否开启 `PROFAPI`，是否链接了正确的库 |
| 运行时找不到 `libdemo.so` | 检查同目录库文件及运行路径，确认 `$ORIGIN` 没有被 shell 展开 |
| 运行报 `undefined symbol: pdemoAdd` | 检查是否误加载了未开启别名的业务库 |
| 只有原始日志，没有 profiler 记录 | 检查预加载路径、loader 的错误输出与实际符号绑定 |
| wrapper 递归或崩溃 | 检查内部是否再次调用 `demoAdd` |
| macOS 报 alias 不支持 | 在 Linux 环境运行本例 |

`LD_PRELOAD` 的拦截范围取决于调用是否经过可替换的动态符号。静态链接、内联、hidden/protected 入口和库内局部绑定都可能改变这个范围；安全执行模式也会限制预加载。[ld.so 手册](https://man7.org/linux/man-pages/man8/ld.so.8.html)描述了相关规则。

这个 demo 的统计结构面向单线程应用。扩展到多线程时，需要线程本地统计或同步；在热路径中加入锁也会增加额外成本。汇总只在正常退出时打印，异常终止不能保证得到报告。

这套实验适合从一个可控 API 开始理解函数包装与调用计时。把它扩展成实际 profiler 时，除了能否拦截函数，还需要明确测量范围、记录开销、并发行为和统计口径，才能让报告对应到真正要回答的性能问题。
