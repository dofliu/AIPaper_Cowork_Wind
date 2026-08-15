#!/usr/bin/env python3
"""
Report the distribution of named raw columns, one line each.

WHY THIS EXISTS
---------------
When an averaged signal comes out implausible, the average is not the thing
to look at -- the members are. Farm C's main bearing temperature is the mean
of five channels and reaches 363 C at p99, which no bearing does. Either one
member carries sentinel values, or one member is a different component that
matched the same wording. Averaging hides which.

The same question arises for Farm C's rotor speed, whose members are named
"Rotor speed 1/2" and "Rotor speed gearbox main shaft 1/2" -- plausibly the
same shaft, plausibly not.

So: print each member separately, with its percentiles and the count of
values that look like sentinels, and the answer is visible.

USAGE
-----
    python3 inspect_channels.py \\
        --workdir /path/to/extracted_care_v6 \\
        --farm    "Wind Farm C" \\
        --columns sensor_194_avg,sensor_195_avg,sensor_196_avg,sensor_197_avg,sensor_198_avg

Add --correlate to also print the pairwise correlation between the columns:
members of the same physical quantity track each other closely; a different
component does not.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import math
import os
import sys

CANDIDATE_DELIMITERS = [";", ",", "\t", "|"]

# Values that are almost certainly "no reading" rather than a measurement.
SENTINELS = (-9999.0, -999.0, 9999.0, 99999.0, -99999.0, 32767.0, -32768.0)
SENTINEL_TOL = 1e-6


def sniff_delimiter(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        header = f.readline()
    best, best_count = ";", -1
    for d in CANDIDATE_DELIMITERS:
        n = header.count(d)
        if n > best_count:
            best, best_count = d, n
    return best


def to_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "na", "n/a", "null"):
        return None
    try:
        f = float(text)
    except ValueError:
        try:
            f = float(text.replace(",", ".", 1))
        except ValueError:
            return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def fmt(x):
    if x is None:
        return "n/a"
    return "%.2f" % x if abs(x) < 100000 else "%.3g" % x


def correlation(a, b):
    n = len(a)
    if n < 2:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--farm", required=True, help='e.g. "Wind Farm C"')
    ap.add_argument("--columns", required=True, help="Comma-separated column names")
    ap.add_argument("--max-files", type=int, default=8)
    ap.add_argument("--max-rows", type=int, default=300000)
    ap.add_argument("--correlate", action="store_true",
                    help="Also print pairwise correlations between the columns")
    args = ap.parse_args()

    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    farm_dir = os.path.join(args.workdir, args.farm)
    if not os.path.isdir(farm_dir):
        candidates = [d for d in glob.glob(os.path.join(args.workdir, "*"))
                      if os.path.isdir(d)
                      and args.farm.lower() in os.path.basename(d).lower()]
        if len(candidates) != 1:
            raise SystemExit("farm directory not found: %s" % farm_dir)
        farm_dir = candidates[0]

    files = []
    for pattern in (os.path.join(farm_dir, "datasets", "*.csv"),
                    os.path.join(farm_dir, "datasets", "*", "*.csv")):
        files = sorted(glob.glob(pattern))
        if files:
            break
    if not files:
        raise SystemExit("no case CSVs under %s/datasets" % farm_dir)
    files = files[:args.max_files]

    values = {c: [] for c in columns}
    aligned = {c: [] for c in columns}   # only rows where ALL columns are present
    n_rows = n_missing_any = 0
    for path in files:
        delimiter = sniff_delimiter(path)
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                continue
            missing = [c for c in columns if c not in header]
            if missing:
                raise SystemExit("column(s) %s not in %s.\nThat file has %d columns, "
                                 "for example: %s"
                                 % (missing, os.path.basename(path), len(header),
                                    header[:20]))
            idx = {c: header.index(c) for c in columns}
            for record in reader:
                if len(record) <= max(idx.values()):
                    continue
                n_rows += 1
                row = {c: to_float(record[idx[c]]) for c in columns}
                for c in columns:
                    if row[c] is not None:
                        values[c].append(row[c])
                if all(row[c] is not None for c in columns):
                    for c in columns:
                        aligned[c].append(row[c])
                else:
                    n_missing_any += 1
                if n_rows >= args.max_rows:
                    break
        if n_rows >= args.max_rows:
            break

    print("%s -- %d rows from %d case file(s)\n"
          % (os.path.basename(farm_dir), n_rows, len(files)))
    print("%-22s %8s %10s %10s %10s %10s %10s %8s"
          % ("column", "n", "min", "p01", "p50", "p99", "max", "sentinel"))
    print("-" * 96)
    for c in columns:
        v = sorted(values[c])
        if not v:
            print("%-22s %8d  (no numeric values)" % (c, 0))
            continue
        n_sent = sum(1 for x in v
                     if any(abs(x - s) < SENTINEL_TOL for s in SENTINELS))
        print("%-22s %8d %10s %10s %10s %10s %10s %8d"
              % (c, len(v), fmt(v[0]), fmt(percentile(v, 0.01)),
                 fmt(percentile(v, 0.50)), fmt(percentile(v, 0.99)),
                 fmt(v[-1]), n_sent))

    if n_missing_any:
        print("\n%d of %d rows had at least one of these columns missing"
              % (n_missing_any, n_rows))

    if args.correlate and len(columns) > 1 and aligned[columns[0]]:
        print("\npairwise correlation on %d complete rows:" % len(aligned[columns[0]]))
        print("  (members of one physical quantity track each other; a different "
              "component does not)")
        for i, a in enumerate(columns):
            for b in columns[i + 1:]:
                r = correlation(aligned[a], aligned[b])
                flag = ""
                if r is not None and r < 0.8:
                    flag = "   <-- LOW: probably not the same quantity"
                print("  %-22s %-22s r=%s%s"
                      % (a, b, "n/a" if r is None else "%.4f" % r, flag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
