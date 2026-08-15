#!/usr/bin/env python3
"""
Frozen Base Scorer Compatibility Check — C0-C6 gate, fail-closed edition.

Gate version: c0c6-gate-v2.0 (supersedes the v1 checker audited in Drive
progress doc v2.8 by Codex B).

WHAT CHANGED IN v2.0 AND WHY
----------------------------
The v1 checker (commit 484c60a) was audited at source level and six
defects were recorded in "進度更新 2026-08-13 v2.8" (Codex B). v2.0 closes
them; each fix is tagged with the P0/P1 id from that document.

  P0-1  Status is now a machine-readable enum per gate:
        PASS / FAIL / UNVERIFIED / NOT_APPLICABLE. There is no boolean
        "gate_all_pass" field that can be produced without evidence, and
        no field named so that a partial conjunction can be misread as a
        full gate result. gate_status is PASS only when C0..C6 are all
        PASS. The process exits non-zero unless gate_status == PASS, so
        this can be wired into CI as a fail-closed gate.
  P0-2  C4 compares case IDENTITY, not counts. Expected case_ids are read
        from g3_case_metadata.csv (the G2 JSON carries only counts), and
        missing / unexpected / duplicate case_ids are reported explicitly.
  P0-3  C3 can never PASS from the score CSV header alone. Label
        isolation must be evidenced by a fit-time provenance manifest
        (--fit-provenance) declaring the fit partition, the files the
        fitting run opened, and their hashes. Absent that: UNVERIFIED.
  P0-4  C5 requires two independent scorer runs (--score-dir-run2) plus a
        freeze receipt (--freeze-receipt: environment, seed, config,
        artifact hash). Comparison mode is an explicit either/or:
        --determinism-mode bit_identical | tolerance (with --tolerance).
        A single run can never yield C5 PASS.
  P0-5  C1 is timestamp-aware. Gap duration is measured in wall-clock
        time from the timestamp column (not by counting rows), classified
        per the R15 frozen policy (<=1h interpolate, <=3h forward-fill,
        >3h non-evaluable), and an explicit per-case evaluability mask
        CSV is written. C6 then checks finiteness ONLY on evaluable
        timestamps, resolving the v1 contradiction where C6 demanded all
        scores finite while C1 declared >3h segments legitimately absent.
  P0-6 / P1
        Input and output SHA-256 receipts, gate version stamp, non-zero
        exit codes, and a CLI whose flags all actually exist and are all
        actually used (--score-glob, --case-id-from, --workdir were
        documented but unimplemented in v1). C0 no longer guesses column
        names by substring: an explicit --signal-map with units is
        required to PASS; without it the checker emits a *suggested*
        mapping for operator review and reports C0 as UNVERIFIED.

SCOPE — WHAT THIS SCRIPT DOES NOT DO
------------------------------------
It AUDITS per-case score streams that were produced elsewhere. It does
not implement either frozen scorer, and it does not re-validate the
published papers.

  Base Scorer 1: Mahalanobis Distance detector
      (Liu et al., Applied Sciences 2022, 12:8661, DOI 10.3390/app12178661)
  Base Scorer 2: Main-bearing SCADA predictive framework
      (Liu et al., Advances in Mechanical Engineering 2026, 18(7))

Running it requires the extracted CARE v6 archive and locally produced
score streams, so it completes only on the local operator's machine.

STATUS OF THE GATE DEFINITIONS THEMSELVES
-----------------------------------------
C0-C6 names and thresholds remain a PROPOSAL synthesised from R15 and the
PI directive v1.0. Merged tooling is not a ratified gate. Do not write
"C0-C6 passed" into a manuscript before the PI or a collaborator ratifies
the definitions AND this script reports gate_status=PASS on real inputs.

GATE DEFINITIONS
----------------
C0  Signal availability & mapping   — all 6 core signals (Active Power,
    Wind Speed, Rotor Speed, Main Bearing Temperature, Pitch Angle,
    Ambient Temperature) mapped to real columns with declared units, via
    an operator-supplied map. No silent substring guessing. A signal the
    archive genuinely lacks may be declared not_available with a reason
    and a ratifier; the omission is then recorded, never inferred.
C1  Missing-feature policy applied  — R15 policy applied over wall-clock
    gaps; per-case evaluability mask emitted; non-evaluable fraction
    reported and flagged above 5% (PI decision 2026-08-15, from the G4
    measured distribution: p95 0.0237, max 0.0364).
C2  Artifact reproducibility        — implementation source, version and
    parameter provenance recorded and hashed (--artifact-manifest).
C3  Label independence              — fit step provably touched only the
    CARE normal reference partition (--fit-provenance).
C4  Case coverage                   — score stream case_id set equals the
    expected case_id set from g3_case_metadata.csv, exactly.
C5  Determinism & freeze            — two independent runs agree under the
    declared comparison mode, with a freeze receipt.
C6  Score sanity / non-degeneracy   — scores finite on every evaluable
    timestamp, and not constant.

USAGE
-----
    python3 base_scorer_compatibility_check.py \\
        --workdir /path/to/extracted_care_v6 \\
        --g2-inventory  /path/to/manifest_out/g2_case_inventory.json \\
        --g3-case-metadata /path/to/manifest_out/g3_case_metadata.csv \\
        --score-dir /path/to/per_case_score_csvs_run1 \\
        --scorer-name "MD_2022" \\
        --output-dir ./compat_out_md2022 \\
        --timestamp-col timestamp \\
        --score-col anomaly_score \\
        --signal-map ./signal_map_md2022.json \\
        --artifact-manifest ./artifact_md2022.json \\
        --fit-provenance ./fit_provenance_md2022.json \\
        --score-dir-run2 /path/to/per_case_score_csvs_run2 \\
        --freeze-receipt ./freeze_receipt_md2022.json \\
        --determinism-mode bit_identical

Every scorer is audited separately; the manuscript's compatibility claim
needs gate_status=PASS for BOTH scorers.

Exit codes:  0 PASS · 1 FAIL · 2 UNVERIFIED · 3 usage/IO error.

Companion side-car templates for the four evidence files can be generated
with --emit-templates <dir>.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import fnmatch
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

GATE_VERSION = "c0c6-gate-v2.0"

PASS = "PASS"
FAIL = "FAIL"
UNVERIFIED = "UNVERIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_UNVERIFIED = 2
EXIT_ERROR = 3

CORE_SIGNALS = [
    "active_power",
    "wind_speed",
    "rotor_speed",
    "main_bearing_temperature",
    "pitch_angle",
    "ambient_temperature",
]

# Used ONLY to emit a suggestion for the operator to review; never to
# silently satisfy C0 (P1 fix).
SIGNAL_HINTS = {
    "active_power": ["active_power", "power", "p_act", "kw", "mw"],
    "wind_speed": ["wind_speed", "windspeed", "ws", "v_wind"],
    "rotor_speed": ["rotor_speed", "rotorspeed", "rpm"],
    "main_bearing_temperature": ["bearing_temp", "main_bearing", "brg_temp"],
    "pitch_angle": ["pitch"],
    "ambient_temperature": ["ambient_temp", "outdoor_temp", "temp_amb", "amb_temp"],
}

SCORE_HINTS = ["score", "anomaly_score", "s_t", "mahalanobis", "residual"]
LABEL_HINTS = ["label", "anomaly", "fault", "event", "class", "status"]

# C1 policy (R15 section 1), expressed in wall-clock time (P0-5 fix).
SHORT_GAP_HOURS = 1.0     # <= 1h  -> linear interpolation
LONG_GAP_HOURS = 3.0      # <= 3h  -> forward fill ; > 3h -> non-evaluable
# Tightened from 0.30 to 0.05 by PI decision, 2026-08-15, on evidence rather
# than convention. The original 0.30 was borrowed from the G5 regime-bin
# exclusion rule before anyone had seen CARE v6's real gap distribution. The
# G4 deep scan then measured it across 15 cases: median non-evaluable fraction
# 0.0037, p95 0.0237, MAXIMUM 0.0364. At 0.30 the threshold sat roughly an
# order of magnitude above the worst case in the archive, so it could never
# fire -- it excluded nothing and protected against nothing. 0.05 still leaves
# more than twice the observed p95 as headroom, while being low enough that a
# genuinely degraded case cannot pass unnoticed.
NON_EVALUABLE_FLAG_FRACTION = 0.05
NOMINAL_INTERVAL_MINUTES_DEFAULT = 10.0

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
]


# --------------------------------------------------------------------------
# receipts / small helpers
# --------------------------------------------------------------------------

def sha256_of_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json_or_none(path, label, errors):
    """Return (obj, receipt). Missing path is legitimate (-> UNVERIFIED later);
    an unreadable/invalid file is an error, never a silent skip."""
    if not path:
        return None, None
    if not os.path.isfile(path):
        errors.append("%s not found: %s" % (label, path))
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError) as exc:
        errors.append("%s unreadable (%s): %s" % (label, exc, path))
        return None, None
    return obj, {"path": os.path.abspath(path), "sha256": sha256_of_file(path)}


def parse_timestamp(raw):
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def is_missing(value):
    if value is None:
        return True
    v = value.strip() if isinstance(value, str) else value
    if v == "":
        return True
    if isinstance(v, str) and v.lower() in ("nan", "na", "n/a", "null", "none"):
        return True
    return False


def to_float(value):
    if is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def suggest_column(fieldnames, hints):
    lower = {c.lower(): c for c in fieldnames}
    for h in hints:
        for lc, orig in lower.items():
            if h in lc:
                return orig
    return None


def suggest_signal_map(header):
    return {s: suggest_column(header, hints) for s, hints in SIGNAL_HINTS.items()}


def is_absent(value):
    """Field-presence test for evidence manifests. Deliberately NOT a falsiness
    test: seed=0 and tolerance=0.0 are legitimate declared values."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def worst_status(statuses):
    """FAIL dominates UNVERIFIED dominates PASS. NOT_APPLICABLE is neutral."""
    if any(s == FAIL for s in statuses):
        return FAIL
    if any(s == UNVERIFIED for s in statuses):
        return UNVERIFIED
    if all(s == NOT_APPLICABLE for s in statuses) and statuses:
        return NOT_APPLICABLE
    return PASS


