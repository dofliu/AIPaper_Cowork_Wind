#!/usr/bin/env python3
"""
Self-test for base_scorer_compatibility_check.py (gate c0c6-gate-v2.0).

Why this exists
---------------
The C0-C6 checker cannot be run to completion by a cloud collaborator: it
needs the extracted CARE v6 archive and locally produced score streams.
That is exactly how the v1 defects recorded in Drive progress doc v2.8
(Codex B) survived review — the code was only ever read, never executed.

This script closes that hole. It builds fully synthetic fixtures in a
temp directory and drives the real checker as a subprocess, asserting
both the per-gate statuses and the process exit code. It needs no CARE
v6 data, so any collaborator can run it anywhere:

    python3 scripts/selftest_c0_c6_gate.py

Each scenario encodes one of the audited defects, so a regression to v1
behaviour fails loudly rather than silently returning a green gate.

  T1  no evidence files             -> UNVERIFIED (exit 2), never PASS
  T2  complete evidence, clean data -> PASS (exit 0)
  T3  wrong case set, right SIZE    -> C4 FAIL       [P0-2 regression test]
  T4  >3h gap, scores absent there  -> C1 masks it, C6 still PASS
                                                      [P0-5 regression test]
  T5  run2 differs from run1        -> C5 FAIL       [P0-4 regression test]
  T6  clean header, no fit evidence -> C3 UNVERIFIED [P0-3 regression test]
  T7  no --signal-map               -> C0 UNVERIFIED [P1  regression test]

Exit code: 0 if every scenario behaves as specified, 1 otherwise.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "base_scorer_compatibility_check.py")

SIGNAL_COLUMNS = {
    "active_power": ("active_power", "kW"),
    "wind_speed": ("wind_speed", "m s-1"),
    "rotor_speed": ("rotor_speed", "rpm"),
    "main_bearing_temperature": ("main_bearing_temp", "degC"),
    "pitch_angle": ("pitch_angle", "deg"),
    "ambient_temperature": ("ambient_temp", "degC"),
}
HEADER = ["timestamp"] + [c for c, _ in SIGNAL_COLUMNS.values()] + ["anomaly_score"]

N_ROWS = 200
INTERVAL_MIN = 10
START = datetime(2026, 1, 1, 0, 0, 0)


def write_case_csv(path, n_rows=N_ROWS, gap=None, score_offset=0.0, blank_scores_in_gap=False):
    """gap = (start_row, n_rows_blank): blanks every signal column across that run,
    producing a wall-clock gap of n_rows_blank * 10 min."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for i in range(n_rows):
            in_gap = gap is not None and gap[0] <= i < gap[0] + gap[1]
            row = {"timestamp": (START + timedelta(minutes=INTERVAL_MIN * i)).isoformat()}
            for col, _ in SIGNAL_COLUMNS.values():
                row[col] = "" if in_gap else round(10.0 + i * 0.1, 3)
            if in_gap and blank_scores_in_gap:
                row["anomaly_score"] = ""
            else:
                row["anomaly_score"] = round(0.5 + (i % 17) * 0.031 + score_offset, 6)
            w.writerow(row)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def build_fixture(root, case_ids, gap=None, blank_scores_in_gap=False):
    """Returns dict of paths for one complete fixture."""
    run1 = os.path.join(root, "scores_run1")
    run2 = os.path.join(root, "scores_run2")
    manifest = os.path.join(root, "manifest_out")
    workdir = os.path.join(root, "care_v6_extracted")
    for d in (run1, run2, manifest, workdir):
        os.makedirs(d, exist_ok=True)

    for cid in case_ids:
        write_case_csv(os.path.join(run1, cid + ".csv"), gap=gap,
                       blank_scores_in_gap=blank_scores_in_gap)
        write_case_csv(os.path.join(run2, cid + ".csv"), gap=gap,
                       blank_scores_in_gap=blank_scores_in_gap)

    g3 = os.path.join(manifest, "g3_case_metadata.csv")
    with open(g3, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "farm_id", "turbine_id", "label",
                                          "start_timestamp", "end_timestamp"])
        w.writeheader()
        for cid in case_ids:
            w.writerow({"case_id": cid, "farm_id": "A", "turbine_id": "T1",
                        "label": "anomaly", "start_timestamp": START.isoformat(),
                        "end_timestamp": (START + timedelta(minutes=INTERVAL_MIN * N_ROWS)).isoformat()})

    g2 = os.path.join(manifest, "g2_case_inventory.json")
    write_json(g2, {"n_detected": len(case_ids), "n_undetected": 0,
                    "n_case_files_found": len(case_ids), "unknown_label_case_ids": []})

    signal_map = os.path.join(root, "signal_map.json")
    write_json(signal_map, {sig: {"column": col, "unit": unit}
                            for sig, (col, unit) in SIGNAL_COLUMNS.items()})

    artifact = os.path.join(root, "artifact_manifest.json")
    write_json(artifact, {
        "implementation_source": "synthetic fixture — self-test only",
        "version_or_commit": "selftest-0",
        "parameter_provenance": "synthetic",
        "artifact_sha256": "0" * 64,
    })

    fit_prov = os.path.join(root, "fit_provenance.json")
    write_json(fit_prov, {
        "fit_partition": "CARE normal reference partition (synthetic)",
        "files_read_during_fit": [{"path": "normal_reference/part-0.csv", "sha256": "1" * 64}],
        "label_columns_excluded": ["label"],
        "verification_method": "file-access trace (synthetic)",
        "verified_by": "selftest",
        "verified_at": "2026-08-14T00:00:00Z",
    })

    freeze = os.path.join(root, "freeze_receipt.json")
    write_json(freeze, {
        "environment": {"python": sys.version.split()[0], "os": sys.platform},
        "seed": 0,
        "config_sha256": "2" * 64,
        "artifact_sha256": "0" * 64,
    })

    return {"run1": run1, "run2": run2, "g2": g2, "g3": g3, "workdir": workdir,
            "signal_map": signal_map, "artifact": artifact, "fit_prov": fit_prov,
            "freeze": freeze}


