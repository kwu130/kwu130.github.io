---
title: "NVLS：NCCL 如何借助 NVSwitch 做网络内归约"
description: "从 AllReduce 的数据路径、NCCL 的算法选择到 CUDA multicast 映射，梳理 NVLink SHARP 的工作边界、验证方法与常见误区。"
publishedAt: 2026-09-02
updatedAt: 2026-09-02
tags:
  - "CUDA"
  - "集合通信"
  - "性能优化"
slug: "nvls"
draft: false
---

在多 GPU 训练中，GPU 不只要做矩阵计算，还要不断交换和归约梯度。NVLS（NVLink SHARP）把 Reduce 的一部分工作下沉到 NVLink Switch，也就是 NVSwitch 网络内部，从而减少 GPU 之间的中间转发和 GPU SM 参与通信计算的程度。

先记住一个工程结论：**NVLS 不是需要业务代码显式调用的新通信库，而是 NCCL 在满足硬件、拓扑和 collective 参数时可能选择的一条优化路径。** 应用通常仍然调用 `ncclAllReduce`、`ncclReduceScatter` 等标准 NCCL 接口。

## NVLS 是什么

NVLS 通常解释为 **NVLink SHARP**。这里的 SHARP（Scalable Hierarchical Aggregation and Reduction Protocol）代表一种网络内归约思想：让交换设备在转发数据的同时完成部分 Reduce，而不是把所有数据送到 GPU 后再由 GPU 归约。

在 NCCL 中，同一条 NVLS transport 还可以服务 `AllGather` 的 multicast/broadcast 路径；这属于 NVLS 能力的扩展用法，不改变它以网络内 Reduce 为核心的设计目标。

可以用下面的类比建立直觉：

```text
IB SHARP  -> 在 InfiniBand Switch 中做网络内归约
NVLS      -> 在 NVLink Switch / NVSwitch 中做网络内归约
```

NVLS 的作用范围通常是一个由 NVSwitch 连接起来的 NVLink domain。它与跨节点网络并不是互斥关系：一个多节点作业可以在节点内使用 NVLS，同时用其他 NCCL 网络算法处理节点间通信，最终路径由 NCCL 根据拓扑和消息特征组合决定。

## 为什么集合通信需要它

以数据并行训练为例，每个 GPU 在反向传播后都有一份梯度，下一步需要得到所有 rank 的归约结果：

```text
GPU0: gradient_0  ─┐
GPU1: gradient_1  ─┼─> AllReduce(sum) ─> 每个 GPU 得到完整结果
GPU2: gradient_2  ─┤
GPU3: gradient_3  ─┘
```

传统 Ring 或 Tree 路径中，GPU 通常同时承担三件事：

1. 从链路接收数据；
2. 在通信 kernel 中执行 `sum`、`max` 等归约；
3. 把部分结果继续发送给其他 GPU。

因此通信会消耗显存带宽、SM、寄存器和 kernel 调度资源。归约次数越多、参与 GPU 越多，GPU 间的中间数据搬运也越明显。训练计算与通信需要并行时，通信 kernel 还可能与主计算争用 SM。

NVLS 的目标不是消除所有数据传输，而是让 NVSwitch 处理适合下沉的归约工作：GPU 更多地负责提供输入和接收结果，交换设备负责在网络内部聚合数据。

## 两条数据路径

### 传统 GPU 归约

下面的图只表达数据流的概念，实际 Ring、Tree 和它们的变体会有不同的分块与调度方式：

```text
GPU0 ──> GPU1 ──> GPU2 ──> ...
  │       │       │
  └─ 接收、归约、写回，再继续转发 ─┘
```

对每一块数据，GPU 可能反复执行 `load -> reduce -> store -> send/recv`。这条路径在没有 NVSwitch，或者当前参数不适合 NVLS 时仍然是常见选择。

### NVLS 归约

使用 NVLS 时，可以把路径抽象为：

```text
GPU0 ─┐
GPU1 ─┼─> NVSwitch 进行网络内 Reduce ─> GPU0/GPU1/...
GPU2 ─┤
GPU3 ─┘
```

这里的“进行网络内 Reduce”并不意味着每一个字节都只经过一次交换设备，也不意味着 GPU 完全不执行通信 kernel。NCCL 仍可能把操作拆成多个阶段，使用不同的分块、树形或多阶段实现。准确的算法和数据路径必须结合 NCCL 日志、拓扑与 profiler 判断。

