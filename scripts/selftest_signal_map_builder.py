#!/usr/bin/env python3
"""
Self-test for care_v6_signal_map_builder.py.

This tool had four defects found by running it against the real archive
rather than by testing it, which is three too many. Each is pinned here.

  T1  "active power" is a substring of "reactive power". Every
      reactive_power channel used to match, tying 12 channels in Farm A
      and 11 in Farm C on a signal with one answer.
  T2  An energy counter in Wh is not an instantaneous power reading, even
      when is_counter is unset -- Farm A carries "Active power - generator
      connected in delta" in Wh.
  T3  A gearbox or generator bearing is a DIFFERENT component from the
      main bearing. The catch-all rule must report a substitute, never
      resolve to one: it silently handed Farm A a high-speed-shaft
      gearbox bearing.
  T4  An operator override has no dictionary description, since by
      definition the dictionary did not name that signal. Printing it
      crashed with KeyError on the operator's machine.
  T5  Redundant channels averaging, and the unit guard that refuses to
      average across different units -- which is what stopped Farm C's
      active power mixing kW converters with aeration motors in percent.

    python3 scripts/selftest_signal_map_builder.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "care_v6_signal_map_builder.py")
sys.path.insert(0, HERE)

import care_v6_signal_map_builder as B  # noqa: E402


def entries(rows):
    """rows: list of (sensor_name, stats, description, unit, is_counter)."""
    return [{"sensor_name": n, "statistics_type": s, "description": d,
             "unit": u, "is_angle": "False", "is_counter": c}
            for n, s, d, u, c in rows]


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

    # ---------------- T1 reactive power must not match ----------------
    print("\nT1  'active power' is a substring of 'reactive power'")
    matched = B.match_signals(entries([
        ("power_29", "average", "Possible grid active power", "kW", "False"),
        ("reactive_power_27", "average", "Possible grid capacitive reactive power",
         "kVAr", "False"),
        ("reactive_power_28", "average", "Grid reactive power", "kVAr", "False"),
    ]))
    names = [c["sensor_name"] for c in matched.get("active_power", [])]
    check("T1 only the real active power channel matches", names == ["power_29"],
          "got %s" % names)

    # ---------------- T2 energy is not power ----------------
    print("\nT2  an energy counter in Wh is not instantaneous power")
    matched = B.match_signals(entries([
        ("power_29", "average", "Possible grid active power", "kW", "False"),
        ("sensor_44", "average", "Active power - generator disconnected", "Wh", "False"),
        ("sensor_50", "average", "Total active power", "Wh", "False"),
    ]))
    names = [c["sensor_name"] for c in matched.get("active_power", [])]
    check("T2 Wh channels are rejected despite is_counter being unset",
          names == ["power_29"], "got %s" % names)

    # ---------------- T3 a substitute is never resolved ----------------
    print("\nT3  a gearbox bearing is a substitute, not a main bearing")
    matched = B.match_signals(entries([
        ("sensor_11", "average", "Temperature in gearbox bearing on high speed shaft",
         "degC", "False"),
        ("sensor_13", "average", "Temperature in generator bearing 2 (Drive End)",
         "degC", "False"),
    ]))
    pick, problem = B.choose(matched.get("main_bearing_temperature", []),
                             average_ties=True)
    check("T3 nothing is resolved", pick is None, "got %s" % pick)
    check("T3 the problem says substitute and names the components",
          problem and "substitute" in problem and "gearbox" in problem,
          "got %s" % (problem or "")[:100])

    real = B.match_signals(entries([
        ("sensor_51", "average", "Rotor bearing temperature 1", "degC", "False"),
        ("sensor_52", "average", "Rotor bearing temperature 2", "degC", "False"),
    ]))
    pick, problem = B.choose(real.get("main_bearing_temperature", []), average_ties=True)
    check("T3 two real rotor bearings DO average", pick is not None and "_average_of" in pick,
          "got %s" % (problem or pick))

    # ---------------- T5 the unit guard ----------------
    print("\nT5  averaging refuses to cross units")
    mixed = B.match_signals(entries([
        ("power_6", "average", "Active power HV grid", "kW", "False"),
        ("power_17", "average", "Active power converter", "kW", "False"),
        ("sensor_3", "average", "Active power aeration motor A", "%", "False"),
    ]))
    pick, problem = B.choose(mixed.get("active_power", []), average_ties=True)
    check("T5 mixed units are not averaged", pick is None)
    check("T5 and the reason names the unit clash",
          problem and "units differ" in problem, "got %s" % (problem or "")[:80])

    picked, problem = B.choose(mixed.get("active_power", []), average_ties=True,
                               pick_sensor="power_6")
    check("T5 an explicit pick resolves the same tie",
          picked is not None and picked["sensor_name"] == "power_6",
          "got %s" % (problem or picked))

    # ---------------- T4 override path, end to end ----------------
    print("\nT4  an operator override prints without a dictionary description")
    with tempfile.TemporaryDirectory() as root:
        farm = os.path.join(root, "Wind Farm A")
        os.makedirs(farm)
        with open(os.path.join(farm, "feature_description.csv"), "w",
                  encoding="cp1252", newline="") as f:
            f.write("sensor_name;statistics_type;description;unit;is_angle;is_counter\n")
            f.write("sensor_0;average;Ambient temperature;\xb0C;False;False\n")
            f.write("sensor_52;average;Rotor rpm;rpm;False;False\n")
            f.write("power_29;average;Possible grid active power;kW;False;False\n")
            f.write("sensor_5;average;Pitch angle;\xb0;True;False\n")
        out = os.path.join(root, "out")
        proc = subprocess.run(
            [sys.executable, BUILDER, "--workdir", root, "--output-dir", out,
             "--average-ties",
             "--header-override", "A:wind_speed=wind_speed_3_avg",
             "--override-unit", "m/s"],
            capture_output=True, text=True)
        check("T4 the builder exits cleanly", proc.returncode == 0,
              proc.stderr[-400:])
        if proc.returncode == 0:
            check("T4 the overridden signal is printed, not crashed on",
                  "wind_speed_3_avg" in proc.stdout,
                  "stdout lacks the override line")
            written = json.load(open(os.path.join(out, "signal_map_Wind_Farm_A.json"),
                                     encoding="utf-8"))
            check("T4 the override lands in the signal map",
                  written.get("wind_speed", {}).get("column") == "wind_speed_3_avg")
            check("T4 and is marked as operator-supplied, not dictionary-derived",
                  "header-override" in written["wind_speed"].get("_source", ""))
            check("T4 the degree sign survived the cp1252 file",
                  written["ambient_temperature"]["unit"] == "°C",
                  "got %r" % written["ambient_temperature"]["unit"])

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
