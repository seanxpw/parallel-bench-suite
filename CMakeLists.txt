# cmake -D CMAKE_C_COMPILER=clang -D CMAKE_CXX_COMPILER=clang++ -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ..
# clang is so problematic try to use g++

cmake_minimum_required(VERSION 3.10)
# CC=/usr/bin/gcc CXX=/usr/bin/g++ cmake .. 
# cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ..
project(ips4o-benchmark-suite)

set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake/)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
include(default_build_type)
add_definitions(-D__STDC_LIMIT_MACROS -D__STDC_CONSTANT_MACROS) # sometimes it says cannot identify uint64_t in txl

#TBB path
set(CMAKE_PREFIX_PATH "$ENV{HOME}/oneTBB/install" ${CMAKE_PREFIX_PATH})

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON) # C++20

set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE}  -DNDEBUG -g -march=native -mcx16 -include cstdint") #-include cstdint is for tlx
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG}  -march=native -g -mcx16 -include cstdint")
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} -DNDEBUG -g -march=native")
set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS_DEBUG} -g -march=native")
# set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -static-libasan -fsanitize=address")

# checker
option(BENCHMARK_DISABLE_CHECKS "Disable benchmark checkers for performance analysis" ON)

if(BENCHMARK_DISABLE_CHECKS)
    message(STATUS "Benchmark checkers are DISABLED for performance analysis (globally).")
    add_compile_definitions(DISABLE_PERF_INTERFERENCE_CHECKS) 
else()
    message(STATUS "Benchmark checkers are ENABLED (globally).")
endif()


set(IPPRADIXSORT "Disable" CACHE STRING "Build type. Default is Disable")
set_property(CACHE IPPRADIXSORT PROPERTY STRINGS Disable Enable)
if ("${IPPRADIXSORT}" STREQUAL "Enable")
  set(IPP_STATIC "ON")
  find_library(IPP_CORE libippcore.a PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_VM libippvm.a PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_S libipps.a PATHS ~/tmp/intel/ipp/lib/intel64)
  find_library(IPP_I libippi.a PATHS ~/tmp/intel/ipp/lib/intel64)
endif()
message(STATUS "ippradixsort: ${IPPRADIXSORT}")

set(IPS4O_TIMER "Disable" CACHE STRING "Build type. Default is Disable")
set_property(CACHE IPS4O_TIMER PROPERTY STRINGS Disable Enable)
if ("${IPS4O_TIMER}" STREQUAL "Enable")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DIPS4O_TIMER")
endif()
message(STATUS "IPS4o timer: ${IPS4O_TIMER}")

add_subdirectory(extern/InPlaceMSDradixsort)
add_subdirectory(extern/NumaArray)
# add_subdirectory(extern/tbb)
add_subdirectory(extern/CPPSFMT)
add_subdirectory(extern/SortChecker)
# add_subdirectory(extern/RADULS)

# Disable parallel as we do not use the default libraries
option(IPS4O_DISABLE_PARALLEL "Enable parallel code of IPS4o" ON)
option(IPS2RA_DISABLE_PARALLEL "Enable parallel code of IPS2RA" ON)
option(PS4O_DISABLE_PARALLEL "Enable parallel code of PS4o" ON)
add_subdirectory(extern/ips4o_journal)
add_subdirectory(extern/ips2ra_journal)
add_subdirectory(extern/ps4o)

# hwloc
include_directories($ENV{HOME}/local/include)
link_directories($ENV{HOME}/local/lib)
find_library(NUMA_LIBRARY numa PATHS $ENV{HOME}/opt/numactl/lib)
# Global libraries
link_libraries(tlx checker dsfmt hwloc numa numa_array)
link_directories($ENV{HOME}/opt/numactl/lib)
## pthreads for parallel data generation and checking
find_package(Threads REQUIRED)
link_libraries(Threads::Threads)

# Data generator
# add_executable(gen src/datagenerator.cpp)

# Benchmark executables
# add_executable (benchmark_raduls src/benchmark/benchmark_raduls.cpp) #seems not support clang
# target_link_libraries(benchmark_raduls PRIVATE raduls)
# target_include_directories(benchmark_raduls PRIVATE extern/RADULS)

# add_executable (benchmark_imsdradix src/benchmark/benchmark_imsdradix.cpp)
# target_link_libraries(benchmark_imsdradix PRIVATE inpmsdradix)


