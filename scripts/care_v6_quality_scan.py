#!/usr/bin/env python3
"""
CARE v6 G4 deep quality scan — missing rates, sentinel values, and the gap
profile that C1's threshold depends on.

WHY THIS EXISTS
---------------
The 2026-08-14 manifest run left G4 at column inventory only; its own note
said so. Two things downstream are blocked on the numbers it did not produce:

  1. C1's "non-evaluable fraction > 30% fails the case" threshold was set by
     convention (borrowed from the G5 regime-bin rule), not from evidence.
     Nobody has seen how much of a real CARE case is actually lost to >3h
     gaps, so 30% may be far too strict or far too generous.
  2. Sentinel values (-999, 9999, and friends) are not missing values to a
     CSV reader — they parse as perfectly good floats and will silently
     poison a Mahalanobis covariance or a bearing-temperature regression.
     They must be found before either scorer is fitted, not after.

This script produces both, plus per-column missing rates, so the 30%
threshold can be set from the data instead of from habit.

WHAT IT REPORTS
---------------
Per farm, per column:  missing rate, sentinel candidates with their counts,
                       basic distribution
Per case:              the C1 gap profile computed with the real policy
                       (<=1h interpolate, <=3h forward-fill, >3h non-evaluable)
                       so the resulting non-evaluable fraction is directly
                       comparable to C1's threshold
Across cases:          the distribution of non-evaluable fractions, with the
                       percentiles needed to choose a defensible threshold

SENTINEL DETECTION
------------------
Two SEPARATE outputs, because the real archive showed one rule is not enough:

  sentinel_candidates    conventional codes only (-999, 9999, -32768, ...),
                         judged on an absolute count of 20+. Safe to treat as
                         missing. -1.0 is deliberately excluded: it is an
                         ordinary pitch angle or sub-zero temperature.
  repeated_value_notes   ADVISORY. Values that repeat and sit outside the IQR.
                         On the 2026-08-14 run this rule alone flagged 83
                         columns in Farm C on values like 0.1, 180.0, 850.0 and
                         -3.99 -- a quantisation floor, a nacelle direction, a
                         rated power and a temperature rail. Physics, not
                         corruption. Never auto-drop these.

Exact zero is never flagged: a curtailed turbine really does produce 0 kW.

Flagging is advisory. The script does not rewrite any data.

USAGE
-----
    python3 care_v6_quality_scan.py \\
        --workdir    /path/to/extracted_care_v6 \\
        --output-dir ./quality_scan_out \\
        [--case-glob "**/datasets/*.csv"] \\
        [--cases-per-farm 0]        # 0 = all cases (slow on Farm C)
        [--max-rows-per-case 0]     # 0 = every row
        [--timestamp-col time_stamp]

Farm C has 957 columns x ~55k rows x 58 cases. Start with
--cases-per-farm 5 for a first look; run the full scan once the shape of
the output is agreed.

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
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
]

# -1.0 is deliberately NOT here. It is a perfectly ordinary reading for a
# pitch angle or a sub-zero temperature, and on the real archive it was the
# single biggest source of false flags.
CONVENTIONAL_SENTINELS = {
    -9999.0, -999.0, -99.0,
    9999.0, 999.0, 99999.0, -99999.0,
    -32768.0, 32767.0, 65535.0,
}

NON_SIGNAL = {"asset_id", "id", "time_stamp", "train_test", "status_type_id"}

SHORT_GAP = timedelta(hours=1)
LONG_GAP = timedelta(hours=3)

REPEAT_FRACTION_THRESHOLD = 0.002   # 0.2% of values identical (non-conventional)
CONVENTIONAL_SENTINEL_MIN_COUNT = 20  # absolute count; fractions dilute across cases
IQR_OUTLIER_MULTIPLE = 5.0

# --- CSV dialect handling -------------------------------------------------
# CARE v6 case files are not guaranteed to be comma-separated. A semicolon
# file read with the default dialect yields a single mega-column, which is
# how three separate tools failed at once on 2026-08-14: the quality scan
# saw "1 column", the split audit could not find train_test, and the sensor
# profiler could not find any power/wind anchor. Detect it instead of
# assuming, and let the operator override.
CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]


def sniff_delimiter(path, override=None):
    """Pick the delimiter that splits the HEADER line into the most fields."""
    if override:
        return {"tab": "\t", "\\t": "\t"}.get(override, override)
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            header = f.readline()
    except OSError:
        return ","
    best, best_count = ",", -1
    for d in CANDIDATE_DELIMITERS:
        count = header.count(d)
        if count > best_count:
            best, best_count = d, count
    return best


def farm_from_path(path, workdir):
    """Farm name is the directory that CONTAINS `datasets`, not the first
    component under --workdir: pointing --workdir one level too high
    otherwise collapses every farm into a single group."""
    rel = os.path.normpath(os.path.relpath(path, workdir))
    parts = rel.split(os.sep)
    for i, part in enumerate(parts):
        if part.lower() == "datasets" and i > 0:
            return parts[i - 1]
    return parts[0] if len(parts) > 1 else "(root)"


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
    if raw is None:
        return None
    v = raw.strip() if isinstance(raw, str) else raw
    if v == "" or (isinstance(v, str) and v.lower() in ("nan", "na", "n/a", "null", "none")):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        # Semicolon-delimited exports often carry comma decimal separators.
        if isinstance(v, str) and "," in v:
            try:
                f = float(v.replace(",", ".", 1))
            except ValueError:
                return None
        else:
            return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def detect_sentinels(values):
    """Return (sentinels, repeated_notes).

    Two OUTPUTS, not one, because the 2026-08-14 real run showed the
    statistical rule alone has poor precision: it flagged 83 columns in Farm C
    on values like 0.1, 180.0, 850.0 and -3.99 -- a quantisation floor, a
    nacelle direction, a rated power and a temperature rail. Those are
    physics, not corruption. Calling them sentinels would have had the sensor
    profiler discard real data.

    sentinels      conventional codes only (-999, 9999, -32768, ...), judged
                   on an absolute count. Safe to treat as missing.
    repeated_notes everything else that repeats and sits outside the bulk of
                   the distribution. ADVISORY ONLY -- most entries here are
                   physical rails. Never auto-drop these; show them to a human.
    """
    n = len(values)
    if n < 200:
        return [], []
    counts = Counter(values)
    sv = sorted(values)
    q1, q3 = quantile(sv, 0.25), quantile(sv, 0.75)
    iqr = (q3 - q1) if (q1 is not None and q3 is not None) else 0.0
    lo = q1 - IQR_OUTLIER_MULTIPLE * iqr if iqr > 0 else None
    hi = q3 + IQR_OUTLIER_MULTIPLE * iqr if iqr > 0 else None

    sentinels, notes = [], []
    for value, count in counts.most_common(25):
        frac = count / n
        if value == 0.0:
            continue  # a curtailed turbine really does produce 0 kW
        if value in CONVENTIONAL_SENTINELS:
            if count >= CONVENTIONAL_SENTINEL_MIN_COUNT:
                sentinels.append({"value": value, "count": count,
                                  "fraction": round(frac, 6),
                                  "reason": "conventional sentinel code"})
            continue
        if lo is not None and (value < lo or value > hi) and frac >= REPEAT_FRACTION_THRESHOLD:
            notes.append({"value": value, "count": count,
                          "fraction": round(frac, 6),
                          "reason": "repeated value outside the IQR",
                          "likely_physical": True})
    return sentinels, notes[:5]


def gap_profile(timestamps):
    """C1 policy applied to the timestamp series itself: classify wall-clock
    gaps between consecutive rows."""
    ts = [t for t in timestamps if t is not None]
    n_unparseable = len(timestamps) - len(ts)
    if len(ts) < 2:
        return {"error": "fewer than 2 parseable timestamps",
                "n_unparseable_timestamps": n_unparseable}

    ts.sort()
    buckets = Counter()
    non_evaluable_seconds = 0.0
    long_gaps = []
    intervals = []
    for a, b in zip(ts, ts[1:]):
        d = b - a
        intervals.append(d.total_seconds())
        if d <= SHORT_GAP:
            buckets["within_1h_interpolate"] += 1
        elif d <= LONG_GAP:
            buckets["1h_to_3h_forward_fill"] += 1
        else:
            buckets["over_3h_non_evaluable"] += 1
            non_evaluable_seconds += d.total_seconds()
            long_gaps.append({"from": a.isoformat(), "to": b.isoformat(),
                              "gap_hours": round(d.total_seconds() / 3600.0, 2)})

    span_seconds = (ts[-1] - ts[0]).total_seconds()
    nominal = statistics.median(intervals) if intervals else None
    return {
        "n_timestamps": len(ts),
        "n_unparseable_timestamps": n_unparseable,
        "first": ts[0].isoformat(),
        "last": ts[-1].isoformat(),
        "span_days": round(span_seconds / 86400.0, 2),
        "median_interval_minutes": round(nominal / 60.0, 2) if nominal else None,
        "gap_buckets": dict(buckets),
        "n_gaps_over_3h": buckets["over_3h_non_evaluable"],
        "non_evaluable_days": round(non_evaluable_seconds / 86400.0, 2),
        "non_evaluable_fraction_of_span": (
            round(non_evaluable_seconds / span_seconds, 4) if span_seconds > 0 else None),
        "longest_gaps": sorted(long_gaps, key=lambda g: -g["gap_hours"])[:10],
    }


def scan_case(path, timestamp_col, max_rows, delimiter_override=None):
    delimiter = sniff_delimiter(path, delimiter_override)
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        header = next(csv.reader(f, delimiter=delimiter), None)
    if not header:
        return None

    stride = 1
    if max_rows:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            total = sum(1 for _ in f) - 1
        if total > max_rows:
            stride = max(1, total // max_rows)

    present = defaultdict(list)
    n_rows_by_col = Counter()
    timestamps = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            if stride > 1 and i % stride:
                continue
            timestamps.append(parse_ts(row.get(timestamp_col)))
            for col in header:
                if col in NON_SIGNAL:
                    continue
                n_rows_by_col[col] += 1
                v = to_float(row.get(col))
                if v is not None:
                    present[col].append(v)
    return {"header": header, "present": present,
            "n_rows_by_col": n_rows_by_col, "timestamps": timestamps,
            "stride": stride, "delimiter": delimiter}


def run(args):
    files = sorted(glob.glob(os.path.join(args.workdir, args.case_glob), recursive=True))
    if not files:
        print("no case files matched %r" % args.case_glob, file=sys.stderr)
        return 3
    os.makedirs(args.output_dir, exist_ok=True)

    by_farm = defaultdict(list)
    for path in files:
        by_farm[farm_from_path(path, args.workdir)].append(path)

    per_case_gaps = {}
    farm_reports = {}

    for farm, farm_files in sorted(by_farm.items()):
        selected = farm_files if not args.cases_per_farm else farm_files[:args.cases_per_farm]
        print("[%s] scanning %d of %d cases" % (farm, len(selected), len(farm_files)),
              file=sys.stderr)

        agg_present = defaultdict(list)
        agg_rows = Counter()
        delimiter_seen = None
        for k, path in enumerate(selected, 1):
            res = scan_case(path, args.timestamp_col, args.max_rows_per_case,
                            args.delimiter)
            if not res:
                continue
            delimiter_seen = res.get("delimiter")
            case_id = os.path.splitext(os.path.basename(path))[0]
            per_case_gaps[case_id] = gap_profile(res["timestamps"])
            per_case_gaps[case_id]["farm"] = farm
            per_case_gaps[case_id]["row_stride_used"] = res["stride"]
            for col, vals in res["present"].items():
                agg_present[col].extend(vals)
            agg_rows.update(res["n_rows_by_col"])
            if k % 10 == 0:
                print("  %d/%d" % (k, len(selected)), file=sys.stderr)

        columns = {}
        for col, n_total in sorted(agg_rows.items()):
            vals = agg_present.get(col, [])
            n_present = len(vals)
            entry = {
                "n_rows": n_total,
                "n_present": n_present,
                "missing_fraction": round(1 - n_present / n_total, 6) if n_total else None,
            }
            if n_present:
                sv = sorted(vals)
                zeros = sum(1 for v in vals if v == 0.0)
                entry.update({
                    "min": sv[0], "p01": quantile(sv, 0.01), "median": quantile(sv, 0.50),
                    "p99": quantile(sv, 0.99), "max": sv[-1],
                    "std": round(statistics.pstdev(vals), 6) if n_present > 1 else 0.0,
                    "frac_exactly_zero": round(zeros / n_present, 6),
                })
                sent, notes = detect_sentinels(vals)
                entry["sentinel_candidates"] = sent
                entry["repeated_value_notes"] = notes
            columns[col] = entry

        flagged = {c: e["sentinel_candidates"] for c, e in columns.items()
                   if e.get("sentinel_candidates")}
        repeated = {c: e["repeated_value_notes"] for c, e in columns.items()
                    if e.get("repeated_value_notes")}
        high_missing = {c: e["missing_fraction"] for c, e in columns.items()
                        if (e.get("missing_fraction") or 0) > 0.30}
        all_missing = [c for c, e in columns.items() if e["n_present"] == 0]

        farm_reports[farm] = {
            "delimiter_used": delimiter_seen,
            "n_cases_scanned": len(selected),
            "n_cases_total": len(farm_files),
            "n_columns": len(columns),
            "n_columns_with_sentinel_candidates": len(flagged),
            "columns_with_sentinel_candidates": flagged,
            "n_columns_with_repeated_value_notes": len(repeated),
            "repeated_value_notes_advisory_only": (
                "These are NOT sentinels. Most are physical rails, quantisation "
                "floors or rated limits. Review by eye; never auto-drop."),
            "columns_with_repeated_value_notes": repeated,
            "n_columns_missing_over_30pct": len(high_missing),
            "columns_missing_over_30pct": high_missing,
            "n_columns_entirely_empty": len(all_missing),
            "columns_entirely_empty": all_missing,
            "columns": columns,
        }
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in farm)
        with open(os.path.join(args.output_dir, "g4_quality_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump({"farm": farm, **farm_reports[farm]}, f, indent=2, ensure_ascii=False)

    # C1 threshold evidence.
    fracs = sorted(
        p["non_evaluable_fraction_of_span"] for p in per_case_gaps.values()
        if p.get("non_evaluable_fraction_of_span") is not None)
    threshold_evidence = {
        "note": (
            "non_evaluable_fraction is computed from wall-clock gaps between "
            "consecutive rows using C1's own policy (>3h = non-evaluable). It is "
            "directly comparable to C1's threshold, which is currently 0.30 by "
            "convention rather than by evidence."),
        "n_cases": len(fracs),
        "min": fracs[0] if fracs else None,
        "p50": quantile(fracs, 0.50),
        "p75": quantile(fracs, 0.75),
        "p90": quantile(fracs, 0.90),
        "p95": quantile(fracs, 0.95),
        "p99": quantile(fracs, 0.99),
        "max": fracs[-1] if fracs else None,
        "n_cases_over_current_30pct_threshold": sum(1 for f in fracs if f > 0.30),
        "n_cases_over_10pct": sum(1 for f in fracs if f > 0.10),
        "n_cases_over_50pct": sum(1 for f in fracs if f > 0.50),
        "reading": _threshold_reading(fracs),
    }

    with open(os.path.join(args.output_dir, "c1_gap_profile.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "policy": {"interpolate_max_hours": 1, "forward_fill_max_hours": 3,
                       "non_evaluable_above_hours": 3},
            "threshold_evidence": threshold_evidence,
            "per_case": per_case_gaps,
        }, f, indent=2, ensure_ascii=False)

    total_sentinels = sum(r["n_columns_with_sentinel_candidates"] for r in farm_reports.values())
    print("\n--- quality scan ---")
    for farm, r in sorted(farm_reports.items()):
        if r["n_columns"] <= 2:
            print("%-14s only %d column(s) parsed -- that is almost certainly a "
                  "delimiter mismatch. Re-run with --delimiter ';' (or 'tab')."
                  % (farm, r["n_columns"]))
        print("%-14s %4d columns | sentinels %3d | repeated-value notes %3d | "
              ">30%% missing %3d | empty %3d"
              % (farm, r["n_columns"], r["n_columns_with_sentinel_candidates"],
                 r["n_columns_with_repeated_value_notes"],
                 r["n_columns_missing_over_30pct"], r["n_columns_entirely_empty"]))
    print("\nC1 non-evaluable fraction across %d cases:" % threshold_evidence["n_cases"])
    for k in ("min", "p50", "p75", "p90", "p95", "p99", "max"):
        print("  %-4s %s" % (k, threshold_evidence[k]))
    print("  cases over the current 30%% threshold: %d"
          % threshold_evidence["n_cases_over_current_30pct_threshold"])
    print("\n%s" % threshold_evidence["reading"])
    if total_sentinels:
        print("\n%d column(s) carry conventional sentinel codes — inspect before fitting either "
              "scorer; they parse as valid floats and will poison a covariance." % total_sentinels)
    print("\nWrote %s" % args.output_dir, file=sys.stderr)
    return 0


def _threshold_reading(fracs):
    if not fracs:
        return "No case produced a usable gap profile; nothing can be said about C1's threshold."
    over = sum(1 for f in fracs if f > 0.30)
    p95 = quantile(fracs, 0.95)
    if over == 0:
        return ("No case exceeds the current 30%% threshold (p95 = %.3f). The threshold "
                "is not binding on this archive — it neither excludes anything nor "
                "protects against anything. Consider tightening it to roughly p95 so it "
                "can actually catch a degraded case, and record the change." % p95)
    if over > len(fracs) * 0.25:
        return ("%d of %d cases (%.0f%%) exceed the current 30%% threshold. Either long "
                "outages are normal in this archive and the threshold is too strict, or "
                "the gap policy needs revisiting. Do not silently drop a quarter of the "
                "archive." % (over, len(fracs), 100.0 * over / len(fracs)))
    return ("%d of %d cases exceed the current 30%% threshold (p95 = %.3f). That is a "
            "plausible exclusion rate; confirm the excluded cases really are degraded "
            "rather than merely seasonal before freezing the threshold."
            % (over, len(fracs), p95))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case-glob", default="**/datasets/*.csv")
    ap.add_argument("--cases-per-farm", type=int, default=0,
                    help="0 = every case (slow on Farm C); try 5 for a first look")
    ap.add_argument("--max-rows-per-case", type=int, default=0,
                    help="0 = every row; a positive value strides the read")
    ap.add_argument("--timestamp-col", default="time_stamp")
    ap.add_argument("--delimiter", default=None,
                    help="CSV delimiter; auto-detected from the header when omitted "
                         "(use 'tab' for tab-separated)")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
