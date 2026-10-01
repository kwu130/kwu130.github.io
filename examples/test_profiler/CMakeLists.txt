cmake_minimum_required(VERSION 3.20)
project(test_profiler LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "This demo requires Linux/ELF. macOS Mach-O is not supported.")
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang)$")
    message(FATAL_ERROR "Use GCC or Clang for the alias/weak attributes.")
endif()

option(DEMO_ENABLE_PROFAPI "Export the original implementation alias" ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_BUILD_RPATH_USE_ORIGIN ON)
add_compile_options(-Wall -Wextra -Wpedantic)

add_library(demo SHARED demo.cpp)
set_target_properties(demo PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES)
if(DEMO_ENABLE_PROFAPI)
    target_compile_definitions(demo PRIVATE PROFAPI)
endif()

add_executable(app main.cpp)
target_link_libraries(app PRIVATE demo)
set_target_properties(app PROPERTIES BUILD_RPATH "$ORIGIN")

if(DEMO_ENABLE_PROFAPI)
    add_library(profiler SHARED profiler.cpp)
    target_link_libraries(profiler PRIVATE demo)
    target_link_options(profiler PRIVATE -Wl,-z,defs)
    set_target_properties(profiler PROPERTIES
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN YES
        BUILD_RPATH "$ORIGIN")

    enable_testing()
    find_program(BASH_EXECUTABLE bash)
    if(NOT BASH_EXECUTABLE)
        message(FATAL_ERROR "bash is required for verify.sh")
    endif()
    add_test(NAME preload_and_symbols
        COMMAND "${BASH_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/verify.sh"
                "$<TARGET_FILE_DIR:app>")
endif()
