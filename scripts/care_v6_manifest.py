#!/usr/bin/env python3
"""
CARE v6 Data Manifest generator (G1-G6).

Implements the deliverable spec in:
  [交辦] CARE v6 Manifest 交付規格（給 Codex B，本機執行）
  (Drive doc id: 1tHS6nYO2mkwr3_o6I79Vib7_Qm1tTDxHIhZEV3mSodc)

Purpose
-------
This project's cloud-based collaborator sessions cannot process the
5,503,439,673-byte CARE_To_Compare_v6.zip archive (Drive file id
1188sErzQonZPE9EcDRudBBPoa-dlQ7C8) — that step is explicitly assigned to
whichever collaborator has local disk access to the extracted archive.
This script exists so that collaborator does not need to re-derive the
G1-G6 procedure from the spec doc by hand: run it, get a machine-readable
manifest (JSON + CSV) plus a human-readable summary that can be pasted
directly into a new "[數據] R13 — CARE v6 G1-G6 Manifest 執行結果" Drive
doc, per the reporting format in section 7 of the spec.

IMPORTANT — heuristics vs. ground truth
----------------------------------------
G1 (archive integrity: hash / size / top-level tree / file count) requires
no assumptions about internal layout and will work unmodified.

G2-G6 require locating case files, timestamp columns, wind-speed columns,
and label information inside the archive. Nobody on the cloud side has
ever seen the actual internal directory structure of CARE v6, so this
script does NOT hardcode guessed paths. Instead:
  - It auto-detects the case/turbine table files using a configurable glob
    pattern (default "**/*.csv") and a best-effort column-name matcher.
  - Every auto-detected choice (which column is timestamp, which is wind
    speed, which is label) is written into the manifest under
    "detection_notes" so a human can sanity-check or override it via CLI
    flags before trusting the G3-G6 outputs.
  - If auto-detection fails for a given case file, that case is recorded
    with status="undetected" rather than silently skipped or guessed.

This keeps the deliverable honest: G1 is unconditionally trustworthy:
G2-G6 are "best-effort, must be spot-checked against a few known cases
before the manifest is treated as the D0 gate evidence."

Usage
-----
    python3 care_v6_manifest.py \\
        --archive /path/to/CARE_To_Compare_v6.zip \\
        --workdir  /path/to/extract_or_scratch_dir \\
        --output-dir ./manifest_out \\
        [--case-glob "**/*.csv"] \\
        [--timestamp-col auto] [--wind-speed-col auto] [--label-col auto] \\
        [--skip-extract]  # if --workdir already holds the extracted archive

Outputs (in --output-dir)
--------------------------
    g1_archive_integrity.json
    g2_case_inventory.json
    g3_case_metadata.csv
    g4_schema_quality.json
    g5_regime_bin_matrix.csv
    g6_leakage_gate.json
    manifest_summary.md   <- paste-ready summary for the Drive report

No third-party dependencies beyond the Python 3 standard library are
required (hashlib, csv, json, zipfile, statistics). This is intentional:
the spec explicitly excludes model training / calibration work from this
deliverable (section 8), so pandas/numpy are not needed here and are not
assumed to be installed on the local execution machine.
"""

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import zipfile
from collections import defaultdict
from datetime import datetime

EXPECTED_ARCHIVE_SIZE_BYTES = 5_503_439_673
EXPECTED_CASE_COUNT = 95
# Two conflicting prior counts this manifest must adjudicate (spec G2):
PAPER_COUNTS = {"anomaly": 44, "normal": 51}          # Data 9(12):138
V6_METADATA_COUNTS = {"anomaly": 45, "normal": 50}    # earlier-round record

# Frozen operating-regime bins per 【已簽核】參數凍結協定 v1.0 §3
REGIME_BINS = [
    ("bin1_lt_4", lambda v: v < 4),
    ("bin2_4_8", lambda v: 4 <= v < 8),
    ("bin3_8_12", lambda v: 8 <= v < 12),
    ("bin4_ge_12", lambda v: v >= 12),
]
MIN_SAMPLES_PER_CELL = 500

