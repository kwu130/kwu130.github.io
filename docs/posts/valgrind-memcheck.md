---
title: "用 Valgrind 定位 C/C++ 内存问题：泄漏、越界与未初始化读取"
description: "从可复现示例出发，读懂 Memcheck 的泄漏分类、非法访问和未初始化值报告，并把检查接入日常开发流程。"
publishedAt: 2024-07-27
updatedAt: 2026-08-30
tags:
  - "C/C++"
  - "调试"
slug: "valgrind-memcheck"
legacyPaths:
  - "/post/Valgrind-jian-ce-nei-cun-xie-lou.html"
issueNumber: 4
draft: false
---

Valgrind 是一组动态分析工具，其中最常用的 **Memcheck** 专门检查内存访问错误。它能够发现堆内存泄漏、越界读写、释放方式不匹配，以及“程序根据未初始化值做出判断”这类很难靠代码审查定位的问题。

本文以 Linux 上的 C++ 程序为例，依次演示泄漏、越界和未初始化读取，并给出一套可以复用的排查顺序。报告中的地址和系统库调用会随编译器、发行版与 Valgrind 版本变化；分析时应把注意力放在错误类型、调用栈和第一处进入项目源码的位置。

## 准备环境

优先使用发行版的软件包，而不是把某个历史版本号写死在安装脚本里：

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install valgrind

# Fedora
sudo dnf install valgrind

# Arch Linux
sudo pacman -S valgrind
```

安装后确认工具可用：

```bash
valgrind --version
```

为了让报告包含文件名和行号，编译时需要保留调试信息。排查阶段可以先关闭优化，使调用栈更容易对应源码：

```bash
g++ -std=c++17 -g -O0 -Wall -Wextra test.cpp -o test
```

一个适合日常排查的命令是：

```bash
valgrind \
  --leak-check=full \
  --show-leak-kinds=all \
  --track-origins=yes \
  --error-exitcode=1 \
  ./test
```

Memcheck 是 Valgrind 的默认工具，因此通常不必额外指定 `--tool=memcheck`。这组参数适合深入排查，但 `--track-origins=yes` 会进一步降低运行速度；如果暂时没有未初始化值问题，可以先去掉它。

## 先建立排查顺序

Memcheck 的输出可能很长，但阅读顺序可以保持固定：

1. **先处理最早出现的错误**：后续报告可能只是第一个错误引发的连锁反应；
2. **找到第一条属于项目代码的栈帧**：系统库和 Valgrind 内部调用通常只是上下文；
3. **区分错误发生点与根因位置**：越界读取发生在使用处，错误的长度或所有权却可能来自更早的代码；
4. **修复后重新运行完整测试**：不要因为当前报告消失，就假设相邻路径也已经安全。

这套顺序比从 `LEAK SUMMARY` 开始逐项猜测更高效，也符合 Valgrind 官方“按报告顺序修复”的建议。

## 检测内存泄漏

先看一个最小泄漏示例：

```cpp
#include <cstring>
#include <iostream>

int main() {
    char* text = new char[10];
    std::strcpy(text, "abc");
    std::cout << text << '\n';
    return 0; // 忘记 delete[] text
}
```

编译后执行：

```bash
g++ -std=c++17 -g -O0 test.cpp -o test
valgrind --leak-check=full --show-leak-kinds=all ./test
```

报告中最关键的一段类似下面这样：

```text
10 bytes in 1 blocks are definitely lost in loss record 1 of 1
   at ...: operator new[](unsigned long)
   by ...: main (test.cpp:5)
```

`test.cpp:5` 指向内存分配的位置。它不一定就是最终的修复位置，却通常是追踪所有权的最佳起点：谁申请了内存、谁应该释放、指针又是在何处丢失的。

### 四种泄漏分类

Memcheck 把未释放的内存分为四类：

| 分类 | 含义 | 通常如何处理 |
| --- | --- | --- |
| `definitely lost` | 已经没有任何指针能访问这块内存 | 确定是泄漏，优先修复 |
| `indirectly lost` | 只能通过另一块已丢失内存访问，例如丢失树的根节点 | 先修复直接丢失的所有者 |
| `possibly lost` | 只剩指向内存块内部的指针，Memcheck 无法确定所有权 | 检查指针运算和自定义分配器 |
| `still reachable` | 程序退出时仍有合法指针可以访问 | 可能合理，也可能是生命周期过长 |

`suppressed` 表示报告被抑制规则过滤，并不是第五种泄漏分类。完整定义可参考 [Memcheck 手册的泄漏检测章节](https://valgrind.org/docs/manual/mc-manual.html#mc-manual.leaks)。

### 修复泄漏

最直接的修复是在最后一次使用后调用匹配的 `delete[]`：

```cpp
delete[] text;
```

但现代 C++ 更推荐让所有权由对象管理。例如，这个例子根本不需要手工申请内存：

```cpp
#include <iostream>
#include <string>

