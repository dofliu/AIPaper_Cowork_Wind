#!/usr/bin/env python3
"""Freeze-on-Alert lock-in geometry — measure the failure before designing for it.

WHY THIS EXISTS
---------------
The 2026-08-16 real-data run showed the headline defect: at alpha=0.01 the
false-alarm rate on unfrozen points is 0.0113 against a nominal 0.01 (correct),
while frozen points run at 0.6819, and the 4.9% of points that are frozen drag
the pooled rate to 0.0445.

R16's recovery policy was then implemented as specified and measured. It changed
nothing (worst-bin 0.0615 vs 0.0616), because it addressed a failure mode that
does not occur: its circuit breaker needs 4320 steps of CONTINUOUS freeze and
the longest real run is far shorter, so it fired zero times.

The lesson is that the next design must be aimed at the geometry the data
actually has. This tool measures that geometry. It proposes nothing and changes
no policy; it reads the per-case CSVs the ratified run already produced.

Everything here is a re-reading of `<ours-dir>/*.csv`, so the numbers are
attributable to the same official run recorded in PROJECT_STATUS section 1 --
not to a re-execution that might differ.

WHAT IT ANSWERS
---------------
Q1  Run-length distribution of freezes. R16's D_freeze_max = 4320 assumed one
    long lock. How long are the runs really, and how much of the frozen mass
    lives beyond a candidate horizon? (The previous instrumentation attempt
    only recorded runs that ended through its own new code paths, so its run
    counts were not trustworthy. These are read off the `frozen` column, which
    is written for every row.)

Q2  Collateral freeze. The 6-of-18 work order rule pools exceedances across all
    four regime bins, and the freeze it triggers then withholds absorption in
    EVERY bin -- including bins that contributed no exceedance to the alarm.
    A bin whose reference is held stale for a fault it never saw is paying for
    someone else's alarm. This measures how much of the frozen mass is that.

Q3  Staleness profile. Does the conditional false-alarm rate inside a freeze
    grow with time since the freeze began? If it does, a bounded freeze can
    recover most of the damage. If it is flat and already high at step one,
    bounding the freeze cannot help and the fix has to be elsewhere.

Q4  Bounded-freeze counterfactual, for horizons that would actually fire.
    STATED PLAINLY: this is a static count over the observed trajectory. Ending
    a freeze early changes every subsequent buffer, p-value and alarm, so these
    numbers are an upper bound on what is recoverable, not a prediction. They
    exist to rank candidate horizons cheaply before paying for a full re-run.

CONVENTIONS
-----------
False-alarm rates are computed on NORMAL cases only. On an anomaly case an
exceedance may be a true positive, and counting it as a false alarm is the
defect that once made the best detector look like the worst (PROJECT_STATUS
section 5). Anomaly cases are reported separately for geometry only.

Every rate is printed next to its denominator (working rule 7).
"""

import argparse
import csv
import fnmatch
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone

DIAGNOSTIC_VERSION = "freeze-lockin-diag-v1.0"

# Same rule as the method and the evaluator. Not a free parameter here: the
# trigger window has to match the one that produced the `frozen` column.
ALARM_OF = 6
ALARM_WINDOW = 18

# Candidate circuit-breaker horizons, in steps of 10 minutes.
# 4320 is R16's value (30 days) and is kept so the table shows why it missed.
HORIZONS = [36, 144, 288, 576, 1152, 4320]

# Steps since a freeze began, bucketed. The first bucket is one alarm window:
# if the rate is already saturated there, staleness is not the mechanism.
STALENESS_BUCKETS = [(0, 18), (18, 36), (36, 144), (144, 288), (288, 576),
                     (576, None)]


def bucket_label(lo, hi):
    return "%d-%s" % (lo, "inf" if hi is None else str(hi))


def load_labels(path):
    labels = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            labels[str(row["case_id"]).strip()] = {
                "label": (row.get("label") or "").strip(),
                "farm": (row.get("farm_id") or "").strip(),
            }
    return labels


def parse_trim(specs):
    trims = {}
    for spec in specs or []:
        if "=" not in spec:
            raise SystemExit("bad --trim-case %r; expected CASE_ID=TIMESTAMP" % spec)
        case_id, ts = spec.split("=", 1)
        try:
            datetime.fromisoformat(ts.strip())
        except ValueError:
            raise SystemExit("bad timestamp in --trim-case %r" % spec)
        trims[case_id.strip()] = ts.strip()
    return trims


