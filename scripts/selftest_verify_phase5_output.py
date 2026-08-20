#!/usr/bin/env python3
"""
Self-test: the Phase 5 acceptance check actually rejects bad batches.

WHY THIS EXISTS
---------------
An acceptance check that only ever passes is worse than none: it converts
"nobody looked" into "it was verified". So each rule is exercised against a
batch that violates exactly that rule, and confirmed to fail -- and against a
clean batch, and confirmed to pass. A rule that cannot fail is removed or
fixed, not shipped.

The fixtures are synthesised here rather than taken from a real run, so this
test needs no CARE data and can run anywhere, including on the machine that is
about to execute Phase 5 for the first time.

  T1  a clean synthetic batch passes.
  T2  null lead time is rejected -- the defect the whole batch exists to
      avoid, and the one that still exits 0 upstream.
  T3  an empty trimmed_cases is rejected. The case-93 trim once lived in a
      config comment applying to nothing, without error.
  T4  a wrong denominator (n_normal_cases_for_far) is rejected.
  T5  pooled_reconstruction.exhaustive = false is rejected.
  T6  a baseline reporting freeze state is rejected, and so is the proposed
      method NOT reporting it. Both directions, because a check that only
      fires one way is not evidence (working rule 3).
  T7  a moved false-alarm figure is rejected: this batch adds lead time and
      must change nothing else.
  T8  a missing run directory is rejected, and the count is reported.
  T9  a comparison.md without the frozen columns is rejected.

    python3 scripts/selftest_verify_phase5_output.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_experiment as E       # noqa: E402
import verify_phase5_output as V      # noqa: E402

TOOL = os.path.join(HERE, "verify_phase5_output.py")

GOOD_MD = ("# Comparison\n\n"
           "| method | worst-bin dev (unfrozen) | frozen % | FAR frozen |\n"
           "|---|---|---|---|\n"
           "| ours | 0.0036 | 4.9% | 0.6819 |\n\n"
           "Detection horizon: 14.00 days, the ratified primary (R27).\n")


def method_block(name, freeze):
    far = {
        "protocol": "three-number-far-v1.0",
        "freeze_state_available": freeze,
        "pooled_reconstruction": {"exhaustive": True, "residual": 0.0},
        "n_normal_cases": V.EXPECT_N_NORMAL,
    }
    if freeze:
        far.update(V.KNOWN_A01)
    return {
        "n_cases": V.EXPECT_N_CASES,
        "n_normal_cases_for_far": V.EXPECT_N_NORMAL,
        "false_alarm_report": far,
        "n_cases_with_lead": 6,
        "n_cases_alarmed_before_detection_horizon": 0,
    }


def make_evaluation(alpha, horizon):
    methods = {"ours": method_block("ours", True)}
    for m in ("static", "aci", "dtaci", "w1acas"):
        methods[m] = method_block(m, False)
    comparison = {}
    for m in methods:
        comparison[m] = {
            "median_lead_days": 8.43,
            "median_lead_days_missed_as_zero": 8.43,
            "detection_rate": 1.0,
            "n_cases_with_lead": 6,
            "n_anomaly_cases_total": 6,
            "false_alarm_report": {"n_normal_cases": V.EXPECT_N_NORMAL},
        }
    return {
        "alpha": alpha,
        "excluded_cases": list(V.EXPECT_EXCLUDED),
        "trimmed_cases": {V.EXPECT_TRIM_CASE: {
            "cut_at": "2023-08-24T13:00:00",
            "n_rows_before": 55873, "n_rows_kept": 55855,
            "n_rows_dropped": V.EXPECT_TRIM_DROPPED}},
        "false_alarm_protocol": "three-number-far-v1.0",
        "detection_horizon_days": horizon,
        "detection_horizon_protocol": {
            "version": E.DETECTION_HORIZON_PROTOCOL,
            "primary_days": E.RATIFIED_DETECTION_HORIZON_DAYS,
            "this_run_is_primary":
                horizon == E.RATIFIED_DETECTION_HORIZON_DAYS,
            "this_run_in_declared_sweep": True,
        },
        "per_method": methods,
        "comparison": comparison,
    }


def build_batch(root, mutate=None):
    """A complete, clean batch; `mutate(tag, doc)` may break one thing."""
    os.makedirs(root, exist_ok=True)
    for tag, alpha, h in V.expected_dirs():
        d = os.path.join(root, tag)
        os.makedirs(d, exist_ok=True)
        doc = make_evaluation(alpha, h)
        if mutate:
            doc = mutate(tag, doc) or doc
        with open(os.path.join(d, "evaluation.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)
        with open(os.path.join(d, "comparison.md"), "w", encoding="utf-8") as f:
            f.write(GOOD_MD)
    return root


def run(batch):
    return subprocess.run([sys.executable, TOOL, batch],
                          capture_output=True, text=True)


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

    primary = "a01_h%g" % E.RATIFIED_DETECTION_HORIZON_DAYS

    with tempfile.TemporaryDirectory() as root:
        print("\nT1  a clean batch passes")
        good = build_batch(os.path.join(root, "good"))
        p = run(good)
        check("T1 clean batch accepted", p.returncode == 0,
              p.stdout[-800:] + p.stderr[-400:])
        check("T1 and says so", "Batch accepted" in p.stdout)

        def case(name, mutate, expect_in_output):
            d = build_batch(os.path.join(root, name), mutate)
            p = run(d)
            check("%s rejected" % name, p.returncode != 0,
                  "exit 0 -- the rule does not fire")
            check("%s names the problem" % name,
                  expect_in_output in p.stdout,
                  "output did not mention %r" % expect_in_output)

        print("\nT2  null lead time")
        def null_lead(tag, doc):
            if tag == primary:
                doc["comparison"]["ours"]["median_lead_days"] = None
                doc["comparison"]["ours"]["detection_rate"] = None
        case("T2", null_lead, "median_lead_days is not null")

        print("\nT3  the trim did nothing")
        def no_trim(tag, doc):
            doc["trimmed_cases"] = {}
        case("T3", no_trim, "case 93")

        print("\nT4  wrong denominator")
        def bad_n(tag, doc):
            doc["per_method"]["ours"]["n_normal_cases_for_far"] = 50
        case("T4", bad_n, "normal cases")

        print("\nT5  pooled not reconstructible")
        def not_exhaustive(tag, doc):
            (doc["per_method"]["ours"]["false_alarm_report"]
             ["pooled_reconstruction"]["exhaustive"]) = False
        case("T5", not_exhaustive, "reconstructible")

        print("\nT6  freeze state, both directions")
        def baseline_has_freeze(tag, doc):
            doc["per_method"]["static"]["false_alarm_report"][
                "freeze_state_available"] = True
        case("T6a", baseline_has_freeze, "freeze")

        def ours_lacks_freeze(tag, doc):
            doc["per_method"]["ours"]["false_alarm_report"][
                "freeze_state_available"] = False
        case("T6b", ours_lacks_freeze, "freeze state")

        print("\nT7  a false-alarm figure moved")
        def far_moved(tag, doc):
            if tag == primary:
                doc["per_method"]["ours"]["false_alarm_report"][
                    "far_frozen_points"] = 0.71
        case("T7", far_moved, "far_frozen_points")

        print("\nT8  a run is missing")
        missing = build_batch(os.path.join(root, "T8"))
        import shutil
        shutil.rmtree(os.path.join(missing, "a05_unbounded"))
        p = run(missing)
        check("T8 rejected", p.returncode != 0)
        check("T8 reports how many were found",
              "found 14 of 15" in p.stdout, p.stdout[-400:])

        print("\nT9  comparison.md is missing the frozen columns")
        bare = build_batch(os.path.join(root, "T9"))
        with open(os.path.join(bare, primary, "comparison.md"), "w",
                  encoding="utf-8") as f:
            f.write("# Comparison\n\n| method | worst-bin dev |\n")
        p = run(bare)
        check("T9 rejected", p.returncode != 0)
        check("T9 names the missing column", "frozen %" in p.stdout)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
