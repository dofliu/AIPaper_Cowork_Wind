#!/usr/bin/env python3
"""
W1-ACAS baseline — a reimplementation for comparison, not our contribution.

WHAT THIS IS
------------
Martinez Gil, O'Donncha, Gifford, Zhou, Patel and Vaculin,
"Adaptive Conformal Anomaly Detection with Time Series Foundation Models for
Signal Monitoring", ICLR 2026 (arXiv:2604.20122v1), Algorithm 1.

The R17 overlap check found this to be the nearest external competitor: a
post-hoc, model-agnostic conformal calibration layer that maps an arbitrary
anomaly score to a p-value and controls the alarm rate under distribution
shift. Its own conclusion lists conditioning the weights on contextual
features as FUTURE work, which is precisely the gap this project fills with
regime-conditional calibration.

That makes it the baseline whose absence a reviewer would ask about, and the
one that turns our "difference one" from an argument into a measurement. It
is model-agnostic by construction, so it applies directly to our frozen
scorers' output without needing their time-series foundation models.

REIMPLEMENTED FROM THE PAPER — NOT AUTHOR CODE
-----------------------------------------------
No official implementation was located. Every equation below is cited to the
paper so the mapping can be checked line by line, and C2 provenance for any
run must record this file, its commit, and the parameter source. Do not
present results from this file as the authors' own numbers.

WHAT DIFFERS FROM THE PAPER'S SETTING
--------------------------------------
The paper derives its nonconformity score from a forecaster's error at D
horizons and takes the median p-value across them (their Eq 15). We apply
the calibration layer to a frozen scalar anomaly score s_t that already
exists, so D = 1 and no aggregation is needed. Everything else — the
weighted conformal p-value, the 1-Wasserstein objective, the projected
gradient update — is unchanged.

ONE DEVIATION IN FORM, NONE IN RESULT
--------------------------------------
Algorithm 1 sorts the past-score buffer at every step to obtain the ranks
pi(k), which would cost O(n log n) per step and make a 95-case archive
impractical in pure Python. The sort is unnecessary: the rank condition
`pi(k) >= |s| - j + 1` that selects which past samples enter the sum is
exactly equivalent to `S_k > S_test`, ties included. This was verified
against the ranked form over 5000 randomised trials with deliberate ties
(0 mismatches; the loose `>=` form mismatches 907/5000, so the strict
comparison is the correct reading of j = sum 1[S_test < s]). The step is
therefore O(n) comparisons and no ordering is computed.

USAGE
-----
    python3 baseline_w1_acas.py \\
        --score-dir  ./scores_MD_2022_run1 \\
        --output-dir ./w1acas_MD_2022 \\
        --score-col  anomaly_score \\
        --timestamp-col timestamp \\
        [--alpha-c 0.01] [--batch-size 10] [--lr 0.001] [--max-past 1440]

Defaults follow the paper's experimental section: alpha_c = 0.01,
n_b = 10, gamma = 0.001, ADAM. The one value not from the paper is
--max-past, frozen at 1440 by PI decision 2026-08-15 so the buffer spans
the same horizon as the project's signed-off rolling window W.

Output per case: timestamp, score, beta — beta being the adaptive p-value,
directly comparable to an alarm rate. Alarm when beta < alpha.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import fnmatch
import json
import math
import os
import sys
from collections import deque
from datetime import datetime, timezone

IMPLEMENTATION_VERSION = "w1acas-reimpl-v1.0"
PAPER = "Martinez Gil et al., ICLR 2026, arXiv:2604.20122v1, Algorithm 1"

# Paper section 6, "W1-ACAS + TSFM".
DEFAULT_ALPHA_C = 0.01
DEFAULT_BATCH = 10
DEFAULT_LR = 0.001
ADAM_BETA1, ADAM_BETA2, ADAM_EPS = 0.9, 0.999, 1e-8


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


def project(w, n_c):
    """Euclidean projection onto {w in [0,1]^n : sum(w) >= n_c}.

    Clip first; if the mass constraint is violated, add a constant to every
    coordinate and re-clip, choosing the constant by bisection so the sum
    lands on n_c. That constant-shift-then-clip form is the projection onto
    this intersection, not an approximation of it."""
    w = [0.0 if x < 0.0 else (1.0 if x > 1.0 else x) for x in w]
    total = sum(w)
    if total >= n_c:
        return w
    if len(w) <= n_c:
        return [1.0] * len(w)          # constraint only reachable at the corner
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        s = sum(min(1.0, x + mid) for x in w)
        if s < n_c:
            lo = mid
        else:
            hi = mid
    return [min(1.0, x + hi) for x in w]


def dW1_dbeta(beta_batch, n_b):
    """Paper Eq 13. Piecewise derivative of the empirical 1-Wasserstein
    distance to the uniform CDF, per batch element, using each element's
    rank within the batch."""
    order = sorted(range(len(beta_batch)), key=lambda i: beta_batch[i])
    rank = [0] * len(beta_batch)
    for position, index in enumerate(order):
        rank[index] = position + 1              # pi_hat(i), 1-based
    out = []
    for i, beta in enumerate(beta_batch):
        lower = (rank[i] - 1) / n_b
        upper = rank[i] / n_b
        if beta < lower:
            out.append(-1.0 / n_b)
        elif beta > upper:
            out.append(1.0 / n_b)
        else:
            out.append(2.0 * beta - (2.0 * rank[i] - 1.0) / n_b)
    return out


def run_stream(scores, alpha_c, n_b, lr, max_past):
    """Algorithm 1 over one scalar score stream. Returns (betas, diagnostics).

    betas[i] is None while the buffer is still shorter than n_c: below that
    the estimator cannot produce a p-value finer than alpha_c, which the
    paper states as its resolution floor."""
    n_c = int(round(1.0 / alpha_c)) - 1
    n = max(max_past, n_c + 1)

    w = [1.0 if i < n_c else 0.0 for i in range(n)]
    m_adam = [0.0] * n
    v_adam = [0.0] * n
    adam_t = 0

    past = deque(maxlen=n)                      # most recent first
    betas = []
    batch_beta = []
    batch_jac = []
    n_updates = 0

    for s_t in scores:
        if s_t is None:
            betas.append(None)
            continue

        m = len(past)
        if m < n_c:
            past.appendleft(s_t)
            betas.append(None)
            continue

        # Weighted conformal p-value. Paper Eq 7, with the rank selector
        # replaced by its equivalent strict comparison (see module docstring).
        mass = 0.0
        above = 0.0
        indicator = [0.0] * m
        for lag in range(m):
            weight = w[lag]
            mass += weight
            if past[lag] > s_t:
                above += weight
                indicator[lag] = 1.0
        denom = mass + 1.0
        beta = (above + 1.0) / denom
        betas.append(beta)

        # Paper Eq 14.
        batch_jac.append([(-beta + indicator[lag]) / denom for lag in range(m)])
        batch_beta.append(beta)

        if len(batch_beta) == n_b:
            dbeta = dW1_dbeta(batch_beta, n_b)
            grad = [0.0] * n
            for i, row in enumerate(batch_jac):
                scale = dbeta[i]
                for lag, value in enumerate(row):
                    grad[lag] += scale * value

            adam_t += 1
            for k in range(n):
                m_adam[k] = ADAM_BETA1 * m_adam[k] + (1 - ADAM_BETA1) * grad[k]
                v_adam[k] = ADAM_BETA2 * v_adam[k] + (1 - ADAM_BETA2) * grad[k] * grad[k]
                m_hat = m_adam[k] / (1 - ADAM_BETA1 ** adam_t)
                v_hat = v_adam[k] / (1 - ADAM_BETA2 ** adam_t)
                w[k] -= lr * m_hat / (math.sqrt(v_hat) + ADAM_EPS)
            w = project(w, n_c)
            batch_beta, batch_jac = [], []
            n_updates += 1

        past.appendleft(s_t)

    diagnostics = {
        "n_c_effective_sample_floor": n_c,
        "alpha_c_resolution_floor": alpha_c,
        "max_past": n,
        "n_weight_updates": n_updates,
        "n_scored": sum(1 for b in betas if b is not None),
        "n_warmup_unscored": sum(1 for b in betas if b is None),
        "final_weight_mass": round(sum(w), 4),
        "final_weight_head": [round(x, 4) for x in w[:10]],
    }
    return betas, diagnostics


def calibration_error(betas, grid=None):
    """Mean |P(beta <= a) - a| over a grid — the quantity Eq 9 minimises, and
    the paper's CalErr metric."""
    values = [b for b in betas if b is not None]
    if not values:
        return None
    grid = grid or [i / 100.0 for i in range(1, 100)]
    n = len(values)
    total = 0.0
    for a in grid:
        total += abs(sum(1 for b in values if b <= a) / n - a)
    return total / len(grid)