def canonical_ts(raw):
    """Make a timestamp comparable as a string.

    The score CSVs write `2023-08-24 13:00:00` and the ratified trim is quoted
    as `2023-08-24T13:00:00`. Space sorts before 'T', so comparing the two raw
    forms puts every row before the cut and the trim silently does nothing --
    the same shape of defect as the case 93 trim that lived in a config
    comment for a day without any code applying it. Both sides go through
    here, and the number of rows actually dropped is reported so that "it did
    nothing" is visible rather than assumed.
    """
    return (raw or "").strip().replace("T", " ")


def analyse_case(path, alpha, trim_at=None):
    """One pass over a case's per-row output. Returns a dict of counters.

    A row counts as calibrated when `exceed` is present; warm-up rows carry an
    empty p_value and take part in nothing. `frozen` is read as written, so
    freeze runs here are exactly the runs the ratified policy produced.
    """
    runs = []                 # lengths of consecutive frozen rows
    run_start_len = 0
    in_run = False

    recent = deque(maxlen=ALARM_WINDOW)   # (bin, exceed) over calibrated rows
    trigger_bins = set()                  # bins that fed the current alarm

    n_rows = 0
    n_calibrated = 0
    n_frozen_rows = 0

    # calibrated points split by frozen state
    calib = {"frozen": 0, "unfrozen": 0}
    exceed = {"frozen": 0, "unfrozen": 0}

    per_bin = {}              # bin -> {"n":, "exceed":, "n_frozen":, "exceed_frozen":}
    collateral = {"n": 0, "exceed": 0}     # frozen calibrated points in non-trigger bins
    attributed = {"n": 0, "exceed": 0}     # frozen calibrated points in trigger bins

    stale = {bucket_label(lo, hi): {"n": 0, "exceed": 0}
             for lo, hi in STALENESS_BUCKETS}
    beyond = {str(d): 0 for d in HORIZONS}   # frozen rows past step d of their run
    runs_over = {str(d): 0 for d in HORIZONS}

    steps_into_run = 0
    n_dropped_by_trim = 0
    cut = canonical_ts(trim_at) if trim_at is not None else None

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if cut is not None and canonical_ts(row.get("timestamp")) >= cut:
                n_dropped_by_trim += 1
                continue
            n_rows += 1
            frozen = (row.get("frozen") or "0").strip() == "1"
            bin_name = (row.get("regime_bin") or "").strip()
            exc_raw = (row.get("exceed") or "").strip()
            is_calibrated = exc_raw != ""
            exc = int(exc_raw) if is_calibrated else None

            if frozen and not in_run:
                # Freeze begins here. The bins that fed the alarm are the bins
                # with an exceedance inside the window that satisfied 6-of-18.
                in_run = True
                steps_into_run = 0
                run_start_len = 0
                trigger_bins = set(b for b, e in recent if e == 1 and b)
            elif not frozen and in_run:
                in_run = False
                runs.append(run_start_len)

            if frozen:
                n_frozen_rows += 1
                run_start_len += 1
                for d in HORIZONS:
                    if steps_into_run >= d:
                        beyond[str(d)] += 1
                steps_into_run += 1

            if not is_calibrated:
                continue

            n_calibrated += 1
            recent.append((bin_name, exc))
            slot = per_bin.setdefault(
                bin_name or "unbinned",
                {"n": 0, "exceed": 0, "n_frozen": 0, "exceed_frozen": 0})
            slot["n"] += 1
            slot["exceed"] += exc

            state = "frozen" if frozen else "unfrozen"
            calib[state] += 1
            exceed[state] += exc

            if frozen:
                slot["n_frozen"] += 1
                slot["exceed_frozen"] += exc

                target = collateral if bin_name not in trigger_bins else attributed
                target["n"] += 1
                target["exceed"] += exc

                s = steps_into_run - 1   # already advanced above
                for lo, hi in STALENESS_BUCKETS:
                    if s >= lo and (hi is None or s < hi):
                        b = stale[bucket_label(lo, hi)]
                        b["n"] += 1
                        b["exceed"] += exc
                        break

    if in_run:
        runs.append(run_start_len)

    for d in HORIZONS:
        runs_over[str(d)] = sum(1 for L in runs if L > d)

    return {
        "n_rows": n_rows,
        "n_rows_dropped_by_trim": n_dropped_by_trim,
        "n_calibrated": n_calibrated,
        "n_frozen_rows": n_frozen_rows,
        "n_freeze_runs": len(runs),
        "run_lengths": runs,
        "calibrated_by_state": calib,
        "exceed_by_state": exceed,
        "per_bin": per_bin,
        "collateral_frozen": collateral,
        "attributed_frozen": attributed,
        "staleness": stale,
        "frozen_rows_beyond_horizon": beyond,
        "runs_over_horizon": runs_over,
    }


