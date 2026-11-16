#!/usr/bin/env bash
# Gold-file update run of one machine, called by jobs/<machine>.job: configure and build the CI
# build ERF-builds/<machine>-ci from the ERF source, run its Particle and SDM ctests against the
# gold files of this repository, replace the gold files of the failed tests and add those of new
# tests, run the tests again against the new gold files, and write the details for the commit
# message. The tests run in place in the build directory; logs stay there, out of this repository.
# Usage: run_golds.sh <dane|matrix|tuolumne>
set -o nounset
set -o pipefail
M=$1
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${ERF_BUILD:?source lc_env.sh first}" "${ERF_HOME:?source lc_env.sh first}"
B=$(dirname "${ERF_BUILD}")/${M}-ci
PY=${VIRTUAL_ENV:+${VIRTUAL_ENV}/bin/}python3
case ${M} in
  dane) NJ=112 ;;
  matrix) NJ=56 ;;
  tuolumne) NJ=64 ;;
  *) echo "unknown machine ${M}"; exit 1 ;;
esac
cd "${B}" || exit 1
step () { echo "$(date '+%F %T') $*" >> golds_steps.txt; }
rm -f golds_steps.txt golds_report.txt golds_provenance.txt ctest_sdm*.log
step "start, ERF $(git -C "${ERF_HOME}" log -1 --format=%h)"

# new modules in ci_env.sh need a configure from a clean cache
if [ ! -f CMakeCache.txt ] || [ ci_env.sh -nt CMakeCache.txt ]; then
    step "clean configure"
    bash cleanup.sh > golds_cleanup.log 2>&1
    rm -rf cpu
fi
source ./ci_env.sh
bash cmake.sh > golds_cmake.log 2>&1 || { step "cmake.sh failed"; exit 1; }
# ctest can list the tests only once the unit-test executables exist
TARGETS="erf_exec fcompare"
if grep -q '^ERF_ENABLE_UNIT_TESTS:BOOL=ON' CMakeCache.txt; then TARGETS="${TARGETS} erf_unit_tests erf_parallel_tests"; fi
cmake --build . -j ${NJ} --target ${TARGETS} > golds_build.log 2>&1 || { step "build failed"; exit 1; }
step "built ${TARGETS}, $(grep -ci warning golds_build.log) lines with 'warning'"
ctest -N > /dev/null 2>&1 || { step "ctest cannot list the tests: ctest -N fails"; exit 1; }

bash ctest_sdm.sh > /dev/null 2>&1
cp ctest_sdm.log ctest_sdm.before.log
step "against the current gold files: $(grep -E 'tests passed' ctest_sdm.log)"
"${PY}" "${REPO}/scripts/update_golds.py" "${M}" "${B}" > golds_report.txt 2>&1 || step "update_golds.py exit status $? (missing plotfiles or an error): see golds_report.txt"
step "$(tail -1 golds_report.txt)"
bash ctest_sdm.sh > /dev/null 2>&1
cp ctest_sdm.log ctest_sdm.after.log
step "against the new gold files: $(grep -E 'tests passed' ctest_sdm.log)"
bash "${REPO}/scripts/provenance.sh" "${M}" "${B}" > golds_provenance.txt 2>&1
step done
