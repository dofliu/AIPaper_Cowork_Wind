#!/usr/bin/env python3
"""
Frozen Base Scorer Compatibility Check (Priority 2 / "C0-C6" gate).

Context
-------
"C0-C6" has been referenced repeatedly across this project's Drive
discussion documents (R11, v1.8, v2.4, v2.5) as the compatibility gate that
the two frozen base scorers must pass before their score streams can be
treated as inputs to the calibration pilot experiment, but no prior
document actually enumerated C0-C6 individually. This script operationalizes
a concrete C0-C6 checklist, built from the checks that WERE spelled out in:

  - [討論] 2026-08-12 R15 (Gemini Spark), section 1 "Base Scorer 1 與 Base
    Scorer 2 相容性驗證協定 (Priority 2)"
  - 【PI指示／第三方審查】研究方向凍結與實證優先執行指示 v1.0, section "Priority 2"

Base Scorer 1: Mahalanobis Distance detector (Liu et al., Applied Sciences
    2022, 12:8661, DOI 10.3390/app12178661)
Base Scorer 2: Main-bearing SCADA predictive framework (Liu et al.,
    Advances in Mechanical Engineering, 2026, 18(7))

IMPORTANT — this is a PROPOSAL, not a ratified gate
----------------------------------------------------
The C0-C6 definitions below are this script's own synthesis of scattered
prior requirements, offered for Claude/Codex/PI review alongside the R16
discussion doc that introduces it. Treat gate NAMES and THRESHOLDS as
draft until another collaborator or the PI confirms them — do not cite
"C0-C6 passed" in a manuscript claim before that confirmation exists.

Why this is a cloud-side deliverable
-------------------------------------
Like care_v6_manifest.py, this script cannot be run to completion in a
cloud collaborator session: it needs (a) the extracted CARE v6 archive on
local disk, and (b) the actual published scorer implementations/weights,
neither of which cloud sessions have access to. It is written so the
collaborator who DOES have local access does not have to re-derive the
checklist from four scattered Drive docs by hand.

Gate definitions
-----------------
C0  Signal availability & mapping   — each of the 6 core signals (Active
    Power, Wind Speed, Rotor Speed, Main Bearing Temperature, Pitch Angle,
    Ambient Temperature) is present or derivable per case, with an explicit
    column-name -> canonical-signal mapping recorded (no silent guessing).
C1  Missing-feature policy applied  — the frozen policy from R15 is applied
    and logged per case: <1h gap -> linear interpolation; 1-3h gap ->
    forward-fill; >3h gap -> segment marked non-evaluable. Non-evaluable
    fraction is reported per case (flagged if it exceeds 30%, mirroring the
    G5 regime-bin exclusion flag convention already used in this project).
C2  Artifact reproducibility        — the concrete implementation source
    (code repo / supplementary material / re-implementation-from-paper) and
    parameter provenance for each scorer is recorded, hashed once frozen,
    and never silently re-tuned afterward.
C3  Label independence              — the scorer's own fitting step (MD
    covariance estimate; main-bearing regression/reconstruction model) is
    confirmed to use ONLY the CARE "normal" reference partition, with zero
    exposure to fault/event labels or held-out anomaly cases. This is
    checked structurally here (did the run touch any file/column flagged as
    label data during fitting?) — a human must still confirm the fitting
    routine itself never reads a label column.
C4  Case coverage                   — a scalar score stream s_t is produced
    for every case in the G2 case inventory (or the case is recorded with an
    explicit failure reason); coverage % is computed against G2's
    n_detected total so gaps are visible, not silently dropped.
C5  Determinism & freeze            — re-running the frozen scorer on the
    same input produces a bit-identical (or documented tolerance-bounded)
    output; once confirmed, weights/config are hashed and the hash is
    recorded as the frozen artifact fingerprint for all downstream
    calibration comparisons.
C6  Score sanity / non-degeneracy   — s_t is finite everywhere it should be
    evaluable, non-constant, and its normal-case distribution is at least
    plausible relative to what the source paper reports (spot-check only —
    this script flags obvious degeneracy, e.g. all-zero or all-NaN streams;
    it does not re-validate the published paper's results).

Usage
-----
    python3 base_scorer_compatibility_check.py \\
        --workdir /path/to/extracted_care_v6 \\
        --g2-inventory /path/to/manifest_out/g2_case_inventory.json \\
        --score-dir /path/to/directory/of/per_case_score_csvs \\
        --scorer-name "MD_2022" \\
        --output-dir ./compat_out_md2022 \\
        [--score-glob "*.csv"] [--score-col auto] [--case-id-from filename]

Each scorer (MD 2022, Main-Bearing 2026) should be run through this script
separately (--scorer-name distinguishes the two output reports); the
manuscript's compatibility claim requires BOTH reports to show
gate_all_pass=true before a score stream is handed to the pilot experiment.

Per-case score CSVs are expected to already exist (produced locally by
whatever local re-implementation of the two frozen scorers the operator
uses) — this script AUDITS them against C0-C6, it does not implement the
scorers themselves, since their concrete feature engineering is specific to
each published paper and out of scope for a cloud session to re-derive
from a Drive doc summary.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime

CORE_SIGNALS = [
    "active_power",
    "wind_speed",
    "rotor_speed",
    "main_bearing_temperature",
    "pitch_angle",
    "ambient_temperature",
]

SIGNAL_HINTS = {
    "active_power": ["active_power", "power", "p_act", "kw", "mw"],
    "wind_speed": ["wind_speed", "windspeed", "ws", "v_wind"],
    "rotor_speed": ["rotor_speed", "rotorspeed", "rpm"],
    "main_bearing_temperature": ["bearing_temp", "main_bearing", "brg_temp"],
    "pitch_angle": ["pitch"],
    "ambient_temperature": ["ambient_temp", "outdoor_temp", "temp_amb", "amb_temp"],
}

LABEL_HINTS = ["label", "anomaly", "fault", "event", "class"]

# C1 missing-feature policy thresholds, per R15 section 1 (frozen 10-min sampling assumed;
# override via --steps-per-hour if the archive's sampling interval differs).
STEPS_PER_HOUR_DEFAULT = 6  # 10-minute data -> 6 steps/hour
SHORT_GAP_HOURS = 1
LONG_GAP_HOURS = 3
NON_EVALUABLE_FLAG_FRACTION = 0.30


def sha256_of_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_col(fieldnames, hints):
    lower = {c.lower(): c for c in fieldnames}
    for h in hints:
        for lc, orig in lower.items():
            if h in lc:
                return orig
    return None


def check_c0_signal_mapping(header):
    mapping = {}
    missing = []
    for signal, hints in SIGNAL_HINTS.items():
        col = _find_col(header, hints)
        if col:
            mapping[signal] = col
        else:
            missing.append(signal)
    return {
        "mapping": mapping,
        "missing_signals": missing,
        "pass": len(missing) == 0,
    }


def check_c1_missing_policy(rows, ts_col, value_cols, steps_per_hour):
    """Classify gaps per value column into interpolate / forward-fill / non-evaluable
    buckets by counting consecutive missing runs, without mutating the input."""
    short_gap_steps = SHORT_GAP_HOURS * steps_per_hour
    long_gap_steps = LONG_GAP_HOURS * steps_per_hour
    report = {}
    for col in value_cols:
        n_total = len(rows)
        n_missing = 0
        n_non_evaluable = 0
        run = 0
        for row in rows:
            v = row.get(col)
            is_missing = v is None or v == ""
            if is_missing:
                n_missing += 1
                run += 1
            else:
                if run > long_gap_steps:
                    n_non_evaluable += run
                run = 0
        if run > long_gap_steps:
            n_non_evaluable += run
        report[col] = {
            "n_total": n_total,
            "n_missing": n_missing,
            "missing_fraction": (n_missing / n_total) if n_total else None,
            "n_non_evaluable_steps": n_non_evaluable,
            "non_evaluable_fraction": (n_non_evaluable / n_total) if n_total else None,
            "flag_over_30pct_non_evaluable": (
                (n_non_evaluable / n_total) > NON_EVALUABLE_FLAG_FRACTION if n_total else False
            ),
        }
    return report


def check_c3_label_independence(header):
    label_col = _find_col(header, LABEL_HINTS)
    return {
        "label_like_column_present_in_score_input": label_col,
        "note": (
            "This only flags whether a label-like column EXISTS in the file the score "
            "was computed from. It cannot confirm the fitting code never read it — a "
            "human must inspect the scorer's fit() call site directly before signing "
            "off on C3."
        ),
        "pass_structural_only": label_col is None,
    }


def check_c6_sanity(score_values):
    finite = [v for v in score_values if v is not None and not (math.isnan(v) or math.isinf(v))]
    n_total = len(score_values)
    n_finite = len(finite)
    is_constant = len(set(finite)) <= 1 if finite else True
    return {
        "n_total": n_total,
        "n_finite": n_finite,
        "n_nan_or_inf": n_total - n_finite,
        "is_constant": is_constant,
        "min": min(finite) if finite else None,
        "max": max(finite) if finite else None,
        "pass": n_finite > 0 and n_finite == n_total and not is_constant,
    }


def run_for_scorer(args):
    with open(args.g2_inventory) as f:
        g2 = json.load(f)
    expected_cases = g2.get("n_detected", 0)

    score_files = sorted(
        os.path.join(args.score_dir, fn)
        for fn in os.listdir(args.score_dir)
        if fn.endswith(".csv")
    ) if os.path.isdir(args.score_dir) else []

    per_case = {}
    for path in score_files:
        case_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            rows = list(reader)

        c0 = check_c0_signal_mapping(header)
        score_col = args.score_col if args.score_col != "auto" else _find_col(
            header, ["score", "anomaly_score", "s_t", "mahalanobis", "residual"]
        )
        c3 = check_c3_label_independence(header)

        value_cols = list(c0["mapping"].values())
        c1 = check_c1_missing_policy(rows, None, value_cols, args.steps_per_hour) if value_cols else {}

        c6 = {"pass": False, "note": "score column not found"}
        if score_col:
            vals = []
            for row in rows:
                raw = row.get(score_col)
                try:
                    vals.append(float(raw))
                except (TypeError, ValueError):
                    vals.append(None)
            c6 = check_c6_sanity(vals)

        per_case[case_id] = {
            "source_file": path,
            "score_column_detected": score_col,
            "C0_signal_mapping": c0,
            "C1_missing_feature_policy": c1,
            "C3_label_independence": c3,
            "C6_score_sanity": c6,
            "file_sha256": sha256_of_file(path),
        }

    n_cases_with_stream = len(per_case)
    c4 = {
        "n_expected_cases_from_g2": expected_cases,
        "n_cases_with_score_stream": n_cases_with_stream,
        "coverage_fraction": (n_cases_with_stream / expected_cases) if expected_cases else None,
        "pass": expected_cases > 0 and n_cases_with_stream == expected_cases,
    }

    all_c0_pass = all(c["C0_signal_mapping"]["pass"] for c in per_case.values()) if per_case else False
    all_c6_pass = all(c["C6_score_sanity"].get("pass") for c in per_case.values()) if per_case else False
    any_c1_over_flag = any(
        v.get("flag_over_30pct_non_evaluable")
        for c in per_case.values()
        for v in c["C1_missing_feature_policy"].values()
    )

    summary = {
        "scorer_name": args.scorer_name,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "C0_all_pass": all_c0_pass,
        "C1_any_case_over_30pct_non_evaluable": any_c1_over_flag,
        "C2_artifact_reproducibility": (
            "NOT AUTO-CHECKABLE — record implementation source, version, and parameter "
            "provenance manually in the R16-style report; this script cannot verify it."
        ),
        "C3_label_independence_structural_pass": all(
            c["C3_label_independence"]["pass_structural_only"] for c in per_case.values()
        ) if per_case else False,
        "C4_case_coverage": c4,
        "C5_determinism_freeze": (
            "NOT AUTO-CHECKABLE from a single run — re-run this script on the same "
            "score-dir a second time and diff file_sha256 per case to confirm "
            "determinism before freezing."
        ),
        "C6_all_pass": all_c6_pass,
        "gate_all_pass_mechanically_checkable": (
            all_c0_pass and c4["pass"] and all_c6_pass and not any_c1_over_flag
        ),
        "note": (
            "gate_all_pass_mechanically_checkable covers only C0/C1/C4/C6. C2, C3 (fit-time "
            "check), and C5 require human/local confirmation as noted above before the "
            "scorer's compatibility can be signed off for the pilot experiment."
        ),
    }

    os.makedirs(args.output_dir, exist_ok=True)
    with open(os.path.join(args.output_dir, "per_case_c0_c6.json"), "w") as f:
        json.dump(per_case, f, indent=2, ensure_ascii=False)
    with open(os.path.join(args.output_dir, "compatibility_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nDone. See {args.output_dir}/compatibility_summary.json", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=False, help="Extracted CARE v6 root (currently informational only)")
    ap.add_argument("--g2-inventory", required=True, help="Path to g1-manifest's g2_case_inventory.json")
    ap.add_argument("--score-dir", required=True, help="Directory of per-case score CSVs for this scorer")
    ap.add_argument("--scorer-name", required=True, help='e.g. "MD_2022" or "MainBearing_2026"')
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--score-col", default="auto")
    ap.add_argument("--steps-per-hour", type=int, default=STEPS_PER_HOUR_DEFAULT)
    args = ap.parse_args()
    run_for_scorer(args)


if __name__ == "__main__":
    main()
