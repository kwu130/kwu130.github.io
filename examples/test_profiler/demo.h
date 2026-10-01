#pragma once

#ifdef __cplusplus
extern "C" {
#endif

int demoAdd(int a, int b);

// 原始实现的入口，仅在编译 libdemo 时开启 PROFAPI 才会导出。
int pdemoAdd(int a, int b);

#ifdef __cplusplus
}
#endif
