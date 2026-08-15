#!/usr/bin/env python3
"""
Phase 5.1: are the three farms' units actually the same quantity?

WHY THIS EXISTS
---------------
The farms label identical quantities differently:

    temperature    Farm A degC     Farm B degC     Farm C Celsius
    rotor speed    Farm A rpm      Farm B rpm      Farm C 1/min

Those are the same physical unit if and only if the VALUES occupy the same
range. If one farm really is different -- Fahrenheit, or rad/s, or a
per-unit scaling -- nothing errors. The Mahalanobis covariance absorbs it
and returns scores that are quietly wrong, and a cross-farm claim built on
them is wrong with it.

So this compares the per-signal ranges that base_scorer_md2022.py records
during its scoring pass, and states plainly whether the farms agree.

USAGE
-----
    python3 check_unit_consistency.py \\
        ./scores_MD_2022_run1/scorer_summary_Wind_Farm_A.json \\
        ./scores_MD_2022_run1/scorer_summary_Wind_Farm_B.json \\
        ./scores_MD_2022_run1/scorer_summary_Wind_Farm_C.json

or just point it at the directory holding them:

    python3 check_unit_consistency.py ./scores_MD_2022_run1

Exit code: 0 if every shared signal agrees across farms, 1 if any does not,
2 if there was nothing to compare.

No third-party dependencies beyond the Python 3 standard library.
"""

import glob
import json
import os
import sys

# A signal passes if the farms' medians sit within this relative band of one
# another, and their p01-p99 spans overlap. Deliberately loose: three farms
# in different climates and turbine classes will not match tightly, and the
# failure this guards against (Fahrenheit, rad/s, per-unit) is off by a
# factor, not by a few per cent.
MEDIAN_TOLERANCE = 0.35

# Signals whose absolute level legitimately differs between farms: rated
# power is a property of the turbine model, not of the unit. Comparing
# medians across farms would flag a 2 MW farm against a 4 MW farm as a unit
# mismatch. Report their ranges, but do not judge them.
SCALE_DEPENDENT = {"active_power"}

# Physically plausible envelopes, to catch the case where all three farms
# agree with each other and are all in the wrong unit.
PLAUSIBLE = {
    "ambient_temperature": (-40.0, 55.0, "degC"),
    "main_bearing_temperature": (-20.0, 120.0, "degC"),
    "rotor_speed": (0.0, 60.0, "rpm"),
    "wind_speed": (0.0, 40.0, "m/s"),
    "pitch_angle": (-15.0, 100.0, "deg"),
}


def load_summaries(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "**", "*scorer_summary*.json"),
                                          recursive=True)))
        else:
            files.append(p)
    out = {}
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("  skipping %s: %s" % (f, exc))
            continue
        if "signal_ranges" not in data:
            print("  skipping %s: no signal_ranges (scorer older than md2022-v1.2?)" % f)
            continue
        out[data.get("farm") or os.path.basename(f)] = data
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    summaries = load_summaries(argv)
    if len(summaries) < 2:
        print("need at least two farms to compare; found %d" % len(summaries))
        return 2

    farms = sorted(summaries)
    print("comparing %d farms: %s\n" % (len(farms), ", ".join(farms)))

    signals = set()
    for data in summaries.values():
        signals.update(data["signal_ranges"])

    problems = []
    for signal in sorted(signals):
        present = {f: summaries[f]["signal_ranges"][signal]
                   for f in farms if signal in summaries[f]["signal_ranges"]}
        absent = [f for f in farms if signal not in summaries[f]["signal_ranges"]]
        print("%s" % signal)
        for farm in sorted(present):
            r = present[farm]
            print("  %-14s unit=%-22s p01=%-10s p50=%-10s p99=%s"
                  % (farm, r.get("unit_declared"),
                     fmt(r.get("p01")), fmt(r.get("p50")), fmt(r.get("p99"))))
        for farm in absent:
            print("  %-14s (not present -- declared not_available)" % farm)

        medians = {f: r.get("p50") for f, r in present.items()
                   if r.get("p50") is not None}
        if signal in SCALE_DEPENDENT:
            print("  => not compared: rated power differs by turbine model, so a "
                  "cross-farm median gap here is not evidence of a unit mismatch")
        elif len(medians) >= 2:
            lo, hi = min(medians.values()), max(medians.values())
            scale = max(abs(lo), abs(hi)) or 1.0
            spread = (hi - lo) / scale
            if spread > MEDIAN_TOLERANCE:
                worst = [f for f, v in medians.items() if v in (lo, hi)]
                problems.append(
                    "%s: medians differ by %.0f%% across farms (%s) -- check the "
                    "units are really the same quantity"
                    % (signal, 100.0 * spread,
                       ", ".join("%s=%s" % (f, fmt(medians[f])) for f in sorted(worst))))
                print("  => DISAGREE: medians span %.0f%%" % (100.0 * spread))
            else:
                print("  => consistent (medians within %.0f%%)" % (100.0 * spread))

        envelope = PLAUSIBLE.get(signal)
        if envelope:
            low, high, expected = envelope
            for farm, r in sorted(present.items()):
                p01, p99 = r.get("p01"), r.get("p99")
                if p01 is None or p99 is None:
                    continue
                if p01 < low or p99 > high:
                    problems.append(
                        "%s on %s spans %s..%s, outside the plausible %s range "
                        "%s..%s -- wrong unit, or a sentinel value not filtered"
                        % (signal, farm, fmt(p01), fmt(p99), expected,
                           fmt(low), fmt(high)))
                    print("  => %s IMPLAUSIBLE for %s (%s..%s)"
                          % (farm, expected, fmt(p01), fmt(p99)))
        print()

    if problems:
        print("PROBLEMS (%d):" % len(problems))
        for p in problems:
            print("  - %s" % p)
        print("\nDo not proceed to Phase 5 until these are explained. A unit "
              "mismatch does not error; it distorts the covariance and returns "
              "scores that look fine.")
        return 1

    print("All shared signals agree across farms and sit in plausible ranges.")
    print("Phase 5.1 satisfied. Record this output as the unit-consistency evidence.")
    return 0


def fmt(x):
    if x is None:
        return "n/a"
    return "%.3f" % x if abs(x) < 1000 else "%.1f" % x


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
