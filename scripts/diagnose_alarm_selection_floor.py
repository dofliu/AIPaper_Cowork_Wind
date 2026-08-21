#!/usr/bin/env python3
"""How much of the frozen-period false-alarm rate is forced by arithmetic alone.

WHY THIS EXISTS
---------------
`docs/FREEZE_LOCKIN_FINDINGS.md` established, empirically, that the 0.6819
false-alarm rate measured on frozen points is a selection effect and not
staleness: it is already 0.589 inside the first 18 steps of a freeze, and it
barely moves when alpha moves 50x. Both are observations. A referee can accept
them and still ask the obvious next question:

    "Selection towards WHAT? How large a rate does the 6-of-18 rule actually
     force, and is 0.68 above or below that?"

Until now the project had no number to answer with. This tool computes one, and
it computes it as a THEOREM rather than a measurement, so the answer does not
depend on any model of the score stream, on the calibrator being correct, or on
CARE v6 in particular.

THE BOUND
---------
Work in the index space of CALIBRATED points, which is the space the alarm rule
lives in (`regime_conditional_calibration.py` appends to `exceed_history` only
when a bin has >= min_bin_samples). Let e_t in {0,1} be the exceedance at
calibrated point t, and

    S_t = sum_{j=0..w-1} e_{t-j}          (w = 18, the alarm window)

The ratified policy sets `frozen` at point t to the alarm state AFTER e_t has
entered the window, so

    F = { t : S_t >= k }                  (k = 6, the alarm's 6-of-18)

is an exact description of the frozen set, not an approximation. Then

    k*|F| <= sum_{t in F} S_t                        (every S_t >= k on F)
           = sum_i e_i * m_i                          (swap the order of summation)
           <= w * sum_{i in N(F)} e_i                 (m_i <= w, and m_i = 0 off N(F))

where m_i = #{ t in F : t-w+1 <= i <= t } and N(F) = union over t in F of the
window [t-w+1, t] -- the frozen points TOGETHER WITH the up-to-17 points that
each freeze looked at before it fired. Therefore

    sum_{i in N(F)} e_i  >=  (k/w) * |F|                                    (*)

and dividing by |N(F)| gives a floor on the exceedance rate over N(F). With
k/w = 1/3 this says: whatever the calibrator does, whatever the data are, the
neighbourhood the alarm rule selected must carry at least one exceedance per
three frozen points. Nothing about the score stream enters the derivation.

WHAT THE BOUND IS NOT
---------------------
It is NOT a floor on the frozen-point rate itself. There is no such floor: six
exceedances in a row followed by silence produce 18 frozen points containing a
single exceedance, a rate of 0.056. The 1/3 belongs to the WINDOW, and the
window is what N(F) restores. Reporting the bound against the frozen set would
be claiming more than the arithmetic gives.

It is also NOT a decomposition. "observed minus floor" is not "the staleness
part". A lower bound says the observed rate cannot be smaller; it says nothing
about how the surplus is composed. The tool prints the ratio and refuses to
label the residual.

WHAT IT CHECKS (both directions -- rule 3)
------------------------------------------
P1  Premise audit. The bound holds only if `frozen` really is `S_t >= k`. That
    is read off the source, and source can drift from what was actually run, so
    every frozen point is re-tested against the recomputed S_t and every
    unfrozen calibrated point is tested for S_t < k. A single violation
    invalidates the derivation, and the tool says so instead of printing a
    floor. This can fail in the direction "the run did not use 6-of-18" as
    easily as in the direction "the tool mis-indexed".

C1  The inequality itself. Observed exceedances on N(F) must be >= (k/w)*|F|.
    If this fails, the tool has a bug -- the arithmetic cannot fail. Non-zero
    exit.

C2  Vacuity. A floor at or below alpha establishes nothing, and a floor that
    silently sits below nominal while the prose says "forced by the rule" is
    exactly the kind of check that only ever passes. Reported as an explicit
    flag, not left for the reader to divide.

INPUTS are the per-case CSVs the ratified run already wrote. Nothing is re-run,
so the numbers are attributable to the run recorded in PROJECT_STATUS section 1.
"""

import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime


ALARM_OF = 6          # ratified 2026-08-11, parameter freeze protocol v1.0
ALARM_WINDOW = 18

