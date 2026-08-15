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

    # ------- T6 the operator's REAL archive shape, end to end -------
    # T4's fixture was sanitised: one farm, no averaging, no substitutes. The
    # operator's archive is not like that, and the tool died on it at the
    # first farm whose channels actually averaged -- after printing Farm A
    # and looking healthy. Reproduce the real shape: Farm A with substitutes
    # only and a destroyed degree sign, Farm B with two rotor bearings that
    # DO average. Anything less than this is not a test of the run path.
    print("\nT6  three farms, the shape the real archive actually has")
    with tempfile.TemporaryDirectory() as root:
        a = os.path.join(root, "Wind Farm A")
        b = os.path.join(root, "Wind Farm B")
        os.makedirs(a)
        os.makedirs(b)
        # Farm A: the degree sign is ALREADY DESTROYED in the file -- these
        # are literally the UTF-8 bytes of U+FFFD, as CARE v6 ships them.
        with open(os.path.join(a, "feature_description.csv"), "wb") as f:
            f.write(b"sensor_name;statistics_type;description;unit;is_angle;is_counter\n")
            f.write(b"sensor_0;average;Ambient temperature;\xef\xbf\xbdC;False;False\n")
            f.write(b"sensor_52;average;Rotor rpm;rpm;False;False\n")
            f.write(b"power_29;average;Possible grid active power;kW;False;False\n")
            f.write(b"sensor_5;average;Pitch angle;\xef\xbf\xbd;True;False\n")
            f.write(b"sensor_11;average;Temperature in gearbox bearing on high speed shaft;"
                    b"\xef\xbf\xbdC;False;False\n")
            f.write(b"sensor_13;average;Temperature in generator bearing 2 (Drive End);"
                    b"\xef\xbf\xbdC;False;False\n")
        # Farm B: two genuine rotor bearings -> --average-ties averages them,
        # producing a derived_from entry with NO "column" key. This is the
        # exact entry shape that crashed.
        with open(os.path.join(b, "feature_description.csv"), "w",
                  encoding="utf-8", newline="") as f:
            f.write("sensor_name;statistics_type;description;unit;is_angle;is_counter\n")
            f.write("sensor_51;average;Rotor bearing temperature 1;degC;False;False\n")
            f.write("sensor_52;average;Rotor bearing temperature 2;degC;False;False\n")
            f.write("sensor_0;average;Ambient temperature;degC;False;False\n")
            f.write("sensor_60;average;Rotor rpm;rpm;False;False\n")
            f.write("power_5;average;Grid active power;kW;False;False\n")
            f.write("sensor_9;average;Pitch angle;deg;True;False\n")
        out = os.path.join(root, "out")
        proc = subprocess.run(
            [sys.executable, BUILDER, "--workdir", root, "--output-dir", out,
             "--average-ties",
             "--header-override", "A:wind_speed=wind_speed_3_avg",
             "--header-override", "B:wind_speed=wind_speed_61_avg",
             "--override-unit", "m/s",
             "--unit-override", "A:ambient_temperature=degC",
             "--not-available",
             "A:main_bearing_temperature=Farm A carries no main bearing channel",
             ],
            capture_output=True, text=True)
        check("T6 the builder survives a farm whose channels average",
              proc.returncode == 0,
              (proc.stderr or "")[-500:])
        if proc.returncode == 0:
            summary = json.load(open(os.path.join(out, "signal_map_summary.json"),
                                     encoding="utf-8"))
            check("T6 both farms reach the summary",
                  sorted(summary["farms"]) == ["Wind Farm A", "Wind Farm B"],
                  "got %s" % sorted(summary["farms"]))
            resolved_b = summary["farms"]["Wind Farm B"]["resolved"]
            check("T6 an averaged signal is labelled, not crashed on",
                  resolved_b.get("main_bearing_temperature", "").startswith("mean("),
                  "got %r" % resolved_b.get("main_bearing_temperature"))

            map_b = json.load(open(os.path.join(out, "signal_map_Wind_Farm_B.json"),
                                   encoding="utf-8"))
            check("T6 and it really is an average of the two rotor bearings",
                  sorted(map_b["main_bearing_temperature"]["derived_from"])
                  == ["sensor_51_avg", "sensor_52_avg"],
                  "got %s" % map_b["main_bearing_temperature"].get("derived_from"))

            map_a = json.load(open(os.path.join(out, "signal_map_Wind_Farm_A.json"),
                                   encoding="utf-8"))
            mb = map_a["main_bearing_temperature"]
            check("T6 --not-available emits the ratified block C0 requires",
                  mb.get("not_available") is True and mb.get("reason")
                  and mb.get("ratified_by") and mb.get("ratified_on"),
                  "got %s" % mb)
            check("T6 the summary shows it as declared, not missing",
                  summary["farms"]["Wind Farm A"]["resolved"]
                  .get("main_bearing_temperature") == "NOT AVAILABLE (ratified)",
                  "got %r" % summary["farms"]["Wind Farm A"]["resolved"]
                  .get("main_bearing_temperature"))

            # The destroyed degree sign must never reach the C0 map as if real.
            check("T6 a corrupted unit is flagged, not silently recorded",
                  "UNREADABLE" in map_a["pitch_angle"]["unit"],
                  "got %r -- this is what shipped as the C0 unit"
                  % map_a["pitch_angle"]["unit"])
            check("T6 --unit-override repairs the one the operator declared",
                  map_a["ambient_temperature"]["unit"] == "degC",
                  "got %r" % map_a["ambient_temperature"]["unit"])
            check("T6 no signal map anywhere still carries mojibake",
                  not any("ï¿½" in json.dumps(json.load(open(
                      os.path.join(out, n), encoding="utf-8")), ensure_ascii=False)
                      for n in os.listdir(out) if n.startswith("signal_map_Wind")))

    # ------- T7 a [FARM:] prefix selects ONE farm -------
    # This was a substring test. The farm names are "Wind Farm A/B/C" and the
    # word FARM contains an "a", so "A:" matched all three: the operator's
    # --header-override for Farm A silently overwrote the ratified Farm C
    # pick, and two farms would have been binned on the wrong farm's wind
    # channel with nothing reported. Cheap to test, expensive to miss.
    print("\nT7  a [FARM:] prefix selects exactly one farm")
    farms = ["Wind Farm A", "Wind Farm B", "Wind Farm C"]
    check("T7 'A' selects only Farm A",
          [f for f in farms if B.farm_matches("A", f)] == ["Wind Farm A"],
          "got %s" % [f for f in farms if B.farm_matches("A", f)])
    check("T7 'B' and 'C' likewise",
          [f for f in farms if B.farm_matches("B", f)] == ["Wind Farm B"]
          and [f for f in farms if B.farm_matches("C", f)] == ["Wind Farm C"])
    check("T7 the full farm name works too",
          B.farm_matches("Wind Farm A", "Wind Farm A")
          and not B.farm_matches("Wind Farm A", "Wind Farm B"))
    check("T7 a bare word from the name selects nothing",
          not any(B.farm_matches("farm", f) for f in farms))
    check("T7 no prefix means every farm",
          all(B.farm_matches(None, f) for f in farms))

    with tempfile.TemporaryDirectory() as root:
        for letter in ("A", "B", "C"):
            d = os.path.join(root, "Wind Farm %s" % letter)
            os.makedirs(os.path.join(d, "datasets"))
            with open(os.path.join(d, "feature_description.csv"), "w",
                      encoding="utf-8", newline="") as f:
                f.write("sensor_name;statistics_type;description;unit;"
                        "is_angle;is_counter\n")
                f.write("sensor_0;average;Ambient temperature;degC;False;False\n")
                f.write("sensor_1;average;Rotor speed;rpm;False;False\n")
                f.write("sensor_2;average;Rotor bearing temperature;degC;False;False\n")
                f.write("sensor_3;average;Pitch angle;deg;True;False\n")
            # Each farm names its wind channel differently, as the real ones do.
            with open(os.path.join(d, "datasets", "1.csv"), "w",
                      encoding="utf-8", newline="") as f:
                n = {"A": 3, "B": 61, "C": 236}[letter]
                f.write("time_stamp;wind_speed_%d_avg;power_%d_avg\n" % (n, n))
                f.write("2023-01-01 00:00:00;8.0;1000\n")
        out = os.path.join(root, "out")
        proc = subprocess.run(
            [sys.executable, BUILDER, "--workdir", root, "--output-dir", out,
             "--average-ties",
             "--header-override", "A:wind_speed=wind_speed_3_avg",
             "--override-unit", "m/s"],
            capture_output=True, text=True)
        check("T7 the builder runs on three farms", proc.returncode == 0,
              (proc.stderr or "")[-400:])
        if proc.returncode == 0:
            maps = {}
            for letter in ("A", "B", "C"):
                maps[letter] = json.load(open(
                    os.path.join(out, "signal_map_Wind_Farm_%s.json" % letter),
                    encoding="utf-8"))
            check("T7 Farm A got the override",
                  maps["A"].get("wind_speed", {}).get("column") == "wind_speed_3_avg")
            check("T7 Farm B did NOT inherit Farm A's column",
                  maps["B"].get("wind_speed", {}).get("column") != "wind_speed_3_avg",
                  "Farm B wind_speed = %r"
                  % maps["B"].get("wind_speed", {}).get("column"))
            check("T7 Farm C did NOT inherit Farm A's column",
                  maps["C"].get("wind_speed", {}).get("column") != "wind_speed_3_avg",
                  "Farm C wind_speed = %r"
                  % maps["C"].get("wind_speed", {}).get("column"))
            # And the unresolved-signal path should read the header and say
            # which columns exist, rather than telling the operator to go look.
            check("T7 an unresolved wind speed reports the real header columns",
                  "wind_speed_61_avg" in proc.stdout
                  and "wind_speed_236_avg" in proc.stdout,
                  "stdout did not name the per-farm wind columns")

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
