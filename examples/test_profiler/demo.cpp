#include "demo.h"

#include <cstdio>
#include <cstdlib>

#ifdef PROFAPI
#if !defined(__ELF__)
#error "PROFAPI requires an ELF target; use Linux with GCC or Clang."
#endif

// alias 与目标函数必须位于同一翻译单元，且类型一致。
// 使用标准可变参数宏，替代 GNU 风格的 args...。
#define DEMO_API(ret, func, ...)                                  \
    extern "C" __attribute__((visibility("default")))             \
        __attribute__((alias(#func))) ret p##func(__VA_ARGS__);  \
    extern "C" __attribute__((visibility("default")))             \
        __attribute__((weak)) ret func(__VA_ARGS__)
#else
#define DEMO_API(ret, func, ...)                                  \
    extern "C" __attribute__((visibility("default")))             \
        ret func(__VA_ARGS__)
#endif

DEMO_API(int, demoAdd, int a, int b) {
    static const bool trace = std::getenv("DEMO_QUIET") == nullptr;
    if (trace) {
        std::printf("[libdemo] original demoAdd(%d, %d)\n", a, b);
    }
    return a + b;
}
