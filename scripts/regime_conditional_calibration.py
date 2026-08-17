#!/usr/bin/env python3
"""
Regime-conditional online calibration — this project's proposed method.

Everything else in scripts/ is scaffolding or a baseline. This is the
contribution.

THE CLAIM
---------
A calibration layer wrapped around a frozen anomaly score, using no event
labels, that holds the false-alarm rate inside each wind-speed operating
regime rather than only on average, and does so without giving up early
warning.

Why "rather than only on average" is the whole point: a detector can be
perfectly calibrated marginally and still over-alarm badly at high wind
while under-alarming at low wind, because the score distribution differs by
regime. Marginal methods have no mechanism to notice. W1-ACAS (ICLR 2026)
minimises E_{a~U[0,1]}|P(beta<=a) - a|, which is uniformity over the
significance level, not conditioning on operating state; its own conclusion
lists contextual conditioning as future work.

FOUR MECHANISMS, ALL FROM THE SIGNED-OFF PROTOCOL
--------------------------------------------------
1. Regime binning. Wind speed is bucketed < 4 / 4-8 / 8-12 / >= 12 m/s
   (parameter protocol v1.0 section 3). Every point is calibrated against
   the history of ITS OWN bin, so a high-wind point is never judged against
   a low-wind reference.

2. Rolling per-bin window. Each bin keeps its own buffer of W = 1440 steps.
   The window is bin-local: a bin that is rarely visited keeps a longer
   wall-clock history, which is what makes the rare regimes calibratable at
   all. Below the minimum sample count the bin reports UNCALIBRATED rather
   than a p-value it cannot support -- that is the D4 identifiability rule
   applied online instead of only at design time.

3. Freeze-on-Alert. While an alarm stands, the calibration buffers stop
   absorbing new scores. Degradation is progressive; a calibrator that
   keeps learning through a fault re-baselines onto the fault and the
   alarm dissolves. This is the self-masking hazard the R15 discussion
   settled on, and it is exactly the behaviour W1-ACAS reports as a
   feature ("quickly adapts to the new anomalous distribution; this helps
   minimise the number of alarms") -- correct for signal monitoring,
   wrong for predictive maintenance.

4. Work-order alarm semantics. A raw point exceedance is not an alarm: the
   rule is 6 exceedances within the last 18 points, matching what a wind
   farm actually dispatches on.

OUTPUT
------
Per timestamp: regime bin, per-bin p-value, point exceedance, work-order
alarm state, and whether the calibrator was frozen. Plus per-bin
false-alarm rates and the worst-bin deviation, which is the paper's primary
metric.

USAGE
-----
    python3 regime_conditional_calibration.py \\
        --score-dir  ./scores_MD_2022_run1 \\
        --output-dir ./rcc_MD_2022_a001 \\
        --score-col  anomaly_score \\
        --wind-col   wind_speed_3_avg \\
        --timestamp-col time_stamp \\
        [--alpha 0.01] [--window 1440] [--min-bin-samples 500]

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import fnmatch
import heapq
import json
import math
import os
import sys
from collections import deque
from datetime import datetime, timezone

METHOD_VERSION = "rcc-v1.0"

# Parameter protocol v1.0 section 3, signed off 2026-08-11.
REGIME_BINS = [
    ("bin1_lt_4", lambda v: v < 4.0),
    ("bin2_4_8", lambda v: 4.0 <= v < 8.0),
    ("bin3_8_12", lambda v: 8.0 <= v < 12.0),
    ("bin4_ge_12", lambda v: v >= 12.0),
]
BIN_NAMES = [name for name, _ in REGIME_BINS]

DEFAULT_ALPHA = 0.01
DEFAULT_WINDOW = 1440            # W, signed off
DEFAULT_MIN_BIN_SAMPLES = 500    # D4 minimum per regime cell, signed off
ALARM_OF = 6                     # work-order rule: 6 of the last 18
ALARM_WINDOW = 18

UNCALIBRATED = None


def to_float(raw):
    if raw is None:
        return None
    v = raw.strip() if isinstance(raw, str) else raw
    if v == "" or (isinstance(v, str) and v.lower() in ("nan", "na", "n/a", "null")):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        if isinstance(v, str) and "," in v:
            try:
                f = float(v.replace(",", ".", 1))
            except ValueError:
                return None
        else:
            return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def regime_of(wind_speed):
    if wind_speed is None:
        return None
    for name, test in REGIME_BINS:
        if test(wind_speed):
            return name
    return None


def conformal_p_value(buffer_scores, score):
    """Standard conformal p-value against this bin's history:
        (#{history > score} + 1) / (n + 1)
    The +1 in both places is the finite-sample correction; it also floors
    the p-value at 1/(n+1), which is why a bin needs enough samples before
    a small alpha is even expressible."""
    n = len(buffer_scores)
    if n == 0:
        return UNCALIBRATED
    above = sum(1 for s in buffer_scores if s > score)
    return (above + 1.0) / (n + 1.0)


ABSORPTION_POLICIES = ("freeze", "none", "bin_local", "gated",
                       "winsor_alpha", "winsor_max")

# The ratified policy. Everything else on this list is an opt-in ablation and
# must be named explicitly; nothing here changes what a default run does.
RATIFIED_ABSORPTION = "freeze"


def winsorising_cap(buffer_scores, alpha):
    """Largest value in the buffer that would not itself be an exceedance.

    Exceedance is (above + 1) / (n + 1) <= alpha, so a point with `above`
    strictly-greater neighbours exceeds iff above <= alpha*(n+1) - 1. The
    j-th largest element has above = j - 1, so the largest NON-exceeding
    element is the (k + 2)-th largest, with k = floor(alpha*(n+1) - 1).

    Returns None when the buffer is too small for that element to exist, in
    which case the caller must not winsorise -- capping against a threshold
    the buffer cannot express would silently invent one.
    """
    n = len(buffer_scores)
    if n == 0:
        return None
    k = int(math.floor(alpha * (n + 1.0) - 1.0))
    idx = k + 1                      # 0-based index of the (k+2)-th largest
    if idx < 0 or idx >= n:
        return None
    return heapq.nlargest(idx + 1, buffer_scores)[idx]


def run_stream(scores, winds, alpha, window, min_bin_samples,
               freeze_on_alert=True, alarm_of=ALARM_OF, alarm_window=ALARM_WINDOW,
               absorption=None):
    """The method, over one case. Returns (records, diagnostics).

    Each record is a dict per timestamp. Points whose bin is not yet
    calibratable carry p_value None and take no part in any rate.

    `absorption` selects what happens to the reference buffers while a work
    order alarm stands. It defaults to the ratified Freeze-on-Alert, and
    `freeze_on_alert=False` keeps meaning the existing "none" ablation, so
    every existing caller behaves exactly as before.

      freeze      ratified: no bin absorbs anything while an alarm stands.
      none        ablation: absorb regardless. Measures self-masking.
      bin_local   ablation: withhold absorption only in bins that fed an
                  exceedance into the window that raised the alarm. Tests
                  whether the alarm is freezing bins that never saw it.
      gated       ablation: absorb only points that did not themselves
                  exceed. The "partial absorption" direction, in its most
                  literal reading.
      winsor_alpha
                  ablation: absorb every point, but cap an exceeding point at
                  the bin's current non-exceeding maximum, i.e. the alpha
                  threshold itself. No free parameter -- the cap is the alpha
                  the protocol already fixes. Predicted to lock in anyway:
                  once the buffer fills with capped values the threshold is
                  its own fixed point. Included because that prediction is
                  worth measuring rather than asserting.

      winsor_max  ablation: same, but cap at the bin's running MAXIMUM instead
                  of its alpha threshold. The difference is the recovery
                  envelope. A benign operating shift usually stays inside the
                  historical envelope, so its points enter unmodified and the
                  buffer recalibrates; a developing fault leaves the envelope,
                  so its magnitude is clipped and can never lift the
                  threshold onto itself. The discriminator is physical --
                  has the machine gone somewhere it has never been -- and it
                  costs no new parameter.

    Only the alarm-time behaviour differs. Outside an alarm every policy
    absorbs the raw score, which is what makes this a drop-in comparison
    against the ratified one rather than five different methods.
    """
    if absorption is None:
        absorption = RATIFIED_ABSORPTION if freeze_on_alert else "none"
    if absorption not in ABSORPTION_POLICIES:
        raise ValueError("unknown absorption policy %r; expected one of %s"
                         % (absorption, ", ".join(ABSORPTION_POLICIES)))

    buffers = {name: deque(maxlen=window) for name in BIN_NAMES}
    exceed_history = deque(maxlen=alarm_window)
    # Which bin each exceedance in the alarm window came from. Only bin_local
    # reads it, but it is maintained unconditionally so the two policies see
    # identical state up to the branch below.
    bin_history = deque(maxlen=alarm_window)
    records = []
    alarm_active = False
    n_frozen_steps = 0
    n_winsorised = 0
    n_gated_out = 0

    for score, wind in zip(scores, winds):
        bin_name = regime_of(wind)
        record = {"regime_bin": bin_name, "score": score, "wind_speed": wind,
                  "p_value": UNCALIBRATED, "exceed": None,
                  "work_order_alarm": alarm_active, "frozen": alarm_active,
                  "bin_n": 0}

        if score is None or bin_name is None:
            records.append(record)
            continue

        buffer_scores = buffers[bin_name]
        record["bin_n"] = len(buffer_scores)
        exceed = None

        if len(buffer_scores) >= min_bin_samples:
            p = conformal_p_value(buffer_scores, score)
            record["p_value"] = p
            exceed = 1 if p <= alpha else 0
            record["exceed"] = exceed
            exceed_history.append(exceed)
            bin_history.append(bin_name)
            if len(exceed_history) == alarm_window:
                alarm_active = sum(exceed_history) >= alarm_of
            record["work_order_alarm"] = alarm_active

        # While an alarm stands the reference is protected, so that a
        # progressive fault cannot be absorbed as the new normal. What
        # "protected" means is the policy under test.
        admitted = score
        if not alarm_active:
            frozen = False
        elif absorption == "freeze":
            frozen = True
        elif absorption == "none":
            frozen = False
        elif absorption == "bin_local":
            trigger_bins = set(b for b, e in zip(bin_history, exceed_history) if e == 1)
            frozen = bin_name in trigger_bins
        elif absorption == "gated":
            frozen = exceed == 1
            if frozen:
                n_gated_out += 1
        else:   # winsor_alpha | winsor_max
            # Only a point the calibrator itself judged to be an exceedance is
            # ever clipped. A bin still below the minimum sample count has no
            # verdict to act on, so its points enter untouched -- clipping
            # against a threshold that bin cannot yet express would be the
            # calibrator guessing, which rule D4 exists to forbid.
            if exceed != 1:
                cap = None
            elif absorption == "winsor_alpha":
                cap = winsorising_cap(buffer_scores, alpha)
            else:
                cap = max(buffer_scores) if buffer_scores else None
            if cap is not None and score > cap:
                admitted = cap
                n_winsorised += 1
            frozen = False

        record["frozen"] = frozen
        if not frozen:
            buffer_scores.append(admitted)
        else:
            n_frozen_steps += 1

        records.append(record)

    diagnostics = {
        "n_rows": len(records),
        "n_calibrated": sum(1 for r in records if r["p_value"] is not None),
        "n_uncalibrated_warmup": sum(
            1 for r in records
            if r["p_value"] is None and r["regime_bin"] is not None and r["score"] is not None),
        "n_frozen_steps": n_frozen_steps,
        "absorption_policy": absorption,
        "n_winsorised_admissions": n_winsorised,
        "n_gated_out": n_gated_out,
        "final_bin_sizes": {name: len(buffers[name]) for name in BIN_NAMES},
    }
    return records, diagnostics


def per_bin_false_alarm_rates(records, alpha):
    """False-alarm rate inside each regime bin, plus the worst-bin deviation.

    Only calibrated points count. A bin that never reached the minimum
    sample count reports None rather than 0, because "no alarms because we
    could not judge" is not the same as "no alarms because none were due"."""
    rates = {}
    for name in BIN_NAMES:
        points = [r for r in records if r["regime_bin"] == name and r["exceed"] is not None]
        if not points:
            rates[name] = {"n": 0, "far": None,
                           "note": "bin never reached the minimum sample count"}
            continue
        far = sum(r["exceed"] for r in points) / len(points)
        rates[name] = {"n": len(points), "far": far, "deviation": abs(far - alpha)}

    observed = [v["deviation"] for v in rates.values() if v.get("deviation") is not None]
    all_points = [r for r in records if r["exceed"] is not None]
    marginal = (sum(r["exceed"] for r in all_points) / len(all_points)) if all_points else None

    return {
        "alpha": alpha,
        "per_bin": rates,
        "marginal_far": marginal,
        "marginal_deviation": abs(marginal - alpha) if marginal is not None else None,
        "worst_bin_deviation": max(observed) if observed else None,
        "n_bins_evaluable": len(observed),
        "primary_metric_note": (
            "worst_bin_deviation is the paper's primary metric. marginal_deviation "
            "is what a non-conditional method optimises; the gap between them is the "
            "quantity this method exists to close."),
    }


def rolling_window_deviation(records, alpha, window):
    """Max |FAR - alpha| over rolling windows of `window` calibrated points.
    The signed-off secondary metric."""
    exceeds = [r["exceed"] for r in records if r["exceed"] is not None]
    if len(exceeds) < window:
        return {"n_windows": 0, "max_deviation": None,
                "note": "fewer calibrated points than one window"}
    running = sum(exceeds[:window])
    worst = abs(running / window - alpha)
    for i in range(window, len(exceeds)):
        running += exceeds[i] - exceeds[i - window]
        worst = max(worst, abs(running / window - alpha))
    return {"n_windows": len(exceeds) - window + 1, "max_deviation": worst,
            "window": window}


def process_dir(args):
    paths = sorted(os.path.join(args.score_dir, fn)
                   for fn in os.listdir(args.score_dir)
                   if fnmatch.fnmatch(fn, args.score_glob))
    if not paths:
        print("no score files matched %r" % args.score_glob, file=sys.stderr)
        return 3
    os.makedirs(args.output_dir, exist_ok=True)

    report = {}
    for i, path in enumerate(paths, 1):
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing = [c for c in (args.score_col, args.wind_col) if c not in header]
            if missing:
                report[os.path.splitext(os.path.basename(path))[0]] = {
                    "error": "columns not in header: %s" % missing,
                    "header_sample": header[:15]}
                continue
            rows = list(reader)

        scores = [to_float(r.get(args.score_col)) for r in rows]
        winds = [to_float(r.get(args.wind_col)) for r in rows]
        records, diagnostics = run_stream(
            scores, winds, args.alpha, args.window, args.min_bin_samples,
            freeze_on_alert=not args.no_freeze_on_alert,
            absorption=args.absorption)

        case_id = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(args.output_dir, case_id + ".csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "wind_speed", "regime_bin", "score",
                             "p_value", "exceed", "work_order_alarm", "frozen"])
            for row, rec in zip(rows, records):
                writer.writerow([
                    row.get(args.timestamp_col, ""),
                    "" if rec["wind_speed"] is None else rec["wind_speed"],
                    rec["regime_bin"] or "",
                    "" if rec["score"] is None else rec["score"],
                    "" if rec["p_value"] is None else "%.10g" % rec["p_value"],
                    "" if rec["exceed"] is None else rec["exceed"],
                    1 if rec["work_order_alarm"] else 0,
                    1 if rec["frozen"] else 0,
                ])

        report[case_id] = {
            "diagnostics": diagnostics,
            "false_alarm_rates": per_bin_false_alarm_rates(records, args.alpha),
            "rolling_window": rolling_window_deviation(records, args.alpha, args.window),
        }
        if i % 5 == 0 or i == len(paths):
            print("  %d/%d cases" % (i, len(paths)), flush=True)

    worst = [r["false_alarm_rates"]["worst_bin_deviation"] for r in report.values()
             if r.get("false_alarm_rates", {}).get("worst_bin_deviation") is not None]
    marg = [r["false_alarm_rates"]["marginal_deviation"] for r in report.values()
            if r.get("false_alarm_rates", {}).get("marginal_deviation") is not None]

    summary = {
        "method_version": METHOD_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "alpha": args.alpha, "window_W": args.window,
            "min_bin_samples": args.min_bin_samples,
            "regime_bins": BIN_NAMES,
            "work_order_rule": "%d of last %d" % (ALARM_OF, ALARM_WINDOW),
            "freeze_on_alert": not args.no_freeze_on_alert,
            "absorption_policy": (args.absorption if args.absorption is not None
                                  else (RATIFIED_ABSORPTION
                                        if not args.no_freeze_on_alert else "none")),
            "absorption_policy_is_ratified": (
                args.absorption in (None, RATIFIED_ABSORPTION)
                and not args.no_freeze_on_alert),
        },
        "parameter_source": "【已簽核】參數凍結協定 v1.0, 劉老師 2026-08-11",
        "n_cases": len(report),
        "mean_worst_bin_deviation": (sum(worst) / len(worst)) if worst else None,
        "mean_marginal_deviation": (sum(marg) / len(marg)) if marg else None,
        "per_case": report,
        "cli_invocation": " ".join(sys.argv),
    }
    with open(os.path.join(args.output_dir, "rcc_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nmean worst-bin deviation: %s" % summary["mean_worst_bin_deviation"])
    print("mean marginal deviation:  %s" % summary["mean_marginal_deviation"])
    print("Wrote %s" % args.output_dir, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--score-col", default="anomaly_score")
    ap.add_argument("--wind-col", required=True,
                    help="Wind speed column, needed for regime binning")
    ap.add_argument("--timestamp-col", default="time_stamp")
    ap.add_argument("--score-glob", default="*.csv")
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument("--min-bin-samples", type=int, default=DEFAULT_MIN_BIN_SAMPLES)
    ap.add_argument("--no-freeze-on-alert", action="store_true",
                    help="Ablation: disable Freeze-on-Alert to measure self-masking")
    ap.add_argument("--absorption", choices=ABSORPTION_POLICIES, default=None,
                    help=("Ablation: what the reference buffers do while an alarm "
                          "stands. Unset means the ratified '%s'. Any other value "
                          "is an unratified experiment and is recorded as such in "
                          "rcc_summary.json." % RATIFIED_ABSORPTION))
    args = ap.parse_args()
    if args.absorption is not None and args.no_freeze_on_alert:
        print("--absorption and --no-freeze-on-alert both set; they name the same "
              "knob and would contradict each other. Use --absorption none.",
              file=sys.stderr)
        return 2
    if not os.path.isdir(args.score_dir):
        print("score dir not found: %s" % args.score_dir, file=sys.stderr)
        return 3
    return process_dir(args)


if __name__ == "__main__":
    sys.exit(main())
