cmake_minimum_required(VERSION 3.18)

project(ips4o-benchmark-suite)

# ------------------------------------------------------------
# Global config
# ------------------------------------------------------------
set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake/)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
include(default_build_type)

add_definitions(-D__STDC_LIMIT_MACROS -D__STDC_CONSTANT_MACROS)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -DNDEBUG -g -march=native -mcx16 -include cstdint")
set(CMAKE_CXX_FLAGS_DEBUG   "${CMAKE_CXX_FLAGS_DEBUG}   -g -march=native -mcx16 -include cstdint")
set(CMAKE_C_FLAGS_RELEASE   "${CMAKE_C_FLAGS_RELEASE}   -DNDEBUG -g -march=native")
set(CMAKE_C_FLAGS_DEBUG     "${CMAKE_C_FLAGS_DEBUG}     -g -march=native")

# IMPORTANT: prevent bundled oneTBB from generating install/export rules (fixes your TBBTargets export errors)
set(CMAKE_SKIP_INSTALL_RULES ON)

# --- Atomic ---
find_library(ATOMIC_LIBRARY NAMES atomic libatomic.so.1 HINTS /usr/lib64 /usr/lib)
if(NOT ATOMIC_LIBRARY)
  set(ATOMIC_LIBRARY atomic)
endif()

# --- Threads ---
find_package(Threads REQUIRED)

# --- OpenMP ---
find_package(OpenMP REQUIRED)

# --- Disable checkers (your flag) ---
option(BENCHMARK_DISABLE_CHECKS "Disable benchmark checkers for performance analysis" ON)
if(BENCHMARK_DISABLE_CHECKS)
  message(STATUS "Benchmark checkers are DISABLED for performance analysis (globally).")
  add_compile_definitions(DISABLE_PERF_INTERFERENCE_CHECKS)
else()
  message(STATUS "Benchmark checkers are ENABLED (globally).")
endif()

# --- IPP Radixsort toggle (unchanged) ---
set(IPPRADIXSORT "Disable" CACHE STRING "Build type. Default is Disable")
set_property(CACHE IPPRADIXSORT PROPERTY STRINGS Disable Enable)
if ("${IPPRADIXSORT}" STREQUAL "Enable")
  set(IPP_STATIC "ON")
  find_library(IPP_CORE libippcore.a PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_VM   libippvm.a   PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_S    libipps.a    PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_I    libippi.a    PATHS ~/tmp/intel/ipp/lib/intel64)
endif()
message(STATUS "ippradixsort: ${IPPRADIXSORT}")

# --- IPS4O timer toggle (unchanged) ---
set(IPS4O_TIMER "Disable" CACHE STRING "Build type. Default is Disable")
set_property(CACHE IPS4O_TIMER PROPERTY STRINGS Disable Enable)
if ("${IPS4O_TIMER}" STREQUAL "Enable")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DIPS4O_TIMER")
endif()
message(STATUS "IPS4o timer: ${IPS4O_TIMER}")

# ------------------------------------------------------------
# [A] hwloc via extern submodule (build static lib only, avoid docs)
# Provides a TARGET named "hwloc" for extern/NumaArray
# ------------------------------------------------------------
include(ExternalProject)

set(HWLOC_SRC_DIR     "${CMAKE_CURRENT_SOURCE_DIR}/extern/hwloc")
# 定义一个固定的安装目录（就在 build/_deps 下，很安全）
set(HWLOC_INSTALL_DIR "${CMAKE_BINARY_DIR}/_deps/hwloc-install") 
file(MAKE_DIRECTORY ${HWLOC_INSTALL_DIR}/include) # 防止 configure 前 include 目录不存在报错

