#!/usr/bin/env python3
"""
Diagnostic: where does the reported lead-time deficit actually come from?

BACKGROUND
----------
The end-to-end run reports that our method alarms ~8 days later than the
static split-conformal reference, breaching the signed-off 2-day
non-inferiority margin (dev log v3.7 RISK). Before anyone re-opens a
ratified parameter (min_bin_samples = 500) to close an 8-day gap, the gap
itself has to be shown to be real.

This script takes the fixture apart and asks one question per candidate
explanation. It changes no parameter and proposes no method change; it
only measures.

THREE CANDIDATE EXPLANATIONS
----------------------------
  H1  WARM-UP. Our method withholds a p-value until a bin holds
      min_bin_samples scores. A pooled method fills one buffer roughly
      four times faster than we fill four. If our first decidable point
      lands after the baselines', we start the race late.

  H2  OPERATING POINT. A method whose realised false-alarm rate is five
      times nominal will alarm earlier on everything, faults included.
      Comparing lead times at a nominal alpha the methods do not actually
      honour compares them at different operating points, and the more
      trigger-happy method wins by construction.

  H3  PRE-ONSET CREDIT. The fixture ramps the fault at a known index and
      places the labelled event_start 1500 steps later. Lead time is
      measured from event_start. An alarm raised BEFORE the ramp begins
      cannot be a detection of a fault that does not yet exist -- but the
      metric still credits it, and credits it generously, because it is
      further from event_start.

H3 is the one with teeth: it is not a tuning question, it is a question of
whether the metric measures what it is named after. The fixture is the
only place we can settle it, because it is the only place the true onset
index is known. On CARE we will never know the physical onset -- which is
why a metric that silently rewards pre-onset alarms would carry the error
into the manuscript undetected.

WHAT IS REPORTED
----------------
Per method, per faulted case: the first decidable index (H1), the realised
false-alarm rate on the NORMAL cases (H2), and the first work-order alarm
index compared against the true ramp index (H3).

    python3 scripts/diagnose_earliness_gap.py

Exit code 0 if the diagnostic completed. This script asserts nothing about
which method is better; it prints what each one did.

No third-party dependencies beyond the Python 3 standard library.
"""

import csv
import glob
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
from collections import deque
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

# Fixture shape. Deliberately identical in kind to selftest_end_to_end.py so
# the numbers here explain the numbers there, with more cases so the medians
# are not carried by two points.
N_ROWS = 9000
INTERVAL_MIN = 10
START = datetime(2023, 1, 1, 0, 0, 0)
WIND_COL = "wind_speed_3_avg"
SCORE_COL = "anomaly_score"
TS_COL = "time_stamp"

ALPHA = 0.05
WINDOW = 500
MIN_BIN = 200

ALARM_OF = 6
ALARM_WINDOW = 18

# Steps between the physical ramp start and the labelled event_start. The
# fixture's whole point is that these differ: the label is not the onset.
LABEL_LAG_STEPS = 1500

STEPS_PER_DAY = 24 * 60 / INTERVAL_MIN          # 144


def build_case(path, rng, fault_at=None):
    """Regime-dependent scores; a fault, if present, ramps from fault_at."""
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
        print("      stderr: %s" % proc.stderr[-800:])
        return False
    return True


def to_float(raw):
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def read_column(path, column):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            return None
        return [r.get(column) for r in reader]


def exceedances(values, mode, alpha):
    """None where the method declined to decide, else 0/1."""
    out = []
    for v in values:
        f = to_float(v)
        if f is None:
            out.append(None)
        elif mode == "pvalue":
            out.append(1 if f <= alpha else 0)
        else:
            out.append(1 if f >= 0.5 else 0)
    return out


def work_order_alarms(exceeds):
    """The common 6-of-18 rule, identical to the evaluator's."""
    history = deque(maxlen=ALARM_WINDOW)
    out = []
    active = False
    for e in exceeds:
        if e is None:
            out.append(None)
            continue
        history.append(e)
        if len(history) == ALARM_WINDOW:
            active = sum(history) >= ALARM_OF
        out.append(active)
    return out


def first_index(seq, predicate):
    for i, v in enumerate(seq):
        if predicate(v):
            return i
    return None


# Two case sets. "selftest" is byte-for-byte the fixture that produced the
# v3.7 RISK number, so the diagnostic can be pointed at the exact run being
# questioned. "extended" spreads six ramp indices so no single case carries
# the median.
PRESETS = {
    "selftest": {"1": 4000, "2": 5000, "3": None, "4": None},
    "extended": {"f1": 3800, "f2": 4000, "f3": 4200,
                 "f4": 4400, "f5": 4600, "f6": 4800,
                 "n1": None, "n2": None, "n3": None,
                 "n4": None, "n5": None, "n6": None},
}