# --------------------------------------------------------------------------
# C0 — signal availability & mapping (explicit map required)
# --------------------------------------------------------------------------

def check_c0(header, signal_map):
    """signal_map schema:
        {"<signal>": {"column": "<header name>", "unit": "kW"}}
      or {"<signal>": {"derived_from": ["colA","colB"], "unit": "kW",
                        "derivation": "free text"}}
    """
    suggestion = suggest_signal_map(header)
    if signal_map is None:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --signal-map supplied. v2.0 does not accept substring-guessed "
                "column names as C0 evidence. Review the suggested mapping below, "
                "confirm units against the CARE v6 data dictionary, and pass it "
                "back with --signal-map."
            ),
            "suggested_mapping_for_operator_review": suggestion,
            "mapping": {},
            "value_columns": [],
        }

    mapping = {}
    value_columns = []
    problems = []
    declared_unavailable = {}
    for signal in CORE_SIGNALS:
        entry = signal_map.get(signal)
        if not isinstance(entry, dict):
            problems.append("signal '%s' missing from signal map" % signal)
            continue

        # A signal the archive genuinely does not carry can be declared absent
        # rather than faked -- Farm A has no main bearing temperature channel,
        # only gearbox and generator bearings. The declaration must name a
        # reason and a ratifier, so an omission is always a recorded decision
        # and never a silent gap. Absence is NOT inferred from a missing key:
        # that path still fails.
        if entry.get("not_available"):
            missing_fields = [k for k in ("reason", "ratified_by", "ratified_on")
                              if is_absent(entry.get(k))]
            if missing_fields:
                problems.append(
                    "signal '%s' is declared not_available but the declaration is "
                    "incomplete: %s" % (signal, missing_fields))
                continue
            declared_unavailable[signal] = {
                "reason": entry["reason"],
                "ratified_by": entry["ratified_by"],
                "ratified_on": entry["ratified_on"],
            }
            continue
        unit = entry.get("unit")
        if is_absent(unit):
            problems.append("signal '%s' has no declared unit" % signal)
        if "column" in entry:
            col = entry["column"]
            if col not in header:
                problems.append(
                    "signal '%s' mapped to column '%s' which is not in the score CSV header"
                    % (signal, col))
                continue
            mapping[signal] = {"column": col, "unit": unit, "derived": False}
            value_columns.append(col)
        elif "derived_from" in entry:
            srcs = entry.get("derived_from") or []
            absent = [c for c in srcs if c not in header]
            if not srcs:
                problems.append("signal '%s' declares derived_from but lists no source columns" % signal)
                continue
            if absent:
                problems.append(
                    "signal '%s' derived_from columns absent from header: %s" % (signal, absent))
                continue
            if is_absent(entry.get("derivation")):
                problems.append("signal '%s' is derived but declares no 'derivation' description" % signal)
            mapping[signal] = {
                "derived_from": srcs,
                "unit": unit,
                "derived": True,
                "derivation": entry.get("derivation"),
            }
            value_columns.extend(srcs)
        else:
            problems.append("signal '%s' entry has neither 'column' nor 'derived_from'" % signal)

    result = {
        "status": PASS if not problems else FAIL,
        "problems": problems,
        "mapping": mapping,
        "value_columns": sorted(set(value_columns)),
        "suggested_mapping_for_operator_review": suggestion,
    }
    if declared_unavailable:
        result["declared_unavailable_signals"] = declared_unavailable
        result["declared_unavailable_note"] = (
            "%d of the %d core signals are declared absent from this archive with a "
            "ratified reason. C0 can pass without them, but any manuscript claim "
            "resting on this scorer must state the reduced signal set explicitly."
            % (len(declared_unavailable), len(CORE_SIGNALS)))
    return result