# add_executable (benchmark_ps4oparallel src/benchmark/benchmark_ps4oparallel.cpp)
# target_link_libraries(benchmark_ps4oparallel PRIVATE ps4o)
# add_executable (benchmark_ps4o src/benchmark/benchmark_ps4o.cpp)
# target_link_libraries(benchmark_ps4o PRIVATE ps4o)

# add_executable (benchmark_ips4ooldparallel src/benchmark/benchmark_ips4ooldparallel.cpp)
# add_executable (benchmark_ips4oml src/benchmark/benchmark_ips4oml.cpp)
add_executable (benchmark_ips4oparallel src/benchmark/benchmark_ips4oparallel.cpp)
target_link_libraries(benchmark_ips4oparallel PRIVATE ips4o)
add_executable (benchmark_ips4o src/benchmark/benchmark_ips4o.cpp)
target_link_libraries(benchmark_ips4o PRIVATE ips4o)

add_executable (benchmark_ips2ra src/benchmark/benchmark_ips2ra.cpp)
target_link_libraries(benchmark_ips2ra PRIVATE ips2ra)
add_executable (benchmark_ips2raparallel src/benchmark/benchmark_ips2raparallel.cpp)
target_link_libraries(benchmark_ips2raparallel PRIVATE ips2ra)


add_executable (benchmark_mcstlmwm src/benchmark/benchmark_mcstlmwm.cpp)
add_executable (benchmark_mcstlbq src/benchmark/benchmark_mcstlbq.cpp)
# add_executable (benchmark_mcstlubq src/benchmark/benchmark_mcstlubq.cpp)
# add_executable (benchmark_tbbparallelsort src/benchmark/benchmark_tbbparallelsort.cpp) it uses old TBB API

# add_executable (benchmark_regionsort src/benchmark/benchmark_regionsort.cpp)
# target_link_libraries(benchmark_regionsort PRIVATE cilkrts)
# target_compile_options(benchmark_regionsort PRIVATE -fcilkplus -DCILKP -DBITS_HACK -DLONG_ARRAY)

# I don't have cilkrts installed
# add_executable (benchmark_pbbsradixsort src/benchmark/benchmark_pbbsradixsort.cpp)
# add_executable (benchmark_pbbssamplesort src/benchmark/benchmark_pbbssamplesort.cpp)
# target_link_libraries(benchmark_pbbsradixsort PRIVATE cilkrts)
# target_compile_options(benchmark_pbbsradixsort PRIVATE -fcilkplus)
# target_link_libraries(benchmark_pbbssamplesort PRIVATE cilkrts)
# target_compile_options(benchmark_pbbssamplesort PRIVATE -fcilkplus)

# target_link_libraries(benchmark_pbbsradixsort PRIVATE cilkrts)
# target_compile_options(benchmark_pbbsradixsort PRIVATE -fcilkplus)
# target_link_libraries(benchmark_pbbssamplesort PRIVATE cilkrts)
# target_compile_options(benchmark_pbbssamplesort PRIVATE -fcilkplus)

# add_executable (benchmark_aspasparallel src/benchmark/benchmark_aspasparallel.cpp)
# add_executable (benchmark_skasort src/benchmark/benchmark_skasort.cpp)
# add_executable (benchmark_yaroslavskiy src/benchmark/benchmark_yaroslavskiy.cpp)
# add_executable (benchmark_blockquicksort src/benchmark/benchmark_blockquicksort.cpp)
# add_executable (benchmark_aspas src/benchmark/benchmark_aspas.cpp)
# add_executable (benchmark_wikisort src/benchmark/benchmark_wikisort.cpp)
# add_executable (benchmark_timsort src/benchmark/benchmark_timsort.cpp)
# add_executable (benchmark_pdqsort src/benchmark/benchmark_pdqsort.cpp)
add_executable (benchmark_stdsort src/benchmark/benchmark_stdsort.cpp)
# add_executable (benchmark_ssss src/benchmark/benchmark_ssss.cpp)
# add_executable (benchmark_learnedsort src/benchmark/benchmark_learnedsort.cpp)

if ("${IPPRADIXSORT}" STREQUAL "Enable")
  add_executable (benchmark_ippradixsort src/benchmark/benchmark_ippradixsort.cpp)
  target_include_directories(benchmark_ippradixsort PRIVATE ~/tmp/intel/ipp/include)
  target_link_libraries(benchmark_ippradixsort PRIVATE ${IPP_S} ${IPP_I} ${IPP_VM} ${IPP_CORE})
endif()