int main() {
    const std::string text = "abc";
    std::cout << text << '\n';
}
```

如果确实需要动态数组，可以使用 `std::vector` 或 `std::unique_ptr<T[]>`。RAII 不能替代检测工具，但能把释放动作绑定到对象生命周期，从设计上减少“忘记释放”这类错误。

## 检测越界访问

下面的 `std::vector` 只有十个元素，有效下标是 `0` 到 `9`：

```cpp
#include <iostream>
#include <vector>

int main() {
    std::vector<int> values(10, 0);
    std::cout << values[10] << '\n';
}
```

Memcheck 会给出类似报告：

```text
Invalid read of size 4
   at ...: main (test.cpp:6)
 Address ... is 0 bytes after a block of size 40 alloc'd
```

“0 bytes after a block of size 40”表示读取地址恰好落在分配块末尾之后。假设当前平台 `sizeof(int) == 4`，十个元素共占 40 字节；`values[10]` 因而正好越过有效范围。

`operator[]` 越界属于未定义行为，程序偶尔打印 `0`、没有崩溃，甚至通过测试，都不能证明访问安全。调试阶段可以改用带边界检查的 `values.at(10)`；它会抛出 `std::out_of_range`，让错误更早暴露。

## 追踪未初始化值

另一个常见问题是读取尚未初始化的局部变量：

```cpp
#include <iostream>

int main() {
    int value;
    if (value == 0) {
        std::cout << "value is zero\n";
    }
}
```

报告通常包含：

```text
Conditional jump or move depends on uninitialised value(s)
   at ...: main (test.cpp:5)
```

错误在 `if` 处暴露，但根因发生在更早的“没有初始化”。添加 `--track-origins=yes` 后，Memcheck 会尝试回溯这个值的来源，代价是更长的运行时间和更高的内存占用。

这里的修复很直接：

```cpp
int value = 0;
```

在真实项目中，来源也可能是未完全填充的结构体、失败后仍被使用的输出参数，或只初始化了部分元素的缓冲区。

## 一组实用参数

| 参数 | 作用 |
| --- | --- |
| `--leak-check=full` | 为每条泄漏记录输出调用栈 |
| `--show-leak-kinds=all` | 显示四种泄漏分类 |
| `--track-origins=yes` | 尝试追踪未初始化值的来源 |
| `--num-callers=30` | 在复杂调用链中保留更多栈帧 |
| `--error-exitcode=1` | 检测到错误时返回非零状态，便于 CI 判断失败 |
| `--log-file=valgrind.log` | 把报告写入文件 |

CI 中可以使用更聚焦的配置：

```bash
valgrind \
  --leak-check=full \
  --errors-for-leak-kinds=definite,possible \
  --error-exitcode=1 \
  ./tests
```

如果第三方库存在已知且暂时无法修复的报告，应使用经过审查、范围尽可能小的 suppression 文件，而不是关闭整类检查。抑制规则还应记录来源和移除条件，避免长期掩盖新的缺陷。

## Valgrind 与 Sanitizer 如何选择

Memcheck 不要求在编译阶段加入检测插桩，但程序运行速度可能比原生慢很多。AddressSanitizer 通常更快，适合在本地开发和 CI 中频繁运行；Valgrind 则适合无法方便重新编译的程序，或需要更细致的泄漏分类时使用。

实用组合通常是：

1. 本地和 CI 高频运行 AddressSanitizer / UndefinedBehaviorSanitizer；
2. 在 Linux 的专项任务中运行 Valgrind；
3. 无论使用哪种工具，都保留单元测试和清晰的资源所有权。

Valgrind 官方也提醒，高优化级别可能让部分报告难以对应源码，甚至引入误报；排查时应从带调试信息的低优化构建开始。更多限制见 [Valgrind Quick Start](https://valgrind.org/docs/manual/quick-start.html)。

## 总结

读 Memcheck 报告时，可以始终按同一条路径处理：先看最早的错误类型，再找到第一条项目代码栈帧，最后回溯内存的所有权、边界和初始化过程。工具告诉你症状在哪里出现，真正的修复则来自更清晰的生命周期、更少的裸指针，以及能够稳定复现问题的测试。
