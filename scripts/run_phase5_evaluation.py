#!/usr/bin/env python3
"""Phase 5 evaluation: every alpha, every ratified horizon, one command.

WHY THIS EXISTS
---------------
The Phase 5 evaluation is now 3 alphas x 5 horizons = 15 runs of
`evaluate_experiment.py`, each differing only in two flags. Typed by hand that
is fifteen chances to transpose a horizon, point at the wrong alpha's method
directory, or quietly drop the `--trim-case`. None of those would raise: they
would produce a full comparison table with wrong numbers in it, which is the
failure mode `docs/PROJECT_STATUS.md` section 5 is a list of.

So the horizons come from `evaluate_experiment.RATIFIED_HORIZON_SWEEP` (R27)
rather than from the operator, the per-alpha method directories are derived
from one naming rule rather than retyped, and the D1/D6 exclusions and the
case-93 trim are applied to every run because they are properties of the
dataset, not of the run.

This script ORCHESTRATES; it computes nothing. Every number it produces comes
out of `evaluate_experiment.py` unchanged, so the numbers remain attributable
to the evaluator and not to this wrapper.

WHAT IT NEEDS THAT THE CLOUD DOES NOT HAVE
------------------------------------------
`--event-info-root`: the extracted CARE_To_Compare directory, whose per-farm
`event_info.csv` carries `event_start`. Without it every lead-time column is
`n/a` -- which is exactly why the committed `experiments/` output still has no
lead time and why this step has to run on a machine that holds the archive.
The script refuses to start without it rather than producing a directory full
of `n/a` that looks like a completed run.

    python3 scripts/run_phase5_evaluation.py \\
        --event-info-root /path/to/CARE_To_Compare \\
        --output-root ./experiments/phase5_2026-08-XX

Exit code: 0 only if every run succeeded. Any failure is reported with the
alpha and horizon that produced it, and the script keeps going so one bad run
does not hide the state of the other fourteen.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_experiment as E  # noqa: E402

# Ratified 2026-08-15 (D1/D6 remediation). Properties of the dataset, applied
# to every run: four cases excluded outright, case 93 trimmed where it overlaps
# case 33 on the same turbine under the opposite label.
EXCLUDE_CASES = "32,56,72,87"
TRIM_CASE = "93=2023-08-24T13:00:00"

# Signed-off 2026-08-11. Not a sweep -- the three levels the protocol reports.
ALPHAS = [("a01", 0.01), ("a05", 0.05), ("a001", 0.001)]
WINDOW = 1440

# How each method's per-case output is addressed. `ours` and the baselines are
# emitted per alpha; W1-ACAS is alpha-independent and emitted once.
METHOD_SPECS = [
    ("ours",   "MD_2022_%s_ours",      "p_value",                       "pvalue"),
    ("w1acas", "MD_2022_w1acas",       "beta",                          "pvalue"),
    ("aci",    "MD_2022_%s_baselines", "aci_alarm",                     "alarm"),
    ("dtaci",  "MD_2022_%s_baselines", "dtaci_alarm",                   "alarm"),
    ("static", "MD_2022_%s_baselines", "static_split_conformal_alarm",  "alarm"),
]
REFERENCE = "static"


def horizon_tag(horizon):
    return "unbounded" if horizon is None else ("h%g" % horizon)


def build_command(args, alpha_tag, alpha, horizon, out_dir):
    cmd = [sys.executable, os.path.join(HERE, "evaluate_experiment.py"),
           "--scores-dir", args.scores_dir,
           "--wind-col", args.wind_col,
           "--timestamp-col", args.timestamp_col,
           "--g3-case-metadata", args.case_metadata,
           "--event-info-root", args.event_info_root,
           "--alpha", str(alpha),
           "--window", str(WINDOW),
           "--reference", REFERENCE,
           "--output-dir", out_dir,
           "--exclude-cases", EXCLUDE_CASES,
           "--trim-case", TRIM_CASE]
    for name, pattern, column, mode in METHOD_SPECS:
        directory = os.path.join(args.experiments_root,
                                 pattern % alpha_tag if "%s" in pattern else pattern)
        cmd += ["--method", "%s=%s:%s:%s" % (name, directory, column, mode)]
    if horizon is not None:
        cmd += ["--detection-horizon-days", str(horizon)]
    return cmd


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-info-root", required=True,
                    help="extracted CARE_To_Compare directory (contains "
                         "'Wind Farm A/B/C', each with event_info.csv). Required: "
                         "without it every lead-time column is n/a.")
    ap.add_argument("--output-root", required=True,
                    help="directory to write the 15 run directories into")
    ap.add_argument("--scores-dir", default="./scores_MD_2022_run1")
    ap.add_argument("--experiments-root", default="./experiments")
    ap.add_argument("--case-metadata", default="./manifest_out/g3_case_metadata.csv")
    ap.add_argument("--wind-col", default="wind_speed")
    ap.add_argument("--timestamp-col", default="timestamp")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the commands that would run, and stop")
    args = ap.parse_args()

    if not os.path.isdir(args.event_info_root):
        raise SystemExit("--event-info-root %r is not a directory"
                         % args.event_info_root)
    # Recursive, to match how evaluate_experiment.load_event_info actually
    # looks for these files. A one-level check here would reject layouts the
    # evaluator accepts, which is a worse failure than not checking at all:
    # the operator would go rearranging a valid directory.
    found = sorted(glob.glob(os.path.join(args.event_info_root, "**",
                                          "event_info.csv"), recursive=True))
    if not found:
        raise SystemExit(
            "no event_info.csv anywhere under %r. That file is what carries "
            "event_start; without it this run would produce lead-time columns "
            "full of n/a and look complete. Point --event-info-root at the "
            "extracted CARE_To_Compare directory, or at any directory holding "
            "the per-farm event_info.csv files."
            % args.event_info_root)
    farms = [os.path.basename(os.path.dirname(p)) for p in found]
    print("event_info.csv found in %d location(s): %s"
          % (len(found), ", ".join(farms)))

    plan = [(tag, a, h) for tag, a in ALPHAS for h in E.RATIFIED_HORIZON_SWEEP]
    print("plan: %d alphas x %d horizons = %d runs"
          % (len(ALPHAS), len(E.RATIFIED_HORIZON_SWEEP), len(plan)))
    print("horizons come from R27 (%s); primary is %g days\n"
          % (E.DETECTION_HORIZON_PROTOCOL, E.RATIFIED_DETECTION_HORIZON_DAYS))

    os.makedirs(args.output_root, exist_ok=True)
    results = []
    for i, (alpha_tag, alpha, horizon) in enumerate(plan, 1):
        tag = "%s_%s" % (alpha_tag, horizon_tag(horizon))
        out_dir = os.path.join(args.output_root, tag)
        cmd = build_command(args, alpha_tag, alpha, horizon, out_dir)
        label = "[%2d/%d] alpha=%-5g H=%-9s" % (i, len(plan), alpha,
                                                horizon_tag(horizon))
        if args.dry_run:
            print("%s\n        %s\n" % (label, " ".join(cmd)))
            continue
        print("%s -> %s" % (label, out_dir), flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        ok = proc.returncode == 0
        if not ok:
            print("        FAILED rc=%d\n        %s"
                  % (proc.returncode, proc.stderr[-600:]), flush=True)
        results.append({"alpha": alpha, "alpha_tag": alpha_tag,
                        "horizon_days": horizon, "tag": tag,
                        "output_dir": out_dir, "ok": ok,
                        "is_primary":
                            horizon == E.RATIFIED_DETECTION_HORIZON_DAYS})
    if args.dry_run:
        return 0

    index_path = os.path.join(args.output_root, "phase5_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"tool": "phase5-evaluation-v1.0",
                   "horizon_protocol": E.DETECTION_HORIZON_PROTOCOL,
                   "primary_horizon_days": E.RATIFIED_DETECTION_HORIZON_DAYS,
                   "declared_sweep_days": list(E.RATIFIED_HORIZON_SWEEP),
                   "alphas": [a for _, a in ALPHAS],
                   "excluded_cases": EXCLUDE_CASES.split(","),
                   "trim_case": TRIM_CASE,
                   "event_info_root": os.path.abspath(args.event_info_root),
                   "farms_with_event_info": farms,
                   "runs": results}, f, indent=2, sort_keys=True)

    failed = [r for r in results if not r["ok"]]
    print("\n%d/%d runs succeeded. index: %s"
          % (len(results) - len(failed), len(results), index_path))
    if failed:
        print("\nFAILED runs -- the rest of the sweep still ran, so fix these "
              "and re-run only them:")
        for r in failed:
            print("  alpha=%g H=%s" % (r["alpha"], horizon_tag(r["horizon_days"])))
        return 1

    primary = [r for r in results if r["is_primary"]]
    print("\nThe %d primary runs (H = %g d) are the headline numbers; the rest "
          "are the declared sweep and must be reported beside them, not "
          "instead of them." % (len(primary), E.RATIFIED_DETECTION_HORIZON_DAYS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