# Claim firewall clause 7, ratified 2026-08-21. See docs/manuscript/README.md.
# 6-of-18 IS a run rule, and the SPC literature computes exact run-length
# properties for supplementary runs rules by Markov chain. The exact
# conditional exceedance rate may therefore already be published, in which
# case this floor is a loose special case of it. The full text has not been
# obtained, so we know neither that it exists nor that it does not -- and
# under that uncertainty the conservative side is to not claim.
#
# Note what is NOT forbidden: reporting the floor, deriving it, using it to
# argue that the frozen-period rate is selection rather than staleness. Only
# the novelty sentence is. Method, yes; contribution, no.
#
# This is the only TIME-LIMITED clause in the firewall. It is reviewed when
# the run rules full text arrives, not silently dropped.
CLAIM_CONSTRAINT = {
    "clause": "claim-firewall-7",
    "ratified": "2026-08-21",
    "status": "ACTIVE_PENDING_FULL_TEXT",
    "forbidden": (
        "any claim that this floor is new, first, previously unnoted, or a "
        "finding of this work. 6-of-18 is a run rule and exact run-length "
        "results for supplementary runs rules exist in the SPC literature "
        "(Markov chain); the exact conditional rate may already be published."
    ),
    "permitted": (
        "reporting and deriving the floor, and using it to establish that the "
        "frozen-period exceedance rate is a selection effect rather than "
        "staleness. Method yes, contribution no."
    ),
    "citation_obligation": (
        "Shewhart supplementary runs rules / conditional false alarm rate "
        "literature must be cited wherever 6-of-18 selection is discussed."
    ),
    "review_when": "run rules full text obtained (LITERATURE_SCAN_2026-08-21 F13)",
}


def load_labels(path):
    labels = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            labels[str(row["case_id"]).strip()] = (row.get("label") or "").strip()
    return labels


def canonical_ts(raw):
    """Make a timestamp comparable as a string.

    The CSVs write `2023-08-24 13:00:00`; the ratified trim is quoted as
    `2023-08-24T13:00:00`. Space sorts before 'T', so comparing the raw forms
    puts every row before the cut and the trim silently does nothing. Both
    sides go through here, and the rows actually dropped are counted, so "it
    did nothing" is visible rather than assumed.
    """
    return (raw or "").strip().replace("T", " ")


def parse_trim(specs):
    trims = {}
    for spec in specs or []:
        if "=" not in spec:
            raise SystemExit("bad --trim-case %r; expected CASE_ID=TIMESTAMP" % spec)
        case_id, ts = spec.split("=", 1)
        try:
            datetime.fromisoformat(ts.strip())
        except ValueError:
            raise SystemExit("bad timestamp in --trim-case %r" % spec)
        trims[case_id.strip()] = ts.strip()
    return trims


def read_calibrated_stream(path, trim_at=None):
    """Return (exceeds, frozen, n_rows, n_dropped) over CALIBRATED points only.

    A row is calibrated when `exceed` is non-empty. Warm-up rows carry no
    verdict and are not part of the alarm window, so including them would
    shift every index and silently break the premise audit.
    """
    exceeds, frozen = [], []
    n_rows = 0
    n_dropped = 0
    cut = canonical_ts(trim_at) if trim_at is not None else None
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if cut is not None and canonical_ts(row.get("timestamp")) >= cut:
                n_dropped += 1
                continue
            n_rows += 1
            raw = (row.get("exceed") or "").strip()
            if raw == "":
                continue
            exceeds.append(int(raw))
            frozen.append((row.get("frozen") or "0").strip() == "1")
    return exceeds, frozen, n_rows, n_dropped


def audit_premise(exceeds, frozen, k=ALARM_OF, w=ALARM_WINDOW):
    """Re-derive the alarm state and compare with what the run wrote.

    Returns counts of disagreements in each direction. Points before the window
    is full are skipped: the policy cannot raise an alarm there, and it also
    cannot be tested there.
    """
    frozen_without_rule = 0     # written frozen, but S_t < k
    rule_without_frozen = 0     # S_t >= k, but written unfrozen
    n_testable = 0
    running = 0
    for t, e in enumerate(exceeds):
        running += e
        if t >= w:
            running -= exceeds[t - w]
        if t < w - 1:
            continue
        n_testable += 1
        should = running >= k
        if frozen[t] and not should:
            frozen_without_rule += 1
        elif should and not frozen[t]:
            rule_without_frozen += 1
    return {"n_testable": n_testable,
            "frozen_without_rule": frozen_without_rule,
            "rule_without_frozen": rule_without_frozen}


