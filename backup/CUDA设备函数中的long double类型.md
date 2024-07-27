# 背景
从CUDA设备端math函数声明中发现部分函数支持long double类型的参数，但实际在使用时nvcc编译却发出以下警告：
```
'long double' is treated as 'double' in device code
```
从字面意思上可以看出，在设备端代码中，CUDA将long double类型当做double类型来处理，那么实际情况是怎样的呢？

# 测试
编译以下测试代码
```
#include <iostream>
#include <cstdio>
#include <cuda_runtime.h>
 
 
__global__
void kernel(long double * d_data) {
    long double x = 1.3;
    *d_data = x;
     
    printf("--------------- device --------------\n");
    char *ch = reinterpret_cast<char*>(d_data);
    for (int i = 0; i < sizeof(long double); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
     
    double z = static_cast<double>(*d_data);
    ch = reinterpret_cast<char*>(&z);
    for (int i = 0; i < sizeof(double); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
}
 
int main() {
     
    long double *d_data;
    long double *h_data;
    h_data = (long double*)malloc(sizeof(long double));
    cudaMalloc((void**)&d_data, sizeof(long double));
    kernel<<<1, 1>>>(d_data);
     
    cudaDeviceSynchronize();
    printf("--------------- host --------------\n");
 
    cudaMemcpy(h_data, d_data, sizeof(long double), cudaMemcpyDeviceToHost);
     
    char *ch = reinterpret_cast<char*>(h_data);
    for (int i = 0; i < sizeof(long double); ++i) {
        printf("addr: %p value: %08x\n", &ch[i], ch[i]);
    }
    printf("\n");
     
    double x = 1.3;
    ch = reinterpret_cast<char*>(&x);
    for (int i = 0; i < sizeof(double); ++i) {
        printf("addr: %p value: %08x\n", &ch[i], ch[i]);
    }
    printf("\n");
     
 
    long double y = 1.3;
    ch = reinterpret_cast<char*>(&y);
    for (int i = 0; i < sizeof(long double); ++i) {
        printf("addr: %p value: %08x\n", &ch[i], ch[i]);
    }
    printf("\n");
     
    double z = static_cast<double>(y);
    ch = reinterpret_cast<char*>(&z);
    for (int i = 0; i < sizeof(double); ++i) {
        printf("addr: %p value: %08x\n", &ch[i], ch[i]);
    }
    printf("\n");
 
    return 0;
}
```
输出结果如下：
```
--------------- device --------------
addr: 0x7f2b80a00000 value: ffffffcd
addr: 0x7f2b80a00001 value: ffffffcc
addr: 0x7f2b80a00002 value: ffffffcc
addr: 0x7f2b80a00003 value: ffffffcc
addr: 0x7f2b80a00004 value: ffffffcc
addr: 0x7f2b80a00005 value: ffffffcc
addr: 0x7f2b80a00006 value: fffffff4
addr: 0x7f2b80a00007 value: 0000003f
addr: 0x7f2b80a00008 value: 00000000
addr: 0x7f2b80a00009 value: 00000000
addr: 0x7f2b80a0000a value: 00000000
addr: 0x7f2b80a0000b value: 00000000
addr: 0x7f2b80a0000c value: 00000000
addr: 0x7f2b80a0000d value: 00000000
addr: 0x7f2b80a0000e value: 00000000
addr: 0x7f2b80a0000f value: 00000000
 
addr: 0x7f2ba4fffd08 value: ffffffcd
addr: 0x7f2ba4fffd09 value: ffffffcc
addr: 0x7f2ba4fffd0a value: ffffffcc
addr: 0x7f2ba4fffd0b value: ffffffcc
addr: 0x7f2ba4fffd0c value: ffffffcc
addr: 0x7f2ba4fffd0d value: ffffffcc
addr: 0x7f2ba4fffd0e value: fffffff4
addr: 0x7f2ba4fffd0f value: 0000003f
 
--------------- host --------------
addr: 0x6bde20 value: ffffffcd
addr: 0x6bde21 value: ffffffcc
addr: 0x6bde22 value: ffffffcc
addr: 0x6bde23 value: ffffffcc
addr: 0x6bde24 value: ffffffcc
addr: 0x6bde25 value: ffffffcc
addr: 0x6bde26 value: fffffff4
addr: 0x6bde27 value: 0000003f
addr: 0x6bde28 value: 00000000
addr: 0x6bde29 value: 00000000
addr: 0x6bde2a value: 00000000
addr: 0x6bde2b value: 00000000
addr: 0x6bde2c value: 00000000
addr: 0x6bde2d value: 00000000
addr: 0x6bde2e value: 00000000
addr: 0x6bde2f value: 00000000
 
addr: 0x7ffdc0ff3b08 value: ffffffcd
addr: 0x7ffdc0ff3b09 value: ffffffcc
addr: 0x7ffdc0ff3b0a value: ffffffcc
addr: 0x7ffdc0ff3b0b value: ffffffcc
addr: 0x7ffdc0ff3b0c value: ffffffcc
addr: 0x7ffdc0ff3b0d value: ffffffcc
addr: 0x7ffdc0ff3b0e value: fffffff4
addr: 0x7ffdc0ff3b0f value: 0000003f
 
addr: 0x7ffdc0ff3af0 value: 00000000
addr: 0x7ffdc0ff3af1 value: 00000068
addr: 0x7ffdc0ff3af2 value: 00000066
addr: 0x7ffdc0ff3af3 value: 00000066
addr: 0x7ffdc0ff3af4 value: 00000066
addr: 0x7ffdc0ff3af5 value: 00000066
addr: 0x7ffdc0ff3af6 value: 00000066
addr: 0x7ffdc0ff3af7 value: ffffffa6
addr: 0x7ffdc0ff3af8 value: ffffffff
addr: 0x7ffdc0ff3af9 value: 0000003f
addr: 0x7ffdc0ff3afa value: 00000000
addr: 0x7ffdc0ff3afb value: 00000000
addr: 0x7ffdc0ff3afc value: 00000001
addr: 0x7ffdc0ff3afd value: 00000000
addr: 0x7ffdc0ff3afe value: 00000000
addr: 0x7ffdc0ff3aff value: 00000000
 
addr: 0x7ffdc0ff3ae8 value: ffffffcd
addr: 0x7ffdc0ff3ae9 value: ffffffcc
addr: 0x7ffdc0ff3aea value: ffffffcc
addr: 0x7ffdc0ff3aeb value: ffffffcc
addr: 0x7ffdc0ff3aec value: ffffffcc
addr: 0x7ffdc0ff3aed value: ffffffcc
addr: 0x7ffdc0ff3aee value: fffffff4
addr: 0x7ffdc0ff3aef value: 0000003f
```
现在我们结合输出来进行分析。

