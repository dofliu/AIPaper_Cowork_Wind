#!/usr/bin/env python3
"""Does every wind-speed group get points in every case? (R26 G3 evidence)

WHY THIS EXISTS
---------------
R26 G3 has to pin down, in writing and BEFORE anything runs, whether POGO's
wealth process carries across cases or resets at each case boundary. This
project's own calibrator resets (`regime_conditional_calibration.py` builds
fresh per-bin buffers per case), so "reset" is the choice that keeps the two
state shapes aligned -- and until now that was the whole argument.

It is not a sufficient argument, because POGO's Theorem 4.1 carries an
assumption this project's method does not have:

    Let ... T_j > 0 ...

`T_j` is the (soft) count of points belonging to group j IN THE STREAM POGO
sees. Under carry there is one stream and `T_j` is a per-farm or per-project
total. Under reset there are 91 streams and `T_j` is a per-case count -- and a
case whose turbine never saw 12 m/s has `T_j = 0` for `bin4_ge_12`. The theorem
then says nothing at all about that group in that case, and, this being the
recurring shape of every defect in `PROJECT_STATUS.md` section 5, nothing would
error: the adapter would run, the group column would be populated, and the
comparison table would look complete.

So the contract needs a measured answer to two questions:

    1. Under per-case reset, does any case leave a group at T_j = 0?
    2. How small does the smallest T_j get, and what does Theorem 4.1 still
       promise at that size?

This tool answers both from outputs that are already in version control. It
runs no algorithm and re-derives no score.

TWO OCCUPANCIES, AND THEY ARE NOT THE SAME NUMBER
-------------------------------------------------
    raw          rows whose `regime_bin` is this bin, calibrated or not.
                 This is what POGO sees: POGO has no warm-up, so every row
                 with a group vector enters its `T_j`.

    calibrated   rows that additionally carry a `p_value`. This project emits
                 one only once that bin's own buffer holds `min_bin_samples`
                 scores, and the buffer stops absorbing while an alarm stands,
                 so `calibrated` is NOT `raw - min_bin_samples`; it is measured
                 here, not computed. This is the population the shared
                 evaluation window can use.

Reporting only one of them would misstate the contract in a specific
direction: `raw` overstates what this project's method can be compared on, and
`calibrated` understates the stream POGO would actually be handed.

WHAT THIS IS NOT
----------------
It is NOT a claim that reset is wrong or that carry is right. Both regimes are
legitimate; the point of G3 is that the choice must be made and written down
before results exist, because it changes what POGO's guarantee says. The
bound printed here is a worst-case upper bound on POGO and must never appear
in a table beside this project's measured worst-bin deviation -- see
`scripts/pogo_bound_scale_check.py` for the same warning at length.

It is also NOT evidence about POGO's empirical behaviour. A tighter bound is
not a better score. Carry hands POGO a threshold inherited from a different
turbine, which may well hurt it; that question is G5's, not this tool's.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Single definition (working rule 5): the bins and the bound both come from the
# module that owns them, never re-typed here.
from regime_conditional_calibration import BIN_NAMES          # noqa: E402
from pogo_bound_scale_check import miscov_bound               # noqa: E402
from evaluate_experiment import parse_ts                      # noqa: E402


def case_id_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def occupancy_of_case(path, cut=None):
    """Per-bin raw and calibrated counts for one emitted case stream.

    `cut` applies the D1/D6 trim. It is compared as a datetime, never as a
    string: the emitted timestamps are `2023-08-24 13:00:00` and the ratified
    cut is written `2023-08-24T13:00:00`, and ' ' < 'T' in ASCII, so a string
    comparison silently keeps every row. That exact defect has already shipped
    twice in this project (PROJECT_STATUS section 5), which is why the dropped
    row count is reported rather than assumed.
    """
    raw = dict((b, 0) for b in BIN_NAMES)
    calibrated = dict((b, 0) for b in BIN_NAMES)
    n_rows = 0
    unbinned = 0
    dropped = 0
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if cut is not None:
                ts = parse_ts((row.get("timestamp") or "").strip())
                if ts is not None and ts >= cut:
                    dropped += 1
                    continue
            n_rows += 1
            b = (row.get("regime_bin") or "").strip()
            if b not in raw:
                unbinned += 1
                continue
            raw[b] += 1
            if (row.get("p_value") or "").strip() != "":
                calibrated[b] += 1
    return {"case_id": case_id_of(path), "n_rows": n_rows,
            "n_unbinned": unbinned, "n_trimmed": dropped,
            "raw": raw, "calibrated": calibrated}


def summarise(cases, alpha, D, q, k):
    """Aggregate the per-case occupancies into what the G3 contract needs."""
    empty_raw, empty_cal, per_case = [], [], []
    carry_raw = dict((b, 0) for b in BIN_NAMES)
    carry_cal = dict((b, 0) for b in BIN_NAMES)
    total_rows = 0
    total_cal = 0

    for c in cases:
        total_rows += c["n_rows"]
        for b in BIN_NAMES:
            carry_raw[b] += c["raw"][b]
            carry_cal[b] += c["calibrated"][b]
            total_cal += c["calibrated"][b]
            if c["raw"][b] == 0:
                empty_raw.append({"case_id": c["case_id"], "bin": b})
            if c["calibrated"][b] == 0:
                empty_cal.append({"case_id": c["case_id"], "bin": b})

        occupied = [c["raw"][b] for b in BIN_NAMES if c["raw"][b] > 0]
        cal_total = sum(c["calibrated"][b] for b in BIN_NAMES)
        entry = {"case_id": c["case_id"], "n_rows": c["n_rows"],
                 "n_calibrated": cal_total,
                 "raw": c["raw"], "calibrated": c["calibrated"],
                 "min_raw_occupied": min(occupied) if occupied else 0,
                 "n_empty_raw_bins": sum(1 for b in BIN_NAMES if c["raw"][b] == 0)}
        # The bound POGO's theorem gives for this case's rarest OCCUPIED group
        # under per-case reset. Empty groups get no bound at all, which is the
        # finding, not a missing value.
        if entry["min_raw_occupied"] > 0 and cal_total > 0:
            entry["reset_bound_at_min_Tj"] = miscov_bound(
                float(c["n_rows"]), float(entry["min_raw_occupied"]),
                k, alpha, D, q)
        else:
            entry["reset_bound_at_min_Tj"] = None
        per_case.append(entry)

    carry_occupied = [carry_raw[b] for b in BIN_NAMES if carry_raw[b] > 0]
    worst = min((e for e in per_case if e["reset_bound_at_min_Tj"] is not None),
                key=lambda e: e["min_raw_occupied"], default=None)

    return {
        "n_cases": len(cases),
        "total_rows": total_rows,
        "total_calibrated": total_cal,
        "bins": BIN_NAMES,
        "carry_raw": carry_raw,
        "carry_calibrated": carry_cal,
        "empty_raw_bins": empty_raw,
        "empty_calibrated_bins": empty_cal,
        "n_cases_with_empty_raw_bin": len(
            set(e["case_id"] for e in empty_raw)),
        "n_cases_with_empty_calibrated_bin": len(
            set(e["case_id"] for e in empty_cal)),
        "worst_case_under_reset": worst,
        "carry_bound_at_min_Tj": (
            miscov_bound(float(total_rows), float(min(carry_occupied)),
                         k, alpha, D, q) if carry_occupied else None),
        "carry_min_Tj": min(carry_occupied) if carry_occupied else 0,
        "per_case": per_case,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours-dir", required=True,
                    help="a directory of emitted per-case streams from "
                         "regime_conditional_calibration.py (needs the "
                         "regime_bin and p_value columns)")
    ap.add_argument("--exclude-cases", default="",
                    help="comma-separated case ids to drop (D1/D6: 32,56,72,87)")
    ap.add_argument("--trim-case", action="append",
                    help="CASE_ID=TIMESTAMP, repeatable. D1/D6 trims case 93 "
                         "at 2023-08-24T13:00:00. Rows at or after the cut "
                         "are dropped and the count is reported.")
    ap.add_argument("--alpha", type=float, default=0.01)
    ap.add_argument("--D", type=float, default=23.81,
                    help="Theorem 4.1 growth constant; 23.81 measured on "
                         "scores_MD_2022_run1 (G1, gate 3.4a)")
    ap.add_argument("--q", type=float, default=0.0)
    ap.add_argument("--k", type=int, default=4,
                    help="group count for the bound; this project's ratified k")
    ap.add_argument("--output", help="optional path for a JSON report")
    args = ap.parse_args()

    excluded = set(x.strip() for x in args.exclude_cases.split(",") if x.strip())
    paths = sorted(
        (os.path.join(args.ours_dir, n) for n in os.listdir(args.ours_dir)
         if n.endswith(".csv") and case_id_of(n) not in excluded),
        key=lambda p: (len(case_id_of(p)), case_id_of(p)))
    if not paths:
        raise SystemExit("no case CSVs under %r" % args.ours_dir)

    trims = {}
    for spec in (args.trim_case or []):
        if "=" not in spec:
            raise SystemExit("bad --trim-case %r; expected CASE_ID=TIMESTAMP" % spec)
        cid, rawts = spec.split("=", 1)
        cut = parse_ts(rawts.strip())
        if cut is None:
            raise SystemExit("bad timestamp in --trim-case %r" % spec)
        trims[cid.strip()] = cut

    cases = [occupancy_of_case(p, trims.get(case_id_of(p))) for p in paths]
    report = summarise(cases, args.alpha, args.D, args.q, args.k)
    report["tool"] = "group-occupancy-v1.0"
    report["trim_applied"] = dict(
        (c["case_id"], c["n_trimmed"]) for c in cases if c["n_trimmed"])
    report["inputs"] = {"ours_dir": args.ours_dir, "alpha": args.alpha,
                        "D": args.D, "q": args.q, "k": args.k,
                        "excluded_cases": sorted(excluded),
                        "trim_cases": dict((c, t.isoformat())
                                           for c, t in trims.items())}

    print("cases %d   rows %d   calibrated %d"
          % (report["n_cases"], report["total_rows"],
             report["total_calibrated"]))
    if trims:
        print("trim: %s" % (report["trim_applied"] or
                            "REQUESTED BUT DROPPED 0 ROWS -- check the cut"))
    print()
    print("  bin              raw (all cases)   calibrated (all cases)   cases with 0 raw")
    for b in BIN_NAMES:
        n_zero = sum(1 for e in report["empty_raw_bins"] if e["bin"] == b)
        print("  %-16s %15d   %22d   %16d"
              % (b, report["carry_raw"][b], report["carry_calibrated"][b],
                 n_zero))
    print()
    print("  cases leaving at least one group EMPTY (raw)        : %d / %d"
          % (report["n_cases_with_empty_raw_bin"], report["n_cases"]))
    print("  cases leaving at least one group EMPTY (calibrated) : %d / %d"
          % (report["n_cases_with_empty_calibrated_bin"], report["n_cases"]))
    print()
    w = report["worst_case_under_reset"]
    if w:
        print("  rarest occupied group under per-case reset: case %s, T_j = %d"
              % (w["case_id"], w["min_raw_occupied"]))
        print("    Theorem 4.1 at that (T=%d, T_j=%d, k=%d) : %.5f"
              % (w["n_rows"], w["min_raw_occupied"], args.k,
                 w["reset_bound_at_min_Tj"]))
    if report["carry_bound_at_min_Tj"] is not None:
        print("  rarest group under full carry            : T_j = %d"
              % report["carry_min_Tj"])
        print("    Theorem 4.1 at that (T=%d, T_j=%d, k=%d) : %.5f"
              % (report["total_rows"], report["carry_min_Tj"], args.k,
                 report["carry_bound_at_min_Tj"]))
    print()
    print("  A group at T_j = 0 is not a small bound, it is NO bound: Theorem "
          "4.1\n  assumes T_j > 0. Under carry that assumption is easy; under "
          "reset it is\n  a per-case fact that has to be checked, which is "
          "what this tool checks.")
    print("  These are worst-case upper bounds on POGO. Never place them beside "
          "this\n  project's measured worst-bin deviation (R25 claim firewall).")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
        print("\nwrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
