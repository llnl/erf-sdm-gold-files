#!/usr/bin/env python3
"""Replace the gold files of the Particle and SDM ctests of an ERF build with its new plotfiles.

Usage: update_golds.py <machine> <build directory> [--all] [--dry-run]

The gold files are <repository>/<machine>/<test>, each the plotfile that the test hands to
amrex_fcompare. They are listed from `ctest -N -V -R '^(Particle|SDM_)'` in the build directory
(ctest must be in PATH: source the build's ci_env.sh first), and the result of the last test run
is read from ctest_sdm.log there. A gold file is replaced when its test failed, and added when
it does not exist yet; --all replaces every gold file that differs. For each replaced gold file
the script prints the largest relative difference of the mesh fields (amrex_fcompare, started
with the launcher of the test, so run the script inside a job), the particle counts, and whether
the particle data are identical. Gold files that no test compares any more are listed, not
deleted. Exit status 1 when a test left no plotfile.
"""
import argparse
import filecmp
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TESTS = "^(Particle|SDM_)"


def gold_tests(build, dest):
    """{test: (fcompare command, gold file, plotfile)} for the tests whose gold file is in dest."""
    out = subprocess.run(["ctest", "-N", "-V", "-R", TESTS], cwd=build, capture_output=True,
                         text=True, check=True).stdout
    commands, tests = {}, {}
    for line in out.splitlines():
        m = re.match(r"^(\d+): Test command: (.*)$", line)
        if m:
            commands[m.group(1)] = m.group(2)
            continue
        m = re.match(r"^\s*Test\s+#(\d+): (\S+)", line)
        if m and m.group(1) in commands:
            tests[m.group(2)] = commands[m.group(1)]
    found = {}
    for name, command in tests.items():
        # ctest prints `sh "-c" "<script>"` without escaping the quotes inside the script
        script = command.split('"-c" "', 1)[1][:-1] if '"-c" "' in command else command
        for part in script.split("&&"):
            try:
                words = shlex.split(part)
            except ValueError:
                continue
            exe = [i for i, w in enumerate(words) if Path(w).name.endswith("fcompare")]
            if not exe or len(words) < exe[0] + 3:
                continue
            gold, plt = Path(words[-2]), Path(words[-1])
            if gold.resolve().parent == dest.resolve():
                if gold.name != name:
                    sys.exit(f"{name}: gold file {gold} is not named after the test")
                found[name] = (words[:exe[0] + 1], gold, plt)
    return found


def failed_tests(log):
    """Names of the tests that failed in a ctest log; None if the log has no summary."""
    text = log.read_text(errors="replace")
    if not re.search(r"tests passed, \d+ tests failed out of", text):
        return None
    failed, listing = set(), False
    for line in text.splitlines():
        if line.startswith("The following tests FAILED:"):
            listing = True
        elif listing:
            m = re.match(r"^\s+\d+ - (\S+) \(", line)
            if m:
                failed.add(m.group(1))
    return failed


def mesh_difference(fcompare, gold, plt):
    """(largest relative difference, its field, largest absolute difference, error text)."""
    try:
        run = subprocess.run(fcompare + ["--allow_diff_grids", str(gold), str(plt)],
                             capture_output=True, text=True)
    except OSError as err:
        return 0.0, "", 0.0, str(err)
    rel, field, absolute = 0.0, "", 0.0
    for line in run.stdout.splitlines():
        words = line.split()
        if len(words) < 3 or words[0] == "level":
            continue
        try:
            a, r = float(words[-2]), float(words[-1])
        except ValueError:
            continue
        absolute = max(absolute, a)
        if r > rel or (a > 0.0 and not field):
            rel, field = max(r, rel), words[0]
    error = ""
    if run.returncode != 0 and absolute == 0.0:
        error = " ".join((run.stdout + run.stderr).split())[-200:]
    return rel, field, absolute, error


def particles(plt):
    """{particle container: number of particles} of a plotfile."""
    counts = {}
    for header in sorted(Path(plt).glob("*/Header")):
        if header.parent.name.startswith("Level_"):
            continue
        lines = header.read_text().split("\n")
        nr = int(lines[2])
        ni = int(lines[3 + nr])
        counts[header.parent.name] = int(lines[5 + nr + ni])
    return counts


def same_files(a, b):
    """True if two directory trees hold the same files with the same bytes."""
    fa = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    return fa == fb and all(filecmp.cmp(a / f, b / f, shallow=False) for f in fa)


def replace(src, dst):
    """Copy src to dst through a temporary directory, so that a failed copy leaves dst intact.
    job_info (build paths and the run's details) is left out: fcompare does not read it."""
    tmp = dst.with_name(dst.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("job_info"))
    shutil.rmtree(dst, ignore_errors=True)
    tmp.rename(dst)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("machine", choices=["dane", "matrix", "tuolumne"])
    parser.add_argument("build", type=Path)
    parser.add_argument("--all", action="store_true", help="replace every gold file that differs")
    parser.add_argument("--dry-run", action="store_true", help="report only")
    args = parser.parse_args()

    dest = Path(__file__).resolve().parent.parent / args.machine
    dest.mkdir(exist_ok=True)
    tests = gold_tests(args.build, dest)
    failed = failed_tests(args.build / "ctest_sdm.log") if (args.build / "ctest_sdm.log").exists() else None
    if failed is None and not args.all:
        sys.exit(f"no complete ctest summary in {args.build / 'ctest_sdm.log'}; run ctest_sdm.sh first")

    status = 0
    counts = {}
    print(f"{'test':36s} {'status':8s} {'rel. diff':>9s} {'field':28s} {'particles (gold -> new)':26s} particle data")
    for name in sorted(tests):
        fcompare, gold, plt = tests[name]
        if not plt.is_dir():
            state, line = "MISSING", f"no plotfile {plt}"
            status = 1
        elif not gold.exists():
            state, line = "NEW", f"{'':9s} {'':28s} {sum(particles(plt).values())}"
        elif args.all or name in failed:
            rel, field, absolute, error = mesh_difference(fcompare, gold, plt)
            old, new = particles(gold), particles(plt)
            data = "identical" if all(same_files(gold / c, plt / c) for c in new) and old.keys() == new.keys() \
                else "differ"
            if absolute == 0.0 and not error and data == "identical":
                state = "SAME"
            else:
                state = "REPLACED"
            line = f"{rel:9.2e} {field:28s} {sum(old.values())} -> {sum(new.values())}"
            line = f"{line:66s} {data if new else '-'}" + (f"  fcompare: {error}" if error else "")
        else:
            state, line = "PASSED", ""
        counts[state] = counts.get(state, 0) + 1
        print(f"{name:36s} {state:8s} {line}".rstrip())
        if state in ("NEW", "REPLACED") and not args.dry_run:
            replace(plt, gold)

    stale = sorted(p.name for p in dest.iterdir() if p.is_dir() and p.name not in tests)
    for name in stale:
        print(f"{name:36s} STALE    no test compares this gold file any more")
    print("summary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
          (f", STALE {len(stale)}" if stale else "") + (" (dry run)" if args.dry_run else ""))
    return status


if __name__ == "__main__":
    sys.exit(main())