## NVLS 与 NCCL 算法的关系

NVLS 是 NCCL 中的算法路径或算法家族，不是一个独立于 NCCL 的用户态通信库。常见算法的角色可以粗略概括如下：

| 算法路径 | 主要特点 | 常见关注点 |
| --- | --- | --- |
| Ring | 分块后沿环多轮传递，带宽利用率通常较好 | 大消息、链路带宽 |
| Tree | 通过树形聚合和分发减少通信轮次 | 延迟、小消息 |
| CollNet | 结合节点内和节点间的集合通信层次 | 多节点拓扑 |
| NVLS | 利用 NVSwitch 的 multicast/reduce 能力 | NVSwitch domain 内的网络内聚合 |
| NVLSTree | 将树形组织与 NVLS 能力结合 | 延迟与网络内归约的折中 |

NCCL 会综合以下因素选择路径：

- GPU 架构和驱动能力；
- GPU 之间的 NVLink/NVSwitch 拓扑；
- rank 数量和 rank 到 GPU 的映射；
- collective 类型、数据类型和 Reduce op；
- 消息大小以及协议、通道等运行时参数；
- NCCL 版本和环境变量。

所以，平台具备 NVLS 能力并不表示所有 collective、所有消息大小都会走 NVLS。让 NCCL 自动选择通常比全局强制某个算法更稳妥。

## 适用条件与边界

下面关于 collective 和环境变量的说明以 NCCL 2.28.9 为基准；其他版本应以对应的文档、源码和启动日志为准。NVLS 能否使用，至少要同时满足下面几类条件：

| 条件 | 需要确认的内容 |
| --- | --- |
| 硬件 | 节点内存在支持 NVLS 的 GPU 与 NVSwitch，而不只是普通 PCIe 连接 |
| 软件 | 驱动、CUDA 与 NCCL 版本组合支持对应的 NVLS 路径 |
| 拓扑 | 参与 collective 的 rank 位于可以互联的 NVSwitch domain，且映射合理 |
| 操作 | NCCL 2.28.9 可为 `AllReduce`、`ReduceScatter` 和 `AllGather` 选择 NVLS；`Reduce` 只使用 Ring |
| 参数 | 当前数据类型、Reduce op、消息大小和 buffer 形式满足实现限制 |
| 配置 | 没有被 `NCCL_ALGO`、`NCCL_PROTO` 或其他变量排除 NVLS |

下面这些情况通常不能使用，或不应预期有 NVLS 收益：

- 只有 PCIe、没有 NVSwitch 的 GPU 系统；
- 当前 NCCL 版本或驱动不支持 NVLS；
- 点对点 `Send/Recv` 等不包含网络内归约的通信；
- 不受当前 NVLS 路径支持的 collective、数据类型或 Reduce op；
- 消息过小，NCCL 判断其他算法延迟更低；
- rank 分布、进程绑定或拓扑发现异常。

“支持 NVLS”描述的是平台具备这项能力，并不等于每次运行都会选择它。

## 应用层怎么使用

应用层不需要寻找 `nvlsAllReduce` 一类专用 API。初始化 communicator 后，继续调用标准 NCCL collective 即可：

```cpp
ncclResult_t result = ncclAllReduce(
    sendbuff,
    recvbuff,
    count,
    ncclFloat,
    ncclSum,
    comm,
    stream);
```

真实程序还需要为每个 rank 设置正确的 CUDA device、创建 communicator 和 stream，并检查异步 CUDA/NCCL 错误。上面的片段只展示调用边界，不是一个可以单独证明 NVLS 的完整 benchmark。

需要特别注意：单 rank 或只有一块 GPU 的测试无法体现 NVSwitch 网络内归约的价值。要验证 NVLS，至少要在目标节点的多 GPU 拓扑上运行一致的多 rank collective，并与 Ring/Tree 等基线比较。

### Buffer registration 不是启用开关

部分 NCCL 通信路径支持或受益于注册通信缓冲区，例如使用 `ncclMemAlloc` 分配后，再通过 `ncclCommRegister` 和 `ncclCommDeregister` 管理生命周期。它的作用是让 NCCL 获得更明确的 buffer 属性，减少某些路径的额外处理；**调用这些接口本身不保证 collective 一定使用 NVLS**。

