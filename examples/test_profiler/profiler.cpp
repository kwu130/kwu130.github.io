#include "demo.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace {
// 本 demo 的应用只有一个线程；生产环境需要线程本地统计或同步。
struct Statistics {
    std::uint64_t calls = 0;
    std::uint64_t total_ns = 0;
    std::uint64_t min_ns = std::numeric_limits<std::uint64_t>::max();
    std::uint64_t max_ns = 0;

    ~Statistics() {
        if (calls == 0) {
            return;
        }
        std::printf("[profiler] summary: calls=%llu total_ns=%llu "
                    "avg_ns=%.2f min_ns=%llu max_ns=%llu\n",
                    static_cast<unsigned long long>(calls),
                    static_cast<unsigned long long>(total_ns),
                    static_cast<double>(total_ns) / static_cast<double>(calls),
                    static_cast<unsigned long long>(min_ns),
                    static_cast<unsigned long long>(max_ns));
    }
};

Statistics statistics;
} // namespace

extern "C" __attribute__((visibility("default")))
int demoAdd(int a, int b) {
    static const bool trace = std::getenv("DEMO_QUIET") == nullptr;
    if (trace) {
        std::printf("[profiler] before demoAdd\n");
    }

    const auto begin = std::chrono::steady_clock::now();
    // 必须调用别名；再次调用 demoAdd 会进入当前 wrapper，导致递归。
    const int ret = pdemoAdd(a, b);
    const auto end = std::chrono::steady_clock::now();
    const auto elapsed = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count());

    ++statistics.calls;
    statistics.total_ns += elapsed;
    if (elapsed < statistics.min_ns) {
        statistics.min_ns = elapsed;
    }
    if (elapsed > statistics.max_ns) {
        statistics.max_ns = elapsed;
    }

    if (trace) {
        std::printf("[profiler] after demoAdd, ret = %d, elapsed_ns = %llu\n",
                    ret, static_cast<unsigned long long>(elapsed));
    }
    return ret;
}