# --------------------------------------------------------------------------
# C1 — timestamp-aware missing-feature policy + evaluability mask
# --------------------------------------------------------------------------

def _missing_runs(flags):
    runs = []
    start = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def check_c1(rows, timestamp_col, value_columns, nominal_interval_minutes,
             score_values=None):
    """Wall-clock gap classification per R15, returning a per-row evaluability
    mask. Returns (result_dict, mask_rows).

    score_values, when supplied, adds a third source of non-evaluability
    alongside long gaps and unparseable timestamps: a row the scorer declined
    to score. A reading outside physical possibility is a fault code, not a
    measurement -- the range filter rejects it, the feature vector is then
    incomplete, and the scorer writes no score. Such a row is in the same
    category as a data gap: there is nothing there to evaluate.

    Ratified 2026-08-15 after C6 failed on 34 cases (1,974 rows) for exactly
    this reason. Before that, evaluability was built from timestamps alone, so
    the mask called these rows evaluable and C6 then demanded a finite score
    for a row the scorer had deliberately left blank.

    This is deliberately NOT a free pass. The rows land in the same
    non_evaluable_fraction that C1 caps at NON_EVALUABLE_FLAG_FRACTION, so a
    scorer that quietly declined most of its input still FAILs here -- it just
    fails at C1, where the coverage question belongs, instead of at C6, where
    the question is whether the scores that do exist are sane."""
    n = len(rows)
    if not timestamp_col:
        return {
            "status": UNVERIFIED,
            "reason": "No --timestamp-col supplied; gap duration cannot be measured in wall-clock time.",
        }, []
    if n == 0:
        return {"status": FAIL, "reason": "score CSV has no data rows"}, []
    if timestamp_col not in (rows[0].keys() if rows else []):
        return {
            "status": FAIL,
            "reason": "timestamp column '%s' not present in score CSV" % timestamp_col,
        }, []

    nominal = timedelta(minutes=nominal_interval_minutes)
    short_gap = timedelta(hours=SHORT_GAP_HOURS)
    long_gap = timedelta(hours=LONG_GAP_HOURS)

    timestamps = [parse_timestamp(r.get(timestamp_col)) for r in rows]
    n_unparseable = sum(1 for t in timestamps if t is None)

    ordered = [t for t in timestamps if t is not None]
    non_monotonic = any(ordered[i] < ordered[i - 1] for i in range(1, len(ordered)))
    duplicate_timestamps = len(ordered) != len(set(ordered))

    # Clock discontinuities: wall-clock stretches with no rows at all.
    clock_gaps = []
    for i in range(1, n):
        a, b = timestamps[i - 1], timestamps[i]
        if a is None or b is None:
            continue
        delta = b - a
        if delta > long_gap:
            clock_gaps.append({
                "after_row_index": i - 1,
                "from": a.isoformat(),
                "to": b.isoformat(),
                "gap_hours": round(delta.total_seconds() / 3600.0, 3),
            })

    # Per-column missing-run classification by wall-clock duration.
    non_evaluable_rows = set()
    per_column = {}
    for col in value_columns:
        flags = [is_missing(r.get(col)) for r in rows]
        runs = _missing_runs(flags)
        buckets = {"interpolate": 0, "forward_fill": 0, "non_evaluable": 0}
        run_details = []
        for start, end in runs:
            before = timestamps[start - 1] if start - 1 >= 0 else None
            after = timestamps[end + 1] if end + 1 < n else None
            if before is not None and after is not None:
                duration = after - before
            elif before is not None and timestamps[end] is not None:
                duration = (timestamps[end] - before) + nominal
            elif after is not None and timestamps[start] is not None:
                duration = (after - timestamps[start]) + nominal
            else:
                duration = None  # whole column missing / no usable timestamps

            if duration is None or duration > long_gap:
                policy = "non_evaluable"
                for i in range(start, end + 1):
                    non_evaluable_rows.add(i)
            elif duration <= short_gap:
                policy = "interpolate"
            else:
                policy = "forward_fill"
            buckets[policy] += (end - start + 1)
            run_details.append({
                "start_row_index": start,
                "end_row_index": end,
                "n_steps": end - start + 1,
                "gap_hours": (round(duration.total_seconds() / 3600.0, 3)
                              if duration is not None else None),
                "policy": policy,
            })

        n_missing = sum(flags)
        per_column[col] = {
            "n_total": n,
            "n_missing": n_missing,
            "missing_fraction": n_missing / n,
            "steps_by_policy": buckets,
            "missing_runs": run_details,
        }

    # Rows whose timestamp could not be parsed are not evaluable either.
    for i, t in enumerate(timestamps):
        if t is None:
            non_evaluable_rows.add(i)

    # Rows the scorer declined to score (see the docstring). Tracked
    # separately so the summary can say how much of the mask came from this
    # source rather than from gaps -- two very different data problems.
    score_absent_rows = set()
    if score_values is not None and len(score_values) == n:
        for i, v in enumerate(score_values):
            if v is None or (isinstance(v, float)
                             and (math.isnan(v) or math.isinf(v))):
                score_absent_rows.add(i)
                non_evaluable_rows.add(i)

    n_non_evaluable = len(non_evaluable_rows)
    non_evaluable_fraction = n_non_evaluable / n
    over_flag = non_evaluable_fraction > NON_EVALUABLE_FLAG_FRACTION

    mask_rows = []
    for i, r in enumerate(rows):
        evaluable = i not in non_evaluable_rows
        if evaluable:
            reason = ""
        elif timestamps[i] is None:
            reason = "unparseable_timestamp"
        elif i in score_absent_rows:
            # Reported before the gap reason: when a row is both, the scorer
            # having declined is the more specific fact.
            reason = "scorer_declined_no_score"
        else:
            reason = "gap_over_%gh" % LONG_GAP_HOURS
        mask_rows.append({
            "row_index": i,
            "timestamp": r.get(timestamp_col, ""),
            "evaluable": "1" if evaluable else "0",
            "non_evaluable_reason": reason,
        })

    hard_problems = []
    if non_monotonic:
        hard_problems.append("timestamps are not monotonically increasing")
    if duplicate_timestamps:
        hard_problems.append("duplicate timestamps present")
    if n_unparseable == n:
        hard_problems.append("no timestamp in the file could be parsed")

    if hard_problems:
        status = FAIL
    elif over_flag:
        status = FAIL
    else:
        status = PASS

    return {
        "status": status,
        "problems": hard_problems,
        "n_non_evaluable_from_scorer_declined": len(score_absent_rows),
        "n_non_evaluable_from_gaps_or_timestamps": (
            len(non_evaluable_rows) - len(score_absent_rows)),
        "scorer_declined_note": (
            "rows the scorer left unscored (range-rejected fault codes or an "
            "incomplete feature vector) count as non-evaluable and are "
            "included in the fraction capped above, ratified 2026-08-15"),
        "policy": {
            "interpolate_max_hours": SHORT_GAP_HOURS,
            "forward_fill_max_hours": LONG_GAP_HOURS,
            "non_evaluable_above_hours": LONG_GAP_HOURS,
            "non_evaluable_flag_fraction": NON_EVALUABLE_FLAG_FRACTION,
            "nominal_interval_minutes": nominal_interval_minutes,
        },
        "n_rows": n,
        "n_unparseable_timestamps": n_unparseable,
        "clock_gaps_over_policy": clock_gaps,
        "n_non_evaluable_rows": n_non_evaluable,
        "non_evaluable_fraction": non_evaluable_fraction,
        "flag_over_threshold": over_flag,
        "per_column": per_column,
    }, mask_rows


