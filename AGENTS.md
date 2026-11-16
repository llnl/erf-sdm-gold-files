# ERF SDM gold files

Gold files of the particle and super-droplet (SDM) regression tests of ERF
(https://github.com/erf-model/ERF) on the LLNL machines Dane, Matrix and Tuolumne. We maintain
the particle and SDM code of ERF, so this repository covers only those tests. It replaces
`erf-llnl-gold-files`, which is no longer maintained.

Repository: https://github.com/LLNL/erf-sdm-gold-files, branch `main`. The working copy is a
clone on LC's run file system, the one the CI builds point at (`ERF_SDM_GOLDFILES_DIR`).

## Contents

- `dane/`, `matrix/`, `tuolumne/`: one directory per test, `<machine>/<test>`. Each holds the
  plotfile that the test compares with `amrex_fcompare`, as the test writes it, without its
  `job_info` (build paths and run details, which `amrex_fcompare` does not read).
- The tests: every test of `Tests/CTestList.cmake` whose name starts with `Particle` or `SDM_` and
  that compares with a gold file (`add_test_r`, `add_test_sdm`), with the gated SDM tests
  (`ERF_TEST_ENABLE_EXTRA_SDM_TESTS=ON`). The other Particle and SDM tests (restart and box
  parity, check scripts) need no gold file but run in the same ctest pass.
- Machine differences come from `Tests/CTestList.cmake`: the collision tests (`SDM_Box3D_IceAgg`,
  `SDM_Box3D_Coal_*`, `SDM_RimingShaft`) run only in CPU builds, so only on Dane, and
  `SDM_SublimationShaft` does not run in HIP builds, so not on Tuolumne.
- `scripts/run_golds.sh`: the update run of one machine (build, test, replace, test again).
- `scripts/update_golds.py`: replaces the gold files of failed and new tests, reports the
  differences.
- `scripts/provenance.sh`: build and machine details for the commit message.
- `jobs/<machine>.job`: the batch job of each machine.

## Builds that use them

The CI builds `$(dirname $ERF_BUILD)/<machine>-ci`, next to the machine's own build
`$ERF_BUILD`, configured from the ERF source `$ERF_HOME` (both set by `lc_env.sh`):

- `cmake.sh` sets `ERF_TEST_GOLD_FILES_DIRECTORY=$ERF_SDM_GOLDFILES_DIR/<machine>`, with the
  maintainers' working copy as the default root.
- `ci_env.sh` holds the modules, and `cmake.sh`, `build.sh`, `build.dnode.sh` and `ctest_sdm.sh`
  source it.
- `ctest_sdm.sh` runs the Particle and SDM tests inside a job (`--unit` adds the SDM unit tests).
- With unit tests enabled, ctest cannot list any test until `erf_unit_tests` and
  `erf_parallel_tests` are built; `run_golds.sh` builds them.

| | Dane | Matrix | Tuolumne |
|---|---|---|---|
| Hardware | CPU (Sapphire Rapids) | NVIDIA H100, `sm_90` | AMD MI300A, `gfx942` |
| Modules | `cmake/3.30.5 ninja/1.11.1 gcc/12.1.1` | `cmake/3.30.5 ninja/1.11.1 gcc/13.3.1 cuda/13.1.1` | `lc_env.sh`: `rocm/7.2.1 rocmcc/7.2.1-cce-21.0.2-magic cray-mpich/9.1.0`, ... |
| Build type | Debug | RelWithDebInfo | RelWithDebInfo |
| `amrex_fcompare` | from the build | separate CPU build (`cpu/`) | separate CPU build (`cpu/`) |
| Launcher | `srun` | `srun` | `flux run`, one GPU per rank |
| Unit tests | built | off: googletest does not link with gcc/13.3.1 | built |

- All three: 4 MPI ranks per test (`ERF_TEST_NRANKS=4`), `ERF_TEST_ENABLE_EXTRA_SDM_TESTS=ON`,
  tolerances 5e-9 relative and 2e-10 absolute for `add_test_r` tests; `add_test_sdm` tests carry
  their own (1e-14 to 5e-12; `ParticleAdvect_AMR*_pcount` 2e-8 to 1e-7).
- Dane and Matrix keep the modules of ERF's LC GitLab CI (`.gitlab/LC/jobs/<machine>.yml`), a
  stated exception to `lc_env.sh`. Tuolumne uses `lc_env.sh`, the machine's default environment.

## Updating the gold files

Update after an ERF change to the particle or SDM code that changes answers, after an AMReX
update, after a change of modules, compilers or operating system, and when a test is added.
Follow the lc-hpc skill for every step on LC (connections, `lc_submit.sh`, bank `asccasc`).

1. **ERF source.** `$ERF_HOME` is a clone of `git@github.com:erf-model/ERF.git`, shared with other
   work: tell its other users before moving it.
   - `git -C $ERF_HOME checkout development && git -C $ERF_HOME pull --ff-only` (remote
     `erfrepo`). A fresh clone: `git clone --recursive git@github.com:erf-model/ERF.git`.
   - `git submodule status`: a line that starts with `+` or `-` means a submodule does not
     match; then `git submodule update --init --recursive`.
   - `git status` must show no modified files.
2. **Modules.** If a machine's environment changed, edit `ci_env.sh` in its build directory. The
   next run then configures from a clean cache, since CMake keeps the old compilers otherwise.
3. **Run**, one job per machine, submitted with the lc-hpc skill's `scripts/lc_submit.sh`:
   `lc_submit.sh <machine> <working copy>/jobs/<machine>.job`. It submits from `jobs/`, where
   the job writes `golds_<machine>_<id>.out` (ignored by git; delete it after the review).
   The job runs `scripts/run_golds.sh <machine>` in the build directory. The tests run in place
   in `Tests/test_files/<test>` there; no other directory is created.
   - Configure (`cmake.sh`) and build `erf_exec` and `fcompare`.
   - Run the tests against the current gold files: `ctest_sdm.before.log`.
   - Replace the gold files of the failed tests and add those of new tests: `golds_report.txt`.
   - Run the tests again against the new gold files: `ctest_sdm.after.log`.
   - Write the build and machine details: `golds_provenance.txt`. Progress is in
     `golds_steps.txt`.
4. **Review** before any commit.
   - `git status` and `git diff --stat` here list the gold files that changed. Plotfiles are
     binary; `golds_report.txt` gives, per replaced test, the largest relative difference of
     the mesh fields and its field, the particle counts, and whether the particle data are
     identical.
   - `ctest_sdm.after.log` must pass every test, apart from the known run-to-run differences
     below.
   - Find the cause of each change. ERF: `git log <old>..<new> -- Source/Particles
     Source/Microphysics/SuperDropletsMoist Tests/test_files/<test>`, then the time stepping, AMR
     and dynamics code; the old commit is in the last commit message of the machine. AMReX: the
     submodule lines. Environment: compare `golds_provenance.txt` with the last commit message.
   - Harmless: round-off differences (relative 1e-16 to about 1e-10) from a new order of
     operations, after a code reorganisation, a new compiler or new flags, with the same
     particle counts. For a test that draws random numbers, a new compiler or library can give
     a new realization of the sample. Then read the plotfiles (for example with yt) and check
     that the physics is the same: domain totals, particle counts, size spectra.
   - Not harmless: differences beyond round-off from ERF commits that were not meant to change
     answers, particle counts or multiplicity sums that change without a reason, new or
     missing fields, NaN or Inf, a test that aborts.
5. **Harmless: commit**, one commit per machine (`git add <machine>`), then
   `git push origin main`. The message carries the reproducibility details, an exception to the
   usual one- or two-line messages that the user asked for. The repository is public: no user
   names, paths, node names or job numbers in files or messages.

   ```
   <machine>: Particle and SDM gold files, ERF <short hash>

   ERF: <hash> (<commit date>) <subject>, development
   Submodules: AMReX <hash>, ...
   Run: <date time zone>, <machine>
   Machine: <OS>, kernel <version>, GPU <model>, driver <version>
   Environment: modules <list>; C++ <compiler and version>; CUDA or HIP <version>
   Build: <type>, ERF_TEST_NRANKS=4, ERF_TEST_ENABLE_EXTRA_SDM_TESTS=ON, launcher <...>
   Tests: <n> gold files, <k> new, <m> replaced; against the new gold files <x> of <y> pass
   <test>: <cause of the change, one line per replaced test>
   ```

   `golds_provenance.txt` holds most of these lines.
6. **Not harmless: no commit.** Restore the gold files (`git checkout -- <machine>` and
   `git clean -fd <machine>`) and summarize for the user: the tests, the size of the
   differences, the suspected ERF commits and the evidence.
7. **Clean up.** The test outputs and logs stay in the build directory; the next run overwrites
   them. Run `git gc` here after a commit, to keep the file count of the run file system low.

## Known run-to-run differences

Particle-to-mesh deposition on GPUs uses atomic additions, so the order of the sums changes
from run to run, and the CPU build on Dane is the only bitwise reproducible one. Most GPU
differences are round-off well inside the tolerances. A test whose particle data diverge
between runs fails now and then against any gold file; such a failure alone is not a
regression.

- Matrix, November 2026: two runs of the same executable differed in the particle data of
  `SDM_MoistBubble3D_AMR1`, `SDM_MoistBubble3D_AMR2` and `SDM_StretchedCoalescence` (a check
  script, no gold file). The first gold run passed all 55 tests against its own new gold files.
- Tuolumne, November 2026 (ROCm 6.4): the same three tests diverged between two builds that
  gave bitwise identical results on Dane.

## Rules

- Never edit a gold file by hand, and never commit logs, reports or job output.
- Commit only after the review of step 4.
- The gold files take about 350 MB and 430 files per machine; the largest file is about 9 MB
  (GitHub rejects files above 100 MB). Each replaced gold file adds its full size to the
  history, which GitHub would like to stay under a few GB.
