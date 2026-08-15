#!/usr/bin/env python3
"""
CARE v6 split & leakage audit — resolves the D1/D6 question the manifest
could only raise.

WHY THIS EXISTS
---------------
The 2026-08-14 asset-level G6 pass found that 95 cases come from only 36
turbines; 30 of those turbines appear in more than one case, giving 108
same-asset case pairs whose spans overlap (73 of them anomaly x normal),
median overlap 289 days.

That is a case-SPAN result. It says asset-period isolation cannot be
ASSUMED. It does not say contamination has occurred, because each case
carries a per-row `train_test` column and each farm ships an event
description file, and the real question is narrower:

    For two cases on the SAME turbine whose spans overlap, do their
    EVALUATION (test/prediction) windows overlap in wall-clock time?

If they do not, the overlap is benign: the shared calendar period sits in
one case's fitting partition and the other's, but the parts we evaluate on
are disjoint. If they do, a "held-out" case is not held out at the
asset-period level and the evaluation contract needs revising.

This script answers that question and nothing else. It is deliberately
cheap: it reads only the timestamp and split columns per case, plus the
small per-farm event description files, so it runs in minutes rather than
the hours a full-width scan would take on Farm C's 957 columns.

WHAT IT DOES NOT ASSUME
-----------------------
The event file schema is not hardcoded. The script locates candidate
event/description files per farm, records their real headers verbatim, and
reports what it found. If it cannot interpret them it says so rather than
guessing an event-window semantics that may not exist.

USAGE
-----
    python3 care_v6_split_audit.py \\
        --workdir    /path/to/extracted_care_v6 \\
        --g3-case-metadata ./manifest_out/g3_case_metadata.csv \\
        --output-dir ./split_audit_out \\
        [--case-glob "**/datasets/*.csv"] \\
        [--split-col train_test] [--timestamp-col time_stamp]

Outputs:
    split_inventory.json     per-case split values, row counts, and the
                             wall-clock span of each split partition
    event_files_found.json   verbatim headers/rows of the per-farm event
                             description files, uninterpreted
    leakage_verdict.json     per overlapping asset pair: do the evaluation
                             windows overlap, and by how long

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import itertools
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
]

# Values that conventionally denote the evaluation partition. Anything not in
# TRAIN_TOKENS and not in EVAL_TOKENS is reported as unrecognised rather than
# bucketed by guesswork.
TRAIN_TOKENS = {"train", "training", "fit", "0", "false"}
EVAL_TOKENS = {"test", "prediction", "predict", "eval", "evaluation", "1", "true"}

EVENT_FILE_HINTS = ("event", "info", "description", "meta", "label", "readme")

# --- CSV dialect handling -------------------------------------------------
# CARE v6 case files are not guaranteed to be comma-separated. A semicolon
# file read with the default dialect yields a single mega-column, which is
# how three separate tools failed at once on 2026-08-14: the quality scan
# saw "1 column", the split audit could not find train_test, and the sensor
# profiler could not find any power/wind anchor. Detect it instead of
# assuming, and let the operator override.
CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]


def sniff_delimiter(path, override=None):
    """Pick the delimiter that splits the HEADER line into the most fields."""
    if override:
        return {"tab": "\t", "\\t": "\t"}.get(override, override)
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            header = f.readline()
    except OSError:
        return ","
    best, best_count = ",", -1
    for d in CANDIDATE_DELIMITERS:
        count = header.count(d)
        if count > best_count:
            best, best_count = d, count
    return best


def farm_from_path(path, workdir):
    """Farm name is the directory that CONTAINS `datasets`, not the first
    component under --workdir: pointing --workdir one level too high
    otherwise collapses every farm into a single group."""
    rel = os.path.normpath(os.path.relpath(path, workdir))
    parts = rel.split(os.sep)
    for i, part in enumerate(parts):
        if part.lower() == "datasets" and i > 0:
            return parts[i - 1]
    return parts[0] if len(parts) > 1 else "(root)"


def parse_ts(raw):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def classify_split(value):
    v = (value or "").strip().lower()
    if not v:
        return "missing"
    if v in TRAIN_TOKENS:
        return "train"
    if v in EVAL_TOKENS:
        return "eval"
    return "unrecognised:" + v


def scan_case(path, split_col, timestamp_col, delimiter_override=None):
    """One pass reading only the two columns we need."""
    delimiter = sniff_delimiter(path, delimiter_override)
    spans = defaultdict(lambda: {"n": 0, "first": None, "last": None})
    counts = Counter()
    header = []
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            header = reader.fieldnames or []
            if split_col not in header:
                return {"error": "split column %r not in header" % split_col,
                        "delimiter_used": delimiter,
                        "n_columns_seen": len(header),
                        "header_sample": header[:20]}
            for row in reader:
                bucket = classify_split(row.get(split_col))
                counts[bucket] += 1
                ts = parse_ts(row.get(timestamp_col))
                rec = spans[bucket]
                rec["n"] += 1
                if ts is not None:
                    if rec["first"] is None or ts < rec["first"]:
                        rec["first"] = ts
                    if rec["last"] is None or ts > rec["last"]:
                        rec["last"] = ts
    except OSError as exc:
        return {"error": "unreadable: %s" % exc}

    return {
        "n_rows": sum(counts.values()),
        "delimiter_used": delimiter,
        "split_value_counts": dict(counts),
        "partitions": {
            k: {
                "n_rows": v["n"],
                "first_timestamp": v["first"].isoformat() if v["first"] else None,
                "last_timestamp": v["last"].isoformat() if v["last"] else None,
            }
            for k, v in sorted(spans.items())
        },
    }


def find_event_files(workdir):
    """Locate the small per-farm description files without assuming a schema."""
    found = []
    for path in sorted(glob.glob(os.path.join(workdir, "**", "*"), recursive=True)):
        if not os.path.isfile(path):
            continue
        base = os.path.basename(path).lower()
        if os.sep + "datasets" + os.sep in path.lower():
            continue
        if not any(h in base for h in EVENT_FILE_HINTS):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        entry = {"path": os.path.abspath(path), "size_bytes": size}
        if base.endswith((".csv", ".tsv", ".txt")) and size < 20 * 1024 * 1024:
            delim = "\t" if base.endswith(".tsv") else ","
            try:
                with open(path, newline="", encoding="utf-8", errors="replace") as f:
                    reader = csv.reader(f, delimiter=delim)
                    rows = list(itertools.islice(reader, 0, 11))
                entry["header"] = rows[0] if rows else []
                entry["first_rows_verbatim"] = rows[1:]
                with open(path, encoding="utf-8", errors="replace") as f:
                    entry["n_lines"] = sum(1 for _ in f)
            except OSError as exc:
                entry["read_error"] = str(exc)
        found.append(entry)
    return found


def overlap_days(a_start, a_end, b_start, b_end):
    if None in (a_start, a_end, b_start, b_end):
        return None
    delta = min(a_end, b_end) - max(a_start, b_start)
    secs = delta.total_seconds()
    return round(secs / 86400.0, 2) if secs > 0 else 0.0



def build_exclusion_plan(pairs, inventory):
    """Turn contaminated pairs into a concrete, auditable exclusion list.

    The PI ratified exclusion over re-splitting on 2026-08-15, so each
    contaminated pair loses exactly one case. Which one is decided by a fixed
    rule, never case by case:

      1. Cross-label pair -> drop the NORMAL case. Anomaly cases are scarcer
         (45 vs 50) and are the ones carrying a labelled event, so they are
         what Earliness and Reliability are measured on. Losing a normal case
         costs calibration data, which the remaining normals still supply.
      2. Same-label pair -> drop the case with the SHORTER evaluation window,
         since that discards less evaluable evidence.

    Overlaps are also reported in absolute terms. An overlap of a few hours
    costs a whole case under this rule, which may be a poor trade; the plan
    flags those rather than hiding them inside the total.
    """
    def eval_span_days(case_id):
        ev = ((inventory.get(case_id) or {}).get("partitions") or {}).get("eval")
        if not ev or not ev["first_timestamp"] or not ev["last_timestamp"]:
            return None
        a, b = parse_ts(ev["first_timestamp"]), parse_ts(ev["last_timestamp"])
        if not a or not b:
            return None
        return (b - a).total_seconds() / 86400.0

    decisions = []
    for p in pairs:
        if p.get("verdict") != "EVAL_WINDOWS_OVERLAP":
            continue
        a, b = p["case_a"], p["case_b"]
        la, lb = p.get("label_a"), p.get("label_b")
        if la != lb:
            drop = a if la == "normal" else b
            rule = "cross_label_drop_normal"
        else:
            sa, sb = eval_span_days(a), eval_span_days(b)
            if sa is None or sb is None:
                drop, rule = None, "UNRESOLVED_no_eval_span"
            else:
                drop = a if sa < sb else b
                rule = "same_label_drop_shorter_eval_window"
        keep = b if drop == a else (a if drop == b else None)
        decisions.append({
            "farm": p["farm"], "turbine_id": p["turbine_id"],
            "case_a": a, "label_a": la, "eval_span_days_a": _r(eval_span_days(a)),
            "case_b": b, "label_b": lb, "eval_span_days_b": _r(eval_span_days(b)),
            "eval_overlap_days": p["eval_overlap_days"],
            "exclude": drop, "keep": keep, "rule": rule,
            "flag_tiny_overlap": (p["eval_overlap_days"] or 0) < 1.0,
        })

    excluded = sorted({d["exclude"] for d in decisions if d["exclude"]})
    by_label = Counter((inventory.get(c) or {}).get("label") for c in excluded)
    tiny = [d for d in decisions if d["flag_tiny_overlap"] and d["exclude"]]
    return {
        "policy": "exclusion (PI decision 2026-08-15), one case per contaminated pair",
        "rules": {
            "cross_label_drop_normal": "anomaly cases are scarcer and carry the "
                                       "labelled event Earliness is measured on",
            "same_label_drop_shorter_eval_window": "discards less evaluable evidence",
        },
        "n_pairs_resolved": len(decisions),
        "excluded_case_ids": excluded,
        "n_excluded": len(excluded),
        "excluded_by_label": dict(by_label),
        "decisions": decisions,
        "review_before_accepting": (
            [] if not tiny else
            ["case %s is excluded over an overlap of only %s days; trimming that "
             "window instead would keep the case -- confirm the trade is intended"
             % (d["exclude"], d["eval_overlap_days"]) for d in tiny]),
    }


def _r(x, nd=1):
    return None if x is None else round(x, nd)


def run(args):
    print("care_v6_split_audit starting", flush=True)
    print("  workdir  : %s" % args.workdir, flush=True)
    print("  case-glob: %s" % args.case_glob, flush=True)
    if not os.path.isdir(args.workdir):
        print("workdir not found: %s" % args.workdir, file=sys.stderr)
        return 3
    if not os.path.isfile(args.g3_case_metadata):
        print("g3_case_metadata.csv not found: %s" % args.g3_case_metadata, file=sys.stderr)
        return 3

    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.g3_case_metadata, newline="", encoding="utf-8", errors="replace") as f:
        case_rows = list(csv.DictReader(f))
    meta_by_case = {r["case_id"]: r for r in case_rows}

    case_files = sorted(glob.glob(os.path.join(args.workdir, args.case_glob), recursive=True))
    if not case_files:
        print("no case files matched %r" % args.case_glob, file=sys.stderr)
        return 3

    print("[split] scanning %d cases (2 columns each)" % len(case_files), file=sys.stderr)
    inventory = {}
    for i, path in enumerate(case_files, 1):
        case_id = os.path.splitext(os.path.basename(path))[0]
        result = scan_case(path, args.split_col, args.timestamp_col, args.delimiter)
        meta = meta_by_case.get(case_id, {})
        result["case_id"] = case_id
        result["farm_id"] = meta.get("farm_id")
        result["turbine_id"] = meta.get("turbine_id")
        result["label"] = meta.get("label")
        result["in_g3_metadata"] = bool(meta)
        inventory[case_id] = result
        if i % 20 == 0:
            print("  %d/%d" % (i, len(case_files)), file=sys.stderr)

    with open(os.path.join(args.output_dir, "split_inventory.json"), "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    events = find_event_files(args.workdir)
    with open(os.path.join(args.output_dir, "event_files_found.json"), "w", encoding="utf-8") as f:
        json.dump({
            "note": ("Headers and first rows are recorded verbatim and are NOT "
                     "interpreted. Read them, then decide what the event-window "
                     "semantics are before anyone codes against this schema."),
            "n_files": len(events),
            "files": events,
        }, f, indent=2, ensure_ascii=False)

    # The actual verdict: same asset, spans overlap -> do EVAL windows overlap?
    by_asset = defaultdict(list)
    for case_id, rec in inventory.items():
        if rec.get("farm_id") and rec.get("turbine_id"):
            by_asset[(rec["farm_id"], rec["turbine_id"])].append(case_id)

    def eval_window(case_id):
        parts = inventory[case_id].get("partitions", {})
        ev = parts.get("eval")
        if not ev or not ev["first_timestamp"] or not ev["last_timestamp"]:
            return None, None
        return parse_ts(ev["first_timestamp"]), parse_ts(ev["last_timestamp"])

    pairs = []
    n_unresolved = 0
    for (farm, turbine), case_ids in sorted(by_asset.items()):
        for a, b in itertools.combinations(sorted(case_ids), 2):
            a_s, a_e = eval_window(a)
            b_s, b_e = eval_window(b)
            if None in (a_s, a_e, b_s, b_e):
                n_unresolved += 1
                pairs.append({
                    "farm": farm, "turbine_id": turbine,
                    "case_a": a, "case_b": b,
                    "eval_overlap_days": None,
                    "verdict": "UNRESOLVED",
                    "reason": "one or both cases have no recognised eval partition",
                    "split_counts_a": inventory[a].get("split_value_counts"),
                    "split_counts_b": inventory[b].get("split_value_counts"),
                })
                continue
            ov = overlap_days(a_s, a_e, b_s, b_e)
            pairs.append({
                "farm": farm, "turbine_id": turbine,
                "case_a": a, "label_a": inventory[a].get("label"),
                "case_b": b, "label_b": inventory[b].get("label"),
                "eval_a": [a_s.isoformat(), a_e.isoformat()],
                "eval_b": [b_s.isoformat(), b_e.isoformat()],
                "eval_overlap_days": ov,
                "cross_label": inventory[a].get("label") != inventory[b].get("label"),
                "verdict": "EVAL_WINDOWS_OVERLAP" if ov and ov > 0 else "EVAL_WINDOWS_DISJOINT",
            })

    contaminated = [p for p in pairs if p["verdict"] == "EVAL_WINDOWS_OVERLAP"]
    cross_label_contaminated = [p for p in contaminated if p.get("cross_label")]

    unrecognised_tokens = sorted({
        k.split(":", 1)[1]
        for rec in inventory.values()
        for k in (rec.get("split_value_counts") or {})
        if k.startswith("unrecognised:")
    })

    verdict = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "split_column": args.split_col,
        "n_cases_scanned": len(inventory),
        "n_cases_with_eval_partition": sum(
            1 for r in inventory.values() if (r.get("partitions") or {}).get("eval")),
        "unrecognised_split_tokens": unrecognised_tokens,
        "n_distinct_assets": len(by_asset),
        "n_assets_in_multiple_cases": sum(1 for v in by_asset.values() if len(v) > 1),
        "n_same_asset_pairs_examined": len(pairs),
        "n_pairs_with_overlapping_eval_windows": len(contaminated),
        "n_cross_label_pairs_with_overlapping_eval_windows": len(cross_label_contaminated),
        "n_pairs_unresolved": n_unresolved,
        "max_eval_overlap_days": max(
            (p["eval_overlap_days"] for p in contaminated), default=None),
        "d1_d6_reading": _reading(contaminated, n_unresolved, unrecognised_tokens, len(pairs)),
        "pairs": sorted(pairs, key=lambda p: -(p["eval_overlap_days"] or -1)),
    }
    with open(os.path.join(args.output_dir, "leakage_verdict.json"), "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2, ensure_ascii=False)

    plan = build_exclusion_plan(pairs, inventory)
    with open(os.path.join(args.output_dir, "exclusion_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    print("\n--- split audit ---")
    print("cases scanned:                    %d" % verdict["n_cases_scanned"])
    print("cases with an eval partition:     %d" % verdict["n_cases_with_eval_partition"])
    if unrecognised_tokens:
        print("UNRECOGNISED split tokens:        %s" % unrecognised_tokens)
    print("same-asset pairs examined:        %d" % verdict["n_same_asset_pairs_examined"])
    print("pairs with OVERLAPPING eval windows: %d (cross-label %d)"
          % (verdict["n_pairs_with_overlapping_eval_windows"],
             verdict["n_cross_label_pairs_with_overlapping_eval_windows"]))
    print("pairs unresolved:                 %d" % n_unresolved)
    print("\n%s" % verdict["d1_d6_reading"])
    if plan["n_excluded"]:
        print("\nexclusion plan: drop %d case(s) -> %s  (by label: %s)"
              % (plan["n_excluded"], ", ".join(plan["excluded_case_ids"]),
                 plan["excluded_by_label"]))
        for note in plan["review_before_accepting"]:
            print("  REVIEW: %s" % note)
    print("\nWrote %s" % args.output_dir, file=sys.stderr)
    return 0


def _reading(contaminated, n_unresolved, unrecognised, n_pairs):
    if not n_pairs:
        return ("NOT APPLICABLE — no turbine appears in more than one case, so there is "
                "no same-asset pair to examine. Check that --g3-case-metadata matches "
                "the cases actually scanned before reading this as reassurance.")
    if unrecognised:
        return ("UNVERIFIED — the split column contains tokens this script does not "
                "recognise (%s). Decide what they mean and re-run before reading any "
                "verdict below." % ", ".join(unrecognised))
    if n_unresolved:
        return ("PARTIAL — %d pair(s) could not be resolved because a case has no "
                "recognised evaluation partition. Resolve those before recording a "
                "D1/D6 verdict." % n_unresolved)
    if not contaminated:
        return ("CLEAN on this criterion — no two cases on the same turbine have "
                "overlapping evaluation windows. Case-span overlap is therefore benign: "
                "the shared calendar period sits in fitting partitions, not in what is "
                "evaluated. This does NOT by itself close D1/D6; it removes the specific "
                "asset-period contamination concern raised by G6.")
    return ("CONTAMINATION PRESENT — %d same-asset pair(s) have overlapping evaluation "
            "windows. A held-out case is not held out at the asset-period level. The "
            "evaluation contract must either exclude one case of each pair or move to an "
            "asset-level split." % len(contaminated))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--g3-case-metadata", required=True,
                    help="manifest_out/g3_case_metadata.csv (supplies farm/turbine/label)")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case-glob", default="**/datasets/*.csv")
    ap.add_argument("--split-col", default="train_test")
    ap.add_argument("--timestamp-col", default="time_stamp")
    ap.add_argument("--delimiter", default=None,
                    help="CSV delimiter; auto-detected from the header when omitted")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