if(EXISTS "${HWLOC_SRC_DIR}")
  # 配置命令：指定安装到我们预设的目录
  if(EXISTS "${HWLOC_SRC_DIR}/configure")
    set(_HWLOC_CONFIGURE_LINE
      "${HWLOC_SRC_DIR}/configure --prefix=${HWLOC_INSTALL_DIR} --disable-shared --enable-static"
    )
  elseif(EXISTS "${HWLOC_SRC_DIR}/autogen.sh")
    set(_HWLOC_CONFIGURE_LINE
      "${HWLOC_SRC_DIR}/autogen.sh && ${HWLOC_SRC_DIR}/configure --prefix=${HWLOC_INSTALL_DIR} --disable-shared --enable-static"
    )
  else()
    message(FATAL_ERROR "extern/hwloc exists but no configure/autogen.sh found.")
  endif()

  ExternalProject_Add(hwloc_ep
    SOURCE_DIR "${HWLOC_SRC_DIR}"
    CONFIGURE_COMMAND /bin/sh -c "${_HWLOC_CONFIGURE_LINE}"
    # 编译命令：标准 make
    BUILD_COMMAND $(MAKE) -j
    # 安装命令：开启 install，把它装到 HWLOC_INSTALL_DIR
    INSTALL_COMMAND $(MAKE) install
    BUILD_IN_SOURCE 1
  )

  # 创建 Target
  add_library(hwloc STATIC IMPORTED GLOBAL)
  add_dependencies(hwloc hwloc_ep)

  # === 关键修正 ===
  # 不再用 if(EXISTS) 去猜，直接指向安装目录下的固定路径
  set(_HWLOC_LIB_A "${HWLOC_INSTALL_DIR}/lib/libhwloc.a")
  
  # 告诉 CMake 库就在这里 (虽然现在文件还不存在，但在链接前它一定会在)
  set_target_properties(hwloc PROPERTIES
    IMPORTED_LOCATION "${_HWLOC_LIB_A}"
    INTERFACE_INCLUDE_DIRECTORIES "${HWLOC_INSTALL_DIR}/include"
  )
else()
  message(WARNING "extern/hwloc not found.")
endif()


# ------------------------------------------------------------
# TCLAP (header-only)
# ------------------------------------------------------------
add_library(tclap INTERFACE)

# Most common layout: extern/tclap/include/tclap/CmdLine.h
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/tclap/include/tclap/CmdLine.h")
  target_include_directories(tclap INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/extern/tclap/include
  )
# Fallback layout: extern/tclap/tclap/CmdLine.h (less common)
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/tclap/tclap/CmdLine.h")
  target_include_directories(tclap INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/extern/tclap
  )