# --------------------------------------------------------------------------
# C2 — artifact reproducibility (manifest required)
# --------------------------------------------------------------------------

C2_REQUIRED_FIELDS = [
    "implementation_source",   # repo URL / supplementary material / re-implementation
    "version_or_commit",
    "parameter_provenance",
    "artifact_sha256",
]


def check_c2(artifact_manifest, receipt):
    if artifact_manifest is None:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --artifact-manifest supplied. C2 requires a recorded and hashed "
                "implementation source, version and parameter provenance; it cannot be "
                "inferred from score CSVs."
            ),
            "required_fields": C2_REQUIRED_FIELDS,
        }
    missing = [k for k in C2_REQUIRED_FIELDS if is_absent(artifact_manifest.get(k))]
    return {
        "status": PASS if not missing else FAIL,
        "missing_fields": missing,
        "manifest_receipt": receipt,
        "implementation_source": artifact_manifest.get("implementation_source"),
        "version_or_commit": artifact_manifest.get("version_or_commit"),
        "artifact_sha256": artifact_manifest.get("artifact_sha256"),
    }


# --------------------------------------------------------------------------
# C3 — label independence (fit-time provenance required; header is not evidence)
# --------------------------------------------------------------------------

def check_c3(fit_provenance, receipt, headers_by_case):
    """Structural header scan is retained ONLY as a secondary red flag. It can
    never produce PASS on its own (P0-3)."""
    label_like_by_case = {}
    for case_id, header in headers_by_case.items():
        col = suggest_column(header, LABEL_HINTS)
        if col:
            label_like_by_case[case_id] = col

    if fit_provenance is None:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --fit-provenance supplied. A score CSV header that lacks a label "
                "column is NOT evidence that the fitting step never read labels. C3 "
                "requires a fit-time provenance record: which partition the scorer was "
                "fitted on, which files the fitting run opened, and their hashes."
            ),
            "required_fields": [
                "fit_partition",            # must be the CARE normal reference partition
                "files_read_during_fit",    # list of {path, sha256}
                "label_columns_excluded",   # list of column names withheld from fit
                "verification_method",      # code-path audit / file-access trace / both
                "verified_by",
                "verified_at",
            ],
            "secondary_header_scan_label_like_columns": label_like_by_case,
        }

    problems = []
    partition = fit_provenance.get("fit_partition")
    if is_absent(partition):
        problems.append("fit_partition not declared")
    elif "normal" not in str(partition).lower():
        problems.append(
            "fit_partition '%s' is not the CARE normal reference partition" % partition)

    files_read = fit_provenance.get("files_read_during_fit")
    if not isinstance(files_read, list) or not files_read:
        problems.append("files_read_during_fit missing or empty")
    else:
        for entry in files_read:
            if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
                problems.append("files_read_during_fit entries need both 'path' and 'sha256'")
                break
        flagged = [
            e.get("path") for e in files_read
            if isinstance(e, dict) and e.get("path")
            and suggest_column([os.path.basename(str(e["path"]))], LABEL_HINTS)
        ]
        if flagged:
            problems.append("fitting run opened label-like files: %s" % flagged)

    if is_absent(fit_provenance.get("verification_method")):
        problems.append("verification_method not declared (code-path audit / file-access trace)")
    if is_absent(fit_provenance.get("verified_by")):
        problems.append("verified_by not declared")

    return {
        "status": PASS if not problems else FAIL,
        "problems": problems,
        "fit_partition": partition,
        "n_files_read_during_fit": len(files_read) if isinstance(files_read, list) else 0,
        "label_columns_excluded": fit_provenance.get("label_columns_excluded"),
        "verification_method": fit_provenance.get("verification_method"),
        "verified_by": fit_provenance.get("verified_by"),
        "provenance_receipt": receipt,
        "secondary_header_scan_label_like_columns": label_like_by_case,
    }