是否需要注册、哪些 buffer 可以注册，以及注册后的限制，都应以当前 NCCL 版本的文档和运行日志为准。所有 rank 还必须遵守相同的 buffer 生命周期与 collective 调用顺序，否则首先会遇到通信正确性问题，而不是性能问题。

## 如何打开和确认 NVLS

### 先看硬件拓扑

在目标节点上先确认 GPU 的连接关系：

```bash
nvidia-smi topo -m
nvidia-smi nvlink -s
```

`topo -m` 可以帮助判断 GPU 之间是否存在 NVLink/NVSwitch 路径；具体输出格式会随驱动版本变化。没有 NVSwitch 的机器不应把“没有 NVLS 日志”当成 NCCL 配置错误。

### 再看 NCCL 版本和日志

调试阶段可以打开初始化、图构建、算法选择和 NVLS 日志：

```bash
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,GRAPH,TUNING,NVLS
```

在 NCCL 2.28.9 中，`NCCL_NVLS_ENABLE` 有三种取值：

| 取值 | 行为 |
| ---: | --- |
| `0` | 禁用 NVLS |
| `1` | 强制尝试初始化 NVLS；multicast 资源建立失败时会让初始化返回错误 |
| `2` | 默认的自动探测模式；平台不支持或资源建立失败时回退到非 NVLS 路径 |

因此，生产环境通常应保留默认值 `2`，而不是设置 `NCCL_NVLS_ENABLE=1`。值 `1` 不会强迫每一个 collective 都选择 NVLS，但会跳过正常的能力探测，并把部分原本可以回退的初始化失败变成作业错误。

`INIT` 和 `NVLS` 子系统用于观察 multicast 能力与资源建立，`TUNING` 会在 `INFO` 级别输出 collective 最终选中的 `Algo NVLS`、`Algo NVLSTree` 等算法。如果还需要查看 `COLL` 子系统中的逐 collective 细节，应把 `NCCL_DEBUG` 提升为 `TRACE` 并把 `COLL` 加入 `NCCL_DEBUG_SUBSYS`。

日志只能说明 NCCL 识别、初始化或选择了相应路径，不能单凭一行日志证明吞吐更高。要评价效果，应记录相同消息大小、rank 数和 stream 配置下的带宽、延迟、SM 利用率与端到端训练时间。

### 只在诊断时强制算法

为了验证某条路径是否可用，可以临时尝试：

```bash
export NCCL_ALGO=NVLS
```

强制算法会过滤掉其他候选路径；对于不支持 NVLS 的 collective 或参数，可能直接报“没有可用算法”，也可能性能变差，因此不适合直接作为生产配置。诊断结束后应恢复自动选择，并保留基线结果。若环境中已经设置了 `NCCL_ALGO=Ring` 或其他过滤条件，也要先确认它没有把 NVLS 排除。

## 从 NCCL 调用到底层硬件

从调用链看，应用只看到一个 collective，但 NCCL 内部需要完成拓扑选择、资源建立、buffer 映射和 kernel 调度：

```text
ncclAllReduce
    ↓
NCCL 读取拓扑和 collective 参数
    ↓
选择 Ring / Tree / NVLS 等候选路径
    ↓
建立通信资源与 buffer 映射
    ↓
通信 kernel 发起 GPU 间数据操作
    ↓
NVSwitch 在支持的阶段执行网络内 Reduce
```

NVLS 实现通常会利用 CUDA Driver 的虚拟内存管理和 multicast 能力。相关概念包括：

- VMM 接口，例如 `cuMemCreate`、`cuMemAddressReserve`、`cuMemMap` 和 `cuMemSetAccess`；
- multicast 对象及其设备、内存绑定接口；
- 面向 multicast 地址的设备侧 `multimem` load/reduce 操作。

可以把普通 VMM 和 multicast 映射作如下抽象：

```text
普通映射：
  一个虚拟地址  -> 一个 GPU 的物理内存

multicast 映射：
  一个 multicast 地址 -> 多个 GPU 的物理内存
```

这只是帮助理解数据如何被多个 GPU 共同观察和归约的模型。上述 Driver API 和设备指令属于实现层，不是应用为了“打开 NVLS”而应该直接调用的接口；它们的可用性和细节还受到 GPU 架构、驱动、CUDA Toolkit 与 NCCL 版本的约束。

## NVLS 的收益应该怎样测

NVLS 的收益通常来自三个方向：