else()
  message(FATAL_ERROR "TCLAP not found. Expected one of:
  - extern/tclap/include/tclap/CmdLine.h
  - extern/tclap/tclap/CmdLine.h
  Please check the tclap submodule layout.")
endif()
# ------------------------------------------------------------
# [B] NUMA headers fallback (no numactl-devel required)
# ------------------------------------------------------------
find_library(NUMA_LIBRARY NAMES numa libnuma.so libnuma.so.1
  HINTS $ENV{HOME}/opt/numactl/lib /usr/lib /usr/lib64 /usr/local/lib
)

if(NOT NUMA_LIBRARY)
  message(FATAL_ERROR "Could not find libnuma (numactl-libs).")
else()
  message(STATUS "Found NUMA library: ${NUMA_LIBRARY}")
  
  # === [FIX] 防止 ld 找不到 -lnuma ===
  # 如果某个子模块写了 link(numa)，我们要拦截它并指向具体文件
  if(NOT TARGET numa)
    add_library(numa UNKNOWN IMPORTED)
    set_target_properties(numa PROPERTIES IMPORTED_LOCATION "${NUMA_LIBRARY}")
  endif()
endif()

find_path(SYSTEM_NUMA_INC NAMES numa.h HINTS /usr/include /usr/local/include)
set(NUMACTL_SUBMODULE_INC "${CMAKE_CURRENT_SOURCE_DIR}/extern/sample_sort_tiled/external/numactl")

if(SYSTEM_NUMA_INC)
  message(STATUS "Found System libnuma headers: ${SYSTEM_NUMA_INC}")
  set(NUMA_INCLUDE_DIR "${SYSTEM_NUMA_INC}")
else()
  message(STATUS "System libnuma headers NOT found. Using headers from submodule...")
  if(NOT EXISTS "${NUMACTL_SUBMODULE_INC}/numa.h")
    message(FATAL_ERROR "numa.h not found. Expected at: ${NUMACTL_SUBMODULE_INC}/numa.h")
  endif()
  set(NUMA_INCLUDE_DIR "${NUMACTL_SUBMODULE_INC}")
endif()

# ------------------------------------------------------------
# Submodules that define tlx/checker/dsfmt/numa_array/etc
# IMPORTANT: build these BEFORE building bundled TBB, but do NOT globally link them.
# ------------------------------------------------------------
add_subdirectory(extern/InPlaceMSDradixsort)
add_subdirectory(extern/NumaArray)
add_subdirectory(extern/CPPSFMT)
add_subdirectory(extern/SortChecker)
# === 【新增补丁】 ===
# 强制指定 dsfmt 库的头文件目录，这样所有链接了 dsfmt 的程序都能找到 SimdMt.hpp
if(TARGET dsfmt)
  target_include_directories(dsfmt INTERFACE 
    "${CMAKE_CURRENT_SOURCE_DIR}/extern/CPPSFMT/include"
  )
endif()
# Disable parallel as we do not use the default libraries (as you had)
option(IPS4O_DISABLE_PARALLEL "Enable parallel code of IPS4o" ON)
option(IPS2RA_DISABLE_PARALLEL "Enable parallel code of IPS2RA" ON)
option(PS4O_DISABLE_PARALLEL "Enable parallel code of PS4o" ON)

add_subdirectory(extern/ips4o_journal)
add_subdirectory(extern/ips2ra_journal)
add_subdirectory(extern/ps4o)

# ------------------------------------------------------------
# Inject NUMA include dirs to targets that include <numa.h>
# (No edits inside extern submodules)
# ------------------------------------------------------------
if(TARGET inpmsdradix)
  target_include_directories(inpmsdradix PRIVATE "${NUMA_INCLUDE_DIR}")
endif()
if(TARGET topo)
  target_include_directories(topo PRIVATE "${NUMA_INCLUDE_DIR}")
endif()
if(TARGET silo)
  target_include_directories(silo PRIVATE "${NUMA_INCLUDE_DIR}")
endif()
if(TARGET numa_array)
  target_include_directories(numa_array INTERFACE "${NUMA_INCLUDE_DIR}")
endif()

# ------------------------------------------------------------
# Inject HWLOC headers to NumaArray targets (no edits)
# ------------------------------------------------------------
if(EXISTS "${HWLOC_SRC_DIR}")
  set(HWLOC_INC_CAND1 "${HWLOC_SRC_DIR}/include")
  set(HWLOC_INC_CAND2 "${CMAKE_BINARY_DIR}/hwloc_ep-prefix/src/hwloc_ep/include")
  set(HWLOC_INC_CAND3 "${CMAKE_BINARY_DIR}/hwloc_ep-prefix/src/hwloc_ep/include/hwloc")

  set(HWLOC_INCLUDE_DIR "")
  if(EXISTS "${HWLOC_INC_CAND1}/hwloc.h")
    set(HWLOC_INCLUDE_DIR "${HWLOC_INC_CAND1}")
  elseif(EXISTS "${HWLOC_INC_CAND2}/hwloc.h")
    set(HWLOC_INCLUDE_DIR "${HWLOC_INC_CAND2}")
  elseif(EXISTS "${HWLOC_INC_CAND3}/hwloc.h")
    set(HWLOC_INCLUDE_DIR "${HWLOC_INC_CAND3}")
  else()
    message(FATAL_ERROR "Cannot find hwloc.h in expected locations:
    - ${HWLOC_INC_CAND1}/hwloc.h
    - ${HWLOC_INC_CAND2}/hwloc.h
    - ${HWLOC_INC_CAND3}/hwloc.h")
  endif()

  message(STATUS "Using hwloc headers from: ${HWLOC_INCLUDE_DIR}")

  if(TARGET topo)
    target_include_directories(topo PUBLIC "${HWLOC_INCLUDE_DIR}")
  endif()
  if(TARGET silo)
    target_include_directories(silo PUBLIC "${HWLOC_INCLUDE_DIR}")
  endif()
  if(TARGET numa_array)
    target_include_directories(numa_array PUBLIC "${HWLOC_INCLUDE_DIR}")
  endif()
endif()
# ------------------------------------------------------------
# TBB (prefer system; fallback to bundled oneTBB)
# ------------------------------------------------------------
find_package(TBB CONFIG QUIET)
if(TBB_FOUND)
  set(TBB_LIBRARY TBB::tbb)
  get_target_property(TBB_INCLUDE_DIR TBB::tbb INTERFACE_INCLUDE_DIRECTORIES)
  message(STATUS "Found System TBB: ${TBB_LIBRARY}")
else()
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/extern/tbb/CMakeLists.txt")
    message(STATUS "Using bundled oneTBB submodule")
    set(TBB_TEST OFF CACHE BOOL "" FORCE)
    set(TBB_EXAMPLES OFF CACHE BOOL "" FORCE)
    # optional: reduce noise / strictness
    set(TBB_STRICT OFF CACHE BOOL "" FORCE)
    
    add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/extern/tbb EXCLUDE_FROM_ALL)

    # ==================== 【在这里插入修复代码】 ====================
    # 强制 TBB 目标使用 C++14 和宽松模式，避免 C++20 的命名冲突错误
    if(TARGET tbb)
      set_target_properties(tbb PROPERTIES CXX_STANDARD 14)
      # 针对 GCC/Clang 开启 -fpermissive
      target_compile_options(tbb PRIVATE $<$<CXX_COMPILER_ID:GNU,Clang>:-fpermissive>)
    endif()

    if(TARGET tbbmalloc)
      set_target_properties(tbbmalloc PROPERTIES CXX_STANDARD 14)
      target_compile_options(tbbmalloc PRIVATE $<$<CXX_COMPILER_ID:GNU,Clang>:-fpermissive>)
    endif()
    # =============================================================

    set(TBB_LIBRARY tbb)
    get_target_property(TBB_INCLUDE_DIR tbb INTERFACE_INCLUDE_DIRECTORIES)
  else()
    message(FATAL_ERROR "TBB not found. Please init submodule or install system oneTBB.")
  endif()
endif()

# Propagate to libs that include <tbb/...> in headers
foreach(lib ips4o ps4o ips2ra)
  if(TARGET ${lib})
    target_link_libraries(${lib} INTERFACE ${TBB_LIBRARY})
    # 注意：如果 TBB_INCLUDE_DIR 为空（有时 add_subdirectory 后可能是这样），这行可能会报错，通常 INTERFACE 链接已经足够
    if(TBB_INCLUDE_DIR)
        target_include_directories(${lib} INTERFACE ${TBB_INCLUDE_DIR})
    endif()
  endif()
endforeach()

# ------------------------------------------------------------
# Helper: link common libs to OUR executables only
# ------------------------------------------------------------
function(link_common_libs tgt)
  if(TARGET ${tgt})
    target_link_libraries(${tgt} PRIVATE
    tclap
      tlx checker dsfmt numa_array
      hwloc
      ${NUMA_LIBRARY}
      Threads::Threads
      ${ATOMIC_LIBRARY}
    )
  endif()
endfunction()

# ------------------------------------------------------------
# Benchmark executables
# ------------------------------------------------------------
add_executable(benchmark_ips4oparallel src/benchmark/benchmark_ips4oparallel.cpp)
target_link_libraries(benchmark_ips4oparallel PRIVATE ips4o OpenMP::OpenMP_CXX ${TBB_LIBRARY})

add_executable(benchmark_ips4o src/benchmark/benchmark_ips4o.cpp)
target_link_libraries(benchmark_ips4o PRIVATE ips4o OpenMP::OpenMP_CXX ${TBB_LIBRARY})

add_executable(benchmark_ips2ra src/benchmark/benchmark_ips2ra.cpp)
target_link_libraries(benchmark_ips2ra PRIVATE ips2ra OpenMP::OpenMP_CXX ${TBB_LIBRARY})

add_executable(benchmark_ips2raparallel src/benchmark/benchmark_ips2raparallel.cpp)
target_link_libraries(benchmark_ips2raparallel PRIVATE ips2ra OpenMP::OpenMP_CXX ${TBB_LIBRARY})

add_executable(benchmark_mcstlmwm src/benchmark/benchmark_mcstlmwm.cpp)
target_link_libraries(benchmark_mcstlmwm PRIVATE OpenMP::OpenMP_CXX)

add_executable(benchmark_mcstlbq src/benchmark/benchmark_mcstlbq.cpp)
target_link_libraries(benchmark_mcstlbq PRIVATE OpenMP::OpenMP_CXX)

# add_executable(benchmark_stdsort src/benchmark/benchmark_stdsort.cpp)
# target_link_libraries(benchmark_stdsort PRIVATE OpenMP::OpenMP_CXX)

if ("${IPPRADIXSORT}" STREQUAL "Enable")
  add_executable(benchmark_ippradixsort src/benchmark/benchmark_ippradixsort.cpp)
  target_include_directories(benchmark_ippradixsort PRIVATE ~/tmp/intel/ipp/include)
  target_link_libraries(benchmark_ippradixsort PRIVATE ${IPP_S} ${IPP_I} ${IPP_VM} ${IPP_CORE} OpenMP::OpenMP_CXX)
endif()

# Link our common libs (no global pollution)
link_common_libs(benchmark_ips4oparallel)
link_common_libs(benchmark_ips4o)
link_common_libs(benchmark_ips2ra)
link_common_libs(benchmark_ips2raparallel)
link_common_libs(benchmark_mcstlmwm)
link_common_libs(benchmark_mcstlbq)
# link_common_libs(benchmark_stdsort)
if ("${IPPRADIXSORT}" STREQUAL "Enable")
  link_common_libs(benchmark_ippradixsort)
endif()

# ------------------------------------------------------------
# ParlayLib
# ------------------------------------------------------------
add_library(parlaylib INTERFACE)
target_include_directories(parlaylib INTERFACE extern/parlaylib/include)

add_executable(benchmark_plss src/benchmark/benchmark_plss.cpp)
target_link_libraries(benchmark_plss PRIVATE parlaylib)
link_common_libs(benchmark_plss)

add_executable(benchmark_plis src/benchmark/benchmark_plis.cpp)
target_link_libraries(benchmark_plis PRIVATE parlaylib)
link_common_libs(benchmark_plis)

add_executable(benchmark_dovetailsort src/benchmark/benchmark_dovetailsort.cpp)
target_include_directories(benchmark_dovetailsort PRIVATE extern/DovetailSort/include/parlay)
link_common_libs(benchmark_dovetailsort)

# add_executable(benchmark_donothing src/benchmark/benchmark_donothing.cpp)
# link_common_libs(benchmark_donothing)

# ------------------------------------------------------------
# sample_sort_tiled
# ------------------------------------------------------------
add_subdirectory(extern/sample_sort_tiled)

add_executable(benchmark_simd src/benchmark/benchmark_simd.cpp)
target_link_libraries(benchmark_simd PRIVATE sample_sort_core)
# If benchmark_simd still needs tlx/checker/dsfmt/numa_array, enable next line:
link_common_libs(benchmark_simd)