# --------------------------------------------------------------------------
# C4 — case coverage by IDENTITY (P0-2)
# --------------------------------------------------------------------------

def read_expected_case_ids(g3_path, errors):
    if not g3_path:
        return None, None
    if not os.path.isfile(g3_path):
        errors.append("g3_case_metadata.csv not found: %s" % g3_path)
        return None, None
    try:
        with open(g3_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "case_id" not in reader.fieldnames:
                errors.append("g3_case_metadata.csv has no 'case_id' column: %s" % g3_path)
                return None, None
            ids = [row["case_id"].strip() for row in reader if row.get("case_id")]
    except OSError as exc:
        errors.append("g3_case_metadata.csv unreadable (%s): %s" % (exc, g3_path))
        return None, None
    return ids, {"path": os.path.abspath(g3_path), "sha256": sha256_of_file(g3_path)}


def check_c4(expected_ids, observed_ids, g2_inventory, g3_receipt):
    if expected_ids is None:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --g3-case-metadata supplied. C4 verifies case IDENTITY; the G2 JSON "
                "carries only counts (n_detected), so a wrong case set of the right size "
                "would pass a count comparison. Supply g3_case_metadata.csv."
            ),
            "n_observed_cases": len(observed_ids),
        }

    expected_set = set(expected_ids)
    observed_set = set(observed_ids)
    duplicate_expected = sorted({c for c in expected_ids if expected_ids.count(c) > 1})
    duplicate_observed = sorted({c for c in observed_ids if observed_ids.count(c) > 1})
    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)

    n_detected = (g2_inventory or {}).get("n_detected")
    g2_consistent = (n_detected == len(expected_set)) if isinstance(n_detected, int) else None

    ok = (not missing and not unexpected
          and not duplicate_expected and not duplicate_observed)

    result = {
        "status": PASS if ok else FAIL,
        "n_expected_case_ids": len(expected_set),
        "n_observed_case_ids": len(observed_set),
        "missing_case_ids": missing,
        "unexpected_case_ids": unexpected,
        "duplicate_case_ids_in_g3": duplicate_expected,
        "duplicate_case_ids_in_score_dir": duplicate_observed,
        "coverage_fraction": (len(expected_set & observed_set) / len(expected_set)
                              if expected_set else None),
        "g2_n_detected": n_detected,
        "g2_count_consistent_with_g3_rows": g2_consistent,
        "g3_receipt": g3_receipt,
    }
    if g2_consistent is False:
        result["note"] = (
            "g2_case_inventory.n_detected disagrees with the g3_case_metadata row count; "
            "the manifest itself needs adjudication before this gate means anything."
        )
    return result


# --------------------------------------------------------------------------
# C5 — determinism & freeze (two runs required, P0-4)
# --------------------------------------------------------------------------

FREEZE_RECEIPT_REQUIRED = [
    "environment",       # python/lib versions, OS
    "seed",
    "config_sha256",
    "artifact_sha256",
]


def check_c5(run1_scores, run2_dir, score_glob, case_id_from, case_id_col,
             score_col, timestamp_col, mode, tolerance, freeze_receipt, freeze_receipt_meta,
             errors):
    if not run2_dir:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --score-dir-run2 supplied. Determinism cannot be established from a "
                "single run: re-hashing one directory only proves the file did not change "
                "on disk. Produce a second independent scorer run and pass it here."
            ),
            "declared_mode": mode,
        }
    if freeze_receipt is None:
        return {
            "status": UNVERIFIED,
            "reason": (
                "No --freeze-receipt supplied. C5 also requires the frozen artifact "
                "fingerprint (environment, seed, config hash, artifact hash) so downstream "
                "calibration comparisons can cite a stable scorer identity."
            ),
            "required_fields": FREEZE_RECEIPT_REQUIRED,
            "declared_mode": mode,
        }

    missing_fields = [k for k in FREEZE_RECEIPT_REQUIRED if is_absent(freeze_receipt.get(k))]

    run2_files = discover_score_files(run2_dir, score_glob, errors)
    run2_scores = {}
    for path in run2_files:
        case_id, rows, header = read_score_file(path, case_id_from, case_id_col, errors)
        if case_id is None:
            continue
        run2_scores[case_id] = {
            "path": path,
            "sha256": sha256_of_file(path),
            "values": [to_float(r.get(score_col)) for r in rows] if score_col else [],
            "timestamps": [r.get(timestamp_col) for r in rows] if timestamp_col else [],
        }

    only_run1 = sorted(set(run1_scores) - set(run2_scores))
    only_run2 = sorted(set(run2_scores) - set(run1_scores))
    shared = sorted(set(run1_scores) & set(run2_scores))

    per_case = {}
    problems = []
    for case_id in shared:
        a, b = run1_scores[case_id], run2_scores[case_id]
        entry = {
            "run1_sha256": a["sha256"],
            "run2_sha256": b["sha256"],
            "bit_identical_file": a["sha256"] == b["sha256"],
        }
        if mode == "bit_identical":
            entry["agrees"] = entry["bit_identical_file"]
            if not entry["agrees"]:
                problems.append("case %s: files differ under bit_identical mode" % case_id)
        else:
            va, vb = a["values"], b["values"]
            if len(va) != len(vb):
                entry["agrees"] = False
                entry["reason"] = "row count differs (%d vs %d)" % (len(va), len(vb))
                problems.append("case %s: %s" % (case_id, entry["reason"]))
            else:
                worst = 0.0
                mismatched_nulls = 0
                for x, y in zip(va, vb):
                    if x is None or y is None:
                        if x is not y:
                            mismatched_nulls += 1
                        continue
                    worst = max(worst, abs(x - y))
                entry["max_abs_diff"] = worst
                entry["n_null_mismatches"] = mismatched_nulls
                entry["agrees"] = worst <= tolerance and mismatched_nulls == 0
                if not entry["agrees"]:
                    problems.append(
                        "case %s: max_abs_diff=%g (tolerance %g), null mismatches=%d"
                        % (case_id, worst, tolerance, mismatched_nulls))
        per_case[case_id] = entry

    if only_run1 or only_run2:
        problems.append("run1/run2 case sets differ (only_run1=%s only_run2=%s)"
                        % (only_run1, only_run2))
    if missing_fields:
        problems.append("freeze receipt missing fields: %s" % missing_fields)
    if not shared:
        problems.append("no cases shared between the two runs")

    return {
        "status": PASS if not problems else FAIL,
        "declared_mode": mode,
        "tolerance": tolerance if mode == "tolerance" else None,
        "problems": problems,
        "n_cases_compared": len(shared),
        "cases_only_in_run1": only_run1,
        "cases_only_in_run2": only_run2,
        "per_case": per_case,
        "freeze_receipt": {
            "environment": freeze_receipt.get("environment"),
            "seed": freeze_receipt.get("seed"),
            "config_sha256": freeze_receipt.get("config_sha256"),
            "artifact_sha256": freeze_receipt.get("artifact_sha256"),
            "receipt_file": freeze_receipt_meta,
        },
    }