# add_executable (benchmark_quickxsort src/benchmark/benchmark_quickxsort.cpp)

# target_include_directories(benchmark_quickxsort PRIVATE extern/QuickXsort)
# target_include_directories(benchmark_aspasparallel PRIVATE extern/aspas_sort/include)
# target_include_directories(benchmark_aspas PRIVATE extern/aspas_sort/include)

# OMP
find_package(OpenMP REQUIRED)
# target_link_libraries(gen PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_raduls PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_imsdradix PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_ps4oparallel PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_ips4ooldparallel PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_ips4oparallel PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_ips2raparallel PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_mcstlmwm PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_mcstlbq PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_mcstlubq PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_skasort PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_yaroslavskiy PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_blockquicksort PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_aspasparallel PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_aspas PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_wikisort PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_timsort PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_pdqsort PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_stdsort PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_ps4o PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_ssss PUBLIC OpenMP::OpenMP_CXX)
# target_link_libraries(benchmark_learnedsort PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_ips4o PUBLIC OpenMP::OpenMP_CXX)
target_link_libraries(benchmark_ips2ra PUBLIC OpenMP::OpenMP_CXX)
if ("${IPPRADIXSORT}" STREQUAL "Enable")
  target_link_libraries(benchmark_ippradixsort PUBLIC OpenMP::OpenMP_CXX)
endif()

find_package(TBB REQUIRED)
# target_link_libraries(ips4o INTERFACE TBB::tbb)
# TBB
# target_link_libraries(benchmark_ps4oparallel PRIVATE  atomic TBB::tbb)
# target_link_libraries(benchmark_ips4ooldparallel PRIVATE  atomic TBB::tbb)
target_link_libraries(benchmark_ips4oparallel PRIVATE  atomic TBB::tbb)
target_link_libraries(benchmark_ips2raparallel PRIVATE  atomic TBB::tbb)
# target_link_libraries(benchmark_tbbparallelsort PRIVATE  TBB::tbb)
# Sequential algorithms
# target_link_libraries(benchmark_ps4o PRIVATE  atomic TBB::tbb)
target_link_libraries(benchmark_ips4o PRIVATE  atomic TBB::tbb)
target_link_libraries(benchmark_ips2ra PRIVATE  atomic TBB::tbb)


#MySort
# add_executable (benchmark_mysort src/benchmark/benchmark_mysort.cpp)
# target_include_directories(benchmark_mysort PRIVATE extern/project1-sorting-seanxpw)

# ParlayLib
add_library(parlaylib INTERFACE)
target_include_directories(parlaylib INTERFACE extern/parlaylib/include)


# ===========================
# PLSS
# ===========================
# Normal version
add_executable(benchmark_plss src/benchmark/benchmark_plss.cpp)
target_link_libraries(benchmark_plss PRIVATE parlaylib)

# Cilk version (same source file, different name and compile options)
# add_executable(benchmark_plss_cilk src/benchmark/benchmark_plss.cpp)
# target_link_libraries(benchmark_plss_cilk PRIVATE parlaylib)
# target_compile_options(benchmark_plss_cilk PRIVATE -DPARLAY_OPENCILK -DCILK -fopencilk)

# ===========================
# PLIS
# ===========================
add_executable(benchmark_plis src/benchmark/benchmark_plis.cpp)
target_link_libraries(benchmark_plis PRIVATE parlaylib)

# add_executable(benchmark_plis_cilk src/benchmark/benchmark_plis.cpp)
# target_link_libraries(benchmark_plis_cilk PRIVATE parlaylib)
# target_compile_options(benchmark_plis_cilk PRIVATE -DPARLAY_OPENCILK -DCILK -fopencilk)

# ===========================
# DovetailSort
# ===========================
add_executable(benchmark_dovetailsort src/benchmark/benchmark_dovetailsort.cpp)
target_include_directories(benchmark_dovetailsort PRIVATE extern/DovetailSort/include/parlay)

# add_executable(benchmark_dovetailsort_cilk src/benchmark/benchmark_dovetailsort.cpp)
# target_include_directories(benchmark_dovetailsort_cilk PRIVATE extern/DovetailSort/include/parlay)
# target_link_libraries(benchmark_dovetailsort_cilk PRIVATE parlaylib)
# target_compile_options(benchmark_dovetailsort_cilk PRIVATE -DPARLAY_OPENCILK -DCILK -fopencilk)


#DoNothing
add_executable(benchmark_donothing src/benchmark/benchmark_donothing.cpp)