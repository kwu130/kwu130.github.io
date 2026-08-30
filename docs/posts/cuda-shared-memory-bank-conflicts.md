---
title: "CUDA Shared Memory Bank Conflict：从地址映射到 Padding 与 XOR Swizzling"
description: "从 shared memory 的 bank 映射和冲突度出发，用矩阵转置解释 32-way conflict，并比较 Padding、XOR Swizzling 与 Nsight Compute 验证方法。"
publishedAt: 2026-08-30
updatedAt: 2026-08-30
tags:
  - "CUDA"
  - "性能优化"
slug: "cuda-shared-memory-bank-conflicts"
draft: false
---

CUDA shared memory 位于片上，带宽高、延迟低，但它并不是一整块可以任意并行访问的存储。硬件把 shared memory 划分为多个 **bank**；同一 warp 的一条指令如果让多个线程访问同一 bank 中的不同地址，请求就必须拆开处理，这就是 **bank conflict**。

理解 bank conflict 的关键不是记住某几个“危险下标”，而是回答三个问题：一条指令访问了哪些字节地址、这些地址映射到哪些 bank、同一 bank 内是否仍是同一个 word。本文先建立一个适用于 32-bit 数据的地址模型，再用矩阵转置说明 Padding 和 XOR Swizzling 如何改变访问布局。

## Shared memory 为什么会发生冲突

在当前常见 NVIDIA GPU 上，可以用下面的模型理解 shared memory：

- 一共有 32 个 bank；
- 相邻的 32-bit word 映射到相邻 bank；
- 每个 bank 每个时钟周期可提供 32 bit 带宽；
- 一个 warp 包含 32 个线程，正好可能同时覆盖全部 32 个 bank。

若 `byte_offset` 是某个数据相对于 shared memory 基址的字节偏移，则对一个 32-bit word：

```text
word_index = byte_offset / 4
bank       = word_index % 32
```

例如字节偏移 52 对应 word 13，也就是 bank 13。再向后移动 32 个 `float`，偏移变为 `52 + 32 × 4 = 180`，对应 word 45，仍然映射到 bank 13。bank 映射是每 128 字节循环一次，而不是每个 bank 负责一段连续地址。

```{figure} ../_static/images/cuda-bank-conflicts/bank-access-patterns.svg
:alt: 32 个线程连续访问、步长为 2 的访问和同地址广播的 bank 映射对比
:width: 100%
```

连续访问覆盖 32 个 bank；步长为 2 时 bank 编号重复，形成 2-way conflict；读取同一个 word 则由硬件广播。

### 无冲突、冲突与广播

同一 warp 执行一条 shared-memory 指令时，常见情况可以分为三类：

| 访问模式 | 硬件行为 |
| --- | --- |
| 不同线程访问不同 bank | 请求可以并行处理 |
| 多个线程访问同一 bank 的不同 word | 请求被拆成多次，发生 bank conflict |
| 多个线程读取同一个 word | 读取一次后广播，不按普通冲突处理 |

如果多个线程写入同一个 shared-memory 地址，也不会形成普通 bank conflict，但最终由哪个线程完成写入是未定义的，不能把它当作可靠的归约或通信方式。

因此，看到多个 lane 的 bank 编号相同还不够：还要检查它们访问的完整地址是否相同。bank conflict 由**同一 warp、同一条指令、同一 bank 中的不同地址**共同决定。

### Stride 与冲突度

假设完整 warp 的 lane `t` 访问 32-bit 数组中的：

```text
shared[base + t * stride]
```

对应 bank 为：

```text
bank(t) = (base + t * stride) % 32
```

若 32 个线程访问的都是不同 word，记 `g = gcd(stride, 32)`，则：

- 实际覆盖的 bank 数为 `32 / g`；
- 每个被覆盖的 bank 收到 `g` 个地址；
- 访问形成 `g`-way conflict。

几个典型例子：

| `stride` | 覆盖的 bank 数 | 结果 |
| ---: | ---: | --- |
| 1 | 32 | 无冲突 |
| 2 | 16 | 2-way conflict |
| 4 | 8 | 4-way conflict |
| 31 | 32 | 无冲突，只是 bank 顺序被置换 |
| 32 | 1 | 32-way conflict |
| 33 | 32 | 无冲突，等价于 bank 步长 1 |