# --------------------------------------------------------------------------
# C6 — score sanity on EVALUABLE timestamps only (P0-5)
# --------------------------------------------------------------------------

def check_c6(score_values, mask_rows, score_col, score_col_confirmed):
    if not score_col:
        return {"status": FAIL, "reason": "score column not found in score CSV"}

    if mask_rows and len(mask_rows) == len(score_values):
        evaluable_idx = [i for i, m in enumerate(mask_rows) if m["evaluable"] == "1"]
    else:
        evaluable_idx = list(range(len(score_values)))

    evaluable_vals = [score_values[i] for i in evaluable_idx]
    finite = [v for v in evaluable_vals
              if v is not None and not (math.isnan(v) or math.isinf(v))]
    n_eval = len(evaluable_vals)
    n_finite = len(finite)
    is_constant = len(set(finite)) <= 1 if finite else True

    evaluable_set = set(evaluable_idx)
    non_evaluable_finite = sum(
        1 for i, v in enumerate(score_values)
        if i not in evaluable_set and v is not None
        and not (math.isnan(v) or math.isinf(v)))

    problems = []
    if n_eval == 0:
        problems.append("no evaluable timestamps remain after the C1 mask")
    if n_finite != n_eval:
        problems.append("%d of %d evaluable timestamps have non-finite scores"
                        % (n_eval - n_finite, n_eval))
    if is_constant:
        problems.append("score stream is constant over evaluable timestamps (degenerate)")

    result = {
        "status": PASS if not problems else FAIL,
        "problems": problems,
        "n_rows_total": len(score_values),
        "n_evaluable": n_eval,
        "n_finite_on_evaluable": n_finite,
        "n_non_evaluable": len(score_values) - n_eval,
        "non_evaluable_coverage_fraction": (
            (len(score_values) - n_eval) / len(score_values) if score_values else None),
        "n_finite_scores_on_non_evaluable_rows": non_evaluable_finite,
        "is_constant_on_evaluable": is_constant,
        "min_on_evaluable": min(finite) if finite else None,
        "max_on_evaluable": max(finite) if finite else None,
    }
    if result["status"] == PASS and not score_col_confirmed:
        result["status"] = UNVERIFIED
        result["reason"] = (
            "Score column '%s' was auto-detected, not operator-confirmed. Re-run with "
            "--score-col %s to convert this to PASS." % (score_col, score_col))
    return result


# --------------------------------------------------------------------------
# score file discovery / reading
# --------------------------------------------------------------------------

def discover_score_files(score_dir, score_glob, errors):
    if not os.path.isdir(score_dir):
        errors.append("score dir not found: %s" % score_dir)
        return []
    return sorted(
        os.path.join(score_dir, fn)
        for fn in os.listdir(score_dir)
        if fnmatch.fnmatch(fn, score_glob)
    )


def read_score_file(path, case_id_from, case_id_col, errors):
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            rows = list(reader)
    except OSError as exc:
        errors.append("score file unreadable (%s): %s" % (exc, path))
        return None, [], []

    if case_id_from == "filename":
        case_id = os.path.splitext(os.path.basename(path))[0]
    else:
        if case_id_col not in header:
            errors.append("--case-id-from column requested but '%s' is not in header of %s"
                          % (case_id_col, path))
            return None, rows, header
        values = {r.get(case_id_col, "").strip() for r in rows if r.get(case_id_col)}
        if len(values) != 1:
            errors.append("expected exactly one case_id in column '%s' of %s, found %d"
                          % (case_id_col, path, len(values)))
            return None, rows, header
        case_id = values.pop()
    return case_id, rows, header


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

TEMPLATES = {
    "signal_map.json": {
        signal: {"column": "<column name in the score CSV>", "unit": "<e.g. kW / m·s-1 / °C / deg>"}
        for signal in CORE_SIGNALS
    },
    "artifact_manifest.json": {
        "implementation_source": "<repo URL | supplementary material | re-implementation-from-paper>",
        "version_or_commit": "<git commit / release tag / 'reimpl-2026-08-14'>",
        "parameter_provenance": "<where every hyperparameter came from; cite paper section or config>",
        "artifact_sha256": "<sha256 of the frozen weights/config bundle>",
        "frozen_at": "<ISO-8601>",
        "frozen_by": "<name>",
    },
    "fit_provenance.json": {
        "fit_partition": "CARE normal reference partition <identify precisely>",
        "files_read_during_fit": [{"path": "<path>", "sha256": "<sha256>"}],
        "label_columns_excluded": ["<label column names withheld from fit>"],
        "verification_method": "<code-path audit | file-access trace | both>",
        "verified_by": "<name>",
        "verified_at": "<ISO-8601>",
    },
    "freeze_receipt.json": {
        "environment": {"python": "<version>", "os": "<version>", "key_libs": {}},
        "seed": "<int or 'not applicable — deterministic closed form'>",
        "config_sha256": "<sha256 of the scorer config used for both runs>",
        "artifact_sha256": "<sha256 of the frozen weights/config bundle>",
        "run1_started_at": "<ISO-8601>",
        "run2_started_at": "<ISO-8601>",
    },
}


