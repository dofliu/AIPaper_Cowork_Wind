#!/usr/bin/env python3
"""
Decide which power column is MEASURED and which is a modelled capability.

WHY THIS EXISTS
---------------
CARE v6 Farm A's dictionary offers two kW channels:

    power_29   "Possible grid active power"
    power_30   "Grid power"

"Possible power" is IEC 61400-26 availability terminology: the power the
turbine COULD have produced at the current wind. It is computed from the
wind speed and the power curve, so it is a smooth function of wind with
almost no scatter -- and a turbine that is underperforming shows NO
deviation in it. That is exactly the anomaly the detector exists to find.
Feed it to the scorer and the most informative feature in the vector goes
quietly dead.

The signal map builder now prefers the measured channel on the strength of
the description alone. This script checks that claim against the data,
because a claim about someone's archive should be verifiable by them in one
command rather than believed.

WHAT IT MEASURES
----------------
For each candidate column, against wind speed:

  scatter   median absolute deviation of the column around its own
            wind-speed-binned median, normalised. A modelled capability
            tracks the power curve almost exactly -> small. A measurement
            carries turbulence, yaw error, curtailment, derating -> larger.

  ge_frac   fraction of rows where this column >= the other candidate.
            Possible power is an upper bound on actual power, so the
            capability channel should be >= the measured one nearly always.

  zero_frac fraction of rows at (near) zero while the wind is above cut-in.
            A stopped turbine still has a possible power; its measured
            power is zero. This separates them sharply.

USAGE
-----
    python3 check_power_channel.py \\
        --workdir /path/to/extracted_care_v6 \\
        --farm    "Wind Farm A" \\
        --columns power_29_avg,power_30_avg \\
        --wind-col wind_speed_3_avg

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import os
import sys

CANDIDATE_DELIMITERS = [";", ",", "\t", "|"]
CUT_IN = 3.0          # m/s; below this a turbine legitimately makes no power
NEAR_ZERO_FRAC = 0.01  # of the observed maximum


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
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return None


def median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def load(farm_dir, columns, wind_col, max_files, max_rows):
    patterns = [os.path.join(farm_dir, "datasets", "*.csv"),
                os.path.join(farm_dir, "datasets", "*", "*.csv")]
    files = []
    for pattern in patterns:
        files = sorted(glob.glob(pattern))
        if files:
            break
    if not files:
        raise SystemExit("no case CSVs found under %s/datasets" % farm_dir)
    files = files[:max_files]

    rows = []
    header_seen = None
    for path in files:
        delimiter = sniff_delimiter(path)
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                continue
            header_seen = header
            missing = [c for c in list(columns) + [wind_col] if c not in header]
            if missing:
                raise SystemExit(
                    "column(s) %s not in %s.\nThat file has: %s"
                    % (missing, os.path.basename(path), header[:25]))
            idx = {c: header.index(c) for c in list(columns) + [wind_col]}
            for record in reader:
                if len(record) <= max(idx.values()):
                    continue
                wind = to_float(record[idx[wind_col]])
                if wind is None:
                    continue
                values = {c: to_float(record[idx[c]]) for c in columns}
                if any(v is None for v in values.values()):
                    continue
                values["_wind"] = wind
                rows.append(values)
                if len(rows) >= max_rows:
                    return rows, files, header_seen
    return rows, files, header_seen


def scatter_around_wind_curve(rows, column):
    """Median |x - median(x within its 0.5 m/s wind bin)|, normalised by the
    column's own scale. Small means the column is essentially a function of
    wind speed -- i.e. modelled."""
    bins = {}
    for r in rows:
        key = int(r["_wind"] * 2)
        bins.setdefault(key, []).append(r[column])
    scale = max((abs(r[column]) for r in rows), default=0.0) or 1.0
    deviations = []
    for values in bins.values():
        if len(values) < 20:
            continue
        centre = median(values)
        deviations.extend(abs(v - centre) for v in values)
    if not deviations:
        return None
    return median(deviations) / scale


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--farm", required=True, help='e.g. "Wind Farm A"')
    ap.add_argument("--columns", required=True,
                    help="Comma-separated candidate power columns")
    ap.add_argument("--wind-col", required=True)
    ap.add_argument("--max-files", type=int, default=6)
    ap.add_argument("--max-rows", type=int, default=200000)
    args = ap.parse_args()

    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    if len(columns) < 1:
        raise SystemExit("give at least one column")

    farm_dir = os.path.join(args.workdir, args.farm)
    if not os.path.isdir(farm_dir):
        matches = [d for d in glob.glob(os.path.join(args.workdir, "*"))
                   if os.path.isdir(d) and args.farm.lower() in os.path.basename(d).lower()]
        if len(matches) != 1:
            raise SystemExit("farm directory not found: %s" % farm_dir)
        farm_dir = matches[0]

    rows, files, _ = load(farm_dir, columns, args.wind_col,
                          args.max_files, args.max_rows)
    if not rows:
        raise SystemExit("no complete rows read")

    print("%s -- %d rows from %d case file(s)"
          % (os.path.basename(farm_dir), len(rows), len(files)))
    print("wind column: %s\n" % args.wind_col)

    above_cut_in = [r for r in rows if r["_wind"] >= CUT_IN]
    print("%-22s %10s %10s %12s" % ("column", "scatter", "zero_frac", "median@8-12"))
    print("-" * 58)
    results = {}
    for column in columns:
        scatter = scatter_around_wind_curve(rows, column)
        scale = max((abs(r[column]) for r in rows), default=0.0) or 1.0
        zero_frac = (sum(1 for r in above_cut_in
                         if abs(r[column]) <= NEAR_ZERO_FRAC * scale)
                     / len(above_cut_in)) if above_cut_in else float("nan")
        rated = median([r[column] for r in rows if 8.0 <= r["_wind"] < 12.0])
        results[column] = {"scatter": scatter, "zero_frac": zero_frac}
        print("%-22s %10s %10.4f %12s"
              % (column,
                 "n/a" if scatter is None else "%.4f" % scatter,
                 zero_frac,
                 "n/a" if rated is None else "%.1f" % rated))

    if len(columns) == 2:
        a, b = columns
        ge = sum(1 for r in rows if r[a] >= r[b]) / len(rows)
        print("\n%s >= %s in %.1f%% of rows" % (a, b, 100.0 * ge))

        sa = results[a]["scatter"]
        sb = results[b]["scatter"]
        print("\nreading:")
        if sa is not None and sb is not None:
            modelled, measured = (a, b) if sa < sb else (b, a)
            ratio = max(sa, sb) / min(sa, sb) if min(sa, sb) > 0 else float("inf")
            print("  %s tracks the wind curve %.1fx more tightly than %s."
                  % (modelled, ratio, measured))
            if ratio < 1.5:
                print("  NOT DECISIVE -- the two behave similarly. Do not choose on "
                      "this evidence alone; check the dictionary descriptions.")
            else:
                print("  => %s looks MODELLED (a capability), %s looks MEASURED."
                      % (modelled, measured))
                print("  Use %s as active_power. A capability channel is a function "
                      "of wind, so an underperforming turbine leaves no trace in it."
                      % measured)
        zero_a, zero_b = results[a]["zero_frac"], results[b]["zero_frac"]
        if zero_a == zero_a and zero_b == zero_b:  # not NaN
            if abs(zero_a - zero_b) > 0.01:
                stops_more = a if zero_a > zero_b else b
                print("  %s sits at zero above cut-in far more often (%.1f%% vs "
                      "%.1f%%), which is what a MEASURED channel does when the "
                      "turbine is stopped." % (stops_more,
                                               100.0 * max(zero_a, zero_b),
                                               100.0 * min(zero_a, zero_b)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
