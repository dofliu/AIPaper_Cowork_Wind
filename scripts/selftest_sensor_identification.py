#!/usr/bin/env python3
"""
Self-test for sensor_identification_profile.py.

Builds a synthetic wind farm whose anonymised channel identities are KNOWN,
runs the profiler as a subprocess, and asserts it recovers them. Needs no
CARE v6 data, so it runs anywhere:

    python3 scripts/selftest_sensor_identification.py

Ground truth planted in the fixture:

    sensor_11_avg -> rotor speed              (1.2 x wind, saturating at 14.5)
    sensor_23_avg -> ambient temperature      (annual cycle, power-independent)
    sensor_31_avg -> main bearing temperature (ambient + 18 + 0.011 x power)
    sensor_44_avg -> pitch angle              (0 below rated, opening above)

Two decoys are planted because they are the failure modes that matter:

    sensor_9_avg  -> a power-derived channel (0.6 x power). It correlates with
                     power at r=1.0 and must NOT beat the real rotor speed.
    sensor_7_avg  -> pure noise. It must not win anything.

The anchors (power_29_avg, wind_speed_3_avg) must also stay out of the
candidate pool — an earlier version let the power anchor win the rotor-speed
template by correlating perfectly with itself.

Exit code: 0 if every assertion holds, 1 otherwise.
"""

import csv
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILER = os.path.join(HERE, "sensor_identification_profile.py")

EXPECTED = {
    "rotor_speed": "sensor_11_avg",
    "ambient_temperature": "sensor_23_avg",
    "main_bearing_temperature": "sensor_31_avg",
    "pitch_angle": "sensor_44_avg",
}

N_ROWS = 30000
RATED_WIND = 12.0
RATED_POWER = 2000.0


def build_case(path, seed, start):
    rng = random.Random(seed)
    rows = []
    for i in range(N_ROWS):
        ts = start + timedelta(minutes=10 * i)
        doy = ts.timetuple().tm_yday

        wind = min(max(0.0, rng.weibullvariate(8.5, 2.1)), 26.0)

        if wind < 3:
            power = 0.0
        elif wind < RATED_WIND:
            power = RATED_POWER * ((wind - 3) / (RATED_WIND - 3)) ** 3
        else:
            power = RATED_POWER
        power = max(0.0, power + rng.gauss(0, 40))

        rotor = min(14.5, 1.2 * wind) + rng.gauss(0, 0.25)
        ambient = 9.0 + 11.0 * math.cos(2 * math.pi * (doy - 200) / 365.25) + rng.gauss(0, 2.0)
        bearing = ambient + 18.0 + 0.011 * power + rng.gauss(0, 1.2)
        pitch = 0.0 if wind < RATED_WIND else min(28.0, (wind - RATED_WIND) * 2.6)
        pitch = max(-1.0, pitch + rng.gauss(0, 0.25))

        rows.append({
            "time_stamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "asset_id": seed,
            "id": i,
            "train_test": "train" if i < int(N_ROWS * 0.67) else "prediction",
            "status_type_id": 0,
            "power_29_avg": round(power, 2),
            "wind_speed_3_avg": round(wind, 3),
            "reactive_power_27_avg": round(rng.gauss(0, 50), 2),
            "sensor_11_avg": round(rotor, 3),
            "sensor_23_avg": round(ambient, 2),
            "sensor_31_avg": round(bearing, 2),
            "sensor_44_avg": round(pitch, 2),
            "sensor_7_avg": round(rng.gauss(500, 80), 2),
            "sensor_9_avg": round(0.6 * power + rng.gauss(0, 30), 2),
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    if not os.path.isfile(PROFILER):
        print("profiler not found: %s" % PROFILER, file=sys.stderr)
        return 1

    failures = []
    checks = 0

    def check(name, cond, detail=""):
        nonlocal checks
        checks += 1
        if cond:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s %s" % (name, detail))
            failures.append(name)

    with tempfile.TemporaryDirectory() as root:
        farm_dir = os.path.join(root, "Wind Farm A", "datasets")
        os.makedirs(farm_dir)
        for case in range(3):
            build_case(os.path.join(farm_dir, "%d.csv" % case),
                       seed=case, start=datetime(2022, 1, 1) + timedelta(days=7 * case))

        out_dir = os.path.join(root, "profile_out")
        proc = subprocess.run(
            [sys.executable, PROFILER,
             "--workdir", root, "--output-dir", out_dir,
             "--cases-per-farm", "3", "--max-rows-per-case", "8000"],
            capture_output=True, text=True)
        check("profiler exits 0", proc.returncode == 0, proc.stderr[-400:])
        if proc.returncode != 0:
            return 1

        summary = json.load(open(os.path.join(out_dir, "identification_summary.json"),
                                 encoding="utf-8"))
        check("summary is CANDIDATE_UNRATIFIED", summary["status"] == "CANDIDATE_UNRATIFIED")

        farm = summary["farms"]["Wind Farm A"]
        check("power anchor found", farm["anchor_power"] == "power_29_avg",
              "got %s" % farm["anchor_power"])
        check("wind anchor found", farm["anchor_wind"] == "wind_speed_3_avg",
              "got %s" % farm["anchor_wind"])

        for signal, expected_col in EXPECTED.items():
            got = farm["top_pick"][signal]
            check("%s -> %s" % (signal, expected_col), got == expected_col,
                  "got %s" % got)

        cands = json.load(open(os.path.join(out_dir, "signal_candidates_Wind_Farm_A.json"),
                               encoding="utf-8"))["candidates"]

        # The anchors must not appear anywhere in the candidate pool.
        all_cols = {c["column"] for v in cands.values() for c in v["candidates"]}
        check("anchors excluded from candidates",
              not ({"power_29_avg", "wind_speed_3_avg", "reactive_power_27_avg"} & all_cols),
              "leaked: %s" % ({"power_29_avg", "wind_speed_3_avg"} & all_cols))

        # The power-derived decoy may appear, but must never win rotor speed.
        rotor_top = cands["rotor_speed"]["candidates"][0]
        check("power-derived decoy does not win rotor_speed",
              rotor_top["column"] != "sensor_9_avg", "got %s" % rotor_top["column"])

        # Pure noise must win nothing.
        winners = {v["candidates"][0]["column"] for v in cands.values() if v["candidates"]}
        check("noise channel wins nothing", "sensor_7_avg" not in winners)

        # Evidence must be present and human-readable, not just a bare score.
        check("winning candidates carry evidence",
              all(v["candidates"][0]["evidence"] for v in cands.values() if v["candidates"]))

        draft = json.load(open(os.path.join(out_dir, "signal_map_draft_Wind_Farm_A.json"),
                               encoding="utf-8"))
        check("draft is marked unratified", draft["_status"] == "CANDIDATE_UNRATIFIED")
        check("draft units are placeholders, not invented",
              all("CONFIRM" in draft[s]["unit"] for s in EXPECTED if draft[s].get("unit")))

        # A draft carrying the warning block must be rejected by the C0 gate,
        # which only accepts entries with a real 'unit'.
        check("draft is not directly usable as a C0 signal map",
              any(k.startswith("_") for k in draft))

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
