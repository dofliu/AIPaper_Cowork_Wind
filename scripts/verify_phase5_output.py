#!/usr/bin/env python3
"""Acceptance check for a Phase 5 evaluation batch.

WHY THIS EXISTS
---------------
The Phase 5 batch produces 15 directories of JSON. Asking an operator to
eyeball them is asking them to miss things, and the things they would miss are
the ones this project has been burned by:

  * lead-time columns full of `null` because `event_info.csv` was never found.
    The run exits 0 and writes a complete-looking comparison table.
  * `trimmed_cases` empty because the case-93 trim did not apply. It lived in a
    config comment for a day doing nothing, silently, and case 93's overlap
    with case 33 went straight into the normal-side false-alarm figures.
  * false-alarm numbers that moved when nothing should have moved -- the only
    thing this batch adds is lead time, so a changed FAR means something else
    changed too.

So the acceptance criteria are checked by a program that fails loudly, not by a
checklist a tired person ticks at 2am. Everything here READS; nothing is
recomputed, so a pass means the evaluator's own output satisfies the protocol,
not that this file agrees with itself.

    python3 scripts/verify_phase5_output.py ./experiments/phase5_2026-08-21

Exit code: 0 if every check passes, 1 otherwise. A non-zero exit means the
batch is not ready to analyse -- report it rather than working around it.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_experiment as E  # noqa: E402

# Ratified dataset facts. Signed off 2026-08-15 (D1/D6 remediation) and
# independently reproduced three times since.
EXPECT_EXCLUDED = ["32", "56", "72", "87"]
EXPECT_TRIM_CASE = "93"
EXPECT_TRIM_DROPPED = 18
EXPECT_N_CASES = 91
EXPECT_N_NORMAL = 47

# Known false-alarm figures at alpha = 0.01, from the R24 recomputation of
# 2026-08-18 and reproduced by the selection-floor tool on 2026-08-20. This
# batch adds lead time and changes nothing else, so these must not move.
# Tolerance is loose enough for formatting, tight enough to catch a real shift.
KNOWN_A01 = {
    "mean_worst_bin_deviation_unfrozen": 0.0036,
    "frozen_point_fraction": 0.0494,
    "far_frozen_points": 0.6819,
}
KNOWN_TOL = 5e-4

METHODS_WITH_FREEZE = ("ours",)


def horizon_tag(h):
    return "unbounded" if h is None else ("h%g" % h)


def expected_dirs():
    out = []
    for tag, alpha in (("a01", 0.01), ("a05", 0.05), ("a001", 0.001)):
        for h in E.RATIFIED_HORIZON_SWEEP:
            out.append(("%s_%s" % (tag, horizon_tag(h)), alpha, h))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch_dir", help="the --output-root you passed to "
                                      "run_phase5_evaluation.py")
    args = ap.parse_args()

    failures = []
    checks = [0]

    def check(name, condition, detail=""):
        checks[0] += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            failures.append(name)
            print("  FAIL  %s   %s" % (name, detail))

    print("verifying %s\n" % os.path.abspath(args.batch_dir))

    # ---- 1. the batch is complete -------------------------------------
    print("1  the batch is complete")
    plan = expected_dirs()
    loaded = {}
    for tag, alpha, h in plan:
        d = os.path.join(args.batch_dir, tag)
        ev = os.path.join(d, "evaluation.json")
        cm = os.path.join(d, "comparison.md")
        if not os.path.isfile(ev):
            check("1 %s/evaluation.json exists" % tag, False, "missing")
            continue
        if not os.path.isfile(cm):
            check("1 %s/comparison.md exists" % tag, False, "missing")
        with open(ev, encoding="utf-8") as f:
            loaded[tag] = json.load(f)
    check("1 all %d runs present" % len(plan), len(loaded) == len(plan),
          "found %d of %d" % (len(loaded), len(plan)))
    if not loaded:
        print("\nnothing to check. Is the path right?")
        return 1

    # ---- 2. lead time actually got computed ---------------------------
    # This is the entire reason the batch has to run on a machine with the
    # archive. If it is null the batch is worthless, however complete it looks.
    print("\n2  lead time was computed (the whole point of this batch)")
    primary_tag = "a01_%s" % horizon_tag(E.RATIFIED_DETECTION_HORIZON_DAYS)
    prim = loaded.get(primary_tag)
    if prim is None:
        check("2 the primary run %s exists" % primary_tag, False)
    else:
        ours = prim["comparison"]["ours"]
        check("2 median_lead_days is not null",
              ours.get("median_lead_days") is not None,
              "null -- event_info.csv was not found; the whole batch is void")
        check("2 detection_rate is not null",
              ours.get("detection_rate") is not None)
        check("2 at least one anomaly case is evaluable",
              (ours.get("n_anomaly_cases_total") or 0) > 0,
              "0 anomaly cases -- event_id did not match any case id")
        check("2 median_lead_days_missed_as_zero is reported too",
              ours.get("median_lead_days_missed_as_zero") is not None,
              "the parameter-free median is what stops misses hiding")

    # ---- 3. the D1/D6 remediation applied -----------------------------
    print("\n3  D1/D6 applied to every run")
    for tag, d in sorted(loaded.items()):
        exc = d.get("excluded_cases")
        trim = (d.get("trimmed_cases") or {}).get(EXPECT_TRIM_CASE)
        ok_exc = exc == EXPECT_EXCLUDED
        ok_trim = trim is not None and trim.get("n_rows_dropped") == EXPECT_TRIM_DROPPED
        if not ok_exc:
            check("3 %s excludes %s" % (tag, EXPECT_EXCLUDED), False, "got %s" % exc)
        if not ok_trim:
            check("3 %s trims case 93 (%d rows)" % (tag, EXPECT_TRIM_DROPPED),
                  False, "got %s" % trim)
    check("3 every run excludes the four D1/D6 cases",
          all(d.get("excluded_cases") == EXPECT_EXCLUDED for d in loaded.values()))
    check("3 every run drops exactly %d rows from case 93" % EXPECT_TRIM_DROPPED,
          all((d.get("trimmed_cases") or {}).get(EXPECT_TRIM_CASE, {})
              .get("n_rows_dropped") == EXPECT_TRIM_DROPPED
              for d in loaded.values()),
          "an empty trimmed_cases means the trim silently did nothing")

    # ---- 4. denominators --------------------------------------------
    print("\n4  denominators (working rule 7: a statistic without its n is not one)")
    for tag, d in sorted(loaded.items()):
        pm = d.get("per_method", {}).get("ours", {})
        if pm.get("n_cases") != EXPECT_N_CASES:
            check("4 %s evaluates %d cases" % (tag, EXPECT_N_CASES), False,
                  "got %s" % pm.get("n_cases"))
        if pm.get("n_normal_cases_for_far") != EXPECT_N_NORMAL:
            check("4 %s uses %d normal cases for FAR" % (tag, EXPECT_N_NORMAL),
                  False, "got %s" % pm.get("n_normal_cases_for_far"))
    check("4 every run evaluates %d cases" % EXPECT_N_CASES,
          all(d["per_method"]["ours"].get("n_cases") == EXPECT_N_CASES
              for d in loaded.values()))
    check("4 every run computes FAR on %d normal cases" % EXPECT_N_NORMAL,
          all(d["per_method"]["ours"].get("n_normal_cases_for_far")
              == EXPECT_N_NORMAL for d in loaded.values()))

    # ---- 5. the three-number false-alarm protocol (R24) ---------------
    print("\n5  the three-number false-alarm protocol is in force")
    bad_recon = [t for t, d in loaded.items()
                 if not (d["per_method"]["ours"]["false_alarm_report"]
                         ["pooled_reconstruction"].get("exhaustive"))]
    check("5 pooled is exactly reconstructible in every run",
          not bad_recon, "not exhaustive in: %s" % ", ".join(sorted(bad_recon)))
    check("5 the protocol version is recorded",
          all(d.get("false_alarm_protocol") for d in loaded.values()))
    # A baseline has no freeze mechanism, so its frozen columns must read as
    # "structurally absent", never as a measured zero.
    for tag, d in sorted(loaded.items()):
        for name, block in d["per_method"].items():
            if name in METHODS_WITH_FREEZE:
                continue
            avail = block["false_alarm_report"].get("freeze_state_available")
            if avail:
                check("5 %s/%s has no freeze state" % (tag, name), False,
                      "reports freeze state but has no freeze mechanism")
    check("5 baselines report freeze state as absent, not as 0%",
          all(not d["per_method"][m]["false_alarm_report"]
              .get("freeze_state_available")
              for d in loaded.values()
              for m in d["per_method"] if m not in METHODS_WITH_FREEZE))
    check("5 the proposed method DOES report freeze state",
          all(d["per_method"]["ours"]["false_alarm_report"]
              .get("freeze_state_available") for d in loaded.values()),
          "without it the frozen fraction is missing and the first number "
          "becomes a self-serving definition")

    # ---- 6. the detection-horizon protocol (R27) ----------------------
    print("\n6  the detection-horizon protocol is in force")
    for tag, alpha, h in plan:
        d = loaded.get(tag)
        if d is None:
            continue
        p = d.get("detection_horizon_protocol") or {}
        if d.get("detection_horizon_days") != h:
            check("6 %s ran at H=%s" % (tag, horizon_tag(h)), False,
                  "got %s" % d.get("detection_horizon_days"))
        if not p.get("this_run_in_declared_sweep"):
            check("6 %s is inside the declared sweep" % tag, False)
    primaries = [t for t, d in loaded.items()
                 if (d.get("detection_horizon_protocol") or {})
                 .get("this_run_is_primary")]
    check("6 exactly %d runs are flagged primary (one per alpha)" % 3,
          len(primaries) == 3, "got %d: %s" % (len(primaries), sorted(primaries)))
    check("6 the unbounded runs are present and unbounded",
          all(loaded[t].get("detection_horizon_days") is None
              for t, _, h in plan if h is None and t in loaded),
          "the most permissive column is the hardest to survive; it must be run")

    # ---- 7. nothing that should be unchanged moved --------------------
    # This batch adds lead time. Everything else is a re-read of per-case CSVs
    # that are already in version control, so a moved false-alarm number means
    # something else changed and the comparison with earlier runs is broken.
    print("\n7  the false-alarm figures did NOT move (only lead time is new)")
    if primary_tag in loaded:
        far = loaded[primary_tag]["per_method"]["ours"]["false_alarm_report"]
        for key, want in sorted(KNOWN_A01.items()):
            got = far.get(key)
            ok = got is not None and abs(got - want) <= KNOWN_TOL
            check("7 %s is still %.4f" % (key, want), ok,
                  "got %s (expected %.4f +/- %g) -- something other than lead "
                  "time changed" % (got, want, KNOWN_TOL))

    # ---- 8. the rendered table carries the three columns --------------
    print("\n8  comparison.md carries the columns a reader needs")
    md_path = os.path.join(args.batch_dir, primary_tag, "comparison.md")
    if os.path.isfile(md_path):
        md = open(md_path, encoding="utf-8").read()
        check("8 the table header has `frozen %`", "frozen %" in md)
        check("8 the table header has `FAR frozen`", "FAR frozen" in md)
        check("8 the horizon and its standing are stated",
              "Detection horizon" in md and "ratified primary" in md,
              "a horizon shown without its standing is what R27 prevents")
    else:
        check("8 comparison.md exists for the primary run", False)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        print("\nThis batch is NOT ready to analyse. Report the failures above;")
        print("do not work around them -- every one of these is a defect that")
        print("produces plausible numbers rather than an error.")
        for name in failures:
            print("  - %s" % name)
        return 1
    print("\nBatch accepted. The %d primary runs (H = %g d) are the headline "
          "numbers;\nthe rest are the declared sweep and must be reported "
          "beside them." % (3, E.RATIFIED_DETECTION_HORIZON_DAYS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
