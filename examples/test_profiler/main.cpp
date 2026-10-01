#include "demo.h"

#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <system_error>

int main(int argc, char** argv) {
    unsigned int iterations = 1;
    if (argc > 2) {
        std::fprintf(stderr, "usage: %s [iterations: 1..1000000]\n", argv[0]);
        return 2;
    }
    if (argc == 2) {
        const char* end = argv[1] + std::strlen(argv[1]);
        const auto parsed = std::from_chars(argv[1], end, iterations);
        if (parsed.ec != std::errc{} || parsed.ptr != end ||
            iterations == 0 || iterations > 1000000) {
            std::fprintf(stderr, "iterations must be an integer in 1..1000000\n");
            return 2;
        }
    }

    std::printf("[app] call demoAdd, iterations = %u\n", iterations);
    std::uint64_t checksum = 0;
    int ret = 0;
    for (unsigned int i = 0; i < iterations; ++i) {
        ret = demoAdd(10, 20);
        if (ret != 30) {
            std::fprintf(stderr, "unexpected result: %d\n", ret);
            return 1;
        }
        checksum += static_cast<std::uint64_t>(ret);
    }
    std::printf("[app] result = %d, calls = %u, checksum = %llu\n",
                ret, iterations, static_cast<unsigned long long>(checksum));
    return 0;
}