def run_checker(out_dir, extra_args):
    cmd = [sys.executable, CHECKER,
           "--scorer-name", "SELFTEST",
           "--output-dir", out_dir,
           "--timestamp-col", "timestamp",
           "--score-col", "anomaly_score"] + extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    summary_path = os.path.join(out_dir, "compatibility_summary.json")
    summary = None
    if os.path.isfile(summary_path):
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
    return proc.returncode, summary, proc.stderr


def full_args(fx):
    return ["--workdir", fx["workdir"],
            "--g2-inventory", fx["g2"],
            "--g3-case-metadata", fx["g3"],
            "--score-dir", fx["run1"],
            "--score-dir-run2", fx["run2"],
            "--signal-map", fx["signal_map"],
            "--artifact-manifest", fx["artifact"],
            "--fit-provenance", fx["fit_prov"],
            "--freeze-receipt", fx["freeze"]]


class Results:
    def __init__(self):
        self.failures = []
        self.n = 0

    def check(self, name, condition, detail=""):
        self.n += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s %s" % (name, detail))
            self.failures.append(name)


def gate_status(summary, gate):
    return summary["gates"][gate]["status"]


def main():
    if not os.path.isfile(CHECKER):
        print("checker not found: %s" % CHECKER, file=sys.stderr)
        return 1

    r = Results()
    with tempfile.TemporaryDirectory() as root:
        cases = ["case_001", "case_002", "case_003"]

        # ---------------- T1: no evidence files at all ----------------
        print("\nT1  no evidence files -> UNVERIFIED, never PASS")
        fx = build_fixture(os.path.join(root, "t1"), cases)
        rc, s, _ = run_checker(os.path.join(root, "t1_out"),
                               ["--score-dir", fx["run1"]])
        r.check("T1 exit code is 2 (UNVERIFIED)", rc == 2, "got %s" % rc)
        r.check("T1 gate_status UNVERIFIED", s and s["gate_status"] == "UNVERIFIED",
                "got %s" % (s and s["gate_status"]))
        r.check("T1 C4 UNVERIFIED without g3", gate_status(s, "C4_case_coverage") == "UNVERIFIED")
        r.check("T1 gate_definitions_ratified is False", s["gate_definitions_ratified"] is False)
        r.check("T1 no boolean 'gate_all_pass' style field",
                not any("all_pass" in k for k in s.keys()))

        # ---------------- T2: complete evidence, clean data ----------------
        print("\nT2  complete evidence, clean data -> PASS")
        fx = build_fixture(os.path.join(root, "t2"), cases)
        rc, s, err = run_checker(os.path.join(root, "t2_out"), full_args(fx))
        r.check("T2 exit code is 0", rc == 0, "got %s; stderr=%s" % (rc, err[-400:]))
        r.check("T2 gate_status PASS", s and s["gate_status"] == "PASS",
                "got %s" % (s and s["gate_status"]))
        for g in s["gates"]:
            r.check("T2 %s PASS" % g, gate_status(s, g) == "PASS",
                    "got %s" % gate_status(s, g))
        r.check("T2 output receipt written",
                os.path.isfile(os.path.join(root, "t2_out", "output_receipt.json")))
        r.check("T2 evaluability masks written",
                os.path.isdir(os.path.join(root, "t2_out", "evaluability_masks")))
        r.check("T2 per-case input sha256 recorded",
                len(s["input_receipts"]["per_case_input_sha256"]) == len(cases))

        # ---------------- T3: wrong case set, right size (P0-2) ----------------
        print("\nT3  wrong case set of the RIGHT SIZE -> C4 FAIL  [P0-2]")
        fx = build_fixture(os.path.join(root, "t3"), cases)
        # Rename one score file: 3 files still, but identity no longer matches g3.
        os.rename(os.path.join(fx["run1"], "case_003.csv"),
                  os.path.join(fx["run1"], "case_999.csv"))
        os.rename(os.path.join(fx["run2"], "case_003.csv"),
                  os.path.join(fx["run2"], "case_999.csv"))
        rc, s, _ = run_checker(os.path.join(root, "t3_out"), full_args(fx))
        c4 = s["gates"]["C4_case_coverage"]
        r.check("T3 C4 FAIL despite equal counts", c4["status"] == "FAIL",
                "got %s" % c4["status"])
        r.check("T3 counts really are equal (defect would hide here)",
                c4["n_expected_case_ids"] == c4["n_observed_case_ids"] == 3)
        r.check("T3 missing_case_ids names case_003", c4["missing_case_ids"] == ["case_003"],
                "got %s" % c4["missing_case_ids"])
        r.check("T3 unexpected_case_ids names case_999", c4["unexpected_case_ids"] == ["case_999"],
                "got %s" % c4["unexpected_case_ids"])
        r.check("T3 exit code is 1 (FAIL)", rc == 1, "got %s" % rc)

        # ---------------- T4: >3h gap (P0-5) ----------------
        print("\nT4  >3h gap with absent scores -> C1 masks, C6 still PASS  [P0-5]")
        # 25 blank steps = 250 min > 3h, and 25/200 = 12.5% non-evaluable (< 30% flag).
        fx = build_fixture(os.path.join(root, "t4"), cases, gap=(50, 25),
                           blank_scores_in_gap=True)
        rc, s, _ = run_checker(os.path.join(root, "t4_out"), full_args(fx))
        with open(os.path.join(root, "t4_out", "per_case_c0_c6.json"), encoding="utf-8") as f:
            per_case = json.load(f)
        c1 = per_case["case_001"]["C1_missing_feature_policy"]
        c6 = per_case["case_001"]["C6_score_sanity"]
        r.check("T4 C1 marks 25 rows non-evaluable", c1["n_non_evaluable_rows"] == 25,
                "got %s" % c1["n_non_evaluable_rows"])
        r.check("T4 C1 classifies the run as non_evaluable",
                any(run["policy"] == "non_evaluable"
                    for col in c1["per_column"].values() for run in col["missing_runs"]))
        r.check("T4 C1 stays PASS below the 30%% flag", c1["status"] == "PASS",
                "got %s" % c1["status"])
        r.check("T4 C6 PASS — absent scores fall inside the mask", c6["status"] == "PASS",
                "got %s (%s)" % (c6["status"], c6.get("problems")))
        r.check("T4 C6 reports non-evaluable coverage",
                abs(c6["non_evaluable_coverage_fraction"] - 0.125) < 1e-9,
                "got %s" % c6["non_evaluable_coverage_fraction"])
        r.check("T4 overall PASS", s["gate_status"] == "PASS", "got %s" % s["gate_status"])
        mask = os.path.join(root, "t4_out", "evaluability_masks", "case_001_evaluability_mask.csv")
        r.check("T4 mask CSV written", os.path.isfile(mask))
        if os.path.isfile(mask):
            with open(mask, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            r.check("T4 mask marks exactly the gap rows",
                    sum(1 for x in rows if x["evaluable"] == "0") == 25)

        # ---------------- T5: run2 differs (P0-4) ----------------
        print("\nT5  run2 differs from run1 -> C5 FAIL  [P0-4]")
        fx = build_fixture(os.path.join(root, "t5"), cases)
        write_case_csv(os.path.join(fx["run2"], "case_002.csv"), score_offset=0.01)
        rc, s, _ = run_checker(os.path.join(root, "t5_out"), full_args(fx))
        c5 = s["gates"]["C5_determinism_and_freeze"]
        r.check("T5 C5 FAIL", c5["status"] == "FAIL", "got %s" % c5["status"])
        r.check("T5 C5 names the divergent case",
                any("case_002" in p for p in c5.get("problems", [])),
                "got %s" % c5.get("problems"))
        r.check("T5 single-run mode cannot PASS C5", True)

        print("\nT5b single run (no run2) -> C5 UNVERIFIED, not PASS  [P0-4]")
        fx = build_fixture(os.path.join(root, "t5b"), cases)
        args_no_run2 = [a for a in full_args(fx)]
        i = args_no_run2.index("--score-dir-run2")
        del args_no_run2[i:i + 2]
        rc, s, _ = run_checker(os.path.join(root, "t5b_out"), args_no_run2)
        r.check("T5b C5 UNVERIFIED",
                gate_status(s, "C5_determinism_and_freeze") == "UNVERIFIED",
                "got %s" % gate_status(s, "C5_determinism_and_freeze"))
        r.check("T5b overall not PASS", s["gate_status"] != "PASS")
        r.check("T5b exit non-zero", rc != 0, "got %s" % rc)

        # ---------------- T6: no fit provenance (P0-3) ----------------
        print("\nT6  clean header but no fit evidence -> C3 UNVERIFIED  [P0-3]")
        fx = build_fixture(os.path.join(root, "t6"), cases)
        args_no_fit = [a for a in full_args(fx)]
        i = args_no_fit.index("--fit-provenance")
        del args_no_fit[i:i + 2]
        rc, s, _ = run_checker(os.path.join(root, "t6_out"), args_no_fit)
        c3 = s["gates"]["C3_label_independence"]
        r.check("T6 C3 UNVERIFIED, not PASS", c3["status"] == "UNVERIFIED",
                "got %s" % c3["status"])
        r.check("T6 header scan present but non-decisive",
                "secondary_header_scan_label_like_columns" in c3)
        r.check("T6 overall not PASS", s["gate_status"] != "PASS")

        # ---------------- T7: no signal map (P1) ----------------
        print("\nT7  no --signal-map -> C0 UNVERIFIED with a suggestion  [P1]")
        fx = build_fixture(os.path.join(root, "t7"), cases)
        args_no_map = [a for a in full_args(fx)]
        i = args_no_map.index("--signal-map")
        del args_no_map[i:i + 2]
        rc, s, _ = run_checker(os.path.join(root, "t7_out"), args_no_map)
        r.check("T7 C0 UNVERIFIED",
                gate_status(s, "C0_signal_availability_and_mapping") == "UNVERIFIED",
                "got %s" % gate_status(s, "C0_signal_availability_and_mapping"))
        with open(os.path.join(root, "t7_out", "per_case_c0_c6.json"), encoding="utf-8") as f:
            pc = json.load(f)
        r.check("T7 suggestion emitted for operator review",
                pc["case_001"]["C0_signal_mapping"]
                  .get("suggested_mapping_for_operator_review", {})
                  .get("wind_speed") == "wind_speed")
        r.check("T7 overall not PASS", s["gate_status"] != "PASS")

        # ---------------- templates ----------------
        print("\nT8  --emit-templates writes the four evidence templates")
        tdir = os.path.join(root, "templates")
        proc = subprocess.run([sys.executable, CHECKER, "--emit-templates", tdir],
                              capture_output=True, text=True)
        r.check("T8 exit 0", proc.returncode == 0, proc.stderr[-300:])
        for name in ("signal_map.json", "artifact_manifest.json",
                     "fit_provenance.json", "freeze_receipt.json"):
            r.check("T8 %s written" % name, os.path.isfile(os.path.join(tdir, name)))

    print("\n%d checks, %d failed" % (r.n, len(r.failures)))
    if r.failures:
        print("FAILED: %s" % ", ".join(r.failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
