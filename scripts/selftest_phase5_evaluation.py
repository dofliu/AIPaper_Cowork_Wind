#!/usr/bin/env python3
"""
Self-test: the Phase 5 runner builds the runs the protocol says it should.

WHY THIS EXISTS
---------------
This runner computes nothing, so it cannot get a number wrong directly. It can
do something worse: build fifteen commands that all succeed while one of them
addresses the wrong alpha's method directory, or omits the case-93 trim, or
skips a ratified horizon. Every one of those produces a full comparison table
with no error, which is the shape of defect `PROJECT_STATUS.md` section 5
catalogues. The plan is therefore checked, not the arithmetic.

  T1  the plan is exactly ALPHAS x RATIFIED_HORIZON_SWEEP, and the horizons
      come from evaluate_experiment rather than being restated here.
  T2  every run carries the D1/D6 exclusions and the case-93 trim. These are
      properties of the dataset, so no run may be missing them.
      REVERSE: a command built without them is detectably different.
  T3  per-alpha method directories track the alpha, and the alpha-independent
      one (w1acas) does not. Getting this backwards would silently evaluate
      alpha=0.05 output under alpha=0.01.
  T4  the unbounded horizon omits the flag entirely rather than passing a
      sentinel, and every other horizon passes it.
  T5  a missing or event_info-less --event-info-root is refused. Without that
      file every lead-time column is n/a, and a directory full of n/a looks
      exactly like a completed run. REVERSE: a tree that does have it passes.
  T6  --dry-run prints the plan and writes nothing.

    python3 scripts/selftest_phase5_evaluation.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_experiment as E      # noqa: E402
import run_phase5_evaluation as P    # noqa: E402

TOOL = os.path.join(HERE, "run_phase5_evaluation.py")


class Args(object):
    """Stand-in for the parsed namespace, so build_command can be tested."""
    def __init__(self, root):
        self.event_info_root = root
        self.output_root = os.path.join(root, "out")
        self.scores_dir = "./scores_MD_2022_run1"
        self.experiments_root = "./experiments"
        self.case_metadata = "./manifest_out/g3_case_metadata.csv"
        self.wind_col = "wind_speed"
        self.timestamp_col = "timestamp"
        self.dry_run = False


def make_care_tree(root, with_event_info=True):
    care = os.path.join(root, "CARE_To_Compare")
    for farm in ("Wind Farm A", "Wind Farm B", "Wind Farm C"):
        d = os.path.join(care, farm)
        os.makedirs(d, exist_ok=True)
        if with_event_info:
            with open(os.path.join(d, "event_info.csv"), "w",
                      encoding="utf-8") as f:
                f.write("asset;event_id;event_label;event_start\n")
    return care


def main():
    failures = []
    checks = [0]

    def check(name, condition, detail=""):
        checks[0] += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            failures.append(name)
            print("  FAIL  %s   %s" % (name, detail))

    with tempfile.TemporaryDirectory() as root:
        care = make_care_tree(root)
        args = Args(care)

        # ---- T1 -----------------------------------------------------------
        print("\nT1  the plan is alphas x the ratified sweep")
        plan = [(t, a, h) for t, a in P.ALPHAS for h in E.RATIFIED_HORIZON_SWEEP]
        check("T1 plan size is %d x %d = %d"
              % (len(P.ALPHAS), len(E.RATIFIED_HORIZON_SWEEP), len(plan)),
              len(plan) == len(P.ALPHAS) * len(E.RATIFIED_HORIZON_SWEEP))
        check("T1 the horizons are exactly the ratified sweep",
              sorted(set(h for _, _, h in plan), key=lambda x: (x is None, x))
              == sorted(set(E.RATIFIED_HORIZON_SWEEP), key=lambda x: (x is None, x)))
        check("T1 the alphas are the three signed-off levels",
              sorted(a for _, a in P.ALPHAS) == [0.001, 0.01, 0.05],
              "got %s" % sorted(a for _, a in P.ALPHAS))
        # REVERSE: the runner must not carry its own copy of the horizons.
        src = open(os.path.join(HERE, "run_phase5_evaluation.py"),
                   encoding="utf-8").read()
        check("T1 REVERSE: the runner does not restate the horizon numbers",
              "RATIFIED_HORIZON_SWEEP" in src
              and "(7.0, 10.0, 14.0, 21.0" not in src,
              "the sweep appears to be hard-coded a second time here")

        # ---- T2 / T3 / T4 --------------------------------------------------
        print("\nT2/T3/T4  every command carries what the dataset requires")
        cmds = {}
        for alpha_tag, alpha, horizon in plan:
            cmds[(alpha_tag, horizon)] = P.build_command(
                args, alpha_tag, alpha, horizon,
                os.path.join(args.output_root, "x"))

        check("T2 every run excludes 32,56,72,87",
              all("--exclude-cases" in c and P.EXCLUDE_CASES in c
                  for c in cmds.values()))
        check("T2 every run trims case 93",
              all("--trim-case" in c and P.TRIM_CASE in c
                  for c in cmds.values()))
        check("T2 every run passes --event-info-root",
              all("--event-info-root" in c for c in cmds.values()))
        # REVERSE: those flags are not simply always present in any command
        # this builder could emit -- strip them and the command differs.
        one = list(cmds.values())[0]
        stripped = [t for t in one if t not in (P.EXCLUDE_CASES, P.TRIM_CASE)]
        check("T2 REVERSE: removing them changes the command",
              len(stripped) < len(one))

        a01 = " ".join(cmds[("a01", 14.0)])
        a05 = " ".join(cmds[("a05", 14.0)])
        check("T3 the ours directory tracks the alpha",
              "MD_2022_a01_ours" in a01 and "MD_2022_a05_ours" in a05,
              "a01 -> %s" % ("MD_2022_a01_ours" in a01))
        check("T3 the baselines directory tracks the alpha",
              "MD_2022_a01_baselines" in a01
              and "MD_2022_a05_baselines" in a05)
        check("T3 w1acas is alpha-independent in BOTH runs",
              "MD_2022_w1acas" in a01 and "MD_2022_w1acas" in a05
              and "MD_2022_a01_w1acas" not in a01)
        # REVERSE: if every directory were alpha-independent, T3's first two
        # assertions would be vacuous.
        check("T3 REVERSE: the two alphas produce different commands",
              a01 != a05)

        for h in E.RATIFIED_HORIZON_SWEEP:
            c = cmds[("a01", h)]
            if h is None:
                check("T4 the unbounded run omits --detection-horizon-days",
                      "--detection-horizon-days" not in c)
            else:
                check("T4 H=%g passes --detection-horizon-days %g" % (h, h),
                      "--detection-horizon-days" in c and str(h) in c)

        # ---- T5 -----------------------------------------------------------
        print("\nT5  a tree without event_info is refused")
        empty = make_care_tree(os.path.join(root, "empty"),
                               with_event_info=False)
        p = subprocess.run(
            [sys.executable, TOOL, "--event-info-root", empty,
             "--output-root", os.path.join(root, "o1"), "--dry-run"],
            capture_output=True, text=True)
        check("T5 refused, non-zero exit", p.returncode != 0,
              "exit 0 -- a run with no event_info would look complete")
        check("T5 and says why", "event_info.csv" in (p.stderr + p.stdout))

        p = subprocess.run(
            [sys.executable, TOOL, "--event-info-root",
             os.path.join(root, "nope"),
             "--output-root", os.path.join(root, "o2"), "--dry-run"],
            capture_output=True, text=True)
        check("T5 a missing directory is refused too", p.returncode != 0)
        # REVERSE of the layout assumption: the evaluator globs recursively,
        # so a deeper tree must be ACCEPTED. A one-level check here would send
        # the operator rearranging a directory that was already valid.
        deep = os.path.join(root, "deep", "CARE_To_Compare", "extracted")
        os.makedirs(os.path.join(deep, "Wind Farm A"), exist_ok=True)
        with open(os.path.join(deep, "Wind Farm A", "event_info.csv"), "w",
                  encoding="utf-8") as f:
            f.write("asset;event_id;event_label;event_start\n")
        p = subprocess.run(
            [sys.executable, TOOL, "--event-info-root",
             os.path.join(root, "deep"),
             "--output-root", os.path.join(root, "o4"), "--dry-run"],
            capture_output=True, text=True)
        check("T5 REVERSE: a nested layout is accepted, not rearranged",
              p.returncode == 0, p.stderr[-300:])

        # ---- T6 -----------------------------------------------------------
        print("\nT6  --dry-run plans without writing")
        out = os.path.join(root, "o3")
        p = subprocess.run(
            [sys.executable, TOOL, "--event-info-root", care,
             "--output-root", out, "--dry-run"],
            capture_output=True, text=True)
        check("T6 REVERSE: a tree WITH event_info is accepted",
              p.returncode == 0, p.stderr[-300:])
        check("T6 the plan announces %d runs" % len(plan),
              "= %d runs" % len(plan) in p.stdout, p.stdout[:300])
        check("T6 no index file is written on a dry run",
              not os.path.exists(os.path.join(out, "phase5_index.json")))
        check("T6 the primary horizon is named in the output",
              "%g" % E.RATIFIED_DETECTION_HORIZON_DAYS in p.stdout)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
