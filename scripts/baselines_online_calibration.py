#!/usr/bin/env python3
"""
Online calibration baselines: static split conformal, ACI, DtACI.

WHY THESE THREE
---------------
The evaluation contract compares our regime-conditional calibration against
static split conformal, ACI with a fixed step, DtACI, and CARE's own
adaptive threshold. W1-ACAS was added in R20 and lives in
baseline_w1_acas.py. This file supplies the first three; the fourth is
deliberately absent and the reason is recorded below.

All of them take a frozen scalar anomaly score stream and a target alarm
rate alpha, and return a per-timestamp threshold and alarm indicator. That
is the interface the project's metrics need: false-alarm rate per
wind-speed regime bin, and per rolling window of W = 1440 steps. It is
deliberately NOT a p-value interface -- ACI and DtACI track a single
adaptive level rather than producing a p-value per point, and pretending
otherwise would make the comparison inexact in our favour.

Consequence: each baseline is run once per target alpha. The signed-off
parameter protocol fixes alpha = 0.01 with 0.05 and 0.001 as secondary, so
that is three runs, not a sweep.

WHAT IS NOT HERE, AND WHY
--------------------------
CARE's own adaptive threshold is part of the baseline set and is NOT
implemented. Its definition is in the CARE To Compare paper, which this
session has not read; the archive ships a README that may describe it, but
nobody has extracted the definition. Guessing at a competitor's method and
then beating it would be worse than having no baseline at all. Use
--list-missing to see this recorded in machine-readable form.

CITATIONS
---------
ACI    Gibbs & Candes, "Adaptive conformal inference under distribution
       shift", NeurIPS 2021.
DtACI  Gibbs & Candes, "Conformal inference for online prediction with
       arbitrary distribution shifts", 2024.
Both are reimplemented from their published update rules, not author code.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import bisect
import csv
import fnmatch
import json
import math
import os
import sys
from collections import deque
from datetime import datetime, timezone

IMPLEMENTATION_VERSION = "online-baselines-v1.0"

# Not implemented, and recorded as such rather than approximated.
MISSING_BASELINES = {
    "care_adaptive_threshold": {
        "status": "NOT_IMPLEMENTED",
        "reason": ("The definition lives in the CARE To Compare paper, which has "
                   "not been read in this project. The archive's README.txt may "
                   "carry it; nobody has extracted it yet."),
        "blocking": "listed in the evaluation contract's baseline set",
        "how_to_unblock": ("Extract the adaptive-threshold definition from the CARE "
                           "paper or the archive README, record it verbatim in a "
                           "Drive doc, then implement against that text."),
    },
}


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


def _quantile_from_sorted(sorted_values, level):
    """Conformal quantile at the given level, with the finite-sample
    adjustment: the index is ceil(level * (n+1)) rather than level * n, and
    a level that lands past the end yields +inf -- meaning "never alarm",
    which is the correct conservative answer when the calibration set is too
    small to certify that level."""
    n = len(sorted_values)
    if n == 0:
        return float("inf")
    k = math.ceil(level * (n + 1))
    if k > n:
        return float("inf")
    if k < 1:
        k = 1
    return sorted_values[k - 1]


def static_split_conformal(scores, alpha, n_cal):
    """Calibrate once on the first n_cal scores, then never update."""
    calibration = sorted(s for s in scores[:n_cal] if s is not None)
    threshold = _quantile_from_sorted(calibration, 1.0 - alpha)
    thresholds, alarms = [], []
    for i, s in enumerate(scores):
        if i < n_cal or s is None:
            thresholds.append(None)
            alarms.append(None)
            continue
        thresholds.append(threshold)
        alarms.append(1 if s > threshold else 0)
    return thresholds, alarms, {"fixed_threshold": threshold,
                                "n_calibration": len(calibration)}


def aci(scores, alpha, gamma, n_cal, window=None):
    """Adaptive Conformal Inference (Gibbs & Candes 2021).

    Tracks an adaptive level alpha_t, updated by the realised error:
        alpha_{t+1} = alpha_t + gamma * (alpha - err_t),
        err_t = 1[S_t > q_t],  q_t = Quantile_{1-alpha_t}(calibration)

    alpha_t is clipped to [0,1]; at alpha_t <= 0 the quantile is +inf and
    the detector never alarms, at alpha_t >= 1 it alarms always. Both are
    legitimate states of the recursion, not error conditions."""
    calibration = deque((s for s in scores[:n_cal] if s is not None),
                        maxlen=window or n_cal)
    ordered = sorted(calibration)
    alpha_t = alpha
    thresholds, alarms, levels = [], [], []

    for i, s in enumerate(scores):
        if i < n_cal or s is None:
            thresholds.append(None)
            alarms.append(None)
            levels.append(None)
            continue

        level = 1.0 - alpha_t
        if level >= 1.0:
            q = float("inf")
        elif level <= 0.0:
            q = float("-inf")
        else:
            q = _quantile_from_sorted(ordered, level)

        err = 1 if s > q else 0
        thresholds.append(q)
        alarms.append(err)
        levels.append(alpha_t)

        alpha_t = min(1.0, max(0.0, alpha_t + gamma * (alpha - err)))

        if window:
            if len(calibration) == calibration.maxlen:
                dropped = calibration[0]
                pos = bisect.bisect_left(ordered, dropped)
                if pos < len(ordered) and ordered[pos] == dropped:
                    ordered.pop(pos)
            calibration.append(s)
            bisect.insort(ordered, s)

    realised = [a for a in alarms if a is not None]
    return thresholds, alarms, {
        "gamma": gamma,
        "final_alpha_t": alpha_t,
        "realised_alarm_rate": (sum(realised) / len(realised)) if realised else None,
        "alpha_t_min": min((l for l in levels if l is not None), default=None),
        "alpha_t_max": max((l for l in levels if l is not None), default=None),
    }


def dtaci(scores, alpha, gammas, n_cal, eta=0.1, sigma=None, window=None):
    """DtACI (Gibbs & Candes 2024): a set of ACI experts at different step
    sizes, aggregated by exponential weighting on the pinball loss.

    The point of the method is robustness to the choice of gamma, which a
    single ACI does not have. Our self-test checks exactly that.

    eta and sigma: the paper gives a data-dependent formula for both. It is
    replaced here by fixed defaults, which is a real deviation -- they are
    tuning constants and their values are not ratified. Any run feeding the
    pilot must record them as parameter provenance under C2, and a reviewer
    could reasonably ask why these values."""
    k = len(gammas)
    if sigma is None:
        sigma = 1.0 / (2.0 * k)

    calibration = deque((s for s in scores[:n_cal] if s is not None),
                        maxlen=window or n_cal)
    ordered = sorted(calibration)
    alpha_experts = [alpha] * k
    weights = [1.0] * k

    thresholds, alarms, combined_levels = [], [], []

    for i, s in enumerate(scores):
        if i < n_cal or s is None:
            thresholds.append(None)
            alarms.append(None)
            combined_levels.append(None)
            continue

        total_w = sum(weights)
        probs = [w / total_w for w in weights] if total_w > 0 else [1.0 / k] * k
        alpha_t = sum(p * a for p, a in zip(probs, alpha_experts))
        alpha_t = min(1.0, max(0.0, alpha_t))

        level = 1.0 - alpha_t
        if level >= 1.0:
            q = float("inf")
        elif level <= 0.0:
            q = float("-inf")
        else:
            q = _quantile_from_sorted(ordered, level)

        alarm = 1 if s > q else 0
        thresholds.append(q)
        alarms.append(alarm)
        combined_levels.append(alpha_t)

        # Per-expert pinball loss at its own level, then exponential weighting
        # with a uniform-mixing term so no expert's weight can vanish.
        new_weights = []
        for j in range(k):
            a_j = min(1.0, max(0.0, alpha_experts[j]))
            lvl = 1.0 - a_j
            if lvl >= 1.0:
                q_j = float("inf")
            elif lvl <= 0.0:
                q_j = float("-inf")
            else:
                q_j = _quantile_from_sorted(ordered, lvl)
            if math.isinf(q_j):
                loss = 1.0                       # bounded stand-in for a degenerate expert
            elif s > q_j:
                loss = alpha * (s - q_j)
            else:
                loss = (1.0 - alpha) * (q_j - s)
            new_weights.append(weights[j] * math.exp(-eta * loss))

        bar_total = sum(new_weights)
        if bar_total <= 0 or not math.isfinite(bar_total):
            new_weights = [1.0] * k
            bar_total = float(k)
        weights = [(1.0 - sigma) * w + sigma * bar_total / k for w in new_weights]
        # Renormalise to keep the exponential weights from underflowing.
        scale = sum(weights)
        if scale > 0:
            weights = [w / scale * k for w in weights]

        for j in range(k):
            err_j = 1 if s > _expert_threshold(ordered, alpha_experts[j]) else 0
            alpha_experts[j] = min(1.0, max(0.0,
                                            alpha_experts[j] + gammas[j] * (alpha - err_j)))

        if window:
            if len(calibration) == calibration.maxlen:
                dropped = calibration[0]
                pos = bisect.bisect_left(ordered, dropped)
                if pos < len(ordered) and ordered[pos] == dropped:
                    ordered.pop(pos)
            calibration.append(s)
            bisect.insort(ordered, s)

    realised = [a for a in alarms if a is not None]
    return thresholds, alarms, {
        "gammas": list(gammas),
        "eta": eta,
        "sigma": sigma,
        "eta_sigma_note": ("fixed defaults, NOT the paper's data-dependent formula; "
                           "record as C2 parameter provenance"),
        "final_expert_weights": [round(w, 4) for w in weights],
        "final_alpha_t": combined_levels[-1] if combined_levels else None,
        "realised_alarm_rate": (sum(realised) / len(realised)) if realised else None,
    }


def _expert_threshold(ordered, alpha_j):
    level = 1.0 - min(1.0, max(0.0, alpha_j))
    if level >= 1.0:
        return float("inf")
    if level <= 0.0:
        return float("-inf")
    return _quantile_from_sorted(ordered, level)


def care_adaptive_threshold(*_args, **_kwargs):
    raise NotImplementedError(
        "CARE's adaptive threshold is in the baseline set but its definition has "
        "not been extracted from the CARE paper or the archive README. "
        "Approximating a competitor's method and then beating it would be worse "
        "than reporting the baseline as missing. See MISSING_BASELINES.")


BASELINES = {
    "static_split_conformal": static_split_conformal,
    "aci": aci,
    "dtaci": dtaci,
}


def process_dir(args):
    paths = sorted(os.path.join(args.score_dir, fn)
                   for fn in os.listdir(args.score_dir)
                   if fnmatch.fnmatch(fn, args.score_glob))
    if not paths:
        print("no score files matched %r" % args.score_glob, file=sys.stderr)
        return 3

    gammas = [float(g) for g in args.dtaci_gammas.split(",")]
    os.makedirs(args.output_dir, exist_ok=True)
    report = {}

    for i, path in enumerate(paths, 1):
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            if args.score_col not in header:
                report[os.path.basename(path)] = {
                    "error": "score column %r not in header" % args.score_col}
                continue
            rows = list(reader)
        scores = [to_float(r.get(args.score_col)) for r in rows]

        case_id = os.path.splitext(os.path.basename(path))[0]
        case_report = {}
        columns = {"timestamp": [r.get(args.timestamp_col, "") for r in rows],
                   "score": scores}

        for name in args.methods.split(","):
            name = name.strip()
            if name not in BASELINES:
                case_report[name] = {"error": "unknown method"}
                continue
            if name == "static_split_conformal":
                th, al, diag = static_split_conformal(scores, args.alpha, args.n_cal)
            elif name == "aci":
                th, al, diag = aci(scores, args.alpha, args.gamma, args.n_cal,
                                   window=args.window)
            else:
                th, al, diag = dtaci(scores, args.alpha, gammas, args.n_cal,
                                     eta=args.eta, window=args.window)
            columns[name + "_threshold"] = th
            columns[name + "_alarm"] = al
            case_report[name] = diag

        out_path = os.path.join(args.output_dir, case_id + ".csv")
        keys = list(columns)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(keys)
            for r in range(len(rows)):
                writer.writerow(["" if columns[k][r] is None else columns[k][r]
                                 for k in keys])
        report[case_id] = case_report
        if i % 5 == 0 or i == len(paths):
            print("  %d/%d cases" % (i, len(paths)), flush=True)

    summary = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "is_author_code": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_alpha": args.alpha,
        "parameters": {"n_cal": args.n_cal, "window": args.window,
                       "aci_gamma": args.gamma, "dtaci_gammas": gammas,
                       "dtaci_eta": args.eta},
        "methods_run": args.methods,
        "missing_baselines": MISSING_BASELINES,
        "per_case": report,
        "cli_invocation": " ".join(sys.argv),
    }
    with open(os.path.join(args.output_dir, "baselines_summary.json"),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("\nWrote %s" % args.output_dir, file=sys.stderr)
    print("NOTE: care_adaptive_threshold is NOT implemented -- see "
          "missing_baselines in the summary.", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-missing", action="store_true",
                    help="Print the baselines that are declared missing and exit")
    ap.add_argument("--score-dir")
    ap.add_argument("--output-dir")
    ap.add_argument("--score-col", default="anomaly_score")
    ap.add_argument("--timestamp-col", default="timestamp")
    ap.add_argument("--score-glob", default="*.csv")
    ap.add_argument("--alpha", type=float, default=0.01,
                    help="Target alarm rate. Signed-off: 0.01 primary, 0.05 and "
                         "0.001 secondary. Run once per value.")
    ap.add_argument("--n-cal", type=int, default=1440,
                    help="Initial calibration length, matched to W = 1440")
    ap.add_argument("--window", type=int, default=1440,
                    help="Rolling calibration window; 0 to freeze the calibration set")
    ap.add_argument("--gamma", type=float, default=0.005, help="ACI step size")
    ap.add_argument("--dtaci-gammas", default="0.001,0.005,0.02,0.1",
                    help="Comma-separated expert step sizes for DtACI")
    ap.add_argument("--eta", type=float, default=0.1,
                    help="DtACI exponential-weighting rate (fixed default, not the "
                         "paper's data-dependent formula)")
    args = ap.parse_args()

    if args.list_missing:
        print(json.dumps(MISSING_BASELINES, indent=2, ensure_ascii=False))
        return 0
    if not args.score_dir or not args.output_dir:
        ap.error("--score-dir and --output-dir are required unless --list-missing")
    if not os.path.isdir(args.score_dir):
        print("score dir not found: %s" % args.score_dir, file=sys.stderr)
        return 3
    args.window = args.window or None
    return process_dir(args)


if __name__ == "__main__":
    sys.exit(main())
