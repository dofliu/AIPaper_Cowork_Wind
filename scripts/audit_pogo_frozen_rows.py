#!/usr/bin/env python3
"""Is POGO's frozen flag POGO's own? Measure it, do not accept the declaration.

WHY THIS EXISTS
---------------
R26 G3's contract (section 3) contains one prohibition that the whole value of
G6 rests on:

    POGO's `frozen` flag must be produced by POGO's OWN exceedance sequence
    under the same 6-of-18 rule. It may never be copied from this project's
    `frozen` column.

Copy it and G6 stops being an independent check: this project's lock-in
geometry gets handed to POGO, which then "independently reproduces" it. The
run completes, the tables fill in, and the agreement looks like the strongest
result in the paper.

Until this tool, the only guard was a receipt field -- `frozen_flag_source`,
a string the implementer writes. A field that says the right thing is not
evidence that the right thing happened; it is evidence that someone typed it.

劉老師 decided on 2026-08-22 (R29) that the owner must hand back POGO's
per-row output so the flag can be compared row by row. That turns two
declarations into measurements:

  * PROVENANCE -- re-derive 6-of-18 from POGO's own `exceed` column and
    compare with the `frozen` POGO wrote, in BOTH directions. Zero
    disagreements is what "POGO produced this itself" means, measured.
    This is the same audit, and the same function, this project already ran
    against its OWN frozen column on ~2.5M points (PROJECT_STATUS 1.00) --
    reused rather than rewritten, so there is one implementation to trust.
  * INDEPENDENCE -- compare POGO's frozen vector with ours, per case, row by
    row. Agreement is the interesting G6 measurement; identity everywhere is
    a copy.

WHAT COUNTS AS THE RED FLAG
---------------------------
NOT "the two agree a lot" -- high agreement is the result G6 exists to look
for, and finding it would be evidence that lock-in is a property of the alarm
policy rather than of this method.

The red flag is IDENTITY across every non-trivial case: the same rows, in the
same order, flagged the same way, with nothing differing anywhere. Cases where
neither side ever freezes are excluded from that judgement -- two quiet cases
agreeing is arithmetic, not provenance.

WHAT THIS IS NOT
----------------
It does not evaluate either method, compares no metric, and says nothing about
which is better. It answers one question: may these two frozen columns be
treated as independently produced?

USAGE
-----
    python3 scripts/audit_pogo_frozen_rows.py \
        --ours-dir experiments/MD_2022_a01_ours \
        --pogo-dir <POGO 逐列輸出目錄> \
        --exclude-cases 32,56,72,87 \
        --trim-case "93=2023-08-24T13:00:00" \
        --alpha 0.01 \
        --output experiments/pogo_r26_<date>/frozen_row_audit_a01.json

Both directories hold one CSV per case, named `<case_id>.csv`. POGO's must
carry at least `timestamp`, `exceed` and `frozen`.

Exit code: 0 only if provenance and independence both hold.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Reused deliberately: the 6-of-18 premise audit that was run against this
# project's own frozen column, and the timestamp canonicaliser whose absence
# once made a ratified trim silently drop nothing.
from diagnose_alarm_selection_floor import (                        # noqa: E402
    ALARM_OF, ALARM_WINDOW, audit_premise, canonical_ts, parse_trim)

CLAIM_CONSTRAINT = {
    "source": "R26 G3 contract section 3 + R29 (2026-08-22) + R25 claim firewall",
    "forbidden": [
        "reporting agreement between the two frozen columns without stating "
        "that POGO's was audited for provenance (6-of-18 over its own exceed)",
        "reading high agreement as evidence that either method is better; it "
        "is evidence about the alarm policy, not about the calibrators",
        "any 'we outperform / match / are incomparable to POGO' statement "
        "before G8 reports",
    ],
    "permitted": [
        "reporting the measured agreement between independently produced "
        "frozen columns, with the provenance audit beside it",
        "arguing from that agreement that freeze lock-in is a property of the "
        "6-of-18 + Freeze-on-Alert policy rather than of this method",
        "reporting per-case disagreement as the evidence that the two columns "
        "were produced separately",
    ],
}


def read_rows(path, trim_at=None, require=("exceed",)):
    """Read one case's stream, keeping only rows carrying a verdict.

    A row counts when every column in `require` is non-empty. Warm-up rows
    carry no verdict and are not part of any alarm window, so including them
    would shift every index and break the premise audit silently.

    Returns (timestamps, exceeds, frozen, n_rows, n_dropped).
    """
    timestamps, exceeds, frozen = [], [], []
    n_rows = 0
    n_dropped = 0
    cut = canonical_ts(trim_at) if trim_at is not None else None
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            ts = canonical_ts(row.get("timestamp"))
            if cut is not None and ts >= cut:
                n_dropped += 1
                continue
            n_rows += 1
            if any((row.get(col) or "").strip() == "" for col in require):
                continue
            timestamps.append(ts)
            exceeds.append(int((row.get("exceed") or "").strip()))
            frozen.append((row.get("frozen") or "0").strip() == "1")
    return timestamps, exceeds, frozen, n_rows, n_dropped


def case_id_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def compare_case(ours, pogo):
    """Align two streams on the shared window and compare their frozen columns.

    `ours` and `pogo` are (timestamps, exceeds, frozen) triples. The shared
    evaluation window is defined by OUR calibrated rows (G3 contract section
    4), so POGO is required to cover exactly those timestamps -- no more, no
    fewer, in the same order.

    Returns (failures, result).
    """
    fails = []
    our_ts, _our_exc, our_frozen = ours
    pogo_ts, pogo_exc, pogo_frozen = pogo

    if len(pogo_ts) != len(our_ts):
        fails.append("window length differs: ours %d rows, POGO %d rows"
                     % (len(our_ts), len(pogo_ts)))
    if len(set(pogo_ts)) != len(pogo_ts):
        fails.append("POGO's rows contain duplicate timestamps")
    if not fails and pogo_ts != our_ts:
        first = next(i for i in range(len(our_ts)) if our_ts[i] != pogo_ts[i])
        fails.append("timestamps diverge at row %d: ours %s, POGO %s"
                     % (first, our_ts[first], pogo_ts[first]))
    if fails:
        return fails, None

    # PROVENANCE: POGO's frozen must BE 6-of-18 over POGO's own exceed, in
    # both directions. Anything non-zero here means the flag did not come from
    # the sequence it is supposed to come from.
    audit = audit_premise(pogo_exc, pogo_frozen, ALARM_OF, ALARM_WINDOW)
    if audit["frozen_without_rule"] or audit["rule_without_frozen"]:
        fails.append(
            "POGO's frozen does not match 6-of-18 over POGO's own exceed: "
            "%d frozen-without-rule, %d rule-without-frozen (of %d testable)"
            % (audit["frozen_without_rule"], audit["rule_without_frozen"],
               audit["n_testable"]))

    n = len(our_ts)
    agree = sum(1 for a, b in zip(our_frozen, pogo_frozen) if a == b)
    both = sum(1 for a, b in zip(our_frozen, pogo_frozen) if a and b)
    either = sum(1 for a, b in zip(our_frozen, pogo_frozen) if a or b)
    result = {
        "n_rows_in_window": n,
        "ours_frozen": sum(our_frozen),
        "pogo_frozen": sum(pogo_frozen),
        "rows_agreeing": agree,
        "agreement": round(agree / float(n), 6) if n else None,
        "jaccard": round(both / float(either), 6) if either else None,
        "identical": our_frozen == pogo_frozen,
        # A case where neither side ever freezes is identical by arithmetic,
        # not by provenance, so it must not count towards the copy verdict.
        "trivial": either == 0,
        "premise_audit": audit,
    }
    return fails, result


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours-dir", required=True,
                    help="this project's per-case output, e.g. "
                         "experiments/MD_2022_a01_ours")
    ap.add_argument("--pogo-dir", required=True,
                    help="POGO's per-row output, one <case_id>.csv per case, "
                         "carrying timestamp, exceed and frozen (R29)")
    ap.add_argument("--exclude-cases", default="",
                    help="comma-separated case ids excluded by D1/D6")
    ap.add_argument("--trim-case", action="append",
                    help="CASE_ID=TIMESTAMP, repeatable; the ratified D1/D6 trim")
    ap.add_argument("--alpha", type=float, required=True,
                    help="recorded in the output; this tool does not use it")
    ap.add_argument("--output", help="write the JSON report here")
    args = ap.parse_args()

    excluded = set(x.strip() for x in args.exclude_cases.split(",") if x.strip())
    trims = parse_trim(args.trim_case)

    if not os.path.isdir(args.ours_dir):
        raise SystemExit("--ours-dir is not a directory: %s" % args.ours_dir)
    if not os.path.isdir(args.pogo_dir):
        raise SystemExit("--pogo-dir is not a directory: %s" % args.pogo_dir)

    our_paths = sorted((os.path.join(args.ours_dir, n)
                        for n in os.listdir(args.ours_dir)
                        if n.endswith(".csv") and case_id_of(n) not in excluded),
                       key=lambda p: case_id_of(p))
    if not our_paths:
        raise SystemExit("no case CSVs in %s after exclusions" % args.ours_dir)

    fails = []
    per_case = []
    for path in our_paths:
        cid = case_id_of(path)
        pogo_path = os.path.join(args.pogo_dir, cid + ".csv")
        if not os.path.exists(pogo_path):
            # Fail-closed: a case POGO did not hand back is a case where the
            # comparison is unchecked, which is not the same as a case where
            # it passed.
            fails.append("case %s: POGO handed back no rows (%s missing)"
                         % (cid, os.path.basename(pogo_path)))
            per_case.append({"case_id": cid, "status": "MISSING"})
            continue

        trim = trims.get(cid)
        our_ts, our_exc, our_fr, _, _ = read_rows(path, trim)
        pogo_ts, pogo_exc, pogo_fr, _, _ = read_rows(pogo_path, trim)

        case_fails, result = compare_case((our_ts, our_exc, our_fr),
                                          (pogo_ts, pogo_exc, pogo_fr))
        fails += ["case %s: %s" % (cid, f) for f in case_fails]
        entry = {"case_id": cid, "status": "OK" if not case_fails else "FAIL"}
        if result:
            entry.update(result)
        per_case.append(entry)

    checked = [c for c in per_case if c.get("status") == "OK"]
    nontrivial = [c for c in checked if not c.get("trivial")]
    identical_nontrivial = [c for c in nontrivial if c["identical"]]

    # INDEPENDENCE. Identity everywhere it could have differed is the copy.
    copied = bool(nontrivial) and len(identical_nontrivial) == len(nontrivial)
    if copied:
        fails.append(
            "POGO's frozen column is identical to ours in ALL %d non-trivial "
            "case(s), row for row. At this scale that is a copied flag, not "
            "agreement, and G6 would be circular (G3 contract section 3)"
            % len(nontrivial))

    total_rows = sum(c.get("n_rows_in_window", 0) for c in checked)
    total_agree = sum(c.get("rows_agreeing", 0) for c in checked)
    ours_frozen = sum(c.get("ours_frozen", 0) for c in checked)
    pogo_frozen = sum(c.get("pogo_frozen", 0) for c in checked)

    verdict = "PASS" if not fails else "FAIL"
    out = {
        "tool": "pogo-frozen-row-audit-v1.0",
        "contract": "docs/method/POGO_G3_STATE_CONTRACT.md section 3 + "
                    "section 6a (R29, 2026-08-22)",
        "alpha": args.alpha,
        "alarm_rule": "%d of last %d" % (ALARM_OF, ALARM_WINDOW),
        "verdict": verdict,
        "provenance_audited": True,
        "independence_established": bool(verdict == "PASS" and nontrivial),
        "independence_note":
            "independence is established only when at least one non-trivial "
            "case differs; with no non-trivial case there is nothing that "
            "could have differed and the check says nothing",
        "n_cases_checked": len(checked),
        "n_cases_nontrivial": len(nontrivial),
        "n_cases_identical_nontrivial": len(identical_nontrivial),
        "n_rows_in_window": total_rows,
        "rows_agreeing": total_agree,
        "agreement": round(total_agree / float(total_rows), 6) if total_rows else None,
        "ours_frozen_rows": ours_frozen,
        "pogo_frozen_rows": pogo_frozen,
        "per_case": per_case,
        "failures": fails,
        "claim_constraint": CLAIM_CONSTRAINT,
    }

    print("POGO frozen-row audit -- %d case(s) checked, %d row(s) in window"
          % (len(checked), total_rows))
    if total_rows:
        print("  agreement          %d/%d (%.4f)"
              % (total_agree, total_rows, total_agree / float(total_rows)))
        print("  frozen rows        ours %d, POGO %d" % (ours_frozen, pogo_frozen))
        print("  non-trivial cases  %d, of which identical %d"
              % (len(nontrivial), len(identical_nontrivial)))
    for f in fails[:20]:
        print("  - %s" % f)
    if len(fails) > 20:
        print("  ... and %d more" % (len(fails) - 20))
    print("\nVERDICT: %s   provenance audited: yes   independence: %s"
          % (verdict, "established" if out["independence_established"] else "NOT established"))
    print("\nCLAIM_CONSTRAINT (%s)" % CLAIM_CONSTRAINT["source"])
    for line in CLAIM_CONSTRAINT["forbidden"]:
        print("  MUST NOT: %s" % line)
    for line in CLAIM_CONSTRAINT["permitted"]:
        print("  MAY:      %s" % line)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print("\nwrote %s" % args.output)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
