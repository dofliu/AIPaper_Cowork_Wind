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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Relative comparison is only meaningful on a RATIO scale -- one with a true
# zero, where "twice as much" means something. Wind speed and rotor speed
# qualify. Temperature in Celsius does NOT: its zero is arbitrary, so 12.6 vs
# 28.1 is a 15.5 K difference between a cool site and a hot one, not a "55%
# disagreement". Nor does pitch angle, whose median sits near zero and whose
# sign flips, making any ratio explode. An earlier version of this checker
# compared everything by ratio and reported three unit mismatches that were
# nothing of the kind, on real data, which is worse than useless: it teaches
# the reader to ignore the checker.
MEDIAN_TOLERANCE = 0.35          # ratio-scale signals, relative

# Interval-scale signals, compared by ABSOLUTE difference in native units.
# Sized to admit real cross-site variation and still catch a unit error,
# which is off by a factor: degC->degF at 20 C is a 48-degree gap, rad/s->rpm
# is 10x.
INTERVAL_TOLERANCE = {
    "ambient_temperature": 25.0,        # K; Nordic vs desert sites
    "main_bearing_temperature": 30.0,   # K; duty and cooling differ
    "pitch_angle": 15.0,                # deg; median pitch is near zero
}

# Signals whose absolute level legitimately differs between farms: rated
# power is a property of the turbine model, not of the unit. Comparing
# medians across farms would flag a 2 MW farm against a 4 MW farm as a unit
# mismatch. Report their ranges, but do not judge them BY MEDIAN -- they are
# still checked for normalisation below.
SCALE_DEPENDENT = {"active_power"}

# Physically plausible envelopes, to catch the case where all three farms
# agree with each other and are all in the wrong unit. Shared with the
# scorer's filter via physical_ranges.py: separate copies drifted apart once
# already, so a value the scorer deliberately kept was reported as
# implausible by the very next tool.
from physical_ranges import PHYSICAL_RANGE as PLAUSIBLE  # noqa: E402


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
            print("  skipping %s: no signal_ranges -- rebuild it with a current "
                  "scorer" % f)
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

    # A summary written before the physical range filter existed looks
    # identical to a filtered one apart from this key, so an operator who
    # re-runs without pulling sees byte-identical numbers and concludes the
    # fix did not work. Say it plainly instead of letting them infer it.
    stale = [f for f in farms if "range_filter" not in summaries[f]]
    if stale:
        print("STALE ARTIFACTS: %s produced by a scorer with NO physical range "
              "filter." % ", ".join(stale))
        print("  Fault codes such as Farm C's 850.0 bearing reading are still in "
              "these numbers.")
        print("  git pull, then re-run base_scorer_md2022.py before reading "
              "anything below.\n")
    else:
        off = [f for f in farms
               if not summaries[f]["range_filter"].get("enabled")]
        if off:
            print("NOTE: range filtering was disabled for %s (--no-range-filter).\n"
                  % ", ".join(off))

    signals = set()
    for data in summaries.values():
        signals.update(data["signal_ranges"])

    problems = []
    for farm in stale:
        problems.append(
            "%s was scored WITHOUT the physical range filter -- re-run the scorer "
            "before trusting any range below" % farm)
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
            print("  => median not compared: rated power differs by turbine model")
        elif len(medians) >= 2 and signal in INTERVAL_TOLERANCE:
            lo, hi = min(medians.values()), max(medians.values())
            gap = hi - lo
            allowed = INTERVAL_TOLERANCE[signal]
            if gap > allowed:
                worst = [f for f, v in medians.items() if v in (lo, hi)]
                problems.append(
                    "%s: medians differ by %.1f across farms (%s), more than the %.0f "
                    "allowed -- check the units are really the same quantity"
                    % (signal, gap,
                       ", ".join("%s=%s" % (f, fmt(medians[f])) for f in sorted(worst)),
                       allowed))
                print("  => DISAGREE: medians span %.1f (interval scale, allowed %.0f)"
                      % (gap, allowed))
            else:
                print("  => consistent (medians span %.1f, within the %.0f allowed for "
                      "an interval scale)" % (gap, allowed))
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

        # A channel declared in kW whose values live in [0, 1] is not in kW:
        # it is per-unit, normalised to rated power. CARE v6 does this, and
        # excluding active_power from the median test hid it completely. The
        # method is unaffected -- normalised power is still a valid feature --
        # but the declared C0 unit is wrong and the manuscript must describe
        # the data as normalised rather than as kW.
        if signal in SCALE_DEPENDENT:
            for farm, r in sorted(present.items()):
                p99, unit = r.get("p99"), (r.get("unit_declared") or "")
                if p99 is None:
                    continue
                if abs(p99) <= 1.5 and unit.strip().lower() in ("kw", "mw", "w"):
                    problems.append(
                        "%s on %s is declared %s but spans up to %s -- that is "
                        "PER-UNIT (normalised to rated power), not %s. Fix the "
                        "declared unit; the values themselves are usable."
                        % (signal, farm, unit, fmt(p99), unit))
                    print("  => %s declared %s but p99=%s: values are NORMALISED"
                          % (farm, unit, fmt(p99)))

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
