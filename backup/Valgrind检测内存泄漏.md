# Valgrind介绍
Valgrind 可以用来检测程序是否有非法使用内存的问题，例如访问未初始化的内存、访问数组时越界、忘记释放动态内存等问题。

可以先看看当前环境下是否已安装Valgrind，部分发行版Linux系统会默认安装Valgrind。如果没有安装，则可以使用下面的命令安装 Valgrind。
```
wget https://sourceware.org/pub/valgrind/valgrind-3.15.0.tar.bz2
tar -jxvf valgrind-3.15.0.tar.bz2
cd valgrind-3.16.1
./configure
make
make install
```
# 检测内存泄漏
假设有以下demo：
```
#include <iostream>
#include <cstring>
 
int main() {
    char *s = new char[10];
    strcpy(s, "abc");
    std::cout << s << "\n";
 
    return 0;
}
```
正常编译运行该demo。
```
g++ test.cpp
./a.out
abc  #输出abc
```
不难看出，上述代码申请了10字节的空间，但是并没有释放，因此存在内存泄漏。

那么，我们使用Valgrid来分析看看。运行以下命令：
```
valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all  ./a.out
```
输出如下：
```
==14889== Memcheck, a memory error detector
==14889== Copyright (C) 2002-2017, and GNU GPL'd, by Julian Seward et al.
==14889== Using Valgrind-3.15.0 and LibVEX; rerun with -h for copyright info
==14889== Command: ./a.out
==14889==
abc
==14889==
==14889== HEAP SUMMARY:
==14889==     in use at exit: 10 bytes in 1 blocks
==14889==   total heap usage: 3 allocs, 2 frees, 73,738 bytes allocated
==14889==
==14889== 10 bytes in 1 blocks are definitely lost in loss record 1 of 1
==14889==    at 0x483C583: operator new[](unsigned long) (in /usr/lib/x86_64-linux-gnu/valgrind/vgpreload_memcheck-amd64-linux.so)
==14889==    by 0x1091BE: main (in /home/ansible/code/cplusplus/C-Plus-Plus-master/data_structures/a.out)
==14889==
==14889== LEAK SUMMARY:
==14889==    definitely lost: 10 bytes in 1 blocks
==14889==    indirectly lost: 0 bytes in 0 blocks
==14889==      possibly lost: 0 bytes in 0 blocks
==14889==    still reachable: 0 bytes in 0 blocks
==14889==         suppressed: 0 bytes in 0 blocks
==14889==
==14889== For lists of detected and suppressed errors, rerun with: -s
==14889== ERROR SUMMARY: 1 errors from 1 contexts (suppressed: 0 from 0)
```
首先从HEAP SUMMARY可以发现，在程序退出时，堆中仍有10字节空间在使用中，累计的堆使用情况为：3次申请，2次释放。正是代码中没有释放new申请的空间导致。（此处显示3次申请，但代码中实际只有1次申请，这是因为系统内部有其他内存申请，比如“abc”的保存，需要系统自己申请内存并释放）

然后从LEAK SUMMARY可以发现，有10字节的内存明确地出现了泄漏，和我们代码中申请的内存大小一致。

LEAK SUMMARY中一共列出了definitely lost、indirectly lost等5中内存泄漏类型，分别代表什么意思呢？

- definitely lost（肯定丢失）：意味着你的程序正在泄漏内存——修复这些泄漏！
- indirectly lost（间接丢失）：意味着您的程序正在泄漏基于指针的结构中的内存。 （例如，如果二叉树的根节点“肯定丢失”，则所有子节点都将“间接丢失”。）如果修复“肯定丢失”泄漏，“间接丢失”泄漏应该消失。
- possibly lost（可能丢失）：意味着您的程序正在泄漏内存，除非您使用指针执行不寻常的操作，这可能导致它们指向已分配块的中间。
- still reachable（仍然可达）：意味着你的程序可能没问题——它没有释放它可能拥有的一些内存。 这是很常见的，而且往往是合理的。
- suppressed（抑制）：意味着泄漏错误已被抑制。 默认抑制文件中有一些抑制。 您可以忽略被抑制的错误。

参考：https://valgrind.org/docs/manual/faq.html#faq.deflost

如果代码比较长，或者工程项目比较大，如何快速定位到文件中具体哪些位置的代码导致内存泄漏呢？

这就要在编译可执行文件时使用-g参数，即编译debug版可执行文件。
```
g++ test.cpp -g
```
然后再次进行内存泄漏检测
```
valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all  ./a.out
```
输出如下：
```
==15220== Memcheck, a memory error detector
==15220== Copyright (C) 2002-2017, and GNU GPL'd, by Julian Seward et al.
==15220== Using Valgrind-3.15.0 and LibVEX; rerun with -h for copyright info
==15220== Command: ./a.out
==15220==
abc
==15220==
==15220== HEAP SUMMARY:
==15220==     in use at exit: 10 bytes in 1 blocks
==15220==   total heap usage: 3 allocs, 2 frees, 73,738 bytes allocated
==15220==
==15220== 10 bytes in 1 blocks are definitely lost in loss record 1 of 1
==15220==    at 0x483C583: operator new[](unsigned long) (in /usr/lib/x86_64-linux-gnu/valgrind/vgpreload_memcheck-amd64-linux.so)
==15220==    by 0x1091BE: main (test.cpp:5)
==15220==
==15220== LEAK SUMMARY:
==15220==    definitely lost: 10 bytes in 1 blocks
==15220==    indirectly lost: 0 bytes in 0 blocks
==15220==      possibly lost: 0 bytes in 0 blocks
==15220==    still reachable: 0 bytes in 0 blocks
==15220==         suppressed: 0 bytes in 0 blocks
==15220==
==15220== For lists of detected and suppressed errors, rerun with: -s
==15220== ERROR SUMMARY: 1 errors from 1 contexts (suppressed: 0 from 0)
```
可以发现内存泄漏处的代码位于test.cpp中的第5行，即 char *s = new char[10];

