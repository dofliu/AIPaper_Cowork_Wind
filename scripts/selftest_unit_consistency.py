#!/usr/bin/env python3
"""
Self-test for check_unit_consistency.py.

This checker returned three WRONG verdicts on the operator's real data --
calling genuine cross-site variation a unit mismatch -- which is worse than
having no checker, because it teaches the reader to ignore it. Each is
pinned here.

  T1  Celsius is an INTERVAL scale. Comparing 12.6 C and 28.1 C by ratio
      gives "55% disagreement"; they are a Nordic site and a hot one, 15.5 K
      apart. Interval-scale signals compare by absolute difference.
  T2  Pitch angle medians sit near zero and change sign, so any ratio
      explodes: -1.04 vs 1.52 was reported as "168%".
  T3  Wind speed and rotor speed ARE ratio scales, and a 10x error there
      must still be caught.
  T4  A channel declared in kW whose values live in [0,1] is per-unit, not
      kW. Excluding active_power from the median test hid this completely
      on the real data -- all three farms.
  T5  The absolute plausibility envelope catches a bearing at 363 C even
      when the farms agree with each other.
  T6  Exit codes: 0 clean, 1 problems, 2 nothing to compare.

    python3 scripts/selftest_unit_consistency.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "check_unit_consistency.py")


def write(root, farm, signals, filtered=True):
    """signals: name -> (p01, p50, p99, unit)"""
    path = os.path.join(root, "scorer_summary_%s.json" % farm.replace(" ", "_"))
    payload = {"farm": farm}
    if filtered:
        payload["range_filter"] = {"enabled": True, "ranges_applied": {},
                                   "readings_rejected_per_column": {}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(payload, **{"signal_ranges": {
            k: {"unit_declared": v[3], "n_samples": 50000,
                "p01": v[0], "p50": v[1], "p99": v[2],
                "min": v[0], "max": v[2]}
            for k, v in signals.items()}}), f)


def run(root):
    proc = subprocess.run([sys.executable, CHECKER, root],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout


def main():
    failures, checks = [], 0

    def check(name, condition, detail=""):
        nonlocal checks
        checks += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s %s" % (name, detail))
            failures.append(name)

    # ---- T1/T2/T3: the operator's real numbers, minus the real faults ----
    print("\nT1/T2  interval scales are not compared by ratio")
    with tempfile.TemporaryDirectory() as root:
        # Verbatim from the real run, with Farm C's two genuine faults
        # (bearing p99=363, rotor speed) replaced by sane values, so anything
        # this reports is a false alarm by construction.
        write(root, "Wind Farm A", {
            "ambient_temperature": (9.0, 19.0, 34.0, "degC"),
            "pitch_angle": (-2.2, -0.1, 89.5, "deg"),
            "rotor_speed": (0.0, 11.4, 14.9, "rpm"),
            "wind_speed": (1.0, 5.5, 16.9, "m/s")})
        write(root, "Wind Farm B", {
            "ambient_temperature": (3.059, 12.56, 24.82, "degC"),
            "main_bearing_temperature": (7.995, 47.125, 57.688, "degC"),
            "pitch_angle": (-0.02, 1.52, 92.9, "deg"),
            "rotor_speed": (0.0, 7.96, 10.12, "rpm"),
            "wind_speed": (0.91, 8.12, 21.156, "m/s")})
        write(root, "Wind Farm C", {
            "ambient_temperature": (15.095, 28.1, 40.059, "Celsius"),
            "main_bearing_temperature": (18.725, 48.564, 57.9, "Celsius"),
            "pitch_angle": (-1.999, -1.038, 90.093, "deg"),
            "rotor_speed": (0.0, 9.8, 13.1, "1/min"),
            "wind_speed": (0.792, 6.939, 20.255, "m/s")})
        code, out = run(root)
        check("T1 ambient temperature 15.5 K apart is NOT a mismatch",
              "ambient_temperature: medians differ" not in out,
              "still flagged")
        check("T2 pitch angle straddling zero is NOT a mismatch",
              "pitch_angle: medians differ" not in out, "still flagged")
        check("T1/T2 degC and Celsius are accepted as the same unit",
              "consistent" in out)
        check("T1/T2 the whole clean set passes", code == 0,
              "exit %d\n%s" % (code, out[-600:]))

    print("\nT3  ratio scales still catch a real error")
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"rotor_speed": (0.0, 11.4, 14.9, "rpm"),
                                    "wind_speed": (1.0, 5.5, 16.9, "m/s")})
        # rad/s instead of rpm: same numbers divided by ~9.55
        write(root, "Wind Farm B", {"rotor_speed": (0.0, 1.19, 1.56, "rad/s"),
                                    "wind_speed": (0.9, 8.1, 21.2, "m/s")})
        code, out = run(root)
        check("T3 a rad/s vs rpm swap is caught",
              "rotor_speed: medians differ" in out, out[-400:])
        check("T3 and wind speed is not dragged in with it",
              "wind_speed: medians differ" not in out)
        check("T3 exit code reports the problem", code == 1, "exit %d" % code)

    print("\nT4  a kW channel living in [0,1] is per-unit, not kW")
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"active_power": (-0.009, 0.113, 0.976, "kW")})
        write(root, "Wind Farm B", {"active_power": (-0.004, 0.276, 1.029, "kW")})
        code, out = run(root)
        check("T4 normalisation is reported", "NORMALISED" in out, out[-400:])
        check("T4 on every farm, not just one", out.count("NORMALISED") >= 2)
        check("T4 and it says the values are still usable",
              "values themselves are usable" in out)
        check("T4 exit code reports it", code == 1, "exit %d" % code)
        # A genuine kW channel must NOT be flagged.
        with tempfile.TemporaryDirectory() as root2:
            write(root2, "Wind Farm A", {"active_power": (0.0, 850.0, 2000.0, "kW")})
            write(root2, "Wind Farm B", {"active_power": (0.0, 1100.0, 3000.0, "kW")})
            code2, out2 = run(root2)
            check("T4 real kW values are not called normalised",
                  "NORMALISED" not in out2)
            check("T4 and differing rated power is not called a mismatch",
                  code2 == 0, out2[-300:])

    print("\nT4b  a per-unit label must also be falsifiable")
    # A check that only fires one way is not evidence. If it only catches
    # "declared kW, actually per-unit", someone can relabel a genuine 2000 kW
    # channel as p.u. and sail through -- the same mistake, mirrored.
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"active_power": (0.0, 0.113, 0.976, "p.u.")})
        write(root, "Wind Farm B", {"active_power": (0.0, 0.276, 1.029, "p.u.")})
        code, out = run(root)
        check("T4b a correct per-unit label passes", code == 0, out[-400:])
        check("T4b and is confirmed against the values, not just accepted",
              "confirmed by p99" in out, out[-300:])
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"active_power": (0.0, 850.0, 2000.0, "p.u.")})
        write(root, "Wind Farm B", {"active_power": (0.0, 0.276, 1.029, "p.u.")})
        code, out = run(root)
        check("T4b a kW channel mislabelled per-unit is caught",
              "NOT normalised" in out, out[-400:])
        check("T4b exit code reports it", code == 1, "exit %d" % code)

    print("\nT5  the plausibility envelope catches agreeing-but-impossible values")
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm B", {
            "main_bearing_temperature": (7.995, 47.125, 57.688, "degC")})
        write(root, "Wind Farm C", {
            "main_bearing_temperature": (18.725, 48.564, 362.976, "Celsius")})
        code, out = run(root)
        check("T5 medians agree, so the median test passes them",
              "consistent" in out)
        check("T5 but 363 C is still caught as implausible",
              "IMPLAUSIBLE" in out, out[-400:])
        check("T5 and the message names a sentinel as a cause",
              "sentinel" in out)

    print("\nT7  a summary from a scorer with no range filter is called stale")
    # A pre-filter summary is byte-identical to a filtered one apart from
    # this key. The operator re-ran without pulling, saw Farm C's bearing
    # p99 unchanged at 362.976, and had no way to tell that the filter had
    # simply not been in the binary. Silence there costs a full six-farm
    # scoring pass.
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"wind_speed": (1.0, 7.0, 18.0, "m/s")})
        write(root, "Wind Farm C",
              {"main_bearing_temperature": (18.7, 48.5, 362.976, "Celsius")},
              filtered=False)
        code, out = run(root)
        check("T7 the stale artifact is named", "STALE ARTIFACTS" in out
              and "Wind Farm C" in out, out[-400:])
        check("T7 it says what is still wrong with the numbers",
              "850" in out or "Fault codes" in out)
        check("T7 it tells the operator to pull and re-run",
              "git pull" in out and "re-run" in out)
        check("T7 and the exit code refuses to pass", code == 1, "exit %d" % code)

    print("\nT6  exit codes")
    with tempfile.TemporaryDirectory() as root:
        write(root, "Wind Farm A", {"wind_speed": (1.0, 7.0, 18.0, "m/s")})
        code, out = run(root)
        check("T6 one farm alone cannot be compared -> 2", code == 2,
              "exit %d" % code)

    print("\nT8  the two tools share one definition of possible")
    sys.path.insert(0, HERE)
    import physical_ranges as PR  # noqa: E402
    import importlib
    checker = importlib.import_module("check_unit_consistency")
    check("T8 the checker's envelopes ARE the shared table",
          checker.PLAUSIBLE is PR.PHYSICAL_RANGE)
    scorer_src = open(os.path.join(HERE, "base_scorer_md2022.py"),
                      encoding="utf-8").read()
    check("T8 the scorer imports them rather than keeping a copy",
          "from physical_ranges import" in scorer_src)
    # The drift that actually happened: scorer allowed -1.0, checker demanded
    # >= 0.0, so a value the scorer kept was flagged by the next tool.
    lo, hi = PR.bounds("rotor_speed")
    check("T8 rotor speed admits the stopped-rotor offset CARE v6 carries",
          lo <= -5.5, "low bound %s but Farm C reads to -5.5" % lo)
    check("T8 while still rejecting a gearbox-shaft channel at 80",
          hi < 80.0, "high bound %s" % hi)

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