def neighbourhood(frozen, w=ALARM_WINDOW):
    """Indices of N(F) = union over frozen t of the window [t-w+1, t].

    Returned as a sorted list. Built by walking maximal frozen runs, so the
    union is formed once rather than by marking w indices per frozen point.
    """
    covered = set()
    runs = []
    n = len(frozen)
    t = 0
    while t < n:
        if not frozen[t]:
            t += 1
            continue
        start = t
        while t < n and frozen[t]:
            t += 1
        end = t - 1                      # inclusive
        runs.append(end - start + 1)
        lo = max(0, start - w + 1)
        covered.update(range(lo, end + 1))
    return sorted(covered), runs


def analyse_case(path, trim_at=None, k=ALARM_OF, w=ALARM_WINDOW):
    exceeds, frozen, n_rows, n_dropped = read_calibrated_stream(path, trim_at)
    audit = audit_premise(exceeds, frozen, k, w)
    nbhd, runs = neighbourhood(frozen, w)
    n_frozen = sum(1 for f in frozen if f)
    return {
        "n_rows": n_rows,
        "n_rows_dropped_by_trim": n_dropped,
        "n_calibrated": len(exceeds),
        "n_frozen": n_frozen,
        "n_frozen_runs": len(runs),
        "longest_frozen_run": max(runs) if runs else 0,
        "n_exceed_frozen": sum(e for e, f in zip(exceeds, frozen) if f),
        "n_exceed_unfrozen": sum(e for e, f in zip(exceeds, frozen) if not f),
        "n_neighbourhood": len(nbhd),
        "n_exceed_neighbourhood": sum(exceeds[i] for i in nbhd),
        "audit": audit,
    }


def rate(num, den):
    return (num / den) if den else None


def aggregate(cases):
    total = {key: 0 for key in
             ("n_rows", "n_rows_dropped_by_trim", "n_calibrated", "n_frozen",
              "n_frozen_runs", "n_exceed_frozen", "n_exceed_unfrozen",
              "n_neighbourhood", "n_exceed_neighbourhood")}
    audit = {"n_testable": 0, "frozen_without_rule": 0, "rule_without_frozen": 0}
    longest = 0
    for c in cases.values():
        for key in total:
            total[key] += c[key]
        for key in audit:
            audit[key] += c["audit"][key]
        longest = max(longest, c["longest_frozen_run"])
    total["longest_frozen_run"] = longest
    total["audit"] = audit
    return total


def derive(total, alpha, k=ALARM_OF, w=ALARM_WINDOW):
    audit = total["audit"]
    premise_holds = (audit["frozen_without_rule"] == 0
                     and audit["rule_without_frozen"] == 0)

    coefficient = k / w
    min_exceed = coefficient * total["n_frozen"]
    floor_rate = rate(min_exceed, total["n_neighbourhood"])
    observed_nbhd = rate(total["n_exceed_neighbourhood"], total["n_neighbourhood"])
    far_frozen = rate(total["n_exceed_frozen"], total["n_frozen"])
    n_unfrozen = total["n_calibrated"] - total["n_frozen"]
    far_unfrozen = rate(total["n_exceed_unfrozen"], n_unfrozen)
    far_pooled = rate(total["n_exceed_frozen"] + total["n_exceed_unfrozen"],
                      total["n_calibrated"])

    inequality_holds = (total["n_exceed_neighbourhood"] >= min_exceed - 1e-9)
    vacuous = (floor_rate is not None and floor_rate <= alpha)

    return {
        "premise": {
            "holds": premise_holds,
            "rule": "%d of last %d, evaluated on calibrated points" % (k, w),
            **audit,
            "note": (
                "frozen state matches the recomputed 6-of-18 rule at every "
                "testable calibrated point, so F = {t : S_t >= k} is exact and "
                "the bound applies"
                if premise_holds else
                "frozen state does NOT match the recomputed rule; the bound "
                "is derived from F = {t : S_t >= k} and does not apply to this "
                "run. Report the disagreement, not a floor."),
        },
        "floor": {
            "coefficient_k_over_w": coefficient,
            "min_exceedances_in_neighbourhood": min_exceed,
            "floor_rate_on_neighbourhood": floor_rate,
            "floor_over_alpha": (floor_rate / alpha) if floor_rate else None,
            "vacuous_at_this_alpha": vacuous,
            "applies": premise_holds and not vacuous,
        },
        "observed": {
            "rate_on_neighbourhood": observed_nbhd,
            "observed_over_floor": (observed_nbhd / floor_rate)
                                   if (observed_nbhd and floor_rate) else None,
            "far_frozen": far_frozen,
            "far_unfrozen": far_unfrozen,
            "far_pooled": far_pooled,
            "frozen_point_fraction": rate(total["n_frozen"], total["n_calibrated"]),
        },
        "checks": {
            "premise_holds": premise_holds,
            "inequality_holds": inequality_holds,
            "floor_is_informative": not vacuous,
        },
    }


