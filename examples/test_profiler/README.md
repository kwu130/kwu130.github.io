# 用 LD_PRELOAD 构建 API profiler

这是一个 Linux/ELF 上的 C++17 教学 demo：包装 `demoAdd`，通过 `pdemoAdd` 调用原始实现，并记录调用次数和耗时。它从原始四个源文件扩展而来，保留了 `PROFAPI`、弱符号和原始函数别名的设计。

完整文章源文件在文档站仓库的 `docs/posts/ld-preload-profiler.md`；发布后的地址为：[从函数拦截到调用计时：用 LD_PRELOAD 写一个 API Profiler](https://kwu130.github.io/posts/ld-preload-profiler/)。

## 环境与构建

需要 Linux、GCC 或 Clang、CMake 3.20+。自动验证还需要 Bash、Python 3 和 GNU binutils 的 `readelf`。

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install build-essential cmake binutils python3

cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel
```

输出 `build/app`、`build/libdemo.so` 和 `build/libprofiler.so`。共享库与程序均使用 `$ORIGIN` 查找同目录依赖，因此不需要设置 `LD_LIBRARY_PATH`。

## 运行

```bash
# 对照组：直接调用 libdemo
./build/app

# profiler：拦截，再调用原始实现
LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app

# 重复三次，观察完整调用链
LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app 3

# 禁用逐次日志，保留应用结果与 profiler 汇总
DEMO_QUIET=1 LD_BIND_NOW=1 \
  LD_PRELOAD="$PWD/build/libprofiler.so" ./build/app 10000

# 自动检查调用顺序、符号表、统计和输入校验
ctest --test-dir build --output-on-failure
```

调用链是 `app -> profiler::demoAdd -> libdemo::pdemoAdd`，随后沿相反方向返回。`libdemo` 中 `demoAdd` 与 `pdemoAdd` 的动态符号地址相同；profiler 只定义 `demoAdd`，对 `pdemoAdd` 保留外部引用。现代 glibc 的动态符号查找通常选择首先找到的定义，这里依赖 `LD_PRELOAD` 的顺序，而非运行时“强符号总覆盖弱符号”。参见 [GCC 属性文档](https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html) 与 [ld.so 手册](https://man7.org/linux/man-pages/man8/ld.so.8.html)。

## 结果解读

以下输出为格式示例，时间值不是当前机器的实测数据：

```text
[app] call demoAdd, iterations = 1
[profiler] before demoAdd
[libdemo] original demoAdd(10, 20)
[profiler] after demoAdd, ret = 30, elapsed_ns = 1800
[app] result = 30, calls = 1, checksum = 30
[profiler] summary: calls=1 total_ns=1800 avg_ns=1800.00 min_ns=1800 max_ns=1800
```

| 字段 | 含义 |
| --- | --- |
| `result` | 最后一次调用的返回值，应为 30 |
| `calls` | 调用次数，应与命令行迭代数一致 |
| `checksum` | 所有返回值之和，应为 `30 × calls` |
| `elapsed_ns` | 单次 `pdemoAdd` 调用的墙钟时间，单位纳秒 |
| `total_ns` / `avg_ns` | 各次耗时之和 / 平均值 |
| `min_ns` / `max_ns` | 最短 / 最长单次耗时 |

计时使用 `std::chrono::steady_clock`，区间只包围 `pdemoAdd`，不含 profiler 自身逐次打印与统计，但包含原始实现中的日志。`DEMO_QUIET=1` 关闭双方逐次日志；环境变量在首次调用时读取并缓存。`LD_BIND_NOW=1` 可把懒绑定移到启动阶段，不能消除缓存、调度和时钟读取的影响。这个加法函数过短，结果用于理解计时机制，不能当作加法性能基准。

统计适用于当前单线程应用，汇总在正常退出时打印；异常终止不会保证汇总。多线程扩展应使用线程本地统计或同步。`int` 加法的输入也应保证结果可表示，本应用固定使用 10 和 20。

## 验证符号

```bash
readelf --dyn-syms --wide build/libdemo.so | grep -E 'demoAdd|pdemoAdd'
readelf --dyn-syms --wide build/libprofiler.so | grep -E 'demoAdd|pdemoAdd'
LD_DEBUG=bindings LD_PRELOAD="$PWD/build/libprofiler.so" \
  ./build/app 2>build/bindings.log
grep -E 'demoAdd|pdemoAdd' build/bindings.log
```

`libdemo.so` 中应看到 `demoAdd` 为 `WEAK DEFAULT`，`pdemoAdd` 为 `GLOBAL DEFAULT`，且两者地址相同；`libprofiler.so` 的 `demoAdd` 为 `GLOBAL DEFAULT`，`pdemoAdd` 为 `UND`。

## 关闭 PROFAPI

```bash
cmake -S . -B build-plain -DDEMO_ENABLE_PROFAPI=OFF \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build-plain --parallel
./build-plain/app
```

此时只生成 app 和 libdemo；libdemo 不导出 `pdemoAdd`，不构建依赖该别名的 profiler。不要把之前构建的 profiler 预加载到这个版本。

## macOS 上使用 Linux 容器

macOS 的 Mach-O 不支持本例依赖的 ELF alias；CMake 会提前报错。安装并启动 Docker 后，在 demo 目录执行：

```bash
docker run --rm -v "$PWD":/work -w /work gcc:14 bash -lc \
  'apt-get update && apt-get install -y cmake binutils python3 &&
   cmake -S . -B build-docker -DCMAKE_BUILD_TYPE=RelWithDebInfo &&
   cmake --build build-docker --parallel &&
   ctest --test-dir build-docker --output-on-failure &&
   LD_PRELOAD=/work/build-docker/libprofiler.so ./build-docker/app 3'
```

`build-docker` 与本机 `build` 分开，避免混用架构和编译器缓存。生成的 ELF 程序需要在 Linux 容器中运行。

## 本次验证范围

2026-10-01 的编辑环境为 macOS arm64，Docker 不可运行。因此完成了无 `PROFAPI` 的本机编译运行、输入校验、profiler 语法检查、脚本语法检查与平台保护检查；Linux 的 alias、符号表和 `LD_PRELOAD` 端到端验证尚未执行，请运行上述 CTest 命令。文档中的耗时示例均为说明格式的示意值。