# 检测越界访问
C++ 程序经常出现的 Bug 就是数组越界访问，例如下面的程序出现了越界访问：
```
#include <iostream>
#include <vector>
int main() {
    std::vector<int> v(10, 0);
    std::cout << v[10] << std::endl;
    return 0;
}
```
使用 Valgrind 分析这段程序，Valgrind 会提示越界访问：
```
==15393== Memcheck, a memory error detector
==15393== Copyright (C) 2002-2017, and GNU GPL'd, by Julian Seward et al.
==15393== Using Valgrind-3.15.0 and LibVEX; rerun with -h for copyright info
==15393== Command: ./a.out
==15393==
==15393== Invalid read of size 4
==15393==    at 0x1092CE: main (test.cpp:5)
==15393==  Address 0x4db2ca8 is 0 bytes after a block of size 40 alloc'd
==15393==    at 0x483BE63: operator new(unsigned long) (in /usr/lib/x86_64-linux-gnu/valgrind/vgpreload_memcheck-amd64-linux.so)
==15393==    by 0x109AE3: __gnu_cxx::new_allocator<int>::allocate(unsigned long, void const*) (new_allocator.h:114)
==15393==    by 0x109A45: std::allocator_traits<std::allocator<int> >::allocate(std::allocator<int>&, unsigned long) (alloc_traits.h:443)
==15393==    by 0x10997D: std::_Vector_base<int, std::allocator<int> >::_M_allocate(unsigned long) (stl_vector.h:343)
==15393==    by 0x1097F0: std::_Vector_base<int, std::allocator<int> >::_M_create_storage(unsigned long) (stl_vector.h:358)
==15393==    by 0x1095FC: std::_Vector_base<int, std::allocator<int> >::_Vector_base(unsigned long, std::allocator<int> const&) (stl_vector.h:302)
==15393==    by 0x10944E: std::vector<int, std::allocator<int> >::vector(unsigned long, int const&, std::allocator<int> const&) (stl_vector.h:521)
==15393==    by 0x1092B0: main (test.cpp:4)
==15393==
0
==15393==
==15393== HEAP SUMMARY:
==15393==     in use at exit: 0 bytes in 0 blocks
==15393==   total heap usage: 3 allocs, 3 frees, 73,768 bytes allocated
==15393==
==15393== All heap blocks were freed -- no leaks are possible
==15393==
==15393== For lists of detected and suppressed errors, rerun with: -s
==15393== ERROR SUMMARY: 1 errors from 1 contexts (suppressed: 0 from 0)
```
从输出中可以看出，在test.cpp:5处报错，Invalid read of size 4，Address 0x4db2ca8 is 0 bytes after a block of size 40 alloc'd，因为v申请了10个元素，每个元素大小为4字节（sizeof(int)），当访问v[10]时，已经超出了v的空间大小（4*10字节），因此报错。

# 检测未初始化的内存
另一种经常出现的 Bug，就是程序访问了未初始化的内存。例如：
```
#include <iostream>
int main() {
    int x;
    if (x == 0) {
        std::cout << "X is zero" << std::endl;
    }
    return 0;
}
```
使用 Valgrind 检测这个程序：
```
==15472== Memcheck, a memory error detector
==15472== Copyright (C) 2002-2017, and GNU GPL'd, by Julian Seward et al.
==15472== Using Valgrind-3.15.0 and LibVEX; rerun with -h for copyright info
==15472== Command: ./a.out
==15472==
==15472== Conditional jump or move depends on uninitialised value(s)
==15472==    at 0x1091B9: main (test.cpp:4)
==15472==
X is zero
==15472==
==15472== HEAP SUMMARY:
==15472==     in use at exit: 0 bytes in 0 blocks
==15472==   total heap usage: 2 allocs, 2 frees, 73,728 bytes allocated
==15472==
==15472== All heap blocks were freed -- no leaks are possible
==15472==
==15472== Use --track-origins=yes to see where uninitialised values come from
==15472== For lists of detected and suppressed errors, rerun with: -s
==15472== ERROR SUMMARY: 1 errors from 1 contexts (suppressed: 0 from 0)
```
输出中提示了test.cpp文件的第 4 行访问了未初始化的内存。

# 总结
以上就是常见的使用Valgrind进行内存泄漏检查的常见，更过的使用方式和场景请参考官方文档 https://valgrind.org/



