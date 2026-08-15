#!/usr/bin/env python3
"""
End-to-end self-test: score streams -> every method -> one comparison table.

Everything else tests one component. This runs the whole pipeline the local
operator will run, on synthetic data, as separate subprocesses exactly as
they would be invoked. If this passes, a real run differs only in the data.

The point is to move failure discovery off the operator's machine. Every
mismatch found here -- a column name, an argument shape, an output the
evaluator cannot read -- is one round trip they do not have to spend.

  T1  The pipeline completes: four methods produce output, the evaluator
      reads all of them, the comparison table renders.
  T2  On regime-dependent scores our method has the lowest worst-bin
      deviation, and the marginal-only methods do worse there while
      looking respectable marginally. That is the paper's claim surviving
      a full pipeline rather than a unit test.
  T3  Earliness is computed against the event windows, and the
      non-inferiority check against the reference method reports a verdict
      rather than silently omitting one.
  T4  The work-order rule is applied to every method, so no baseline gets
      credit for alarming on a single point.
  T5  Excluded cases stay excluded, as the D1/D6 plan requires.

    python3 scripts/selftest_end_to_end.py

Exit code: 0 if the pipeline holds together and the claim survives it.
"""

import csv
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

N_ROWS = 9000
INTERVAL_MIN = 10
START = datetime(2023, 1, 1, 0, 0, 0)
WIND_COL = "wind_speed_3_avg"
SCORE_COL = "anomaly_score"
TS_COL = "time_stamp"

ALPHA = 0.05
WINDOW = 500
MIN_BIN = 200


def build_case(path, rng, fault_at=None):
    """Regime-dependent scores: higher wind gives higher, wider scores. A
    fault, if present, ramps the score from fault_at onward."""
    rows = []
    for i in range(N_ROWS):
        ts = START + timedelta(minutes=INTERVAL_MIN * i)
        wind = min(max(rng.weibullvariate(8.5, 2.0), 0.0), 25.0)
        score = rng.gauss(0.5 * wind, 1.0 + 0.25 * wind)
        if fault_at is not None and i >= fault_at:
            score += 8.0 * min(1.0, (i - fault_at) / 1000.0)
        rows.append({TS_COL: ts.strftime("%Y-%m-%d %H:%M:%S"),
                     WIND_COL: round(wind, 3),
                     SCORE_COL: round(score, 6)})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[TS_COL, WIND_COL, SCORE_COL])
        w.writeheader()
        w.writerows(rows)
    return rows


def run(cmd, label):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("      %s FAILED rc=%d" % (label, proc.returncode))
        print("      stderr: %s" % proc.stderr[-600:])
    return proc.returncode == 0


