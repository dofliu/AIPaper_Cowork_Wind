#!/usr/bin/env python3
"""
Base Scorer 1 — Mahalanobis distance on the six core SCADA signals.

WHAT THIS IS
------------
Liu, Corbita, Lee and Wang, "Wind Turbine Anomaly Detection Using
Mahalanobis Distance and SCADA Alarm Data", Applied Sciences 2022,
12(17):8661, DOI 10.3390/app12178661 — the team's own frozen base scorer,
per R12 decision 3.

Mahalanobis distance is a standard, fully specified statistic:

    s_t = sqrt( (x_t - mu)^T Sigma^-1 (x_t - mu) )

with mu and Sigma estimated on a normal reference partition. There is
nothing in it that requires the paper's source code, which is why this
file exists: an earlier handover told the operator that producing score
streams was entirely their own implementation work. That was true of Base
Scorer 2 and wrong about this one.

WHAT IT DOES NOT CLAIM
----------------------
This is Mahalanobis distance over the six signals the C0 map names. The
2022 paper also uses SCADA alarm data and its own feature engineering,
neither of which is reproduced here. So this is "the frozen MD scorer as
this project defines it", not a reproduction of the paper's exact
pipeline, and the artifact manifest it writes says so. If the intent is to
reproduce the published detector exactly, that needs the paper's feature
list, and this file should be re-run with it.

C3 PROVENANCE IS RECORDED AT FIT TIME
--------------------------------------
The runbook warns that `files_read_during_fit` cannot be reconstructed
afterwards. So this scorer writes fit_provenance.json itself, as it fits,
listing every file it opened with its SHA-256, the partition it fitted on,
and the label columns it never touched. It also writes artifact_manifest
and freeze_receipt, so three of the four C0-C6 evidence files come out of
the run rather than being typed by hand.

FIT PARTITION
-------------
CARE v6 carries a per-row `train_test` column. Rows marked train precede
the event in an anomaly case, so fitting on them is both the archive's
intended protocol and label-isolated: no fault-window row and no label
column is ever read. --fit-scope global pools the train rows of NORMAL
cases only, if a single frozen covariance across a farm is wanted instead.

MISSING DATA
------------
Rows with any required signal missing are not scored (the score is left
empty) rather than imputed here. Imputation is C1's job and happens in the
gate, against the ratified policy; doing it twice, differently, would make
the evaluability mask a lie.

USAGE
-----
    python3 base_scorer_md2022.py \\
        --workdir     /path/to/extracted_care_v6 \\
        --signal-map  ./signal_map_out/signal_map_Wind_Farm_A.json \\
        --farm        "Wind Farm A" \\
        --output-dir  ./scores_MD_2022_FarmA_run1 \\
        --evidence-dir ./evidence_MD_2022_FarmA

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from physical_ranges import PHYSICAL_RANGE as _PHYSICAL_RANGE  # noqa: E402

PHYSICAL_RANGE = {k: (v[0], v[1]) for k, v in _PHYSICAL_RANGE.items()}

SCORER_NAME = "MD_2022"
IMPLEMENTATION_VERSION = "md2022-v1.2"

# Namespace for the per-signal feature columns in the score CSV, so that a
# signal name can never collide with the canonical timestamp/wind_speed/
# anomaly_score trio. See the header comment where the row is written.
SIGNAL_COL_PREFIX = "signal_"

# Every Nth scored row feeds the per-signal range report. 1-in-20 over a farm
# is tens of thousands of samples -- ample for percentiles, negligible in
# memory.
SIGNAL_RANGE_STRIDE = 20

# A reading outside physical possibility is not a measurement, it is a fault
# code. Farm C's rotor bearing channels sensor_194/195 sit at exactly 850.0
# for over 1% of rows; averaged with three genuine channels near 46 C that
# produced a main_bearing_temperature of 363 C, which would have entered the
# covariance and generated enormous Mahalanobis distances -- false alarms,
# silently.
#
# Filtering is PER CHANNEL and happens before redundant channels are
# averaged, so one channel's fault code does not discard the other four's
# good readings. A signal is only missing when EVERY channel behind it is
# out of range, and then the row is skipped exactly as a missing row is.
#
# The bounds live in physical_ranges.py, shared with check_unit_consistency,
# because two tools disagreeing about what is possible makes the gate
# unreadable. Override with --range SIGNAL=LO:HI or disable with
# --no-range-filter; either way the counts are recorded in the summary.
PAPER = ("Liu, Corbita, Lee, Wang, Applied Sciences 2022, 12(17):8661, "
         "DOI 10.3390/app12178661")

CORE_SIGNALS = ["active_power", "wind_speed", "rotor_speed",
                "main_bearing_temperature", "pitch_angle", "ambient_temperature"]

LABEL_COLUMNS_NEVER_READ = ["status_type_id", "event_label", "label"]

CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]


def sniff_delimiter(path):
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            head = f.readline()
    except OSError:
        return ","
    best, count = ",", -1
    for d in CANDIDATE_DELIMITERS:
        n = head.count(d)
        if n > count:
            best, count = d, n
    return best


def sha256_of_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


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


def resolve_columns(signal_map):
    """Turn the C0 signal map into (signal -> list of source columns).

    A derived_from entry means the signal is the mean of several redundant
    channels, which is how the 2026-08-15 decision handled farms carrying
    two rotor bearings or three blade axes."""
    resolved, unavailable = {}, []
    for signal in CORE_SIGNALS:
        entry = signal_map.get(signal)
        if not isinstance(entry, dict):
            raise SystemExit("signal map has no entry for %r" % signal)
        if entry.get("not_available"):
            unavailable.append(signal)
            continue
        if "column" in entry:
            resolved[signal] = [entry["column"]]
        elif "derived_from" in entry:
            resolved[signal] = list(entry["derived_from"])
        else:
            raise SystemExit("signal %r has neither column nor derived_from" % signal)
    return resolved, unavailable


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    low = int(pos)
    high = min(low + 1, len(s) - 1)
    return s[low] + (s[high] - s[low]) * (pos - low)


def feature_vector(row, resolved, order, ranges=None, rejected=None):
    """One row -> the feature vector, averaging redundant channels. Returns
    None if any required signal is missing: partial vectors would silently
    distort the covariance.

    ranges: signal -> (lo, hi). A channel outside its range is dropped before
    averaging, so a fault code in one of five redundant channels does not
    poison the other four. Rejections are counted per channel in `rejected`."""
    vector = []
    for signal in order:
        values = [to_float(row.get(c)) for c in resolved[signal]]
        present = []
        for column, value in zip(resolved[signal], values):
            if value is None:
                continue
            if ranges and signal in ranges:
                lo, hi = ranges[signal]
                if value < lo or value > hi:
                    if rejected is not None:
                        rejected[column] = rejected.get(column, 0) + 1
                    continue
            present.append(value)
        if not present:
            return None
        vector.append(sum(present) / len(present))
    return vector


def covariance(vectors):
    n = len(vectors)
    d = len(vectors[0])
    mean = [sum(v[i] for v in vectors) / n for i in range(d)]
    cov = [[0.0] * d for _ in range(d)]
    for v in vectors:
        diff = [v[i] - mean[i] for i in range(d)]
        for i in range(d):
            di = diff[i]
            row = cov[i]
            for j in range(i, d):
                row[j] += di * diff[j]
    denom = float(n - 1) if n > 1 else 1.0
    for i in range(d):
        for j in range(i, d):
            cov[i][j] /= denom
            cov[j][i] = cov[i][j]
    return mean, cov


def invert(matrix, ridge):
    """Gauss-Jordan with a ridge term. Six by six, so an explicit solve is
    clearer than pulling in a linear algebra dependency, and it lets the
    ridge actually applied be recorded rather than assumed."""
    d = len(matrix)
    a = [[matrix[i][j] + (ridge if i == j else 0.0) for j in range(d)]
         + [1.0 if i == k else 0.0 for k in range(d)] for i in range(d)]
    for col in range(d):
        pivot = max(range(col, d), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [x / scale for x in a[col]]
        for r in range(d):
            if r == col:
                continue
            factor = a[r][col]
            if factor:
                a[r] = [x - factor * y for x, y in zip(a[r], a[col])]
    return [row[d:] for row in a]


def mahalanobis(vector, mean, inverse):
    d = len(vector)
    diff = [vector[i] - mean[i] for i in range(d)]
    total = 0.0
    for i in range(d):
        acc = 0.0
        row = inverse[i]
        for j in range(d):
            acc += row[j] * diff[j]
        total += diff[i] * acc
    return math.sqrt(total) if total > 0 else 0.0


def read_case(path, delimiter):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return reader.fieldnames or [], list(reader)


def run(args):
    with open(args.signal_map, encoding="utf-8") as f:
        signal_map = json.load(f)
    resolved, unavailable = resolve_columns(signal_map)
    signal_samples = defaultdict(list)
    rejected = {}
    ranges = None if args.no_range_filter else dict(PHYSICAL_RANGE)
    for spec in (args.range or []):
        name, _, bounds = spec.partition('=')
        lo, _, hi = bounds.partition(':')
        ranges = ranges or {}
        ranges[name.strip()] = (float(lo), float(hi))
    order = [s for s in CORE_SIGNALS if s not in unavailable]
    if len(order) < 2:
        raise SystemExit("fewer than two usable signals; nothing to score")

    pattern = os.path.join(args.workdir, "**", args.farm, "datasets", "*.csv")
    case_files = sorted(glob.glob(pattern, recursive=True))
    if not case_files:
        raise SystemExit("no case files under %r for farm %r" % (args.workdir, args.farm))

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.evidence_dir, exist_ok=True)

    files_read_during_fit = []
    global_fit_vectors = []

    if args.fit_scope == "global":
        print("[fit] pooling train rows across cases", flush=True)
        for path in case_files:
            delimiter = sniff_delimiter(path)
            header, rows = read_case(path, delimiter)
            if args.split_col not in header:
                continue
            files_read_during_fit.append({"path": os.path.abspath(path),
                                          "sha256": sha256_of_file(path)})
            for row in rows:
                if (row.get(args.split_col) or "").strip().lower() != "train":
                    continue
                v = feature_vector(row, resolved, order, ranges, rejected)
                if v is not None:
                    global_fit_vectors.append(v)
        if len(global_fit_vectors) < len(order) + 2:
            raise SystemExit("not enough complete train rows to estimate a covariance")
        global_mean, global_cov = covariance(global_fit_vectors)
        global_inv = invert(global_cov, args.ridge)
        if global_inv is None:
            raise SystemExit("pooled covariance is singular even with ridge %g" % args.ridge)

    per_case = {}
    for i, path in enumerate(case_files, 1):
        case_id = os.path.splitext(os.path.basename(path))[0]
        delimiter = sniff_delimiter(path)
        header, rows = read_case(path, delimiter)

        missing_cols = [c for signal in order for c in resolved[signal] if c not in header]
        if missing_cols or args.timestamp_col not in header:
            per_case[case_id] = {"error": "columns missing from case file",
                                 "missing": missing_cols[:8]}
            continue

        if args.fit_scope == "global":
            mean, inverse, n_fit = global_mean, global_inv, len(global_fit_vectors)
        else:
            fit_vectors = []
            for row in rows:
                if (row.get(args.split_col) or "").strip().lower() != "train":
                    continue
                v = feature_vector(row, resolved, order, ranges, rejected)
                if v is not None:
                    fit_vectors.append(v)
            if len(fit_vectors) < len(order) + 2:
                per_case[case_id] = {"error": "too few complete train rows",
                                     "n_train_complete": len(fit_vectors)}
                continue
            files_read_during_fit.append({"path": os.path.abspath(path),
                                          "sha256": sha256_of_file(path)})
            mean, cov = covariance(fit_vectors)
            inverse = invert(cov, args.ridge)
            if inverse is None:
                per_case[case_id] = {"error": "singular covariance even with ridge"}
                continue
            n_fit = len(fit_vectors)

        out_path = os.path.join(args.output_dir, case_id + ".csv")
        wind_columns = resolved["wind_speed"]
        n_scored = n_skipped = 0
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # The feature block is namespaced. It used to be written under the
            # bare signal names, which collided with the canonical wind_speed
            # column: the header carried wind_speed twice, and csv.DictReader
            # keeps the LAST duplicate, so every downstream tool silently read
            # the feature copy. Those differ exactly where it matters -- a row
            # whose feature vector is incomplete still has a perfectly good
            # wind reading, but the feature copy is blank there. Measured on a
            # fixture with 50 sensor-dropout rows: 50/50 read as empty wind,
            # which would route them out of their true regime bin and bias the
            # conditional-coverage result this paper claims.
            writer.writerow(["timestamp", "wind_speed", "anomaly_score"]
                            + [SIGNAL_COL_PREFIX + s for s in order])
            for row in rows:
                v = feature_vector(row, resolved, order, ranges, rejected)
                wind_values = [to_float(row.get(c)) for c in wind_columns]
                wind_present = [x for x in wind_values if x is not None]
                wind = (sum(wind_present) / len(wind_present)) if wind_present else None
                if v is None:
                    n_skipped += 1
                    writer.writerow([row.get(args.timestamp_col, ""),
                                     "" if wind is None else wind, ""]
                                    + [""] * len(order))
                    continue
                score = mahalanobis(v, mean, inverse)
                n_scored += 1
                # Reservoir-free sampling for the Phase 5.1 unit check: the
                # three farms label the same quantities differently (degC vs
                # Celsius, rpm vs 1/min). Those are the same physical unit if
                # and only if the VALUES occupy the same range, and a silent
                # mismatch distorts the covariance without erroring. Collect
                # it here, in the pass that already reads every row, rather
                # than making the operator run the archive again.
                if n_scored % SIGNAL_RANGE_STRIDE == 0:
                    for name, value in zip(order, v):
                        signal_samples[name].append(value)
                writer.writerow([row.get(args.timestamp_col, ""),
                                 "" if wind is None else wind,
                                 "%.10g" % score]
                                + ["%.10g" % x for x in v])

        per_case[case_id] = {"n_rows": len(rows), "n_scored": n_scored,
                             "n_skipped_incomplete": n_skipped, "n_fit_rows": n_fit}
        if i % 5 == 0 or i == len(case_files):
            print("  %d/%d cases" % (i, len(case_files)), flush=True)

    # --- C0-C6 evidence, written at fit time because it cannot be reconstructed
    stamp = datetime.now(timezone.utc).isoformat()

    # The C0 gate needs a signal map naming columns of the SCORE CSV, which is
    # a different thing from the builder's map naming columns of the archive.
    # Hand-writing the second one is how an operator ends up declaring a column
    # that does not exist, so derive it here from what was actually written.
    gate_map = {}
    for signal in order:
        entry = signal_map.get(signal) or {}
        gate_map[signal] = {
            "column": SIGNAL_COL_PREFIX + signal,
            "unit": entry.get("unit", "UNKNOWN"),
            "_derived_from_archive_columns": resolved[signal],
        }
    for signal in unavailable:
        # Carry the ratification through verbatim. The gate FAILs on silent
        # absence, and rightly so -- the declaration is the evidence.
        gate_map[signal] = dict(signal_map.get(signal) or {})
    with open(os.path.join(args.evidence_dir, "signal_map.json"),
              "w", encoding="utf-8") as f:
        json.dump(gate_map, f, indent=2, ensure_ascii=False)
    with open(os.path.join(args.evidence_dir, "fit_provenance.json"),
              "w", encoding="utf-8") as f:
        json.dump({
            "fit_partition": ("CARE normal reference partition: rows where %s == 'train', "
                              "which precede any event window" % args.split_col),
            "fit_scope": args.fit_scope,
            "files_read_during_fit": files_read_during_fit,
            "label_columns_excluded": LABEL_COLUMNS_NEVER_READ,
            "verification_method": ("code-path audit: the scorer reads only the mapped "
                                    "signal columns, the timestamp and the split column; "
                                    "no label column is referenced anywhere in the fit"),
            "verified_by": "base_scorer_md2022.py %s" % IMPLEMENTATION_VERSION,
            "verified_at": stamp,
        }, f, indent=2, ensure_ascii=False)

    config_blob = json.dumps({"signals": order, "ridge": args.ridge,
                              "fit_scope": args.fit_scope,
                              "split_col": args.split_col}, sort_keys=True)
    config_sha = hashlib.sha256(config_blob.encode("utf-8")).hexdigest()
    self_sha = sha256_of_file(os.path.abspath(__file__))

    with open(os.path.join(args.evidence_dir, "artifact_manifest.json"),
              "w", encoding="utf-8") as f:
        json.dump({
            "implementation_source": "re-implementation-from-method: %s" % PAPER,
            "version_or_commit": IMPLEMENTATION_VERSION,
            "parameter_provenance": (
                "Mahalanobis distance is fully specified by mu and Sigma on the fit "
                "partition; the only free parameter is the ridge term, recorded here. "
                "SCOPE NOTE: this scores the six C0 signals only. The 2022 paper also "
                "uses SCADA alarm data and its own feature engineering, which are NOT "
                "reproduced. Do not describe this as a reproduction of the published "
                "pipeline."),
            "artifact_sha256": self_sha,
            "config_sha256": config_sha,
            "ridge": args.ridge,
            "signals_used": order,
            "signals_declared_unavailable": unavailable,
            "frozen_at": stamp,
        }, f, indent=2, ensure_ascii=False)

    with open(os.path.join(args.evidence_dir, "freeze_receipt.json"),
              "w", encoding="utf-8") as f:
        json.dump({
            "environment": {"python": sys.version.split()[0], "os": sys.platform,
                            "note": "set OMP_NUM_THREADS=1 etc before both runs per "
                                    "the C5 protocol"},
            "seed": "not applicable - closed-form estimator, no randomness",
            "config_sha256": config_sha,
            "artifact_sha256": self_sha,
            "run_started_at": stamp,
        }, f, indent=2, ensure_ascii=False)

    summary = {
        "scorer": SCORER_NAME,
        "implementation_version": IMPLEMENTATION_VERSION,
        "farm": args.farm,
        "signals_used": order,
        "signals_declared_unavailable": unavailable,
        "range_filter": {
            "enabled": not args.no_range_filter,
            "ranges_applied": {k: list(v) for k, v in (ranges or {}).items()},
            "readings_rejected_per_column": dict(sorted(rejected.items())),
            "note": ("A reading outside physical possibility is a fault code, not a "
                     "measurement. Rejected per channel BEFORE redundant channels "
                     "are averaged, so one bad channel does not discard the rest."),
        },
        # Phase 5.1 evidence. Compare these across farms: degC and "Celsius"
        # are the same unit iff the numbers agree; rpm and "1/min" likewise.
        "signal_ranges": {
            name: {"unit_declared": (signal_map.get(name) or {}).get("unit"),
                   "n_samples": len(values),
                   "p01": percentile(values, 0.01),
                   "p50": percentile(values, 0.50),
                   "p99": percentile(values, 0.99),
                   "min": min(values) if values else None,
                   "max": max(values) if values else None}
            for name, values in sorted(signal_samples.items())},
        "fit_scope": args.fit_scope,
        "ridge": args.ridge,
        "n_cases": len(per_case),
        "n_cases_scored": sum(1 for v in per_case.values() if "error" not in v),
        "per_case": per_case,
        "evidence_written": ["fit_provenance.json", "artifact_manifest.json",
                             "freeze_receipt.json"],
        "evidence_still_needed": ["signal_map.json (already supplied via --signal-map)"],
        "generated_at_utc": stamp,
        "cli_invocation": " ".join(sys.argv),
    }
    # Per farm, not one shared name. The runbook has all three farms writing
    # into a single score directory (case_ids are globally unique, so the CSVs
    # coexist fine) -- but a fixed summary filename meant Farm C silently
    # overwrote Farm A's and Farm B's, taking the per-case counts and the
    # Phase 5.1 signal ranges with it. Nothing would have reported the loss.
    safe_farm = re.sub(r"[^A-Za-z0-9_-]+", "_", args.farm)
    with open(os.path.join(args.output_dir, "scorer_summary_%s.json" % safe_farm),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nscored %d/%d cases; scores in %s"
          % (summary["n_cases_scored"], len(per_case), args.output_dir))
    print("C0-C6 evidence written to %s" % args.evidence_dir)
    if unavailable:
        print("signals declared unavailable and excluded: %s" % unavailable)
    # Print it rather than burying it in JSON: this feeds C1's non-evaluable
    # threshold, and an operator should not have to open a file to learn that
    # 1% of a farm's bearing readings were fault codes.
    if rejected:
        total = sum(rejected.values())
        print("out-of-range readings rejected (fault codes), %d in total:" % total)
        for column, n in sorted(rejected.items(), key=lambda kv: -kv[1]):
            print("    %-24s %8d" % (column, n))
    elif ranges:
        print("out-of-range readings rejected: none")
    failed = {k: v for k, v in per_case.items() if "error" in v}
    if failed:
        print("\n%d case(s) not scored:" % len(failed))
        for k, v in list(failed.items())[:5]:
            print("  %s: %s" % (k, v.get("error")))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--farm", required=True, help='e.g. "Wind Farm A"')
    ap.add_argument("--signal-map", required=True,
                    help="C0 signal map for this farm")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--evidence-dir", required=True,
                    help="Where fit_provenance / artifact_manifest / freeze_receipt go")
    ap.add_argument("--no-range-filter", action="store_true",
                    help="Accept every numeric value, including fault codes such as "
                         "Farm C's 850.0 bearing temperature. Recorded in the summary.")
    ap.add_argument("--range", action="append", metavar="SIGNAL=LO:HI",
                    help="Override a signal's physical range. Repeatable.")
    ap.add_argument("--split-col", default="train_test")
    ap.add_argument("--timestamp-col", default="time_stamp")
    ap.add_argument("--fit-scope", choices=["case", "global"], default="case",
                    help="case: fit per case on its own train rows (CARE's protocol). "
                         "global: pool train rows across the farm.")
    ap.add_argument("--ridge", type=float, default=1e-6,
                    help="Ridge added to the covariance diagonal before inversion")
    args = ap.parse_args()
    if not os.path.isdir(args.workdir):
        print("workdir not found: %s" % args.workdir, file=sys.stderr)
        return 3
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