def emit_templates(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    written = []
    for name, body in TEMPLATES.items():
        path = os.path.join(target_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        written.append(path)
    print("Wrote evidence-file templates:")
    for p in written:
        print("  " + p)
    print("\nFill these in and pass them via --signal-map / --artifact-manifest /"
          "\n--fit-provenance / --freeze-receipt. Until then the corresponding gates"
          "\nreport UNVERIFIED and the overall gate cannot pass.")


# --------------------------------------------------------------------------
# main audit
# --------------------------------------------------------------------------

def run_for_scorer(args):
    errors = []

    g2_inventory, g2_receipt = load_json_or_none(args.g2_inventory, "--g2-inventory", errors)
    signal_map, signal_map_receipt = load_json_or_none(args.signal_map, "--signal-map", errors)
    artifact_manifest, artifact_receipt = load_json_or_none(
        args.artifact_manifest, "--artifact-manifest", errors)
    fit_provenance, fit_receipt = load_json_or_none(args.fit_provenance, "--fit-provenance", errors)
    freeze_receipt, freeze_receipt_meta = load_json_or_none(
        args.freeze_receipt, "--freeze-receipt", errors)
    expected_ids, g3_receipt = read_expected_case_ids(args.g3_case_metadata, errors)

    workdir_status = NOT_APPLICABLE
    workdir_note = None
    if args.workdir:
        if os.path.isdir(args.workdir):
            workdir_status = PASS
        else:
            workdir_status = FAIL
            errors.append("--workdir does not exist: %s" % args.workdir)
            workdir_note = "extracted CARE v6 root not found"

    score_files = discover_score_files(args.score_dir, args.score_glob, errors)

    per_case = {}
    headers_by_case = {}
    run1_scores = {}
    observed_ids = []
    mask_dir = os.path.join(args.output_dir, "evaluability_masks")

    for path in score_files:
        case_id, rows, header = read_score_file(path, args.case_id_from, args.case_id_col, errors)
        if case_id is None:
            continue
        observed_ids.append(case_id)
        headers_by_case[case_id] = header

        c0 = check_c0(header, signal_map)

        score_col_confirmed = args.score_col != "auto"
        score_col = args.score_col if score_col_confirmed else suggest_column(header, SCORE_HINTS)

        timestamp_col = args.timestamp_col
        if timestamp_col and timestamp_col not in header:
            errors.append("timestamp column '%s' not in header of %s" % (timestamp_col, path))

        # Scores are parsed before C1 now: the evaluability mask needs to know
        # which rows the scorer declined, so that C1 counts them against its
        # coverage cap and C6 does not demand a score for them.
        score_values = [to_float(r.get(score_col)) for r in rows] if score_col else []

        value_columns = c0.get("value_columns") or []
        c1, mask_rows = check_c1(rows, timestamp_col, value_columns,
                                 args.nominal_interval_minutes,
                                 score_values=score_values if score_col else None)

        c6 = check_c6(score_values, mask_rows, score_col, score_col_confirmed)

        if mask_rows:
            os.makedirs(mask_dir, exist_ok=True)
            mask_path = os.path.join(mask_dir, "%s_evaluability_mask.csv" % case_id)
            with open(mask_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["row_index", "timestamp", "evaluable", "non_evaluable_reason"])
                writer.writeheader()
                writer.writerows(mask_rows)
        else:
            mask_path = None

        run1_scores[case_id] = {
            "path": path,
            "sha256": sha256_of_file(path),
            "values": score_values,
        }

        per_case[case_id] = {
            "source_file": os.path.abspath(path),
            "input_sha256": run1_scores[case_id]["sha256"],
            "n_rows": len(rows),
            "score_column": score_col,
            "score_column_operator_confirmed": score_col_confirmed,
            "timestamp_column": timestamp_col,
            "evaluability_mask_file": os.path.abspath(mask_path) if mask_path else None,
            "C0_signal_mapping": c0,
            "C1_missing_feature_policy": c1,
            "C6_score_sanity": c6,
        }

    # Gate roll-ups.
    if per_case:
        c0_status = worst_status([c["C0_signal_mapping"]["status"] for c in per_case.values()])
        c1_status = worst_status([c["C1_missing_feature_policy"]["status"] for c in per_case.values()])
        c6_status = worst_status([c["C6_score_sanity"]["status"] for c in per_case.values()])
    else:
        c0_status = c1_status = c6_status = UNVERIFIED

    c2 = check_c2(artifact_manifest, artifact_receipt)
    c3 = check_c3(fit_provenance, fit_receipt, headers_by_case)
    c4 = check_c4(expected_ids, observed_ids, g2_inventory, g3_receipt)
    c5 = check_c5(run1_scores, args.score_dir_run2, args.score_glob, args.case_id_from,
                  args.case_id_col, (args.score_col if args.score_col != "auto" else
                                     suggest_column(next(iter(headers_by_case.values()), []),
                                                    SCORE_HINTS)),
                  args.timestamp_col, args.determinism_mode, args.tolerance,
                  freeze_receipt, freeze_receipt_meta, errors)

    gates = {
        "C0_signal_availability_and_mapping": {
            "status": c0_status,
            "detail": "per-case; see per_case_c0_c6.json",
            "declared_unavailable_signals": sorted({
                sig for c in per_case.values()
                for sig in (c["C0_signal_mapping"].get("declared_unavailable_signals") or {})
            }),
            "n_cases_failing": sum(
                1 for c in per_case.values() if c["C0_signal_mapping"]["status"] == FAIL),
        },
        "C1_missing_feature_policy": {
            "status": c1_status,
            "detail": "per-case; wall-clock gap classification + evaluability mask",
            "n_cases_over_flag_fraction": sum(
                1 for c in per_case.values()
                if c["C1_missing_feature_policy"].get("flag_over_threshold")),
        },
        "C2_artifact_reproducibility": c2,
        "C3_label_independence": c3,
        "C4_case_coverage": c4,
        "C5_determinism_and_freeze": c5,
        "C6_score_sanity": {
            "status": c6_status,
            "detail": "per-case; finiteness checked on evaluable timestamps only",
            "n_cases_failing": sum(
                1 for c in per_case.values() if c["C6_score_sanity"]["status"] == FAIL),
        },
    }

    if not per_case:
        errors.append("no readable per-case score CSVs were found in --score-dir")

    gate_status = worst_status([g["status"] for g in gates.values()])
    if errors and gate_status == PASS:
        gate_status = UNVERIFIED

    summary = {
        "gate_version": GATE_VERSION,
        "gate_definitions_ratified": False,
        "gate_definitions_note": (
            "C0-C6 names and thresholds remain a PROPOSAL (R15 + PI directive v1.0 "
            "synthesis). Tooling being merged is not gate ratification. gate_status "
            "below describes evidence only."
        ),
        "scorer_name": args.scorer_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gate_status": gate_status,
        "status_enum": [PASS, FAIL, UNVERIFIED, NOT_APPLICABLE],
        "gates": gates,
        "n_cases_audited": len(per_case),
        "errors": errors,
        "workdir": {
            "path": os.path.abspath(args.workdir) if args.workdir else None,
            "status": workdir_status,
            "note": workdir_note,
        },
        "input_receipts": {
            "g2_inventory": g2_receipt,
            "g3_case_metadata": g3_receipt,
            "signal_map": signal_map_receipt,
            "artifact_manifest": artifact_receipt,
            "fit_provenance": fit_receipt,
            "freeze_receipt": freeze_receipt_meta,
            "score_dir": os.path.abspath(args.score_dir),
            "score_dir_run2": os.path.abspath(args.score_dir_run2) if args.score_dir_run2 else None,
            "score_glob": args.score_glob,
            "per_case_input_sha256": {k: v["input_sha256"] for k, v in per_case.items()},
        },
        "cli_invocation": " ".join(sys.argv),
    }

    os.makedirs(args.output_dir, exist_ok=True)
    per_case_path = os.path.join(args.output_dir, "per_case_c0_c6.json")
    summary_path = os.path.join(args.output_dir, "compatibility_summary.json")
    with open(per_case_path, "w", encoding="utf-8") as f:
        json.dump(per_case, f, indent=2, ensure_ascii=False)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    output_receipt = {
        "gate_version": GATE_VERSION,
        "gate_status": gate_status,
        "outputs": {
            os.path.basename(per_case_path): sha256_of_file(per_case_path),
            os.path.basename(summary_path): sha256_of_file(summary_path),
        },
    }
    if os.path.isdir(mask_dir):
        output_receipt["outputs"]["evaluability_masks"] = {
            fn: sha256_of_file(os.path.join(mask_dir, fn))
            for fn in sorted(os.listdir(mask_dir))
        }
    receipt_path = os.path.join(args.output_dir, "output_receipt.json")
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(output_receipt, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("\ngate_status=%s (%s)" % (gate_status, GATE_VERSION), file=sys.stderr)
    print("See %s" % summary_path, file=sys.stderr)

    if gate_status == PASS:
        return EXIT_PASS
    if gate_status == FAIL:
        return EXIT_FAIL
    return EXIT_UNVERIFIED


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit-templates", metavar="DIR",
                    help="Write blank evidence-file templates to DIR and exit")
    ap.add_argument("--workdir", help="Extracted CARE v6 root; existence is checked and recorded")
    ap.add_argument("--g2-inventory", help="Path to g2_case_inventory.json (counts cross-check)")
    ap.add_argument("--g3-case-metadata",
                    help="Path to g3_case_metadata.csv — the case_id source of truth for C4")
    ap.add_argument("--score-dir", help="Directory of per-case score CSVs (run 1)")
    ap.add_argument("--score-dir-run2", help="Directory of per-case score CSVs from an independent run 2 (C5)")
    ap.add_argument("--score-glob", default="*.csv", help="Filename glob for score CSVs (default *.csv)")
    ap.add_argument("--case-id-from", choices=["filename", "column"], default="filename",
                    help="Where each file's case_id comes from (default filename)")
    ap.add_argument("--case-id-col", default="case_id",
                    help="Column holding case_id when --case-id-from column")
    ap.add_argument("--scorer-name", help='e.g. "MD_2022" or "MainBearing_2026"')
    ap.add_argument("--output-dir")
    ap.add_argument("--score-col", default="auto",
                    help="Score column name; 'auto' detects but caps C6 at UNVERIFIED")
    ap.add_argument("--timestamp-col", help="Timestamp column; required for C1/C6 to be verifiable")
    ap.add_argument("--signal-map", help="JSON mapping the 6 core signals to columns + units (C0)")
    ap.add_argument("--artifact-manifest", help="JSON recording implementation source/version/params (C2)")
    ap.add_argument("--fit-provenance", help="JSON recording fit-time file access + partition (C3)")
    ap.add_argument("--freeze-receipt", help="JSON recording environment/seed/config/artifact hashes (C5)")
    ap.add_argument("--determinism-mode", choices=["bit_identical", "tolerance"],
                    default="bit_identical", help="How run1 and run2 must agree (C5)")
    ap.add_argument("--tolerance", type=float, default=0.0,
                    help="Max absolute score difference when --determinism-mode tolerance")
    ap.add_argument("--nominal-interval-minutes", type=float,
                    default=NOMINAL_INTERVAL_MINUTES_DEFAULT,
                    help="Nominal SCADA sampling interval, used only at series boundaries")
    args = ap.parse_args()

    if args.emit_templates:
        emit_templates(args.emit_templates)
        return EXIT_PASS

    required = ["score_dir", "scorer_name", "output_dir"]
    missing = [("--" + r.replace("_", "-")) for r in required if not getattr(args, r)]
    if missing:
        ap.error("missing required arguments: %s" % ", ".join(missing))

    if args.determinism_mode == "tolerance" and args.tolerance <= 0:
        ap.error("--determinism-mode tolerance requires a positive --tolerance")

    try:
        return run_for_scorer(args)
    except OSError as exc:
        print("I/O error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