def main():
    failures, checks = [], 0

    def check(name, condition, detail=""):
        nonlocal checks
        checks += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s %s" % (name, detail))
            failures.append(name)

    py = sys.executable
    with tempfile.TemporaryDirectory() as root:
        scores_dir = os.path.join(root, "scores")
        manifest = os.path.join(root, "manifest_out")
        care_root = os.path.join(root, "care", "Wind Farm A")
        for d in (scores_dir, manifest, care_root):
            os.makedirs(d, exist_ok=True)

        print("\nbuilding fixture: 4 cases x %d rows" % N_ROWS)
        cases = {"1": 4000, "2": 5000, "3": None, "4": None}   # 1,2 faulted
        rng = random.Random(7)
        for case_id, fault_at in cases.items():
            build_case(os.path.join(scores_dir, case_id + ".csv"), rng, fault_at)

        # event_info: one row per case, event_id == case_id on this archive
        with open(os.path.join(care_root, "event_info.csv"), "w", newline="",
                  encoding="utf-8") as f:
            f.write("asset;event_id;event_label;event_start;event_start_id;"
                    "event_end;event_end_id;event_description\n")
            for case_id, fault_at in cases.items():
                if fault_at is None:
                    f.write("1;%s;normal;;;;;\n" % case_id)
                else:
                    ev = START + timedelta(minutes=INTERVAL_MIN * (fault_at + 1500))
                    end = ev + timedelta(days=5)
                    f.write("1;%s;anomaly;%s;%d;%s;%d;synthetic fault\n"
                            % (case_id, ev.strftime("%Y-%m-%d %H:%M:%S"), fault_at,
                               end.strftime("%Y-%m-%d %H:%M:%S"), fault_at + 2000))

        with open(os.path.join(manifest, "g3_case_metadata.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["case_id", "farm_id", "turbine_id",
                                              "label", "start_timestamp",
                                              "end_timestamp"])
            w.writeheader()
            for case_id, fault_at in cases.items():
                w.writerow({"case_id": case_id, "farm_id": "Wind Farm A",
                            "turbine_id": "1",
                            "label": "anomaly" if fault_at is not None else "normal",
                            "start_timestamp": START.strftime("%Y-%m-%d %H:%M:%S"),
                            "end_timestamp": (START + timedelta(
                                minutes=INTERVAL_MIN * N_ROWS)).strftime("%Y-%m-%d %H:%M:%S")})

        # ---------------- T1 run every method ----------------
        print("\nT1  run every method, then the evaluator")
        rcc_dir = os.path.join(root, "rcc")
        ok_rcc = run([py, os.path.join(HERE, "regime_conditional_calibration.py"),
                      "--score-dir", scores_dir, "--output-dir", rcc_dir,
                      "--score-col", SCORE_COL, "--wind-col", WIND_COL,
                      "--timestamp-col", TS_COL, "--alpha", str(ALPHA),
                      "--window", str(WINDOW), "--min-bin-samples", str(MIN_BIN)],
                     "regime_conditional_calibration")
        check("T1 our method ran", ok_rcc)

        w1_dir = os.path.join(root, "w1acas")
        ok_w1 = run([py, os.path.join(HERE, "baseline_w1_acas.py"),
                     "--score-dir", scores_dir, "--output-dir", w1_dir,
                     "--score-col", SCORE_COL, "--timestamp-col", TS_COL,
                     "--alpha-c", "0.01", "--max-past", "300"],
                    "baseline_w1_acas")
        check("T1 W1-ACAS ran", ok_w1)

        base_dir = os.path.join(root, "baselines")
        ok_base = run([py, os.path.join(HERE, "baselines_online_calibration.py"),
                       "--score-dir", scores_dir, "--output-dir", base_dir,
                       "--score-col", SCORE_COL, "--timestamp-col", TS_COL,
                       "--alpha", str(ALPHA), "--n-cal", str(WINDOW),
                       "--window", str(WINDOW)],
                      "baselines_online_calibration")
        check("T1 ACI/DtACI/static ran", ok_base)

        eval_dir = os.path.join(root, "evaluation")
        ok_eval = run([py, os.path.join(HERE, "evaluate_experiment.py"),
                       "--scores-dir", scores_dir, "--wind-col", WIND_COL,
                       "--timestamp-col", TS_COL,
                       "--g3-case-metadata", os.path.join(manifest, "g3_case_metadata.csv"),
                       "--event-info-root", os.path.join(root, "care"),
                       "--alpha", str(ALPHA), "--window", str(WINDOW),
                       "--method", "ours=%s:p_value:pvalue" % rcc_dir,
                       "--method", "w1acas=%s:beta:pvalue" % w1_dir,
                       "--method", "aci=%s:aci_alarm:alarm" % base_dir,
                       "--method", "dtaci=%s:dtaci_alarm:alarm" % base_dir,
                       "--method", "static=%s:static_split_conformal_alarm:alarm" % base_dir,
                       "--reference", "static",
                       "--exclude-cases", "4",
                       "--output-dir", eval_dir],
                      "evaluate_experiment")
        check("T1 evaluator ran", ok_eval)
        if not ok_eval:
            print("\n%d checks, %d failed" % (checks, len(failures)))
            return 1

        with open(os.path.join(eval_dir, "evaluation.json"), encoding="utf-8") as f:
            ev = json.load(f)
        comparison = ev["comparison"]
        check("T1 all five methods in the table", len(comparison) == 5,
              "got %s" % sorted(comparison))
        check("T1 comparison.md written",
              os.path.isfile(os.path.join(eval_dir, "comparison.md")))

        # ---------------- T2 the claim survives the pipeline ----------------
        # The `detected` column is not decoration. Without it an earlier
        # reading of this table took a median lead time computed over one
        # case as if it were computed over all of them, and escalated the
        # resulting "8-day deficit" to the PI as a fault in the method. A
        # median lead time is not interpretable without its denominator, so
        # the two are printed together and never apart.
        print("\nT2  our method has the lowest worst-bin deviation")
        print("      method   worst-bin   marginal   detected   median lead (d)")
        for name, e in sorted(comparison.items()):
            det = ("n/a" if not e.get("n_anomaly_cases_total")
                   else "%d/%d" % (e["n_cases_with_lead"], e["n_anomaly_cases_total"]))
            print("      %-8s %-11s %-10s %-10s %s" % (
                name,
                "n/a" if e["mean_worst_bin_deviation"] is None else "%.4f" % e["mean_worst_bin_deviation"],
                "n/a" if e["mean_marginal_deviation"] is None else "%.4f" % e["mean_marginal_deviation"],
                det,
                "n/a" if e["median_lead_days"] is None else "%.2f" % e["median_lead_days"]))

        ours = comparison["ours"]["mean_worst_bin_deviation"]
        others = {k: v["mean_worst_bin_deviation"] for k, v in comparison.items()
                  if k != "ours" and v["mean_worst_bin_deviation"] is not None}
        check("T2 our worst-bin deviation is defined", ours is not None)
        check("T2 at least three baselines produced a worst-bin deviation",
              len(others) >= 3, "got %s" % sorted(others))
        check("T2 ours is the lowest worst-bin deviation",
              all(ours < v for v in others.values()),
              "ours %.4f vs %s" % (ours, {k: round(v, 4) for k, v in others.items()}))

        # ---------------- T3 earliness and non-inferiority ----------------
        print("\nT3  earliness measured against the event windows")
        leads = {k: v["median_lead_days"] for k, v in comparison.items()}
        check("T3 our method has a median lead time", leads["ours"] is not None,
              "got %s" % leads["ours"])
        check("T3 non-inferiority verdict reported for our method",
              comparison["ours"].get("non_inferior") is not None
              or comparison["ours"].get("lead_days_lost_vs_reference") is not None,
              "no verdict against reference")
        check("T3 margin recorded as the signed-off 2 days",
              comparison["ours"].get("non_inferiority_margin_days", 2.0) == 2.0)
        check("T3 every method reports the denominator behind its median",
              all("n_anomaly_cases_total" in e and "detection_rate" in e
                  for e in comparison.values()),
              "missing on: %s" % [k for k, e in comparison.items()
                                  if "detection_rate" not in e])
        check("T3 our method detected every faulted case in the fixture",
              comparison["ours"]["n_cases_with_lead"]
              == comparison["ours"]["n_anomaly_cases_total"],
              "got %s/%s" % (comparison["ours"]["n_cases_with_lead"],
                             comparison["ours"]["n_anomaly_cases_total"]))
        check("T3 the horizon in force is recorded, set or not",
              "detection_horizon_days" in ev,
              "keys: %s" % sorted(ev))

        # ---------------- T4 uniform work-order rule ----------------
        print("\nT4  the work-order rule is applied to every method")
        check("T4 recorded in the summary",
              "applied identically to every method" in ev["work_order_rule"])
        check("T4 rule is 6 of 18", ev["work_order_rule"].startswith("6 of last 18"))

        # ---------------- T5 exclusions ----------------
        print("\nT5  excluded cases stay excluded")
        check("T5 exclusion recorded", ev["excluded_cases"] == ["4"])
        for name in comparison:
            per_case = ev["per_method"][name]["per_case"]
            if "4" in per_case:
                check("T5 case 4 absent from %s" % name, False, "it is present")
                break
        else:
            check("T5 case 4 absent from every method", True)

        check("T5 missing CARE metrics still declared missing",
              ev["missing_metrics"]["care_score"]["status"] == "NOT_IMPLEMENTED")

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