## 第一部分输出
这里是在设备端定义一个long double类型，并赋值1.3，然后按照long double所占字节数将其内存中的数据按十六进制进行输出。可以发现，long double在设备端占16字节，然后其低8字节有具体的数值，高8字节全为0（这会不会就是所说的treated as double，继续往下分析）。

## 第二部分输出
这里是将设备端的long double通过static_cast转为double后输出其内存中的十六进制数据。可以发现，该double类型的数据在内存中的值和上面的long double的低8字节完全一致。

## 第三部分输出
这里是将设备端的long double拷贝到主机端后对齐内存数据进行十六进制输出。可以发现，其输出结果和设备端一致，可以说明拷贝是准确无误的。

## 第四部分输出
这里是在主机端定义一个double变量并赋值1.3，然后输出其内存数据的十六进制形式。可以发现，其输出结果和设备端的double类型一致，且和设备端long double的低8字节一致。

## 第五部分输出
这里是在主机端定义一个long double变量并赋值1.3，然后输出其内存数据的十六进制形式。可以发现，其输出结果和设备端的long double完全不一样，说明真正的long double(1.3)的内存数据应该是这样的。

## 第六部分输出
这里是在主机端的long double通过static_cast转为double后输出其内存中的十六进制数据。可以发现，转换后的double的十六进制形式
并不是简单取long double的低8字节，而是转成double(1.3)真实的十六进制形式。

# 总结
综上所述，设备端的long double虽然是16字节，但是其内部数据是按照double构成的，真实的数据分布在低8字节上，高8字节并不会使用，当期处理long double类型的数据时，可以近似看作取低8字节作为double类型进行操作。

PS：从上面的测试结果还可以看出一个问题，static_cast在主机端和设备端的表现形式不一致，设备端和主机端不同的long double被static_cast作用后却得到了相同的结果，理论上static_cast在主机端和设备端的表现应该一样，这里不一样，猜测还是因为对于long double特殊的处理逻辑，比如当在设备端调用static_cast<double>(*d_data)时，static_cast并没有将*d_data当做16字节的long double，而是当做了8字节的double，也就是说传进去的入参实际上是long double的前8个字节，所以本质上做了一个static_cast<double>(double)。

验证static_cast在主机端和设备端表现应该一致：

```
#include <iostream>
#include <cstdio>
#include <cuda_runtime.h>
 
 
__global__
void kernel() {
    printf("--------------- device --------------\n");
     
    float f = 1.3;
    char *ch = reinterpret_cast<char*>(&f);
    for (int i = 0; i < sizeof(float); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
     
    int ii = static_cast<int>(f);
    ch = reinterpret_cast<char*>(&ii);
    for (int i = 0; i < sizeof(int); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
}
 
int main() {
    kernel<<<1, 1>>>();
     
    cudaDeviceSynchronize();
    printf("--------------- host --------------\n");
     
    float f = 1.3;
    char *ch = reinterpret_cast<char*>(&f);
    for (int i = 0; i < sizeof(float); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
     
    int ii = static_cast<int>(f);
    ch = reinterpret_cast<char*>(&ii);
    for (int i = 0; i < sizeof(int); ++i) {
        printf("addr: %p value: %08x\n", &(ch[i]), ch[i]);
    }
    printf("\n");
 
    return 0;
}
```
输出结果为：
```
--------------- device --------------
addr: 0x7f1f36fffd08 value: 00000066
addr: 0x7f1f36fffd09 value: 00000066
addr: 0x7f1f36fffd0a value: ffffffa6
addr: 0x7f1f36fffd0b value: 0000003f
 
addr: 0x7f1f36fffd0c value: 00000001
addr: 0x7f1f36fffd0d value: 00000000
addr: 0x7f1f36fffd0e value: 00000000
addr: 0x7f1f36fffd0f value: 00000000
 
--------------- host --------------
addr: 0x7ffce3298954 value: 00000066
addr: 0x7ffce3298955 value: 00000066
addr: 0x7ffce3298956 value: ffffffa6
addr: 0x7ffce3298957 value: 0000003f
 
addr: 0x7ffce3298950 value: 00000001
addr: 0x7ffce3298951 value: 00000000
addr: 0x7ffce3298952 value: 00000000
addr: 0x7ffce3298953 value: 00000000
```
从上面的测试可以发现，对于float转int，主机端和设备端的static_cast表现形式一致。