def rate(num, den):
    return (num / den) if den else None


def quantiles(values, qs=(0.5, 0.9, 0.95, 0.99, 1.0)):
    if not values:
        return {str(q): None for q in qs}
    ordered = sorted(values)
    out = {}
    for q in qs:
        idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        out[str(q)] = ordered[idx]
    return out


def aggregate(cases):
    """Sum counters across a set of cases. Rates are computed from pooled
    counts, never as a mean of per-case rates -- a case with 400 calibrated
    points would otherwise weigh as much as one with 50,000."""
    total = {
        "n_cases": len(cases),
        "n_rows": 0, "n_calibrated": 0, "n_frozen_rows": 0, "n_freeze_runs": 0,
        "calibrated_by_state": {"frozen": 0, "unfrozen": 0},
        "exceed_by_state": {"frozen": 0, "unfrozen": 0},
        "per_bin": {},
        "collateral_frozen": {"n": 0, "exceed": 0},
        "attributed_frozen": {"n": 0, "exceed": 0},
        "staleness": {bucket_label(lo, hi): {"n": 0, "exceed": 0}
                      for lo, hi in STALENESS_BUCKETS},
        "frozen_rows_beyond_horizon": {str(d): 0 for d in HORIZONS},
        "runs_over_horizon": {str(d): 0 for d in HORIZONS},
    }
    all_runs = []
    for c in cases:
        for k in ("n_rows", "n_calibrated", "n_frozen_rows", "n_freeze_runs"):
            total[k] += c[k]
        all_runs.extend(c["run_lengths"])
        for state in ("frozen", "unfrozen"):
            total["calibrated_by_state"][state] += c["calibrated_by_state"][state]
            total["exceed_by_state"][state] += c["exceed_by_state"][state]
        for name, slot in c["per_bin"].items():
            dst = total["per_bin"].setdefault(
                name, {"n": 0, "exceed": 0, "n_frozen": 0, "exceed_frozen": 0})
            for k in dst:
                dst[k] += slot[k]
        for key in ("collateral_frozen", "attributed_frozen"):
            total[key]["n"] += c[key]["n"]
            total[key]["exceed"] += c[key]["exceed"]
        for label, slot in c["staleness"].items():
            total["staleness"][label]["n"] += slot["n"]
            total["staleness"][label]["exceed"] += slot["exceed"]
        for d in HORIZONS:
            total["frozen_rows_beyond_horizon"][str(d)] += c["frozen_rows_beyond_horizon"][str(d)]
            total["runs_over_horizon"][str(d)] += c["runs_over_horizon"][str(d)]

    total["run_length_quantiles"] = quantiles(all_runs)
    total["n_runs_pooled"] = len(all_runs)
    total["mean_run_length"] = rate(sum(all_runs), len(all_runs))
    return total


def derive(total, alpha):
    """Turn pooled counts into the rates the design decision needs."""
    calib = total["calibrated_by_state"]
    exc = total["exceed_by_state"]
    n_all = calib["frozen"] + calib["unfrozen"]
    e_all = exc["frozen"] + exc["unfrozen"]

    out = {
        "alpha": alpha,
        "n_calibrated": n_all,
        "far_pooled": rate(e_all, n_all),
        "far_unfrozen": rate(exc["unfrozen"], calib["unfrozen"]),
        "far_frozen": rate(exc["frozen"], calib["frozen"]),
        "frozen_share_of_calibrated": rate(calib["frozen"], n_all),
        "n_frozen_calibrated": calib["frozen"],
        "n_unfrozen_calibrated": calib["unfrozen"],
    }

    coll, attr = total["collateral_frozen"], total["attributed_frozen"]
    n_frozen_calib = coll["n"] + attr["n"]
    out["collateral"] = {
        "n_collateral": coll["n"],
        "n_attributed": attr["n"],
        "collateral_share_of_frozen": rate(coll["n"], n_frozen_calib),
        "far_collateral": rate(coll["exceed"], coll["n"]),
        "far_attributed": rate(attr["exceed"], attr["n"]),
        "note": ("collateral = frozen calibrated points in a bin that fed no "
                 "exceedance into the 6-of-18 window that started the freeze"),
    }

    out["staleness"] = {
        label: {"n": slot["n"], "far": rate(slot["exceed"], slot["n"])}
        for label, slot in total["staleness"].items()
    }

    out["horizons"] = {}
    for d in HORIZONS:
        out["horizons"][str(d)] = {
            "runs_longer_than_d": total["runs_over_horizon"][str(d)],
            "frozen_rows_beyond_d": total["frozen_rows_beyond_horizon"][str(d)],
            "share_of_frozen_rows_released": rate(
                total["frozen_rows_beyond_horizon"][str(d)], total["n_frozen_rows"]),
        }
    out["horizon_caveat"] = (
        "static counterfactual over the observed trajectory; cutting a freeze "
        "changes every later buffer, p-value and alarm, so these are an upper "
        "bound on what a circuit breaker could release, not a prediction")

    out["per_bin"] = {}
    for name, slot in sorted(total["per_bin"].items()):
        out["per_bin"][name] = {
            "n": slot["n"],
            "far": rate(slot["exceed"], slot["n"]),
            "n_frozen": slot["n_frozen"],
            "frozen_share": rate(slot["n_frozen"], slot["n"]),
            "far_frozen": rate(slot["exceed_frozen"], slot["n_frozen"]),
            "far_unfrozen": rate(slot["exceed"] - slot["exceed_frozen"],
                                 slot["n"] - slot["n_frozen"]),
        }
    return out