SENTINEL_VALUES = {-999, -9999, 9999, 99999, -99999}

TIMESTAMP_COL_HINTS = ["timestamp", "time", "date", "datetime", "ts"]
WIND_SPEED_COL_HINTS = ["wind_speed", "windspeed", "ws", "v_wind", "wind"]
LABEL_COL_HINTS = ["label", "anomaly", "fault", "status", "class"]
FARM_ID_HINTS = ["farm", "site", "wf"]
TURBINE_ID_HINTS = ["turbine", "wtg", "unit", "asset"]


def sha256_of_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def run_g1(archive_path, output_dir, workdir, skip_extract):
    print("[G1] hashing archive (this can take a while for a 5.5GB file)...", file=sys.stderr)
    size_bytes = os.path.getsize(archive_path)
    digest = sha256_of_file(archive_path)

    if not skip_extract:
        os.makedirs(workdir, exist_ok=True)
        print(f"[G1] extracting to {workdir} ...", file=sys.stderr)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(workdir)

    # Top-2-level tree
    tree = []
    depth_limit = 2
    root_depth = workdir.rstrip(os.sep).count(os.sep)
    file_count = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(workdir):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if depth < depth_limit:
            rel = os.path.relpath(dirpath, workdir)
            tree.append({"path": rel, "n_subdirs": len(dirnames), "n_files": len(filenames)})
        for fn in filenames:
            file_count += 1
            try:
                total_bytes += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass

    result = {
        "archive_path": archive_path,
        "sha256": digest,
        "size_bytes": size_bytes,
        "size_matches_expected": size_bytes == EXPECTED_ARCHIVE_SIZE_BYTES,
        "expected_size_bytes": EXPECTED_ARCHIVE_SIZE_BYTES,
        "top_level_tree": tree,
        "extracted_file_count": file_count,
        "extracted_total_bytes": total_bytes,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    }
    with open(os.path.join(output_dir, "g1_archive_integrity.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return result


def _find_col(fieldnames, hints):
    lower = {c.lower(): c for c in fieldnames}
    for h in hints:
        for lc, orig in lower.items():
            if h in lc:
                return orig
    return None


def discover_case_files(workdir, case_glob):
    import glob
    pattern = os.path.join(workdir, case_glob)
    return sorted(glob.glob(pattern, recursive=True))


def read_header(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        try:
            return next(reader)
        except StopIteration:
            return []


def run_g2_g6(workdir, output_dir, case_glob, ts_col_override, ws_col_override, label_col_override):
    case_files = discover_case_files(workdir, case_glob)
    print(f"[G2-G6] discovered {len(case_files)} candidate case files via glob '{case_glob}'", file=sys.stderr)

    case_rows = []
    schema_by_farm = defaultdict(lambda: {"columns": set(), "n_cases": 0})
    regime_matrix = defaultdict(lambda: {b: 0 for b, _ in REGIME_BINS})
    leakage_time_ranges = []
    detection_notes = []
    anomaly_count = 0
    normal_count = 0
    undetected = 0

    for path in case_files:
        header = read_header(path)
        if not header:
            undetected += 1
            detection_notes.append({"file": path, "status": "undetected", "reason": "empty/unreadable header"})
            continue

        ts_col = ts_col_override if ts_col_override != "auto" else _find_col(header, TIMESTAMP_COL_HINTS)
        ws_col = ws_col_override if ws_col_override != "auto" else _find_col(header, WIND_SPEED_COL_HINTS)
        label_col = label_col_override if label_col_override != "auto" else _find_col(header, LABEL_COL_HINTS)
        farm_col = _find_col(header, FARM_ID_HINTS)
        turbine_col = _find_col(header, TURBINE_ID_HINTS)

        case_id = os.path.splitext(os.path.basename(path))[0]
        # Infer farm from path components (A/B/C style directories) as a fallback.
        farm_guess = None
        for part in os.path.normpath(path).split(os.sep):
            if part.upper() in ("A", "B", "C"):
                farm_guess = part.upper()
                break

        if ts_col is None or (ws_col is None and label_col is None):
            undetected += 1
            detection_notes.append({
                "file": path, "status": "undetected",
                "reason": "could not confidently identify timestamp/label/wind-speed columns",
                "header_seen": header,
            })
            continue

        timestamps = []
        wind_speeds = []
        label_value = None
        n_rows = 0
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                n_rows += 1
                if ts_col and row.get(ts_col):
                    timestamps.append(row[ts_col])
                if ws_col and row.get(ws_col) not in (None, ""):
                    try:
                        wind_speeds.append(float(row[ws_col]))
                    except ValueError:
                        pass
                if label_col and label_value is None and row.get(label_col) not in (None, ""):
                    label_value = row[label_col]

        label_norm = "anomaly" if label_value and str(label_value).strip().lower() in (
            "1", "true", "anomaly", "fault", "abnormal") else (
            "normal" if label_value is not None else "unknown")
        if label_norm == "anomaly":
            anomaly_count += 1
        elif label_norm == "normal":
            normal_count += 1

        start_ts = timestamps[0] if timestamps else None
        end_ts = timestamps[-1] if timestamps else None
        if start_ts and end_ts:
            leakage_time_ranges.append((case_id, farm_guess, start_ts, end_ts))

        # Sampling-interval regularity: only checked if timestamps parse as ISO-ish; left as
        # a flag for the local operator since real timestamp format is unknown from here.
        irregular_interval_flag = "unchecked_format_unknown"

        for bin_name, pred in REGIME_BINS:
            count = sum(1 for v in wind_speeds if pred(v))
            regime_matrix[case_id][bin_name] = count

        sentinel_hits = 0  # populated in schema pass below, per-file spot check
        case_rows.append({
            "case_id": case_id,
            "farm_id": farm_guess or (row.get(farm_col) if farm_col else "unknown"),
            "turbine_id": (row.get(turbine_col) if turbine_col else "unknown"),
            "label": label_norm,
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "n_records": n_rows,
            "sampling_interval_check": irregular_interval_flag,
            "source_file": path,
        })

        schema_by_farm[farm_guess or "unknown"]["columns"] |= set(header)
        schema_by_farm[farm_guess or "unknown"]["n_cases"] += 1

        detection_notes.append({
            "file": path, "status": "detected",
            "timestamp_col": ts_col, "wind_speed_col": ws_col, "label_col": label_col,
        })

    # G2: case inventory + version-drift adjudication
    g2 = {
        "n_case_files_found": len(case_files),
        "n_detected": len(case_rows),
        "n_undetected": undetected,
        "anomaly_count": anomaly_count,
        "normal_count": normal_count,
        "matches_paper_counts_44_51": (anomaly_count, normal_count) == (PAPER_COUNTS["anomaly"], PAPER_COUNTS["normal"]),
        "matches_v6_metadata_counts_45_50": (anomaly_count, normal_count) == (V6_METADATA_COUNTS["anomaly"], V6_METADATA_COUNTS["normal"]),
        "matches_expected_total_95": (anomaly_count + normal_count) == EXPECTED_CASE_COUNT,
        "note": "If neither prior count matches, list case_ids with label='unknown' below for manual adjudication per spec G2.",
        "unknown_label_case_ids": [r["case_id"] for r in case_rows if r["label"] == "unknown"],
    }
    with open(os.path.join(output_dir, "g2_case_inventory.json"), "w", encoding="utf-8") as f:
        json.dump(g2, f, indent=2, ensure_ascii=False)

    # G3: case-level metadata CSV
    g3_path = os.path.join(output_dir, "g3_case_metadata.csv")
    with open(g3_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "case_id", "farm_id", "turbine_id", "label", "start_timestamp",
            "end_timestamp", "n_records", "sampling_interval_check", "source_file"])
        writer.writeheader()
        for r in case_rows:
            writer.writerow(r)

    # G4: schema & data quality (column presence only from headers already read;
    # missing-rate / sentinel-value scan requires a second full pass, done here
    # at low cost since files were already streamed once above would be ideal,
    # but kept separate for clarity and because header-only info is cheap).
    g4 = {}
    for farm, info in schema_by_farm.items():
        g4[farm] = {
            "n_columns": len(info["columns"]),
            "n_cases": info["n_cases"],
            "columns": sorted(info["columns"]),
        }
    g4["note"] = ("Missing-rate and sentinel-value (-999/9999 style) scanning requires a "
                  "column-by-column pass; run care_v6_schema_quality.py-style deep scan "
                  "separately if G4 needs full quantitative missing-rate numbers — this "
                  "manifest pass only confirms column inventory per farm for a first D0 look.")
    with open(os.path.join(output_dir, "g4_schema_quality.json"), "w", encoding="utf-8") as f:
        json.dump(g4, f, indent=2, ensure_ascii=False)

    # G5: regime bin matrix (case x bin) + exclusion stats vs frozen 500-sample rule
    g5_path = os.path.join(output_dir, "g5_regime_bin_matrix.csv")
    excluded_cells = 0
    total_cells = 0
    with open(g5_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id"] + [b for b, _ in REGIME_BINS] + ["n_excluded_cells_lt_500"])
        for case_id, counts in regime_matrix.items():
            n_excl = 0
            for b, _ in REGIME_BINS:
                total_cells += 1
                if counts[b] < MIN_SAMPLES_PER_CELL:
                    n_excl += 1
                    excluded_cells += 1
            writer.writerow([case_id] + [counts[b] for b, _ in REGIME_BINS] + [n_excl])
    g5_summary = {
        "total_cells": total_cells,
        "excluded_cells_lt_500_samples": excluded_cells,
        "excluded_fraction": (excluded_cells / total_cells) if total_cells else None,
        "flag_if_over_30pct": (excluded_cells / total_cells > 0.30) if total_cells else None,
    }

    # G6: leakage gate — ASSET-LEVEL cross-case time overlap.
    #
    # v1 of this check grouped by farm only and compared just ADJACENT pairs
    # after sorting by start time. On the real archive that saturated at
    # (n_cases - 1) overlaps per farm — every adjacent pair overlapped — which
    # is uninformative: cases within a farm are different turbines monitored
    # over the same calendar period, so calendar overlap is expected and is
    # not leakage. The question that actually matters for D1/D6 is whether the
    # SAME physical asset appears in more than one case over overlapping time,
    # because then a "held-out" case is not held out at the asset-period level.
    #
    # v2 groups by (farm_id, turbine_id), compares all pairs, and measures the
    # real overlap duration. Cross-label pairs (anomaly x normal on the same
    # asset over the same period) are reported separately as the highest-risk
    # class of contamination.
    def _parse_ts(value):
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    by_asset = defaultdict(list)
    for r in case_rows:
        by_asset[(r["farm_id"], r["turbine_id"])].append(r)

    asset_overlaps = []
    n_unparseable_span = 0
    for (farm, turbine), rows_for_asset in by_asset.items():
        for i in range(len(rows_for_asset)):
            for j in range(i + 1, len(rows_for_asset)):
                a, b = rows_for_asset[i], rows_for_asset[j]
                s1, e1 = _parse_ts(a["start_timestamp"]), _parse_ts(a["end_timestamp"])
                s2, e2 = _parse_ts(b["start_timestamp"]), _parse_ts(b["end_timestamp"])
                if None in (s1, e1, s2, e2):
                    n_unparseable_span += 1
                    continue
                delta = min(e1, e2) - max(s1, s2)
                if delta.total_seconds() > 0:
                    asset_overlaps.append({
                        "farm": farm,
                        "turbine_id": turbine,
                        "case_a": a["case_id"],
                        "label_a": a["label"],
                        "case_b": b["case_id"],
                        "label_b": b["label"],
                        "overlap_days": round(delta.total_seconds() / 86400.0, 2),
                        "cross_label": a["label"] != b["label"],
                    })

    multi_case_assets = {k: [r["case_id"] for r in v] for k, v in by_asset.items() if len(v) > 1}
    cross_label_overlaps = [o for o in asset_overlaps if o["cross_label"]]

    # The official split lives in a per-row column (train_test), not in a root
    # manifest file — v1 looked only for a root file and wrongly reported "not
    # determinable".
    split_columns_by_farm = {}
    for farm, schema in schema_by_farm.items():
        found = [c for c in schema.get("columns", []) if c.strip().lower() in
                 ("train_test", "train/test", "traintest", "split", "subset")]
        if found:
            split_columns_by_farm[farm] = found
    all_farms_have_split = (
        bool(split_columns_by_farm)
        and len(split_columns_by_farm) == len(schema_by_farm)
    )

    g6 = {
        "official_train_test_split_found": (
            "column:" + ",".join(sorted({c for v in split_columns_by_farm.values() for c in v}))
            if all_farms_have_split else None
        ),
        "split_columns_by_farm": split_columns_by_farm,
        "note_official_split": (
            "Split column detected per farm. This records only that the column EXISTS; "
            "its value distribution per case has not been read. Tabulate train/test row "
            "counts per case before treating the split as D0 evidence."
            if all_farms_have_split else
            "No train_test-style column found in any farm schema; check archive root files "
            "for a manifest/split file and record manually."
        ),
        "asset_level_overlap_method": (
            "grouped by (farm_id, turbine_id); all pairs compared; overlap measured as "
            "min(end) - max(start) on case span timestamps"
        ),
        "n_distinct_assets": len(by_asset),
        "n_assets_in_multiple_cases": len(multi_case_assets),
        "assets_in_multiple_cases": {"%s|%s" % k: v for k, v in sorted(multi_case_assets.items())},
        "n_asset_level_overlapping_pairs": len(asset_overlaps),
        "n_cross_label_overlapping_pairs": len(cross_label_overlaps),
        "max_overlap_days": max((o["overlap_days"] for o in asset_overlaps), default=None),
        "median_overlap_days": (
            sorted(o["overlap_days"] for o in asset_overlaps)[len(asset_overlaps) // 2]
            if asset_overlaps else None
        ),
        "asset_level_overlaps": sorted(asset_overlaps, key=lambda o: -o["overlap_days"]),
        "n_pairs_skipped_unparseable_span": n_unparseable_span,
        "leakage_interpretation": (
            "Case-span overlap on the same asset does NOT by itself prove contamination: "
            "the spans come from G3 and ignore both the train_test column and the actual "
            "event windows. It DOES mean asset-period isolation cannot be assumed, so any "
            "calibration/evaluation split must be constructed at the asset level, not the "
            "case level. Verify against event_info and the train_test column before "
            "recording a D1/D6 verdict."
        ),
        "normal_cases_with_fault_pointing_columns": [
            r["case_id"] for r in case_rows
            if r["label"] == "normal" and any(h in c.lower() for c in schema_by_farm.get(r["farm_id"], {}).get("columns", []) for h in ("fault", "anomaly", "event"))
        ],
        "event_label_storage_note": "Populate manually from source_file inspection; not auto-derivable without knowing v6's event-window schema.",
    }
    with open(os.path.join(output_dir, "g6_leakage_gate.json"), "w", encoding="utf-8") as f:
        json.dump(g6, f, indent=2, ensure_ascii=False)

    return g2, g4, g5_summary, g6, detection_notes


def write_summary(output_dir, g1, g2, g5_summary, g6):
    lines = []
    lines.append("# CARE v6 G1-G6 Manifest — auto-generated summary")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append("## G1 — Archive Integrity")
    lines.append(f"- SHA-256: `{g1['sha256']}`")
    lines.append(f"- Size: {g1['size_bytes']} bytes (expected {g1['expected_size_bytes']}, match={g1['size_matches_expected']})")
    lines.append(f"- Extracted files: {g1['extracted_file_count']}, total bytes: {g1['extracted_total_bytes']}")
    lines.append("")
    lines.append("## G2 — Case Inventory / Version Drift")
    lines.append(f"- Detected: {g2['n_detected']} / undetected: {g2['n_undetected']} (glob found {g2['n_case_files_found']})")
    lines.append(f"- anomaly={g2['anomaly_count']}, normal={g2['normal_count']}")
    lines.append(f"- Matches paper (44/51): {g2['matches_paper_counts_44_51']}")
    lines.append(f"- Matches v6 metadata (45/50): {g2['matches_v6_metadata_counts_45_50']}")
    lines.append(f"- Matches expected total 95: {g2['matches_expected_total_95']}")
    if g2["unknown_label_case_ids"]:
        lines.append(f"- ⚠️ Unresolved-label cases needing manual review: {g2['unknown_label_case_ids']}")
    lines.append("")
    lines.append("## G5 — Regime Bin Feasibility")
    lines.append(f"- Excluded cells (<500 samples): {g5_summary['excluded_cells_lt_500_samples']} / {g5_summary['total_cells']} "
                  f"({g5_summary['excluded_fraction']:.1%} )" if g5_summary["total_cells"] else "- No cells computed")
    if g5_summary.get("flag_if_over_30pct"):
        lines.append("- ⚠️ Exclusion fraction exceeds 30% — per spec, this must be reported to PI before proceeding (may require a [勘誤] doc, but NOT a post-hoc bin change after seeing results).")
    lines.append("")
    lines.append("## G6 — Leakage Gate")
    lines.append(f"- Distinct assets: {g6['n_distinct_assets']}; "
                 f"assets appearing in >1 case: {g6['n_assets_in_multiple_cases']}")
    lines.append(f"- Asset-level overlapping case pairs: {g6['n_asset_level_overlapping_pairs']} "
                 f"(cross-label anomaly x normal: {g6['n_cross_label_overlapping_pairs']})")
    if g6["n_asset_level_overlapping_pairs"]:
        lines.append(f"- Overlap duration: median {g6['median_overlap_days']} d, max {g6['max_overlap_days']} d")
        lines.append("- ⚠️ Asset-period isolation cannot be assumed. Calibration/evaluation splits "
                     "must be built at the asset level, not the case level.")
    if g6["normal_cases_with_fault_pointing_columns"]:
        lines.append(f"- ⚠️ Normal cases with fault-pointing columns present: {g6['normal_cases_with_fault_pointing_columns']}")
    if g6["official_train_test_split_found"]:
        lines.append(f"- Official train/test split: found as {g6['official_train_test_split_found']} "
                     "(existence only; value distribution not yet tabulated)")
    else:
        lines.append("- Official train/test split: NOT auto-determined — verify manually against archive root files.")
    lines.append("")
    lines.append("## Caveat (read before trusting G2-G6)")
    lines.append("G2-G6 rely on best-effort auto-detection of timestamp/wind-speed/label columns "
                  "(see detection_notes in each JSON file / g3 CSV `source_file` column). "
                  "Spot-check a handful of `status=detected` cases against the raw files before "
                  "using these numbers as D0 gate evidence, and inspect any `status=undetected` "
                  "entries — they are excluded from all counts above, not silently assumed normal.")
    with open(os.path.join(output_dir, "manifest_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True, help="Path to local CARE_To_Compare_v6.zip")
    ap.add_argument("--workdir", required=True, help="Extraction / scratch directory")
    ap.add_argument("--output-dir", required=True, help="Where to write manifest files")
    ap.add_argument("--case-glob", default="**/*.csv", help="Glob (relative to workdir) for per-case data files")
    ap.add_argument("--timestamp-col", default="auto")
    ap.add_argument("--wind-speed-col", default="auto")
    ap.add_argument("--label-col", default="auto")
    ap.add_argument("--skip-extract", action="store_true", help="Set if --workdir already contains the extracted archive")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    g1 = run_g1(args.archive, args.output_dir, args.workdir, args.skip_extract)
    g2, g4, g5_summary, g6, notes = run_g2_g6(
        args.workdir, args.output_dir, args.case_glob,
        args.timestamp_col, args.wind_speed_col, args.label_col,
    )
    with open(os.path.join(args.output_dir, "detection_notes.json"), "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
    write_summary(args.output_dir, g1, g2, g5_summary, g6)

    print(f"Done. See {args.output_dir}/manifest_summary.md for a paste-ready report.", file=sys.stderr)


if __name__ == "__main__":
    main()
