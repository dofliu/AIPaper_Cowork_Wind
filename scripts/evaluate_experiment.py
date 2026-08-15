#!/usr/bin/env python3
"""
Experiment evaluation — puts every method on the same ruler.

WHY THIS EXISTS SEPARATELY
--------------------------
Each method emits its own natural output: our layer emits a per-bin
p-value, W1-ACAS emits beta, ACI and DtACI emit a point alarm. Comparing
those directly would compare their output conventions as much as their
behaviour. This module takes whatever each produces, converts it to a
common point-exceedance series, and then applies the SAME downstream rules
to all of them:

  * the work-order rule, 6 exceedances within 18 points
  * regime binning for the per-bin false-alarm rate
  * the same rolling window W for the windowed deviation
  * the same event windows for earliness

That last point matters more than it looks. A baseline that alarms on
single points would appear to detect earlier than a method that requires a
work order, purely because of the alarm convention. Applying 6-of-18 to
every method removes that artefact. If a baseline is later reported
without it, the comparison is not the one this file produces.

METRICS
-------
worst_bin_deviation   max over regime bins of |FAR - alpha|, on NORMAL cases
                      only. The primary metric: what a marginal method
                      cannot see. Faulted cases are excluded from every
                      false-alarm figure, since an alarm there is a
                      detection rather than a false alarm.
marginal_deviation    |FAR - alpha| pooled. What a marginal method
                      optimises. Reported alongside so the gap is visible.
rolling_deviation     max |FAR - alpha| over rolling windows of W points.
median_lead_days      median detection lead time on ANOMALY cases only,
                      measured from the first work-order alarm to
                      event_start. Reported ONLY over cases the method
                      actually detected -- always read it next to
                      detection_rate, never on its own.
detection_rate        fraction of ANOMALY cases on which the method raised
                      a work-order alarm at all. A median lead time over
                      the one case a method happened to catch is not
                      comparable with a median over all of them, and
                      without this column the table cannot show the
                      difference.
median_lead_missed_0  same median with a missed detection scored as zero
                      days of warning, which is what a fault you never
                      alarm on actually gives you. Parameter-free, and
                      computed over a denominator common to every method.
non_inferiority       lead-time loss against a reference method, checked
                      against the signed-off margin of 2 days.

THE DETECTION HORIZON, AND WHY IT IS NOT DEFAULTED
--------------------------------------------------
Lead time as defined above is unbounded below: it is event_start minus the
first alarm, whenever that alarm falls. A method that alarms early and
often therefore harvests lead time from alarms raised before the fault
existed, and the metric records that as superb early warning.

This is not hypothetical. scripts/diagnose_earliness_gap.py builds a
fixture where the true ramp index is known, and finds the static reference
taking 6.11 of its 16.53 reported days from an alarm raised 880 steps
BEFORE the fault began, with ACI taking 8.28 of 18.70 the same way. On
CARE the physical onset is unknown, so nothing would have flagged it.

--detection-horizon-days H makes an alarm count as a detection only if it
falls within H days before event_start; anything earlier is a false alarm,
not early warning. H is a new evaluation parameter and is therefore NOT
defaulted: unset, the evaluator keeps the previous unbounded behaviour and
records detection_horizon_days: null plus an explicit caveat in the
summary, so an unbounded run can never be mistaken for a bounded one.
Choosing H is a decision for the PI, not for this file.

WHAT IS NOT HERE
----------------
CARE's own score and Reliability metrics. Their definitions are in the CARE
To Compare paper, which this project has not read. They are named in the
evaluation contract, and inventing them would be worse than reporting them
missing -- the same position as CARE's adaptive threshold baseline.

USAGE
-----
    python3 evaluate_experiment.py \\
        --scores-dir ./scores_MD_2022_run1 \\
        --wind-col   wind_speed_3_avg \\
        --timestamp-col time_stamp \\
        --g3-case-metadata ./manifest_out/g3_case_metadata.csv \\
        --event-info-root  /path/to/extracted_care_v6 \\
        --alpha 0.01 \\
        --method "ours=./rcc_MD_2022_a001:p_value:pvalue" \\
        --method "w1acas=./w1acas_MD_2022:beta:pvalue" \\
        --method "aci=./baselines_MD_2022_a001:aci_alarm:alarm" \\
        --method "dtaci=./baselines_MD_2022_a001:dtaci_alarm:alarm" \\
        --method "static=./baselines_MD_2022_a001:static_split_conformal_alarm:alarm" \\
        --reference static \\
        --output-dir ./evaluation_MD_2022_a001

Each --method is NAME=DIR:COLUMN:MODE, where MODE is `pvalue` (exceed when
the column is <= alpha) or `alarm` (exceed when the column is 1).

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import json
import math
import os
import statistics
import sys
from collections import deque
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_conditional_calibration as R  # noqa: E402

EVAL_VERSION = "eval-v1.1"
NON_INFERIORITY_MARGIN_DAYS = 2.0     # signed-off, parameter protocol v1.0

MISSING_METRICS = {
    "care_score": {"status": "NOT_IMPLEMENTED",
                   "reason": "definition is in the CARE To Compare paper, unread"},
    "care_reliability": {"status": "NOT_IMPLEMENTED",
                         "reason": "definition is in the CARE To Compare paper, unread"},
}

TIMESTAMP_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]


def parse_ts(raw):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def to_float(raw):
    if raw is None or raw == "":
        return None
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def sniff_delimiter(path):
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            head = f.readline()
    except OSError:
        return ","
    best, count = ",", -1
    for d in (",", ";", "\t", "|"):
        n = head.count(d)
        if n > count:
            best, count = d, n
    return best


def load_event_info(root):
    """{case_id: {label, start, end, description}} keyed by event_id, which is
    one row per case on this archive."""
    events = {}
    for path in sorted(glob.glob(os.path.join(root, "**", "event_info.csv"),
                                 recursive=True)):
        delimiter = sniff_delimiter(path)
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                with open(path, newline="", encoding=encoding) as f:
                    rows = list(csv.DictReader(f, delimiter=delimiter))
                break
            except (UnicodeDecodeError, OSError):
                rows = None
        if not rows:
            continue
        for r in rows:
            key = (r.get("event_id") or "").strip()
            if not key:
                continue
            events[key] = {
                "label": (r.get("event_label") or "").strip().lower(),
                "start": parse_ts(r.get("event_start")),
                "end": parse_ts(r.get("event_end")),
                "description": (r.get("event_description") or "").strip(),
                "asset": (r.get("asset") or r.get("asset_id") or "").strip(),
            }
    return events


def work_order_alarms(exceeds, of=R.ALARM_OF, window=R.ALARM_WINDOW):
    """The common downstream rule, applied identically to every method."""
    history = deque(maxlen=window)
    out = []
    active = False
    for e in exceeds:
        if e is None:
            out.append(None)
            continue
        history.append(e)
        if len(history) == window:
            active = sum(history) >= of
        out.append(active)
    return out


def read_reference(scores_dir, wind_col, timestamp_col, score_glob):
    """Timestamps and wind speeds per case, from the score stream itself."""
    reference = {}
    for path in sorted(glob.glob(os.path.join(scores_dir, score_glob))):
        case_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            if wind_col not in header:
                reference[case_id] = {"error": "wind column %r missing" % wind_col}
                continue
            rows = list(reader)
        reference[case_id] = {
            "timestamps": [parse_ts(r.get(timestamp_col)) for r in rows],
            "winds": [to_float(r.get(wind_col)) for r in rows],
        }
    return reference


def read_method(directory, column, mode, alpha):
    """Point exceedances per case for one method."""
    out = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        case_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if column not in (reader.fieldnames or []):
                out[case_id] = None
                continue
            values = [r.get(column) for r in reader]
        exceeds = []
        for v in values:
            f = to_float(v)
            if f is None:
                exceeds.append(None)
            elif mode == "pvalue":
                exceeds.append(1 if f <= alpha else 0)
            else:
                exceeds.append(1 if f >= 0.5 else 0)
        out[case_id] = exceeds
    return out


def evaluate_case(exceeds, timestamps, winds, alpha, window, event,
                  detection_horizon_days=None):
    """Metrics for one case under one method.

    detection_horizon_days bounds how early an alarm may be and still count
    as a detection. Unset means unbounded, which is the historical
    behaviour and lets an alarm raised long before the fault be scored as
    early warning -- see the module docstring."""
    alarms = work_order_alarms(exceeds)

    records = []
    for e, w in zip(exceeds, winds):
        records.append({"regime_bin": R.regime_of(w), "exceed": e})
    far = R.per_bin_false_alarm_rates(records, alpha)
    rolling = R.rolling_window_deviation(records, alpha, window)

    lead_days = None
    first_alarm = None
    first_alarm_any = None
    pre_window_alarm = False
    has_event_window = bool(event and event.get("start"))
    if has_event_window:
        horizon_start = None
        if detection_horizon_days is not None:
            horizon_start = event["start"] - timedelta(days=detection_horizon_days)

        for a, ts in zip(alarms, timestamps):
            if not a or ts is None:
                continue
            if first_alarm_any is None:
                first_alarm_any = ts
            # Outside the horizon this alarm is a false alarm, not early
            # warning; keep looking for one inside it rather than crediting
            # this one and stopping.
            if horizon_start is not None and ts < horizon_start:
                pre_window_alarm = True
                continue
            first_alarm = ts
            break

        if first_alarm is not None:
            delta = (event["start"] - first_alarm).total_seconds() / 86400.0
            lead_days = delta          # positive = alarmed before the event

    return {
        "worst_bin_deviation": far["worst_bin_deviation"],
        "marginal_deviation": far["marginal_deviation"],
        "per_bin_far": {k: v.get("far") for k, v in far["per_bin"].items()},
        "rolling_max_deviation": rolling.get("max_deviation"),
        "n_work_order_alarm_points": sum(1 for a in alarms if a),
        "first_alarm": first_alarm.isoformat() if first_alarm else None,
        "first_alarm_any": first_alarm_any.isoformat() if first_alarm_any else None,
        "alarm_before_detection_horizon": pre_window_alarm,
        "has_event_window": has_event_window,
        "lead_days": lead_days,
    }


def run(args):
    methods = {}
    for spec in args.method:
        try:
            name, rest = spec.split("=", 1)
            directory, column, mode = rest.rsplit(":", 2)
        except ValueError:
            print("bad --method %r; expected NAME=DIR:COLUMN:MODE" % spec, file=sys.stderr)
            return 3
        if mode not in ("pvalue", "alarm"):
            print("bad mode %r in %r" % (mode, spec), file=sys.stderr)
            return 3
        methods[name] = (directory, column, mode)

    reference = read_reference(args.scores_dir, args.wind_col,
                               args.timestamp_col, args.score_glob)
    events = load_event_info(args.event_info_root) if args.event_info_root else {}

    labels = {}
    if args.g3_case_metadata and os.path.isfile(args.g3_case_metadata):
        with open(args.g3_case_metadata, newline="", encoding="utf-8",
                  errors="replace") as f:
            for row in csv.DictReader(f):
                labels[row["case_id"]] = row.get("label")

    excluded = set(x.strip() for x in (args.exclude_cases or "").split(",") if x.strip())

    per_method = {}
    for name, (directory, column, mode) in methods.items():
        series = read_method(directory, column, mode, args.alpha)
        per_case = {}
        for case_id, exceeds in series.items():
            if case_id in excluded:
                continue
            ref = reference.get(case_id)
            if not ref or "error" in ref:
                per_case[case_id] = {"error": "no reference stream"}
                continue
            if exceeds is None:
                per_case[case_id] = {"error": "column %r missing" % column}
                continue
            n = min(len(exceeds), len(ref["timestamps"]))
            per_case[case_id] = evaluate_case(
                exceeds[:n], ref["timestamps"][:n], ref["winds"][:n],
                args.alpha, args.window, events.get(case_id),
                detection_horizon_days=args.detection_horizon_days)
            per_case[case_id]["label"] = labels.get(case_id)

        # The research question is explicit about which cases each metric
        # belongs to: false-alarm deviation on NORMAL cases, earliness on the
        # held-out ANOMALY cases. Computing a false-alarm rate over a faulted
        # case counts true detections as false alarms, and penalises exactly
        # the method that detected the fault -- an earlier version of this
        # evaluator did that and made the best detector look worst.
        def _far_pool(key):
            return [v[key] for v in per_case.values()
                    if isinstance(v, dict) and v.get(key) is not None
                    and (v.get("label") == "normal" or not labels)]

        worst = _far_pool("worst_bin_deviation")
        marg = _far_pool("marginal_deviation")
        # Every anomaly case with an event window is a case this method was
        # asked to detect, whether or not it managed to. Keeping the two
        # counts apart is the whole point: median_lead_days is a median over
        # the detected ones, so on its own it rewards a method for missing
        # the hard cases -- the ones it misses simply leave the pool. A
        # method that caught 1 of 6 faults once out-ranked one that caught
        # 6 of 6 on exactly this arithmetic.
        anomaly_cases = [v for v in per_case.values()
                         if isinstance(v, dict) and "error" not in v
                         and (v.get("label") == "anomaly" or not labels)]
        # Only cases carrying an event window can be detected early or late
        # at all; one without a window is outside this metric, not a miss.
        detectable = [v for v in anomaly_cases if v.get("has_event_window")]
        leads = [v["lead_days"] for v in detectable
                 if v.get("lead_days") is not None]
        n_anomaly = len(detectable)
        # A fault never alarmed on gives zero days of warning. Scoring a miss
        # as 0 puts every method on one denominator without inventing a
        # parameter; it is reported next to, not instead of, the median over
        # detections.
        leads_missed_zero = list(leads) + [0.0] * max(0, n_anomaly - len(leads))
        n_pre_horizon = sum(1 for v in detectable
                            if v.get("alarm_before_detection_horizon"))

        per_method[name] = {
            "n_cases": len(per_case),
            "n_normal_cases_for_far": len(worst),
            "n_anomaly_cases_for_earliness": n_anomaly,
            "metric_scoping_note": (
                "false-alarm deviations are computed on NORMAL cases only and "
                "earliness on ANOMALY cases only, per the research question. An "
                "alarm on a faulted case is a detection, not a false alarm."),
            "earliness_denominator_note": (
                "median_lead_days is a median over DETECTED cases only. Read it "
                "with detection_rate; a high median over few detections is not "
                "comparable with a lower median over all of them."),
            "mean_worst_bin_deviation": (sum(worst) / len(worst)) if worst else None,
            "mean_marginal_deviation": (sum(marg) / len(marg)) if marg else None,
            "median_lead_days": statistics.median(leads) if leads else None,
            "median_lead_days_missed_as_zero": (
                statistics.median(leads_missed_zero) if leads_missed_zero else None),
            "n_cases_with_lead": len(leads),
            "n_anomaly_cases_total": n_anomaly,
            "detection_rate": (len(leads) / n_anomaly) if n_anomaly else None,
            "n_cases_alarmed_before_detection_horizon": n_pre_horizon,
            "per_case": per_case,
        }

    # Non-inferiority on earliness against the reference method.
    ref_name = args.reference
    comparison = {}
    ref_median = (per_method.get(ref_name) or {}).get("median_lead_days")
    for name, block in per_method.items():
        entry = {
            "mean_worst_bin_deviation": block["mean_worst_bin_deviation"],
            "mean_marginal_deviation": block["mean_marginal_deviation"],
            "median_lead_days": block["median_lead_days"],
            "median_lead_days_missed_as_zero": block["median_lead_days_missed_as_zero"],
            "detection_rate": block["detection_rate"],
            "n_cases_with_lead": block["n_cases_with_lead"],
            "n_anomaly_cases_total": block["n_anomaly_cases_total"],
            "n_cases_alarmed_before_detection_horizon":
                block["n_cases_alarmed_before_detection_horizon"],
        }
        if ref_median is not None and block["median_lead_days"] is not None:
            loss = ref_median - block["median_lead_days"]
            entry["lead_days_lost_vs_reference"] = loss
            entry["non_inferior"] = loss <= NON_INFERIORITY_MARGIN_DAYS
            entry["non_inferiority_margin_days"] = NON_INFERIORITY_MARGIN_DAYS
            # The verdict compares two medians taken over different case
            # sets whenever the detection rates differ. Say so on the
            # record rather than letting the yes/no stand unqualified.
            ref_rate = (per_method.get(ref_name) or {}).get("detection_rate")
            this_rate = block["detection_rate"]
            if ref_rate is not None and this_rate is not None and ref_rate != this_rate:
                entry["verdict_caveat"] = (
                    "detection rates differ (%s %.2f vs %s %.2f); the two "
                    "medians are taken over different case sets and the "
                    "verdict is not a like-for-like comparison"
                    % (name, this_rate, ref_name, ref_rate))
        comparison[name] = entry

    os.makedirs(args.output_dir, exist_ok=True)
    summary = {
        "eval_version": EVAL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "alpha": args.alpha,
        "window_W": args.window,
        "work_order_rule": "%d of last %d, applied identically to every method"
                           % (R.ALARM_OF, R.ALARM_WINDOW),
        "reference_method": ref_name,
        "detection_horizon_days": args.detection_horizon_days,
        "detection_horizon_note": (
            "UNSET: lead time is unbounded and an alarm raised before the fault "
            "began still counts as early warning. Not a safe basis for a "
            "non-inferiority claim; see the module docstring."
            if args.detection_horizon_days is None else
            "an alarm earlier than this many days before event_start is a false "
            "alarm, not a detection"),
        "excluded_cases": sorted(excluded),
        "missing_metrics": MISSING_METRICS,
        "comparison": comparison,
        "per_method": per_method,
        "cli_invocation": " ".join(sys.argv),
    }
    with open(os.path.join(args.output_dir, "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = ["| method | worst-bin dev | marginal dev | detected | "
             "median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |",
             "|---|---|---|---|---|---|---|---|"]
    for name, e in sorted(comparison.items(),
                          key=lambda kv: (kv[1]["mean_worst_bin_deviation"] is None,
                                          kv[1]["mean_worst_bin_deviation"])):
        detected = ("n/a" if e.get("n_anomaly_cases_total") in (None, 0)
                    else "%d/%d (%.0f%%)" % (e["n_cases_with_lead"],
                                             e["n_anomaly_cases_total"],
                                             100.0 * e["detection_rate"]))
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            name,
            "n/a" if e["mean_worst_bin_deviation"] is None else "%.4f" % e["mean_worst_bin_deviation"],
            "n/a" if e["mean_marginal_deviation"] is None else "%.4f" % e["mean_marginal_deviation"],
            detected,
            "n/a" if e["median_lead_days"] is None else "%.2f" % e["median_lead_days"],
            "n/a" if e["median_lead_days_missed_as_zero"] is None else "%.2f" % e["median_lead_days_missed_as_zero"],
            "n/a" if e.get("lead_days_lost_vs_reference") is None else "%.2f" % e["lead_days_lost_vs_reference"],
            "" if e.get("non_inferior") is None else ("yes" if e["non_inferior"] else "NO")))
    table = "\n".join(lines)

    if args.detection_horizon_days is None:
        horizon_note = (
            "**Detection horizon: UNSET.** Lead time is unbounded, so an alarm "
            "raised before the fault began is still counted as early warning. "
            "Run with --detection-horizon-days to bound it. See "
            "scripts/diagnose_earliness_gap.py for a fixture where this "
            "inflates a baseline by 6.11 of its 16.53 reported days.\n")
    else:
        horizon_note = (
            "Detection horizon: %.2f days. An alarm earlier than that before "
            "event_start is counted as a false alarm, not a detection.\n"
            % args.detection_horizon_days)

    with open(os.path.join(args.output_dir, "comparison.md"), "w", encoding="utf-8") as f:
        f.write("# Comparison (alpha = %s)\n\n%s\n\n"
                "Work-order rule %d-of-%d applied identically to every method.\n\n"
                "%s\n"
                "`median lead (d)` is a median over DETECTED cases only; read it "
                "with the `detected` column. `lead, miss=0` scores a missed fault "
                "as zero days of warning, over one denominator for every method.\n\n"
                "CARE score and Reliability are not implemented; see missing_metrics.\n"
                % (args.alpha, table, R.ALARM_OF, R.ALARM_WINDOW, horizon_note))

    print("\n" + table)
    print("\nWrote %s" % args.output_dir, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores-dir", required=True,
                    help="Original score stream, used for timestamps and wind speed")
    ap.add_argument("--wind-col", required=True)
    ap.add_argument("--timestamp-col", default="time_stamp")
    ap.add_argument("--score-glob", default="*.csv")
    ap.add_argument("--g3-case-metadata")
    ap.add_argument("--event-info-root",
                    help="Extracted CARE v6 root; event_info.csv supplies the event "
                         "windows earliness is measured against")
    ap.add_argument("--alpha", type=float, default=0.01)
    ap.add_argument("--window", type=int, default=1440)
    ap.add_argument("--method", action="append", required=True,
                    metavar="NAME=DIR:COLUMN:MODE")
    ap.add_argument("--reference", default="static",
                    help="Method to measure earliness non-inferiority against")
    ap.add_argument("--detection-horizon-days", type=float, default=None,
                    help="an alarm counts as a detection only within this many "
                         "days before event_start; earlier alarms are false "
                         "alarms. Unset = unbounded (previous behaviour), which "
                         "credits pre-onset alarms as early warning. Not "
                         "defaulted on purpose: this is a ratifiable parameter.")
    ap.add_argument("--exclude-cases",
                    help="Comma-separated case_ids to drop (D1/D6 exclusion plan)")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