def fmt(x, spec="%.4f"):
    return "n/a" if x is None else (spec % x)


def report(derived, total, alpha):
    out = []
    out.append("alarm-selection floor, alpha = %g" % alpha)
    out.append("")
    p = derived["premise"]
    out.append("  premise (%s): %s" % (p["rule"], "OK" if p["holds"] else "VIOLATED"))
    out.append("    testable calibrated points   %d" % p["n_testable"])
    out.append("    frozen but rule says no      %d" % p["frozen_without_rule"])
    out.append("    rule says yes but not frozen %d" % p["rule_without_frozen"])
    out.append("")
    out.append("  counts")
    out.append("    calibrated points            %d" % total["n_calibrated"])
    out.append("    frozen points |F|            %d (%s of calibrated)"
               % (total["n_frozen"],
                  fmt(derived["observed"]["frozen_point_fraction"], "%.4f")))
    out.append("    frozen runs                  %d (longest %d)"
               % (total["n_frozen_runs"], total["longest_frozen_run"]))
    out.append("    neighbourhood |N(F)|         %d" % total["n_neighbourhood"])
    out.append("")
    f = derived["floor"]
    o = derived["observed"]
    out.append("  the bound")
    out.append("    forced exceedances >= (k/w)|F| = %s" %
               fmt(f["min_exceedances_in_neighbourhood"], "%.1f"))
    out.append("    floor rate on N(F)           %s  (%s x nominal alpha)"
               % (fmt(f["floor_rate_on_neighbourhood"]), fmt(f["floor_over_alpha"], "%.1f")))
    out.append("    observed rate on N(F)        %s  (%s x the floor)"
               % (fmt(o["rate_on_neighbourhood"]), fmt(o["observed_over_floor"], "%.2f")))
    out.append("")
    out.append("  for reference (three-number report, recomputed here)")
    out.append("    FAR frozen                   %s" % fmt(o["far_frozen"]))
    out.append("    FAR unfrozen                 %s" % fmt(o["far_unfrozen"]))
    out.append("    FAR pooled                   %s" % fmt(o["far_pooled"]))
    out.append("")
    if not f["applies"]:
        if not p["holds"]:
            out.append("  VERDICT: bound does not apply -- premise violated.")
        else:
            out.append("  VERDICT: floor is at or below alpha; it establishes nothing "
                       "at this alpha.")
    else:
        out.append("  VERDICT: the 6-of-18 rule alone forces a rate of at least %s "
                   "on the" % fmt(f["floor_rate_on_neighbourhood"]))
        out.append("  points it selected -- %s times nominal -- before any "
                   "staleness," % fmt(f["floor_over_alpha"], "%.0f"))
        out.append("  any miscalibration, or any property of this dataset is "
                   "invoked.")
    out.append("")
    out.append("  The floor is a lower bound on N(F), not on the frozen set, and not")
    out.append("  a decomposition: the surplus over the floor is NOT labelled here.")
    out.append("")
    out.append("  CLAIM FIREWALL CLAUSE 7 (ratified 2026-08-21, time-limited):")
    out.append("  6-of-18 is a run rule, and exact run-length results for")
    out.append("  supplementary runs rules exist in the SPC literature. This floor")
    out.append("  may already be a special case of a published exact result, so it")
    out.append("  must NOT be written as new, first, or a finding of this work.")
    out.append("  Reporting it, deriving it, and using it to argue selection over")
    out.append("  staleness all remain permitted. Method yes, contribution no.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours-dir", required=True,
                    help="directory of per-case CSVs from the calibration layer")
    ap.add_argument("--case-metadata", required=True,
                    help="g3_case_metadata.csv, for the case labels")
    ap.add_argument("--alpha", type=float, required=True,
                    help="nominal level of the run being read; used only to say "
                         "whether the floor is informative")
    ap.add_argument("--label", default="normal",
                    help="case label to include (default normal: the false-alarm "
                         "population). Pass 'all' to ignore labels.")
    ap.add_argument("--case-glob", default="*.csv")
    ap.add_argument("--exclude-cases", default="",
                    help="comma-separated case ids to drop (D1/D6: 32,56,72,87)")
    ap.add_argument("--trim-case", action="append",
                    help="CASE_ID=TIMESTAMP, repeatable (D1/D6: 93=2023-08-24T13:00:00)")
    ap.add_argument("--alarm-of", type=int, default=ALARM_OF)
    ap.add_argument("--alarm-window", type=int, default=ALARM_WINDOW)
    ap.add_argument("--output", required=True, help="path for the JSON report")
    args = ap.parse_args()

    if not 0 < args.alarm_of <= args.alarm_window:
        raise SystemExit("--alarm-of must be in (0, --alarm-window]")

    labels = load_labels(args.case_metadata)
    excluded = set(x.strip() for x in args.exclude_cases.split(",") if x.strip())
    trims = parse_trim(args.trim_case)

    cases = {}
    skipped = {"excluded": [], "wrong_label": [], "unknown_case": []}
    for path in sorted(glob.glob(os.path.join(args.ours_dir, args.case_glob))):
        case_id = os.path.splitext(os.path.basename(path))[0]
        if case_id in excluded:
            skipped["excluded"].append(case_id)
            continue
        if args.label != "all":
            if case_id not in labels:
                skipped["unknown_case"].append(case_id)
                continue
            if labels[case_id] != args.label:
                skipped["wrong_label"].append(case_id)
                continue
        cases[case_id] = analyse_case(path, trims.get(case_id),
                                      args.alarm_of, args.alarm_window)

    if not cases:
        raise SystemExit("no cases matched; nothing to report")

    total = aggregate(cases)
    derived = derive(total, args.alpha, args.alarm_of, args.alarm_window)

    trim_applied = {cid: {"cut_at": trims[cid],
                          "n_rows_dropped": cases[cid]["n_rows_dropped_by_trim"]}
                    for cid in trims if cid in cases}

    payload = {
        "tool": "alarm-selection-floor-v1.0",
        # Ratified 2026-08-21 as claim firewall clause 7. It rides in the
        # OUTPUT, not only in the docs, because the person who writes the
        # manuscript paragraph will be reading this JSON, not README.md --
        # and the constraint is invisible in the numbers themselves.
        "claim_constraint": CLAIM_CONSTRAINT,
        "generated_from": os.path.abspath(args.ours_dir),
        "alpha": args.alpha,
        "alarm_rule": "%d of last %d" % (args.alarm_of, args.alarm_window),
        "population": {
            "label": args.label,
            "n_cases_used": len(cases),
            "excluded_cases": sorted(excluded),
            "n_skipped_wrong_label": len(skipped["wrong_label"]),
            "n_skipped_unknown_case": len(skipped["unknown_case"]),
            "trimmed_cases": trim_applied,
        },
        "totals": total,
        **derived,
        "per_case": cases,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    print(report(derived, total, args.alpha))
    print("\nwrote %s" % args.output)

    if not derived["checks"]["inequality_holds"]:
        print("\nFAIL: observed exceedances on N(F) are below the algebraic "
              "floor. The inequality cannot fail; this is a bug in this tool.",
              file=sys.stderr)
        return 2
    if not derived["checks"]["premise_holds"]:
        print("\nFAIL: the run's frozen column does not match the %d-of-%d rule; "
              "no floor is reported." % (args.alarm_of, args.alarm_window),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