def process_file(path, args):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if args.score_col not in header:
            return None, {"error": "score column %r not in header" % args.score_col,
                          "header_sample": header[:15]}
        rows = list(reader)

    scores = [to_float(r.get(args.score_col)) for r in rows]
    betas, diagnostics = run_stream(scores, args.alpha_c, args.batch_size,
                                    args.lr, args.max_past)
    diagnostics["calibration_error"] = calibration_error(betas)

    case_id = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, case_id + ".csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "score", "beta"])
        for r, s, b in zip(rows, scores, betas):
            writer.writerow([r.get(args.timestamp_col, ""),
                             "" if s is None else s,
                             "" if b is None else "%.10g" % b])
    return out_path, diagnostics


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--score-col", default="anomaly_score")
    ap.add_argument("--timestamp-col", default="timestamp")
    ap.add_argument("--score-glob", default="*.csv")
    ap.add_argument("--alpha-c", type=float, default=DEFAULT_ALPHA_C,
                    help="Critical false alarm rate; also the p-value resolution floor")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--lr", type=float, default=DEFAULT_LR)
    ap.add_argument("--max-past", type=int, default=1440,
                    help="Past-score buffer, frozen at 1440 by PI decision "
                         "2026-08-15 to match the signed-off rolling window "
                         "W = 1440 steps (~10 days at 10-minute sampling). Cost is "
                         "O(buffer) per step. Changing it changes a frozen "
                         "parameter and must be ratified.")
    args = ap.parse_args()

    if not os.path.isdir(args.score_dir):
        print("score dir not found: %s" % args.score_dir, file=sys.stderr)
        return 3
    paths = sorted(os.path.join(args.score_dir, fn)
                   for fn in os.listdir(args.score_dir)
                   if fnmatch.fnmatch(fn, args.score_glob))
    if not paths:
        print("no score files matched %r" % args.score_glob, file=sys.stderr)
        return 3

    print("baseline_w1_acas starting (%s)" % IMPLEMENTATION_VERSION, flush=True)
    report = {}
    for i, path in enumerate(paths, 1):
        out_path, diagnostics = process_file(path, args)
        case_id = os.path.splitext(os.path.basename(path))[0]
        report[case_id] = diagnostics
        if i % 5 == 0 or i == len(paths):
            print("  %d/%d cases" % (i, len(paths)), flush=True)

    errors = [d["calibration_error"] for d in report.values()
              if d.get("calibration_error") is not None]
    summary = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "reimplemented_from": PAPER,
        "is_author_code": False,
        "provenance_note": (
            "Reimplemented from the paper's equations; no official code was "
            "located. Record this file and its commit as C2 parameter "
            "provenance for any run. Do not report these as the authors' numbers."),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {"alpha_c": args.alpha_c, "batch_size": args.batch_size,
                       "lr": args.lr, "max_past": args.max_past,
                       "optimiser": "ADAM", "horizons_D": 1},
        "n_cases": len(report),
        "mean_calibration_error": (sum(errors) / len(errors)) if errors else None,
        "per_case": report,
        "cli_invocation": " ".join(sys.argv),
    }
    with open(os.path.join(args.output_dir, "w1acas_summary.json"),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nmean calibration error: %s" % summary["mean_calibration_error"])
    print("Wrote %s" % args.output_dir, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