1. **减少 GPU 归约工作**：通信 kernel 少做一部分中间 `load/reduce/store`；
2. **减少中间转发**：NVSwitch 可以在网络内部聚合，而不必让每个 GPU 完成所有中继归约；
3. **改善计算通信重叠条件**：SM 压力降低后，主计算 kernel 与通信的资源竞争可能减轻。

“可能”很重要。实际端到端效果还取决于消息大小、计算通信重叠方式、NCCL 通道数、节点间通信比例和训练框架的 bucket 切分。一个合适的验证矩阵至少应包含：

| 维度 | 建议对比 |
| --- | --- |
| 消息大小 | 从小消息到接近训练 bucket 的大消息 |
| collective | `AllReduce`、`ReduceScatter`，必要时加入其他业务操作 |
| 算法 | 自动选择、Ring/Tree 基线、NVLS 诊断配置 |
| rank 布局 | 目标生产布局与简化布局 |
| 指标 | algbw、busbw、延迟、SM 利用率、端到端 step time |

可以先使用 NCCL Tests 做隔离测试，再用 Nsight Systems 或 Nsight Compute 观察真实训练中的 kernel、链路和重叠情况。只看一次 `all_reduce_perf` 的峰值带宽，不足以推出整个训练作业一定加速。

## 没有走 NVLS 时的排查顺序

如果预期走 NVLS，但日志中没有相关路径，可以按这个顺序缩小范围：

1. **确认拓扑**：检查 GPU 型号、NVSwitch 数量和 `nvidia-smi topo -m` 输出；
2. **确认软件**：记录驱动、CUDA Toolkit、NCCL 版本，确认它们来自目标环境；
3. **确认 rank 映射**：检查每个进程绑定的 GPU，排除重复绑定、跨 domain 或容器设备映射错误；
4. **确认 collective 参数**：先用 `ncclSum` 和常见浮点类型测试 `AllReduce`/`ReduceScatter`，再逐步增加其他参数；
5. **清理算法过滤**：检查 `NCCL_ALGO`、`NCCL_PROTO`、`NCCL_P2P_DISABLE`、`NCCL_SHM_DISABLE` 等变量；
6. **提高日志粒度**：先保留 `INIT`、`GRAPH`、`TUNING`、`NVLS` 输出；需要逐 collective 细节时再使用 `TRACE` 与 `COLL`；
7. **最后才做性能判断**：在固定输入、rank 数和进程布局下，与基线重复测量。

排查时不要把“未出现 `NVLS` 字样”直接等同于“功能损坏”。NCCL 可能因为消息规模、数据类型、操作类型或当前拓扑选择了更合适的路径。

## 与 IB SHARP 的区别

两者都采用网络内归约思想，但所在层级不同：

| 对比项 | NVLS | IB SHARP |
| --- | --- | --- |
| 互联网络 | NVLink / NVSwitch | InfiniBand |
| 归约位置 | NVLink Switch / NVSwitch | InfiniBand Switch |
| 典型范围 | 节点内或一个 NVSwitch domain | 多节点 InfiniBand 网络 |
| 常见调用入口 | NCCL collective | NCCL、MPI 或 SHARP 相关软件栈 |
| 主要目标 | 降低 GPU 间 Reduce 的设备侧开销 | 降低网络集合通信的中间转发和归约开销 |

因此，“NVLS 是 NVLink 网络里的 SHARP 思想”是一个有用的类比，但不能据此认为两者可以直接互换，或共享完全相同的配置、拓扑和性能结论。

## 小结

NVLS 的核心是把部分 Reduce 从 GPU SM 下沉到 NVLink Switch：

```text
应用调用 NCCL collective
        ↓
NCCL 检查硬件、拓扑和参数
        ↓
选择合适的通信路径
        ↓
NVSwitch 在支持的阶段参与网络内归约
```

使用时最重要的三点是：

- 继续使用标准 NCCL API，不需要编写专用 NVLS 调用；
- 把环境变量和日志当作诊断手段，不把“启用变量”当成性能保证；
- 用拓扑、NCCL Tests、profiler 和端到端训练指标共同验证，而不是只凭日志关键字下结论。

进一步阅读可以参考 [NCCL 的 collective 文档](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/collectives.html)、[NCCL 环境变量说明](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html) 和 [CUDA Driver API 的虚拟地址管理接口](https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__VA.html)。