这条结论要求 lane 都处于活动状态、每个 lane 访问一个 32-bit word，并且地址彼此不同。`stride = 0` 时虽然公式给出 `gcd(0, 32) = 32`，但所有线程读取的是同一地址，应按 broadcast 处理。

### 宽数据类型不能只看数组下标

“下标 `% 32`”只适合一个 lane 访问一个 32-bit word 的简化场景：

- `float`、`int32_t`：通常可以直接使用上述模型；
- `double`、`int64_t`：每个元素覆盖两个连续的 32-bit word；
- `half`：两个 16-bit 元素可能位于同一个 32-bit word 中；
- `float2`、`float4` 等向量类型：一次源码访问覆盖多个 word，也可能生成多条硬件指令；
- 单线程每次访问超过 128 bit 时，请求还可能按 transaction 拆分。

分析这些类型时，应先换算每个 lane 涉及的字节范围，再结合编译后的 SASS 和 profiler 中的 transaction 或 wavefront，而不是把元素下标直接对 32 取模。

## 矩阵转置为何需要 shared memory

设输入矩阵 `A` 为 `height × width`、按行存储，输出满足：

```text
B[col][row] = A[row][col]
```

如果一个 warp 按行连续读取 `A`，读取可以合并；但直接写入转置后的 `B` 时，相邻线程会沿列方向大步长写入，通常产生大量 global-memory transaction。shared memory 可以在片上暂存一个 tile，把“按行读取 A”的线程排列转换为“按行写入 B”的排列，使两侧的全局内存访问都保持合并。

下面使用 `32 × 8` 个线程搬运一个 `32 × 32` tile。每个线程在循环中处理四个元素，线程数比 `32 × 32` block 更克制，同时仍覆盖完整 tile：

```cpp
constexpr int TILE_DIM = 32;
constexpr int BLOCK_ROWS = 8;

__global__ void transpose_conflicted(const float* input,
                                     float* output,
                                     int width,
                                     int height) {
    __shared__ float tile[TILE_DIM][TILE_DIM];

    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;

    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        if (x < width && y + j < height) {
            tile[threadIdx.y + j][threadIdx.x] =
                input[(y + j) * width + x];
        }
    }

    __syncthreads();

    x = blockIdx.y * TILE_DIM + threadIdx.x;
    y = blockIdx.x * TILE_DIM + threadIdx.y;

    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        if (x < height && y + j < width) {
            output[(y + j) * height + x] =
                tile[threadIdx.x][threadIdx.y + j];
        }
    }
}
```

启动配置使用向上取整，因此不要求矩阵尺寸是 32 的倍数：

```cpp
dim3 block(TILE_DIM, BLOCK_ROWS);
dim3 grid((width + TILE_DIM - 1) / TILE_DIM,
          (height + TILE_DIM - 1) / TILE_DIM);

transpose_conflicted<<<grid, block>>>(input, output, width, height);
```

注意 `__syncthreads()` 位于条件分支之外。边界 block 中有些线程不搬运数据，但整个 block 仍必须到达同一个 barrier；把同步写进 `if (x < width && y < height)` 可能使部分线程提前跳过，从而产生未定义行为甚至挂起。

### 冲突发生在 tile 的列访问

C++ 二维数组按行存储，`tile[row][col]` 的 32-bit word 下标为：

```text
word_index = row * 32 + col
bank       = (row * 32 + col) % 32
```

写入 `tile[threadIdx.y + j][threadIdx.x]` 时，同一 warp 的 `threadIdx.x` 从 0 到 31，访问同一行的连续列，覆盖全部 32 个 bank，没有冲突。

读取 `tile[threadIdx.x][threadIdx.y + j]` 时，同一 warp 的列固定、行从 0 到 31。相邻地址相差 32 个 word，全部映射到同一个 bank，形成 32-way conflict。

```{figure} ../_static/images/cuda-bank-conflicts/transpose-padding.svg
:alt: 32 乘 32 tile 的列访问全部落入同一 bank，增加一列 padding 后分散到 32 个 bank
:width: 100%
```

行跨度从 32 个 word 改为 33 个 word 后，列访问的 bank 步长从 0 变为 1。

## 方案一：增加一列 Padding

最直接的修复只需把 shared-memory 数组改成：

```cpp
__shared__ float tile[TILE_DIM][TILE_DIM + 1];
```

其余逻辑下标保持不变。此时：

```text
bank = (row * 33 + col) % 32
     = (row + col) % 32
```