def fmt(x, spec="%.4f"):
    return "n/a" if x is None else spec % x


def report(derived_normal, derived_anomaly, total_normal, total_anomaly, alpha):
    L = []
    a = L.append
    a("")
    a("=" * 72)
    a("Freeze-on-Alert lock-in geometry  (alpha=%g)" % alpha)
    a("=" * 72)

    a("")
    a("Q1  Freeze run lengths (steps of 10 min), normal cases")
    q = total_normal["run_length_quantiles"]
    a("    runs=%d  mean=%s  p50=%s  p90=%s  p95=%s  p99=%s  max=%s"
      % (total_normal["n_runs_pooled"], fmt(total_normal["mean_run_length"], "%.1f"),
         q["0.5"], q["0.9"], q["0.95"], q["0.99"], q["1.0"]))
    qa = total_anomaly["run_length_quantiles"]
    a("    anomaly cases for comparison: runs=%d  max=%s"
      % (total_anomaly["n_runs_pooled"], qa["1.0"]))

    a("")
    a("Q0  False-alarm decomposition, normal cases only")
    d = derived_normal
    a("    pooled    FAR=%s   n=%d" % (fmt(d["far_pooled"]), d["n_calibrated"]))
    a("    unfrozen  FAR=%s   n=%d  (%.1f%% of calibrated)"
      % (fmt(d["far_unfrozen"]), d["n_unfrozen_calibrated"],
         100.0 * (1.0 - (d["frozen_share_of_calibrated"] or 0))))
    a("    frozen    FAR=%s   n=%d  (%.1f%% of calibrated)"
      % (fmt(d["far_frozen"]), d["n_frozen_calibrated"],
         100.0 * (d["frozen_share_of_calibrated"] or 0)))

    a("")
    a("Q2  Collateral freeze: frozen points in bins that fed no exceedance")
    c = d["collateral"]
    a("    collateral n=%d (%s of frozen)   FAR=%s"
      % (c["n_collateral"], fmt(c["collateral_share_of_frozen"]),
         fmt(c["far_collateral"])))
    a("    attributed n=%d                  FAR=%s"
      % (c["n_attributed"], fmt(c["far_attributed"])))

    a("")
    a("Q3  Staleness profile inside a freeze (steps since it began)")
    a("    %-12s %10s %10s" % ("bucket", "n", "FAR"))
    for lo, hi in STALENESS_BUCKETS:
        label = bucket_label(lo, hi)
        s = d["staleness"][label]
        a("    %-12s %10d %10s" % (label, s["n"], fmt(s["far"])))

    a("")
    a("Q4  Bounded-freeze counterfactual (upper bound, see caveat)")
    a("    %-8s %14s %18s %12s" % ("D_max", "runs>D", "frozen rows>D", "released"))
    for dd in HORIZONS:
        h = d["horizons"][str(dd)]
        a("    %-8s %14d %18d %12s"
          % (dd, h["runs_longer_than_d"], h["frozen_rows_beyond_d"],
             fmt(h["share_of_frozen_rows_released"])))

    a("")
    a("Per-bin, normal cases")
    a("    %-12s %10s %9s %9s %9s %9s"
      % ("bin", "n", "FAR", "frz share", "FAR|frz", "FAR|unfrz"))
    for name, b in d["per_bin"].items():
        a("    %-12s %10d %9s %9s %9s %9s"
          % (name, b["n"], fmt(b["far"]), fmt(b["frozen_share"]),
             fmt(b["far_frozen"]), fmt(b["far_unfrozen"])))
    a("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours-dir", required=True,
                    help="directory of per-case CSVs from regime_conditional_calibration.py")
    ap.add_argument("--case-metadata", required=True,
                    help="g3_case_metadata.csv, for the normal/anomaly label")
    ap.add_argument("--alpha", type=float, default=0.01)
    ap.add_argument("--case-glob", default="*.csv")
    ap.add_argument("--exclude-cases", default="",
                    help="comma separated case ids to drop, e.g. the D1/D6 exclusions")
    ap.add_argument("--trim-case", action="append",
                    help="CASE_ID=TIMESTAMP; rows at or after the timestamp are dropped")
    ap.add_argument("--output", required=True, help="path for the JSON report")
    args = ap.parse_args()

    if not os.path.isdir(args.ours_dir):
        print("ours dir not found: %s" % args.ours_dir, file=sys.stderr)
        return 3

    labels = load_labels(args.case_metadata)
    trims = parse_trim(args.trim_case)
    excluded = set(x.strip() for x in args.exclude_cases.split(",") if x.strip())

    paths = sorted(os.path.join(args.ours_dir, fn)
                   for fn in os.listdir(args.ours_dir)
                   if fnmatch.fnmatch(fn, args.case_glob))

    by_label = {"normal": [], "anomaly": []}
    skipped = {"excluded": [], "unlabelled": [], "not_a_case": []}
    per_case = {}

    for i, path in enumerate(paths, 1):
        case_id = os.path.splitext(os.path.basename(path))[0]
        if case_id in excluded:
            skipped["excluded"].append(case_id)
            continue
        meta = labels.get(case_id)
        if meta is None:
            skipped["unlabelled"].append(case_id)
            continue
        res = analyse_case(path, args.alpha, trims.get(case_id))
        res["label"] = meta["label"]
        res["farm"] = meta["farm"]
        per_case[case_id] = res
        if meta["label"] in by_label:
            by_label[meta["label"]].append(res)
        if i % 10 == 0 or i == len(paths):
            print("  %d/%d files" % (i, len(paths)), flush=True)

    total_normal = aggregate(by_label["normal"])
    total_anomaly = aggregate(by_label["anomaly"])
    derived_normal = derive(total_normal, args.alpha)
    derived_anomaly = derive(total_anomaly, args.alpha)

    text = report(derived_normal, derived_anomaly, total_normal, total_anomaly, args.alpha)
    print(text)

    # A configured trim that drops nothing is the case 93 failure again, so it
    # is reported rather than left to be assumed.
    trim_effect = {}
    for case_id in trims:
        dropped = per_case.get(case_id, {}).get("n_rows_dropped_by_trim")
        trim_effect[case_id] = dropped
        if dropped is None:
            print("WARNING: --trim-case %s names a case not present in %s"
                  % (case_id, args.ours_dir), file=sys.stderr)
        elif dropped == 0:
            print("WARNING: --trim-case %s dropped 0 rows -- check the timestamp"
                  % case_id, file=sys.stderr)
        else:
            print("trim: case %s dropped %d rows" % (case_id, dropped), file=sys.stderr)

    payload = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "alpha": args.alpha,
        "source_dir": args.ours_dir,
        "excluded_cases": sorted(excluded),
        "trimmed_cases": trims,
        "trim_rows_dropped": trim_effect,
        "n_cases_normal": total_normal["n_cases"],
        "n_cases_anomaly": total_anomaly["n_cases"],
        "skipped": skipped,
        "normal": derived_normal,
        "anomaly_geometry_only": {
            "n_freeze_runs": total_anomaly["n_runs_pooled"],
            "run_length_quantiles": total_anomaly["run_length_quantiles"],
            "frozen_share_of_calibrated": derived_anomaly["frozen_share_of_calibrated"],
            "note": ("rates on anomaly cases are omitted on purpose: an "
                     "exceedance there can be a true positive"),
        },
        "run_length_quantiles_normal": total_normal["run_length_quantiles"],
        "mean_run_length_normal": total_normal["mean_run_length"],
        "per_case": {
            cid: {
                "label": r["label"], "farm": r["farm"],
                "n_calibrated": r["n_calibrated"],
                "n_frozen_rows": r["n_frozen_rows"],
                "n_freeze_runs": r["n_freeze_runs"],
                "max_run_length": max(r["run_lengths"]) if r["run_lengths"] else 0,
                "far_frozen": rate(r["exceed_by_state"]["frozen"],
                                   r["calibrated_by_state"]["frozen"]),
                "far_unfrozen": rate(r["exceed_by_state"]["unfrozen"],
                                     r["calibrated_by_state"]["unfrozen"]),
            }
            for cid, r in sorted(per_case.items())
        },
        "text_report": text,
        "cli_invocation": " ".join(sys.argv),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("Wrote %s" % args.output, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
