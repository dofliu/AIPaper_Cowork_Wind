#!/usr/bin/env python3
"""
Self-test for base_scorer_md2022.py.

  T1  A fault in a signal the scorer USES raises the score materially.
      Without this, everything downstream is measuring noise.
  T2  A clean case stays flat, so T1 is detection and not drift.
  T3  A fault in a signal declared not_available is INVISIBLE. This is not
      a defect -- it is the consequence of Farm A having no main bearing
      channel, and it is worth a failing test if it ever stops being true,
      because the manuscript's limitation section depends on it.
  T4  The three C0-C6 evidence files are written at fit time and carry what
      the gate requires.
  T5  Label isolation: the fit reads no label column. Checked by feeding a
      status column that would wreck the covariance if it were read.
  T6  Determinism, as C5 requires.

    python3 scripts/selftest_md2022.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import csv
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCORER = os.path.join(HERE, "base_scorer_md2022.py")

N = 6000
FIT_ROWS = 3000
FAULT_AT = 4000
COLS = ["time_stamp", "train_test", "status_type_id", "power_29_avg",
        "wind_speed_3_avg", "sensor_52_avg", "sensor_7_avg", "sensor_5_avg",
        "sensor_0_avg"]


def build(path, rng, fault_on=None):
    """fault_on: which column ramps from FAULT_AT, or None for a clean case."""
    start = datetime(2023, 1, 1)
    rows = []
    for i in range(N):
        wind = min(max(rng.weibullvariate(8.5, 2.0), 0.0), 25.0)
        power = 0.0 if wind < 3 else (2000.0 * ((wind - 3) / 9.0) ** 3
                                      if wind < 12 else 2000.0)
        rec = {
            "time_stamp": (start + timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S"),
            "train_test": "train" if i < FIT_ROWS else "prediction",
            # A label-like column with a wild scale: if the fit ever read it,
            # the covariance would be dominated by it and T1 would collapse.
            "status_type_id": 0 if i < FAULT_AT else 99999,
            "power_29_avg": power + rng.gauss(0, 30),
            "wind_speed_3_avg": wind,
            "sensor_52_avg": min(14.5, 1.2 * wind) + rng.gauss(0, 0.2),
            "sensor_7_avg": 30 + 0.01 * power + rng.gauss(0, 1),
            "sensor_5_avg": 0.0 if wind < 12 else (wind - 12) * 2.6,
            "sensor_0_avg": 9 + rng.gauss(0, 3),
        }
        if fault_on and i >= FAULT_AT:
            rec[fault_on] += 12.0 * min(1.0, (i - FAULT_AT) / 800.0)
        rows.append({k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in rec.items()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def signal_map(main_bearing_available):
    m = {
        "active_power": {"column": "power_29_avg", "unit": "kW"},
        "wind_speed": {"column": "wind_speed_3_avg", "unit": "m/s"},
        "rotor_speed": {"column": "sensor_52_avg", "unit": "rpm"},
        "pitch_angle": {"column": "sensor_5_avg", "unit": "deg"},
        "ambient_temperature": {"column": "sensor_0_avg", "unit": "degC"},
    }
    if main_bearing_available:
        m["main_bearing_temperature"] = {"column": "sensor_7_avg", "unit": "degC"}
    else:
        m["main_bearing_temperature"] = {
            "not_available": True,
            "reason": "this farm has no main bearing channel",
            "ratified_by": "PI", "ratified_on": "2026-08-15"}
    return m


def mean_score(path, lo, hi):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    values = [float(r["anomaly_score"]) for r in rows[lo:hi] if r["anomaly_score"]]
    return sum(values) / len(values) if values else None


def run_scorer(root, farm_dir, map_path, out, ev):
    proc = subprocess.run(
        [sys.executable, SCORER, "--workdir", root, "--farm", "Wind Farm A",
         "--signal-map", map_path, "--output-dir", out, "--evidence-dir", ev],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print("      scorer failed: %s" % proc.stderr[-500:])
    return proc.returncode == 0


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

    with tempfile.TemporaryDirectory() as root:
        datasets = os.path.join(root, "care", "Wind Farm A", "datasets")
        os.makedirs(datasets)
        rng = random.Random(11)
        build(os.path.join(datasets, "1.csv"), rng, fault_on="sensor_52_avg")
        build(os.path.join(datasets, "2.csv"), rng, fault_on=None)
        build(os.path.join(datasets, "3.csv"), rng, fault_on="sensor_7_avg")

        # ---- T1/T2: main bearing AVAILABLE, fault on rotor speed ----
        print("\nT1/T2  fault in a used signal rises; a clean case stays flat")
        map_a = os.path.join(root, "map_available.json")
        with open(map_a, "w", encoding="utf-8") as f:
            json.dump(signal_map(True), f)
        out_a = os.path.join(root, "scores_a")
        ev_a = os.path.join(root, "evidence_a")
        ok = run_scorer(os.path.join(root, "care"), "Wind Farm A", map_a, out_a, ev_a)
        check("T1 scorer ran", ok)
        if not ok:
            return 1

        before = mean_score(os.path.join(out_a, "1.csv"), FIT_ROWS, FAULT_AT - 100)
        after = mean_score(os.path.join(out_a, "1.csv"), FAULT_AT + 1000, N)
        clean_before = mean_score(os.path.join(out_a, "2.csv"), FIT_ROWS, FAULT_AT - 100)
        clean_after = mean_score(os.path.join(out_a, "2.csv"), FAULT_AT + 1000, N)
        print("      faulted case: %.3f -> %.3f" % (before, after))
        print("      clean case:   %.3f -> %.3f" % (clean_before, clean_after))
        check("T1 score rises at least 3x on the faulted case", after > 3 * before,
              "%.3f -> %.3f" % (before, after))
        check("T2 clean case stays within 30%%",
              abs(clean_after - clean_before) / clean_before < 0.30,
              "%.3f -> %.3f" % (clean_before, clean_after))

        # ---- T3: fault in an unavailable signal is invisible ----
        print("\nT3  a fault in a not_available signal is invisible, by construction")
        map_u = os.path.join(root, "map_unavailable.json")
        with open(map_u, "w", encoding="utf-8") as f:
            json.dump(signal_map(False), f)
        out_u = os.path.join(root, "scores_u")
        ev_u = os.path.join(root, "evidence_u")
        check("T3 scorer ran without the unavailable signal",
              run_scorer(os.path.join(root, "care"), "Wind Farm A", map_u, out_u, ev_u))
        u_before = mean_score(os.path.join(out_u, "3.csv"), FIT_ROWS, FAULT_AT - 100)
        u_after = mean_score(os.path.join(out_u, "3.csv"), FAULT_AT + 1000, N)
        print("      bearing-fault case, bearing excluded: %.3f -> %.3f"
              % (u_before, u_after))
        check("T3 the bearing fault does not move the score",
              abs(u_after - u_before) / u_before < 0.30,
              "%.3f -> %.3f -- if this now detects, the limitation text is stale"
              % (u_before, u_after))
        summary = json.load(open(os.path.join(out_u, "scorer_summary_Wind_Farm_A.json"),
                                 encoding="utf-8"))
        check("T3 the exclusion is recorded in the summary",
              summary["signals_declared_unavailable"] == ["main_bearing_temperature"])
        check("T3 and the signal is absent from the feature set",
              "main_bearing_temperature" not in summary["signals_used"])

        # ---- T4 evidence files ----
        print("\nT4  C0-C6 evidence written at fit time")
        prov = json.load(open(os.path.join(ev_a, "fit_provenance.json"), encoding="utf-8"))
        art = json.load(open(os.path.join(ev_a, "artifact_manifest.json"), encoding="utf-8"))
        frz = json.load(open(os.path.join(ev_a, "freeze_receipt.json"), encoding="utf-8"))
        check("T4 fit_partition names the normal reference",
              "normal" in prov["fit_partition"].lower())
        check("T4 every fit file carries a sha256",
              prov["files_read_during_fit"]
              and all(e.get("sha256") and e.get("path")
                      for e in prov["files_read_during_fit"]))
        check("T4 artifact manifest has the C2 fields",
              all(art.get(k) for k in ("implementation_source", "version_or_commit",
                                       "parameter_provenance", "artifact_sha256")))
        check("T4 artifact manifest states the scope limit",
              "NOT reproduced" in art["parameter_provenance"]
              or "not reproduced" in art["parameter_provenance"].lower())
        check("T4 freeze receipt has the C5 fields",
              all(k in frz for k in ("environment", "seed", "config_sha256",
                                     "artifact_sha256")))

        # ---- T5 label isolation ----
        print("\nT5  the fit never reads a label column")
        check("T5 label columns declared excluded",
              "status_type_id" in prov["label_columns_excluded"])
        # status_type_id jumps to 99999 at FAULT_AT. Had the fit read it, the
        # covariance would be dominated by it and T1's ratio would collapse.
        check("T5 a wild label column did not enter the covariance",
              after > 3 * before,
              "T1's ratio would have collapsed if status_type_id were read")

        # ---- T7 no duplicate header names ----
        # The feature block used to be written under the bare signal names, so
        # the header carried wind_speed twice. csv.DictReader keeps the LAST
        # duplicate, and every downstream tool reads with DictReader, so all of
        # them silently got the feature copy -- which is blank on exactly the
        # rows where a sensor dropped out but wind was still measured fine.
        # Those rows would then miss their regime bin, biasing the conditional
        # coverage result the paper claims. Pinned so it cannot come back.
        print("\nT7  the score CSV has no duplicate column names")
        with open(os.path.join(out_a, "1.csv"), newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        dupes = sorted({c for c in header if header.count(c) > 1})
        check("T7 no column name appears twice", not dupes, "duplicated: %s" % dupes)
        check("T7 the canonical trio leads the header",
              header[:3] == ["timestamp", "wind_speed", "anomaly_score"],
              "got %s" % header[:3])
        check("T7 feature columns are namespaced",
              all(c.startswith("signal_") for c in header[3:]),
              "got %s" % header[3:])

        # A row whose feature vector is incomplete must still report its wind
        # speed -- that is the whole point of the canonical column.
        print("\nT7  wind speed survives a row the scorer could not score")
        hole = os.path.join(datasets, "4.csv")
        build(hole, random.Random(23), fault_on=None)
        with open(hole, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        head, ri = rows[0], rows[0].index("sensor_52_avg")
        blanked = 0
        for r in rows[1:]:
            if r[head.index("train_test")] == "prediction" and blanked < 40:
                r[ri] = ""
                blanked += 1
        with open(hole, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=";").writerows(rows)
        out_h = os.path.join(root, "scores_hole")
        run_scorer(os.path.join(root, "care"), "Wind Farm A", map_a, out_h,
                   os.path.join(root, "evidence_h"))
        with open(os.path.join(out_h, "4.csv"), newline="", encoding="utf-8") as f:
            scored = list(csv.DictReader(f))
        unscorable = [r for r in scored if not r["anomaly_score"]]
        check("T7 the dropout rows really were unscorable",
              len(unscorable) == blanked,
              "expected %d, got %d" % (blanked, len(unscorable)))
        check("T7 and every one of them still carries its wind speed",
              unscorable and all(r["wind_speed"] for r in unscorable),
              "%d of %d read as empty wind"
              % (sum(1 for r in unscorable if not r["wind_speed"]), len(unscorable)))

        # ---- T8 the gate's signal map is emitted, not hand-written ----
        print("\nT8  the C0 map names columns that exist in the score CSV")
        gate_map = json.load(open(os.path.join(ev_a, "signal_map.json"),
                                  encoding="utf-8"))
        named = [e["column"] for e in gate_map.values() if "column" in e]
        check("T8 every named column is really in the score CSV",
              named and all(c in header for c in named),
              "missing: %s" % [c for c in named if c not in header])
        check("T8 units are carried through from the builder's map",
              gate_map["wind_speed"].get("unit") == "m/s",
              "got %r" % gate_map["wind_speed"].get("unit"))
        gate_map_u = json.load(open(os.path.join(ev_u, "signal_map.json"),
                                    encoding="utf-8"))
        check("T8 a not_available declaration is carried through verbatim",
              gate_map_u["main_bearing_temperature"].get("not_available") is True
              and gate_map_u["main_bearing_temperature"].get("ratified_by") == "PI")

        # ---- T9 fault codes do not reach the covariance ----
        # Farm C's sensor_194/195 sit at 850.0 for over 1% of rows. Averaged
        # with three genuine channels near 46 C that produced a main bearing
        # temperature of 363 C, which would have entered the covariance and
        # generated enormous distances -- false alarms, with nothing reported.
        print("\nT9  an out-of-range fault code is rejected per channel")
        bear = os.path.join(datasets, "5.csv")
        build(bear, random.Random(31), fault_on=None)
        with open(bear, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        head = rows[0]
        bi = head.index("sensor_7_avg")
        # Period 37, not 40. The summary's signal_ranges sample every 20th
        # scored row, so a spike period sharing a factor with 20 can land
        # perfectly out of phase and never be sampled -- which is exactly what
        # a first version of this test did, and it read as the filter failing.
        # Stride sampling can miss a periodic artefact entirely; the score CSV
        # below is the ground truth, so assert against that.
        spiked = 0
        for n, r in enumerate(rows[1:]):
            if n % 37 == 0:
                r[bi] = "850.0"
                spiked += 1
        with open(bear, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=";").writerows(rows)

        out_f = os.path.join(root, "scores_filtered")
        out_r = os.path.join(root, "scores_raw")
        run_scorer(os.path.join(root, "care"), "Wind Farm A", map_a, out_f,
                   os.path.join(root, "ev_f"))
        proc = subprocess.run(
            [sys.executable, SCORER, "--workdir", os.path.join(root, "care"),
             "--farm", "Wind Farm A", "--signal-map", map_a,
             "--output-dir", out_r, "--evidence-dir", os.path.join(root, "ev_r"),
             "--no-range-filter"], capture_output=True, text=True)
        check("T9 both runs completed", proc.returncode == 0, proc.stderr[-300:])

        sf = json.load(open(os.path.join(out_f, "scorer_summary_Wind_Farm_A.json"),
                            encoding="utf-8"))
        sr = json.load(open(os.path.join(out_r, "scorer_summary_Wind_Farm_A.json"),
                            encoding="utf-8"))

        def max_bearing(directory):
            with open(os.path.join(directory, "5.csv"), newline="",
                      encoding="utf-8") as f:
                vals = [float(r["signal_main_bearing_temperature"])
                        for r in csv.DictReader(f)
                        if r["signal_main_bearing_temperature"]]
            return max(vals)

        mb_f = max_bearing(out_f)
        mb_r = max_bearing(out_r)
        print("      bearing max: filtered %.2f, unfiltered %.2f" % (mb_f, mb_r))
        check("T9 the fault code reaches the feature vector when unfiltered",
              mb_r > 800, "unfiltered max %.2f -- fixture did not inject" % mb_r)
        check("T9 and is gone when filtered", mb_f < 150,
              "filtered max %.2f" % mb_f)
        check("T9 the rejections are counted per channel, not just dropped",
              sf["range_filter"]["readings_rejected_per_column"].get("sensor_7_avg", 0) > 0,
              "got %s" % sf["range_filter"]["readings_rejected_per_column"])
        check("T9 the filter records that it was enabled",
              sf["range_filter"]["enabled"] is True
              and sr["range_filter"]["enabled"] is False)
        check("T9 and the ranges applied are recorded, not implied",
              "main_bearing_temperature" in sf["range_filter"]["ranges_applied"])

        # ---- T6 determinism ----
        print("\nT6  identical input -> identical output (C5 requirement)")
        out_b = os.path.join(root, "scores_b")
        ev_b = os.path.join(root, "evidence_b")
        run_scorer(os.path.join(root, "care"), "Wind Farm A", map_a, out_b, ev_b)
        same = True
        for name in ("1.csv", "2.csv", "3.csv"):
            with open(os.path.join(out_a, name), encoding="utf-8") as f1, \
                 open(os.path.join(out_b, name), encoding="utf-8") as f2:
                if f1.read() != f2.read():
                    same = False
                    break
        check("T6 two runs produce identical score files", same)

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