同一列的 32 行会分别落到 32 个 bank，原来的 32-way conflict 被消除。这也是 NVIDIA Best Practices Guide 中处理二维 tile 冲突的经典方法。

一个 `float tile[32][32]` 占用 4096 字节；增加一列后占用 4224 字节，只多 128 字节。它是否影响 occupancy，取决于增加后的每 block shared-memory 用量是否跨过当前 GPU 的资源分配边界，不能仅凭“用了 padding”就断言 occupancy 一定下降。

Padding 还会改变每行起始地址的对齐：33 个 `float` 的行跨度是 132 字节，不是 16 的倍数。普通标量访问没有问题；如果把行首强制解释为 `float4*`、`int4*` 等 16 字节对齐的向量指针，后续行可能不满足对齐要求。此时应重新设计布局、为向量访问单独处理边界，或检查生成指令，不能假设编译器一定安全拆分，也不能笼统地说 kernel 必然报错。

## 方案二：XOR Swizzling

如果不希望增加 shared-memory 容量，可以保持 `tile[32][32]`，通过改变元素的**物理存放位置**来打散 bank。这里参考 [CUDA shared memory 避免 bank conflict 的 swizzling 机制解析](https://zhuanlan.zhihu.com/p/4746910252) 第 4 节的思路，并统一使用 `row` 表示行、`col` 表示列。

### 逻辑位置和物理位置

逻辑位置描述元素在算法中的坐标，例如转置算法中的 `tile[row][col]`；物理位置描述该元素实际写入 shared memory 的坐标。普通布局中两者相同，而 Swizzling 在二者之间增加一个映射：

```text
(physical_row, physical_col) = f(logical_row, logical_col)
```

算法始终使用逻辑坐标表达“需要哪个元素”，只有在生成 shared-memory 地址时才换算成物理坐标。这个区分很重要：Swizzling 改变的是存储布局，不是矩阵的数学含义。

一个可用的布局映射至少要满足三个条件：

1. **一一对应**：不同逻辑元素不能覆盖同一个物理位置，一个逻辑元素也不能对应多个物理位置；
2. **范围不变**：映射后的行列仍位于原数组范围内，否则就会扩大 shared-memory 用量或发生越界；
3. **读写一致**：写入和读取同一逻辑元素时必须使用相同映射，否则会读到其他元素。

### Swizzling 的映射函数

本文使用的映射保持行坐标不变，只用逻辑行置换逻辑列：

```text
physical_row = logical_row
physical_col = logical_col XOR logical_row
```

例如逻辑坐标 `(row=2, col=3)` 不再存入 `tile[2][3]`，而是存入：

```text
physical_row = 2
physical_col = 3 XOR 2 = 1
```

算法读写的仍是逻辑元素 `(2, 3)`，只有访问 shared memory 时才把它转换为物理坐标 `(2, 1)`。

后续证明会使用异或的几条基本性质：

```text
a XOR b = b XOR a                         // 交换律
(a XOR b) XOR c = a XOR (b XOR c)         // 结合律
a XOR a = 0
a XOR 0 = a
a != b  <=>  a XOR b != 0
```

为了让简单的 `col XOR row` 映射保持在原数组内，本文还限定：

- 行、列具有相同的取值范围；
- 取值从 0 开始，到 `2^k - 1` 结束；
- 本例中 `k=5`，所以 `row`、`col` 都位于 `[0, 31]`。

如果 tile 不是方阵、边长不是 2 的幂，或者一次指令访问多个 word，就需要选择参与异或的具体 bit，而不能直接异或完整行列下标。

```{figure} ../_static/images/cuda-bank-conflicts/xor-swizzle.svg
:alt: 逻辑矩阵的行列坐标通过列异或行映射到物理列，并让行访问和列访问覆盖不同 bank
:width: 100%
```

XOR Swizzling 保持行不变，只置换行内列位置。图中 `row=1` 时，物理列顺序变为 `1, 0, 3, 2, 5, 4, 7, 6`；`row=3` 时则变为 `3, 2, 1, 0, 7, 6, 5, 4`。

### 一对一映射

映射前后行坐标保持不变，所以只需证明：同一行中的不同逻辑列，映射后仍对应不同物理列。

固定逻辑行 `r`，取两个不同逻辑列 `c1 != c2`：

```text
p1 = c1 XOR r
p2 = c2 XOR r
```

将两个物理列异或：

```text
p1 XOR p2
  = (c1 XOR r) XOR (c2 XOR r)
  = (c1 XOR c2) XOR (r XOR r)
  = c1 XOR c2
  != 0
```

因此 `p1 != p2`。同一行中不会有两个逻辑列映射到同一个物理列；不同行的物理行本来就不同，所以整个二维映射是一一对应的。

这个映射还是自身的逆操作：

```text
(col XOR row) XOR row = col
```

所以只要知道行号，就能从物理列恢复逻辑列。代码不必保存额外的反向查找表。

### 映射前后的取值范围保持不变

对于边长为 `2^k` 的 tile，合法行列坐标都能用 `k` bit 表示。两个 `k`-bit 数异或不会产生第 `k+1` 位，因此：

```text
0 <= logical_col XOR logical_row <= 2^k - 1
```

本文 `k=5`，所以任意 `row`、`col` 的异或结果仍位于 `[0, 31]`。例如固定 `row=3`：

```text
col=3   -> physical_col = 3 XOR 3  = 0
col=28  -> physical_col = 28 XOR 3 = 31
```

上一节已经证明同一行的 32 个映射结果两两不同；现在又知道它们全部落在只有 32 个值的 `[0, 31]` 中，因此这些结果必然恰好覆盖 `0..31`，只是顺序发生了改变。映射前后的列取值范围完全一致，不需要额外 shared memory。

### 同一逻辑列在映射后也互不冲突

还需要证明列方向：固定逻辑列 `c`，取两个不同行 `r1 != r2`，它们对应的物理列为：

```text
p1 = c XOR r1
p2 = c XOR r2
```

两者异或后：

```text
p1 XOR p2
  = (c XOR r1) XOR (c XOR r2)
  = (c XOR c) XOR (r1 XOR r2)
  = r1 XOR r2
  != 0
```

所以 `p1 != p2`。同一逻辑列的不同行会映射到不同物理列。

固定行 `row=3` 与固定列 `col=3` 时，前 8 个物理列甚至呈现相同序列：

| 访问方向 | 变化的逻辑坐标 | 物理列序列 |
| --- | --- | --- |
| 固定 `row=3` 的行访问 | `col=0..7` | `3, 2, 1, 0, 7, 6, 5, 4` |
| 固定 `col=3` 的列访问 | `row=0..7` | `3, 2, 1, 0, 7, 6, 5, 4` |

两组访问涉及的逻辑元素不同，但产生的 bank 排列相同。扩展到完整 `0..31` 后，无论沿逻辑行还是逻辑列访问，物理列都会覆盖全部 32 个值。

对 `float tile[32][32]`，映射后逻辑元素 `(row, col)` 的 bank 为：

```text
word_index = row * 32 + (col XOR row)
bank       = word_index % 32
           = col XOR row
```

由这个式子可以直接检查两种访问方向：

- **逻辑行访问**：`row` 固定、`col=0..31`，`col XOR row` 是全部 32 个 bank 的一个排列；
- **逻辑列访问**：`col` 固定、`row=0..31`，`col XOR row` 同样是全部 32 个 bank 的一个排列。

因此，一列中的 32 个逻辑元素会被分散到 32 个物理列，也就是 32 个 bank。

### 在转置 kernel 中应用映射

对应实现如下：

```cpp
__device__ __forceinline__ int swizzled_col(int row, int col) {
    return row ^ col;
}

__global__ void transpose_swizzled(const float* input,
                                   float* output,
                                   int width,
                                   int height) {
    __shared__ float tile[TILE_DIM][TILE_DIM];

    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;

    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        const int row = threadIdx.y + j;
        if (x < width && y + j < height) {
            tile[row][swizzled_col(row, threadIdx.x)] =
                input[(y + j) * width + x];
        }
    }

    __syncthreads();

    x = blockIdx.y * TILE_DIM + threadIdx.x;
    y = blockIdx.x * TILE_DIM + threadIdx.y;

    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        const int logical_row = threadIdx.x;
        const int logical_col = threadIdx.y + j;
        if (x < height && y + j < width) {
            output[(y + j) * height + x] =
                tile[logical_row]
                    [swizzled_col(logical_row, logical_col)];
        }
    }
}
```

代码中的读写过程可以拆成两步：

1. 从 global memory 加载时，线程要写入逻辑位置 `(row, threadIdx.x)`，实际写入物理位置 `(row, row XOR threadIdx.x)`；
2. 转置读取时，线程需要逻辑位置 `(threadIdx.x, threadIdx.y + j)`，实际读取物理位置 `(threadIdx.x, threadIdx.x XOR (threadIdx.y + j))`。

写入阶段中，warp 访问固定逻辑行、连续逻辑列，映射后的物理列覆盖 0 到 31；读取阶段中，逻辑行连续变化、逻辑列固定，映射后的物理列仍互不相同。两条 shared-memory 访问路径因此都不会产生普通 bank conflict。

最容易出现的错误是只在写入时应用 Swizzling，读取时仍使用原始下标。这样编译和运行都可能正常，却会从错误的物理位置取数，产生静默的数据错误。把映射封装为一个函数，并让所有访问都从逻辑坐标计算物理坐标，可以降低这种风险。

这个简单映射依赖本文的约束：tile 两个维度都是 32，坐标范围为 0 到 31，每个元素正好是一个 32-bit word。对于非二次幂 tile、向量化访问、多阶段流水线或 Tensor Memory Accelerator（TMA），应根据 transaction 宽度和目标架构设计 swizzle，不能直接照搬 `row ^ col`。

## Padding 与 Swizzling 如何选择

| 维度 | Padding | XOR Swizzling |
| --- | --- | --- |
| 核心方式 | 改变行跨度 | 改变逻辑坐标到物理地址的映射 |
| 额外 shared memory | 每个 32×32 `float` tile 增加 128 字节 | 无 |
| 代码复杂度 | 低，逻辑下标不变 | 中，所有读写路径都必须映射 |
| 对齐影响 | 行跨度可能不再满足向量对齐 | 可保持原始行跨度 |
| 适合场景 | 常规二维 tile、转置、矩阵乘 | shared memory 紧张或布局需要组合重排 |
| 主要风险 | 资源边界和向量化对齐 | 读写映射不一致导致静默错误 |

工程上通常先尝试 Padding：实现简单、容易审查，而且增加的容量很小。只有当 shared-memory 容量、occupancy 临界点、向量对齐或更复杂的数据布局使 Padding 不合适时，再引入封装良好的 Swizzling。

## 用 Nsight Compute 验证，而不是只看公式

bank 映射可以预判风险，但优化是否值得做仍应通过测量确认。推荐按以下顺序验证：

1. **先验证正确性**：与 CPU 转置结果比较，至少覆盖 `1×1`、`31×33`、`1024×2048` 以及宽高互换的矩阵；
2. **保持实验条件一致**：预热 kernel，多次运行，固定输入尺寸和编译选项；
3. **定位 shared-memory 指令**：在 Nsight Compute 的 Shared Memory 表中比较 Requests、Wavefronts 和 Bank Conflicts；
4. **观察 excessive wavefronts**：冲突会让一个请求需要更多串行 wavefront，Padding 或 Swizzling 后应明显下降；
5. **最后看 kernel 时间**：冲突度降低不代表总时间按相同比例下降，实际收益还受 global memory、指令吞吐、occupancy 和延迟隐藏影响。

不要只根据“32-way conflict”推导 kernel 会慢 32 倍。冲突描述的是一条 shared-memory 请求如何被拆分，而 kernel 还可能包含大量计算、全局内存访问和可隐藏延迟的其他 warp。

## 总结

bank conflict 的本质是同一 warp 的一条指令把多个不同地址映射到同一 bank。对 32-bit、完整 warp 的等步长访问，`gcd(stride, 32)` 可以快速判断冲突度；broadcast、宽数据类型和多 transaction 指令则需要额外分析。

矩阵转置把这个问题展示得最清楚：`32×32` tile 的列访问让所有 lane 命中同一 bank；增加一列 Padding 把行跨度改为 33，XOR Swizzling 则在不增加容量的前提下置换物理列。两种方法都应先保证索引和同步正确，再用 Nsight Compute 验证冲突与端到端性能。

## 参考资料

- NVIDIA, [CUDA Programming Guide: Shared Memory Access Patterns](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-cuda-kernels.html#shared-memory-access-patterns)
- NVIDIA, [CUDA C++ Best Practices Guide: Shared Memory and Memory Banks](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#shared-memory-and-memory-banks)
- NVIDIA, [Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html)
- frankshi, [CUDA shared memory 避免 bank conflict 的 swizzling 机制解析](https://zhuanlan.zhihu.com/p/4746910252)