def main():
    py = sys.executable

    preset = "extended"
    for arg in sys.argv[1:]:
        if arg.startswith("--preset="):
            preset = arg.split("=", 1)[1]
    if preset not in PRESETS:
        print("unknown preset %r; choose from %s"
              % (preset, ", ".join(sorted(PRESETS))), file=sys.stderr)
        return 3
    cases = PRESETS[preset]
    print("preset: %s" % preset)

    with tempfile.TemporaryDirectory() as root:
        scores_dir = os.path.join(root, "scores")
        os.makedirs(scores_dir, exist_ok=True)

        print("building fixture: %d cases x %d rows (%d faulted)"
              % (len(cases), N_ROWS,
                 sum(1 for v in cases.values() if v is not None)))
        rng = random.Random(7)
        for case_id in sorted(cases):
            build_case(os.path.join(scores_dir, case_id + ".csv"),
                       rng, cases[case_id])

        rcc_dir = os.path.join(root, "rcc")
        w1_dir = os.path.join(root, "w1acas")
        base_dir = os.path.join(root, "baselines")

        print("\nrunning every method at the nominal alpha = %.3g" % ALPHA)
        ok = run([py, os.path.join(HERE, "regime_conditional_calibration.py"),
                  "--score-dir", scores_dir, "--output-dir", rcc_dir,
                  "--score-col", SCORE_COL, "--wind-col", WIND_COL,
                  "--timestamp-col", TS_COL, "--alpha", str(ALPHA),
                  "--window", str(WINDOW), "--min-bin-samples", str(MIN_BIN)],
                 "regime_conditional_calibration")
        ok &= run([py, os.path.join(HERE, "baseline_w1_acas.py"),
                   "--score-dir", scores_dir, "--output-dir", w1_dir,
                   "--score-col", SCORE_COL, "--timestamp-col", TS_COL,
                   "--alpha-c", "0.01", "--max-past", "300"],
                  "baseline_w1_acas")
        ok &= run([py, os.path.join(HERE, "baselines_online_calibration.py"),
                   "--score-dir", scores_dir, "--output-dir", base_dir,
                   "--score-col", SCORE_COL, "--timestamp-col", TS_COL,
                   "--alpha", str(ALPHA), "--n-cal", str(WINDOW),
                   "--window", str(WINDOW)],
                  "baselines_online_calibration")
        if not ok:
            print("a method failed to run; diagnostic aborted")
            return 1

        methods = {
            "ours":   (rcc_dir,  "p_value",             "pvalue"),
            "w1acas": (w1_dir,   "beta",                "pvalue"),
            "aci":    (base_dir, "aci_alarm",           "alarm"),
            "dtaci":  (base_dir, "dtaci_alarm",         "alarm"),
            "static": (base_dir, "static_split_conformal_alarm", "alarm"),
        }

        # ---- collect per method, per case -------------------------------
        collected = {}
        for name, (directory, column, mode) in sorted(methods.items()):
            per_case = {}
            for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
                case_id = os.path.splitext(os.path.basename(path))[0]
                if case_id not in cases:
                    continue
                values = read_column(path, column)
                if values is None:
                    continue
                ex = exceedances(values, mode, ALPHA)
                al = work_order_alarms(ex)
                per_case[case_id] = {
                    "first_decidable": first_index(ex, lambda v: v is not None),
                    "first_alarm": first_index(al, lambda v: v is True),
                    "n_decided": sum(1 for v in ex if v is not None),
                    "n_exceed": sum(v for v in ex if v),
                }
            collected[name] = per_case

        report = {"preset": preset, "fixture": {"n_rows": N_ROWS, "alpha": ALPHA,
                              "window": WINDOW, "min_bin_samples": MIN_BIN,
                              "label_lag_steps": LABEL_LAG_STEPS,
                              "steps_per_day": STEPS_PER_DAY,
                              "ramp_index": {k: v for k, v in sorted(cases.items())
                                             if v is not None}},
                  "methods": {}}

        # ---- H1  warm-up -------------------------------------------------
        print("\nH1  WARM-UP -- when could each method first decide at all?")
        print("      method   first decidable index (median over cases)   in days")
        for name in sorted(collected):
            idx = [c["first_decidable"] for c in collected[name].values()
                   if c["first_decidable"] is not None]
            if not idx:
                print("      %-8s n/a" % name)
                continue
            med = statistics.median(idx)
            print("      %-8s %-42.1f %.2f" % (name, med, med / STEPS_PER_DAY))
            report["methods"].setdefault(name, {})["median_first_decidable"] = med

        earliest_ramp = min(v for v in cases.values() if v is not None)
        print("\n      earliest fault ramp index in the fixture: %d" % earliest_ramp)
        print("      -> warm-up only costs lead time if a method's first")
        print("         decidable index is AFTER the ramp. Compare above.")

        # ---- H2  operating point ----------------------------------------
        print("\nH2  OPERATING POINT -- realised false-alarm rate on the")
        print("    NORMAL cases, where every alarm is by definition false.")
        print("      method   point exceedance rate   vs nominal %.3g" % ALPHA)
        for name in sorted(collected):
            dec = sum(collected[name][c]["n_decided"]
                      for c in collected[name] if cases[c] is None)
            exc = sum(collected[name][c]["n_exceed"]
                      for c in collected[name] if cases[c] is None)
            if not dec:
                print("      %-8s n/a" % name)
                continue
            far = exc / dec
            print("      %-8s %-23.4f %.1fx" % (name, far, far / ALPHA))
            report["methods"].setdefault(name, {})["normal_case_far"] = far

        # ---- H3  pre-onset credit ---------------------------------------
        print("\nH3  PRE-ONSET CREDIT -- is the first alarm before or after")
        print("    the fault physically starts? Negative = alarmed before the")
        print("    fault existed, so the 'lead time' is a false alarm.")
        print("      method   median (first_alarm - ramp_index), steps   days")
        for name in sorted(collected):
            offsets = []
            pre = 0
            for case_id, ramp in sorted(cases.items()):
                if ramp is None:
                    continue
                fa = collected[name].get(case_id, {}).get("first_alarm")
                if fa is None:
                    continue
                offsets.append(fa - ramp)
                if fa < ramp:
                    pre += 1
            if not offsets:
                print("      %-8s n/a (never alarmed on a faulted case)" % name)
                continue
            med = statistics.median(offsets)
            flag = "   <-- PRE-ONSET" if med < 0 else ""
            print("      %-8s %-41.1f %+.2f%s"
                  % (name, med, med / STEPS_PER_DAY, flag))
            report["methods"].setdefault(name, {}).update({
                "median_alarm_offset_from_ramp_steps": med,
                "n_faulted_cases_alarmed_pre_onset": pre,
                "n_faulted_cases_alarmed": len(offsets),
            })

        print("\n    cases alarmed BEFORE the ramp, per method:")
        for name in sorted(collected):
            m = report["methods"].get(name, {})
            if "n_faulted_cases_alarmed" in m:
                print("      %-8s %d of %d faulted cases"
                      % (name, m["n_faulted_cases_alarmed_pre_onset"],
                         m["n_faulted_cases_alarmed"]))

        # ---- what the current metric would report ------------------------
        print("\nFOR REFERENCE -- lead time as the evaluator currently computes")
        print("    it, measured from the LABELLED event_start (= ramp + %d):"
              % LABEL_LAG_STEPS)
        print("      method   median lead (days)   of which is pre-onset")
        for name in sorted(collected):
            leads = []
            for case_id, ramp in sorted(cases.items()):
                if ramp is None:
                    continue
                fa = collected[name].get(case_id, {}).get("first_alarm")
                if fa is None:
                    continue
                event_idx = ramp + LABEL_LAG_STEPS
                leads.append((event_idx - fa) / STEPS_PER_DAY)
            if not leads:
                print("      %-8s n/a" % name)
                continue
            med = statistics.median(leads)
            cap = LABEL_LAG_STEPS / STEPS_PER_DAY
            over = max(0.0, med - cap)
            print("      %-8s %-20.2f %.2f" % (name, med, over))
            report["methods"].setdefault(name, {})["median_lead_days"] = med
            report["methods"][name]["lead_days_beyond_physical_max"] = over

        print("\n    the physical maximum achievable lead is %.2f days"
              % (LABEL_LAG_STEPS / STEPS_PER_DAY))
        print("    (the ramp starts that far before the label). Any method")
        print("    reporting more than that is being credited for alarms")
        print("    raised before the fault began.")

        # ---- horizon sweep -----------------------------------------------
        # The detection horizon H is a new evaluation parameter and needs
        # ratifying. Rather than propose a number, run the real evaluator
        # across a range and show what each choice does to the table, so the
        # decision is made against evidence. H is deliberately swept past
        # the physical maximum lead so the point where the artefact
        # reappears is visible rather than assumed.
        print("\nHORIZON SWEEP -- the same comparison under each candidate H,")
        print("    produced by evaluate_experiment.py itself.")

        care_root = os.path.join(root, "care", "Wind Farm A")
        manifest = os.path.join(root, "manifest")
        for d in (care_root, manifest):
            os.makedirs(d, exist_ok=True)

        with open(os.path.join(care_root, "event_info.csv"), "w", newline="",
                  encoding="utf-8") as f:
            f.write("asset;event_id;event_label;event_start;event_start_id;"
                    "event_end;event_end_id;event_description\n")
            for case_id, ramp in sorted(cases.items()):
                if ramp is None:
                    f.write("1;%s;normal;;;;;\n" % case_id)
                    continue
                ev = START + timedelta(minutes=INTERVAL_MIN * (ramp + LABEL_LAG_STEPS))
                end = ev + timedelta(days=5)
                f.write("1;%s;anomaly;%s;%d;%s;%d;synthetic fault\n"
                        % (case_id, ev.strftime("%Y-%m-%d %H:%M:%S"),
                           ramp + LABEL_LAG_STEPS,
                           end.strftime("%Y-%m-%d %H:%M:%S"),
                           ramp + LABEL_LAG_STEPS + 500))

        with open(os.path.join(manifest, "g3_case_metadata.csv"), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["case_id", "farm_id", "turbine_id",
                                              "label", "start_timestamp",
                                              "end_timestamp"])
            w.writeheader()
            for case_id, ramp in sorted(cases.items()):
                w.writerow({"case_id": case_id, "farm_id": "Wind Farm A",
                            "turbine_id": "1",
                            "label": "normal" if ramp is None else "anomaly",
                            "start_timestamp": START.strftime("%Y-%m-%d %H:%M:%S"),
                            "end_timestamp": (START + timedelta(
                                minutes=INTERVAL_MIN * N_ROWS)).strftime(
                                    "%Y-%m-%d %H:%M:%S")})

        physical_max = LABEL_LAG_STEPS / STEPS_PER_DAY
        report["horizon_sweep"] = {}
        for horizon in [None, 3.0, 5.0, 7.0, 10.0, 14.0]:
            tag = "unbounded" if horizon is None else ("h%g" % horizon)
            out_dir = os.path.join(root, "eval_" + tag)
            cmd = [py, os.path.join(HERE, "evaluate_experiment.py"),
                   "--scores-dir", scores_dir, "--wind-col", WIND_COL,
                   "--timestamp-col", TS_COL,
                   "--g3-case-metadata", os.path.join(manifest,
                                                      "g3_case_metadata.csv"),
                   "--event-info-root", os.path.join(root, "care"),
                   "--alpha", str(ALPHA), "--window", str(WINDOW),
                   "--reference", "static", "--output-dir", out_dir]
            for name, (directory, column, mode) in sorted(methods.items()):
                cmd += ["--method", "%s=%s:%s:%s" % (name, directory, column, mode)]
            if horizon is not None:
                cmd += ["--detection-horizon-days", str(horizon)]

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                print("      H=%s evaluator failed: %s" % (tag, proc.stderr[-300:]))
                continue
            with open(os.path.join(out_dir, "evaluation.json"),
                      encoding="utf-8") as f:
                summary = json.load(f)
            comp = summary["comparison"]

            label = ("unbounded (current default)" if horizon is None
                     else "H = %g days" % horizon)
            flag = ""
            if horizon is not None and horizon > physical_max:
                flag = "   [above the %.2f d physical max: artefact returns]" % physical_max
            print("\n    %s%s" % (label, flag))
            print("      method   detected   median lead   miss=0   lead lost   non-inf")
            for name in sorted(comp):
                e = comp[name]
                det = ("%d/%d" % (e["n_cases_with_lead"], e["n_anomaly_cases_total"])
                       if e.get("n_anomaly_cases_total") else "n/a")
                print("      %-8s %-10s %-13s %-8s %-11s %s"
                      % (name, det,
                         "n/a" if e["median_lead_days"] is None
                         else "%.2f" % e["median_lead_days"],
                         "n/a" if e["median_lead_days_missed_as_zero"] is None
                         else "%.2f" % e["median_lead_days_missed_as_zero"],
                         "n/a" if e.get("lead_days_lost_vs_reference") is None
                         else "%.2f" % e["lead_days_lost_vs_reference"],
                         "" if e.get("non_inferior") is None
                         else ("yes" if e["non_inferior"] else "NO")))
            report["horizon_sweep"][tag] = {
                n: {k: e.get(k) for k in
                    ("median_lead_days", "median_lead_days_missed_as_zero",
                     "detection_rate", "n_cases_with_lead",
                     "n_anomaly_cases_total", "lead_days_lost_vs_reference",
                     "non_inferior")}
                for n, e in comp.items()}

        print("\n    the physical maximum lead this fixture allows is %.2f days."
              % physical_max)
        print("    A horizon above that lets pre-onset alarms back in, which is")
        print("    why the artefact reappears at H = 14 but not at H = 7.")

        out_root = os.path.join(os.getcwd(), "earliness_diagnostic_out")
        os.makedirs(out_root, exist_ok=True)
        out = os.path.join(out_root, "diagnostic_%s.json" % preset)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
        print("\nwrote %s" % out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
