#!/usr/bin/env bash
# Build and machine details of a CI build, for the commit message of a gold-file update. The
# repository is public: no user names, paths, node names or job numbers.
# Usage: provenance.sh <machine> <build directory>; run it inside the job, after ci_env.sh.
set -o nounset
M=$1
B=$2
cache () { grep -E "^$1:" "${B}/CMakeCache.txt" | head -1 | cut -d= -f2-; }
SRC=$(cache CMAKE_HOME_DIRECTORY)
echo "ERF: $(git -C "${SRC}" log -1 --date=iso --format='%H (%cd) %s'), branch $(git -C "${SRC}" rev-parse --abbrev-ref HEAD)"
n=$(git -C "${SRC}" status --porcelain --untracked-files=no | wc -l)
echo "ERF tree: $([ "${n}" = 0 ] && echo clean || echo "${n} modified files")"
git -C "${SRC}" submodule status | awk '{sub("Submodules/", "", $2); printf "Submodule %s: %s %s\n", $2, $1, $3}'
echo "Run: $(date '+%Y-%m-%d %H:%M %Z'), ${M}"
echo "OS: $(. /etc/os-release && echo "${PRETTY_NAME}"), kernel $(uname -r)"
echo "Modules: $(module -t list 2>&1 | tr '\n' ' ')"
cxx=$(cache CMAKE_CXX_COMPILER)
echo "C++: $(basename "${cxx}"): $(${cxx} --version 2>&1 | head -1)"
case ${M} in
  matrix)
    arch=$(cache AMReX_CUDA_ARCH); [ -n "${arch}" ] || arch=$(cache CMAKE_CUDA_ARCHITECTURES)
    echo "CUDA: $(nvcc --version 2>&1 | tail -1), arch ${arch}"
    echo "GPU: $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>&1 | sort | uniq -c | tr -s ' ' | tr '\n' ';')" ;;
  tuolumne)
    hip=$(cache CMAKE_HIP_COMPILER)
    if [ -n "${hip}" ]; then hv="$(basename "${hip}"): $(${hip} --version 2>&1 | head -1)"; else hv="compiled by the C++ compiler, $(hipconfig --version 2>/dev/null)"; fi
    echo "HIP: ${hv}, arch $(cache AMReX_AMD_ARCH)"
    echo "HIP runtime of erf_exec: $(ldd "${B}/Exec/erf_exec" | grep -oE 'rocm-[0-9.]+/lib/libamdhip64[^ ]*' | head -1)"
    echo "MPI: $(${cxx} -show 2>&1 | grep -oE 'mpich/[0-9.]+' | head -1), GPU transport $(${cxx} -show 2>&1 | grep -oE 'lmpi_gtl[a-z_]*' | head -1)"
    echo "GPU driver: $(cat /sys/module/amdgpu/version 2>/dev/null || echo unknown)" ;;
esac
echo "Build: $(cache CMAKE_BUILD_TYPE), particles $(cache ERF_ENABLE_PARTICLES), precision $(cache ERF_PRECISION)/$(cache ERF_PARTICLES_PRECISION)"
echo "Tests: ERF_TEST_NRANKS=$(cache ERF_TEST_NRANKS), ERF_TEST_ENABLE_EXTRA_SDM_TESTS=$(cache ERF_TEST_ENABLE_EXTRA_SDM_TESTS), ERF_TEST_FCOMPARE_RTOL/ATOL=$(cache ERF_TEST_FCOMPARE_RTOL)/$(cache ERF_TEST_FCOMPARE_ATOL)"
echo "Launcher: $(basename "$(cache MPIEXEC_EXECUTABLE)") $(cache MPIEXEC_PREFLAGS)"
case $(cache FCOMPARE_EXE) in */cpu/*) echo "fcompare: separate CPU build" ;; *) echo "fcompare: this build" ;; esac
echo "Python: $(${VIRTUAL_ENV:+${VIRTUAL_ENV}/bin/}python3 --version 2>&1)"
