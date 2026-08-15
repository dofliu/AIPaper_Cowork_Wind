#!/usr/bin/env python3
"""
Self-test: the earliness metric reports what it claims to report.

WHY THIS EXISTS
---------------
Two defects in eval-v1.0 both produced plausible numbers with no error:

  1. median_lead_days was a median over the cases a method DETECTED. A
     method that alarmed on one fault in six was ranked on that one case,
     while a method that caught all six was ranked on all six. Misses left
     the pool instead of counting against it, so missing the hard cases
     raised the score.

  2. lead time was unbounded, so an alarm raised before the fault began was
     credited as early warning -- and credited generously, being further
     from event_start. On the end-to-end fixture this gave the static
     reference 6.11 of its 16.53 days from an alarm 880 steps BEFORE the
     ramp, which is what produced the 8-day "non-inferiority breach" that
     went to the PI as a method problem.

Both are the failure mode this project has now hit three times: no
exception, a number that looks fine, wrong in a direction that matters.
So the fixes get behavioural tests, and the tests are checked in reverse --
each one is confirmed to FAIL against the old behaviour, or it is only
decoration.

  T1  detection_rate is reported, and equals detected / detectable.
  T2  a method that misses most faults cannot hide it in the median:
      median_lead_days stays high, median_lead_days_missed_as_zero drops.
  T3  with a detection horizon, an alarm entirely before the window is not
      a detection, and is recorded as such.
  T4  REVERSE: the same fixture, horizon unset, still credits that alarm.
      If the horizon logic were removed, T3 and T4 would agree -- and this
      test is what notices.
  T5  the summary always records which horizon was in force.

    python3 scripts/selftest_earliness_metric.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

N_ROWS = 400
INTERVAL_MIN = 10
START = datetime(2023, 1, 1, 0, 0, 0)
WIND_COL = "wind_speed_3_avg"
SCORE_COL = "anomaly_score"
TS_COL = "time_stamp"

EVENT_ROW = 300                 # where event_start falls
STEPS_PER_DAY = 24 * 60 / INTERVAL_MIN            # 144

# Alarm patterns, as (first_row, last_row) of point exceedance.
# "eager" fires long before the event and then goes quiet, so it has no
# alarm inside a tight horizon at all. "timely" fires just before the event.
EAGER = (50, 120)
TIMELY = (280, 340)

ANOMALY_CASES = ["a1", "a2", "a3"]
NORMAL_CASES = ["n1"]


def write_scores(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[TS_COL, WIND_COL, SCORE_COL])
        w.writeheader()
        for i in range(N_ROWS):
            ts = START + timedelta(minutes=INTERVAL_MIN * i)
            # Wind cycles through all four regime bins so per-bin rates are
            # defined; the earliness metric does not depend on the value.
            wind = [2.0, 6.0, 10.0, 14.0][i % 4]
            w.writerow({TS_COL: ts.strftime("%Y-%m-%d %H:%M:%S"),
                        WIND_COL: wind, SCORE_COL: 0.0})


def write_method(path, span):
    """A method output with an alarm column we control exactly."""
    lo, hi = span if span else (None, None)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "alarm"])
        for i in range(N_ROWS):
            ts = START + timedelta(minutes=INTERVAL_MIN * i)
            hit = 1 if (lo is not None and lo <= i <= hi) else 0
            w.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), hit])


def build(root, patterns):
    scores_dir = os.path.join(root, "scores")
    care_root = os.path.join(root, "care", "Wind Farm A")
    manifest = os.path.join(root, "manifest")
    for d in (scores_dir, care_root, manifest):
        os.makedirs(d, exist_ok=True)

    all_cases = ANOMALY_CASES + NORMAL_CASES
    for case_id in all_cases:
        write_scores(os.path.join(scores_dir, case_id + ".csv"))

    with open(os.path.join(care_root, "event_info.csv"), "w", newline="",
              encoding="utf-8") as f:
        f.write("asset;event_id;event_label;event_start;event_start_id;"
                "event_end;event_end_id;event_description\n")
        for case_id in all_cases:
            if case_id in ANOMALY_CASES:
                ev = START + timedelta(minutes=INTERVAL_MIN * EVENT_ROW)
                end = ev + timedelta(days=2)
                f.write("1;%s;anomaly;%s;%d;%s;%d;synthetic\n"
                        % (case_id, ev.strftime("%Y-%m-%d %H:%M:%S"), EVENT_ROW,
                           end.strftime("%Y-%m-%d %H:%M:%S"), EVENT_ROW + 100))
            else:
                f.write("1;%s;normal;;;;;\n" % case_id)

    with open(os.path.join(manifest, "g3_case_metadata.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "farm_id", "turbine_id",
                                          "label", "start_timestamp",
                                          "end_timestamp"])
        w.writeheader()
        for case_id in all_cases:
            w.writerow({"case_id": case_id, "farm_id": "Wind Farm A",
                        "turbine_id": "1",
                        "label": "anomaly" if case_id in ANOMALY_CASES else "normal",
                        "start_timestamp": START.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_timestamp": (START + timedelta(
                            minutes=INTERVAL_MIN * N_ROWS)).strftime("%Y-%m-%d %H:%M:%S")})

    method_dirs = {}
    for name, per_case in patterns.items():
        d = os.path.join(root, "m_" + name)
        os.makedirs(d, exist_ok=True)
        for case_id in all_cases:
            write_method(os.path.join(d, case_id + ".csv"), per_case.get(case_id))
        method_dirs[name] = d

    return scores_dir, care_root, manifest, method_dirs


def evaluate(root, scores_dir, care_root, manifest, method_dirs, horizon, tag):
    out_dir = os.path.join(root, "eval_" + tag)
    cmd = [sys.executable, os.path.join(HERE, "evaluate_experiment.py"),
           "--scores-dir", scores_dir, "--wind-col", WIND_COL,
           "--timestamp-col", TS_COL,
           "--g3-case-metadata", os.path.join(manifest, "g3_case_metadata.csv"),
           "--event-info-root", os.path.join(root, "care"),
           "--alpha", "0.05", "--window", "100",
           "--reference", "timely",
           "--output-dir", out_dir]
    for name, d in sorted(method_dirs.items()):
        cmd += ["--method", "%s=%s:alarm:alarm" % (name, d)]
    if horizon is not None:
        cmd += ["--detection-horizon-days", str(horizon)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("      evaluator FAILED rc=%d\n      %s"
              % (proc.returncode, proc.stderr[-800:]))
        return None
    with open(os.path.join(out_dir, "evaluation.json"), encoding="utf-8") as f:
        return json.load(f)


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

    # eager: fires early then goes quiet, on every anomaly case.
    # timely: fires just before the event, on every anomaly case.
    # partial: fires just before the event, but only on ONE case.
    patterns = {
        "eager":   {c: EAGER for c in ANOMALY_CASES},
        "timely":  {c: TIMELY for c in ANOMALY_CASES},
        "partial": {"a1": TIMELY},
    }

    with tempfile.TemporaryDirectory() as root:
        scores_dir, care_root, manifest, method_dirs = build(root, patterns)

        unbounded = evaluate(root, scores_dir, care_root, manifest,
                             method_dirs, None, "unbounded")
        # 1.0 day = 144 rows before row 300 -> row 156. eager is quiet by
        # then; timely is not.
        bounded = evaluate(root, scores_dir, care_root, manifest,
                           method_dirs, 1.0, "bounded")

        if unbounded is None or bounded is None:
            print("\nevaluator did not run; cannot test")
            return 1

        ub = unbounded["comparison"]
        bd = bounded["comparison"]

        # ---- T1  detection rate is reported and correct ------------------
        print("\nT1  detection_rate is reported and equals detected/detectable")
        check("T1 detection_rate present for every method",
              all("detection_rate" in ub[m] for m in patterns),
              "got %s" % sorted(ub))
        check("T1 timely detected all 3 anomaly cases",
              ub["timely"]["n_cases_with_lead"] == 3
              and ub["timely"]["n_anomaly_cases_total"] == 3,
              "got %s/%s" % (ub["timely"]["n_cases_with_lead"],
                             ub["timely"]["n_anomaly_cases_total"]))
        check("T1 partial detected exactly 1 of 3",
              ub["partial"]["n_cases_with_lead"] == 1
              and ub["partial"]["n_anomaly_cases_total"] == 3,
              "got %s/%s" % (ub["partial"]["n_cases_with_lead"],
                             ub["partial"]["n_anomaly_cases_total"]))
        check("T1 partial detection_rate is 1/3",
              abs(ub["partial"]["detection_rate"] - 1.0 / 3.0) < 1e-9,
              "got %s" % ub["partial"]["detection_rate"])
        check("T1 the denominator counts cases with an event window, not "
              "all four cases",
              ub["timely"]["n_anomaly_cases_total"] == len(ANOMALY_CASES),
              "got %s" % ub["timely"]["n_anomaly_cases_total"])

        # ---- T2  a miss cannot hide inside the median ---------------------
        print("\nT2  missing most faults shows up somewhere")
        p_med = ub["partial"]["median_lead_days"]
        t_med = ub["timely"]["median_lead_days"]
        check("T2 partial's median over DETECTED cases matches timely's",
              p_med is not None and t_med is not None
              and abs(p_med - t_med) < 1e-9,
              "partial %s vs timely %s" % (p_med, t_med))
        p_zero = ub["partial"]["median_lead_days_missed_as_zero"]
        t_zero = ub["timely"]["median_lead_days_missed_as_zero"]
        check("T2 with misses scored as zero, partial drops below timely",
              p_zero is not None and t_zero is not None and p_zero < t_zero,
              "partial %s vs timely %s" % (p_zero, t_zero))
        check("T2 partial's miss-as-zero median is 0 (it caught 1 of 3)",
              p_zero is not None and abs(p_zero) < 1e-9, "got %s" % p_zero)
        check("T2 the caveat is attached when detection rates differ",
              "verdict_caveat" in ub["partial"],
              "keys: %s" % sorted(ub["partial"]))

        # ---- T3  the horizon excludes a pre-window alarm -------------------
        print("\nT3  with a horizon, an alarm entirely before the window is")
        print("    a false alarm, not early warning")
        check("T3 eager detects nothing inside a 1-day horizon",
              bd["eager"]["n_cases_with_lead"] == 0,
              "got %s" % bd["eager"]["n_cases_with_lead"])
        check("T3 eager's early alarms are recorded, not silently dropped",
              bd["eager"]["n_cases_alarmed_before_detection_horizon"] == 3,
              "got %s" % bd["eager"]["n_cases_alarmed_before_detection_horizon"])
        check("T3 timely is unaffected by the horizon",
              bd["timely"]["n_cases_with_lead"] == 3,
              "got %s" % bd["timely"]["n_cases_with_lead"])
        check("T3 no lead time exceeds the horizon",
              bd["timely"]["median_lead_days"] is not None
              and bd["timely"]["median_lead_days"] <= 1.0 + 1e-9,
              "got %s" % bd["timely"]["median_lead_days"])

        # ---- T4  REVERSE: without the horizon the old behaviour returns ---
        print("\nT4  REVERSE -- unset horizon still credits that same alarm,")
        print("    so T3 is testing the horizon and not something else")
        check("T4 unbounded credits eager on all 3 cases",
              ub["eager"]["n_cases_with_lead"] == 3,
              "got %s" % ub["eager"]["n_cases_with_lead"])
        check("T4 unbounded gives eager MORE lead time than timely",
              ub["eager"]["median_lead_days"] > ub["timely"]["median_lead_days"],
              "eager %s vs timely %s" % (ub["eager"]["median_lead_days"],
                                         ub["timely"]["median_lead_days"]))
        check("T4 that credit exceeds the horizon it would be denied under",
              ub["eager"]["median_lead_days"] > 1.0,
              "got %s" % ub["eager"]["median_lead_days"])
        check("T4 bounded and unbounded genuinely disagree on eager",
              ub["eager"]["n_cases_with_lead"] != bd["eager"]["n_cases_with_lead"],
              "both %s" % ub["eager"]["n_cases_with_lead"])
        check("T4 unbounded records no pre-horizon exclusions",
              ub["eager"]["n_cases_alarmed_before_detection_horizon"] == 0,
              "got %s" % ub["eager"]["n_cases_alarmed_before_detection_horizon"])

        # ---- T5  the horizon in force is always on the record --------------
        print("\nT5  the summary states which horizon was in force")
        check("T5 unbounded run records null",
              unbounded.get("detection_horizon_days") is None
              and "detection_horizon_days" in unbounded)
        check("T5 unbounded run carries the caveat",
              "UNSET" in (unbounded.get("detection_horizon_note") or ""),
              "got %r" % unbounded.get("detection_horizon_note"))
        check("T5 bounded run records the value",
              bounded.get("detection_horizon_days") == 1.0,
              "got %s" % bounded.get("detection_horizon_days"))
        check("T5 eval version bumped past the version with the defects",
              unbounded.get("eval_version") != "eval-v1.0",
              "got %s" % unbounded.get("eval_version"))

        print("\n    what the two runs report for each method:")
        print("      method    unbounded lead / detected      1-day horizon")
        for m in sorted(patterns):
            print("      %-9s %-8s %-2d/%-2d %20s %d/%d"
                  % (m,
                     "n/a" if ub[m]["median_lead_days"] is None
                     else "%.3f" % ub[m]["median_lead_days"],
                     ub[m]["n_cases_with_lead"], ub[m]["n_anomaly_cases_total"],
                     "n/a" if bd[m]["median_lead_days"] is None
                     else "%.3f" % bd[m]["median_lead_days"],
                     bd[m]["n_cases_with_lead"], bd[m]["n_anomaly_cases_total"]))

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
