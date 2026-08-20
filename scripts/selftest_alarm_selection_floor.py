#!/usr/bin/env python3
"""
Self-test: the alarm-selection floor is the bound it claims to be.

WHY THIS EXISTS
---------------
`diagnose_alarm_selection_floor.py` reports a THEOREM, and a theorem stated by
a program is only as good as the program's indexing. Two ways it could be
wrong while still printing a believable number:

  1. Report the floor against the frozen set instead of its neighbourhood.
     There is no floor on the frozen set -- six exceedances then silence give
     18 frozen points holding one exceedance -- so the tool would print a
     "guaranteed" 1/3 next to an observed 0.056 and the inequality check would
     be the only thing to notice. T3 constructs exactly that sequence.

  2. Dilate by the wrong amount. Off by one in either direction changes
     |N(F)| and therefore the floor, silently, in a direction that makes the
     paper's number look better or worse. T1 hand-computes |N(F)| on a
     sequence small enough to check by eye.

Every check is reverse-validated: each one is confirmed to FAIL when the
behaviour it pins is removed, or it is decoration.

  T1  hand-computed fixture: |F|, |N(F)|, the floor and the observed rate all
      match values worked out by hand.
  T2  REVERSE of T1: dilating by w-1 instead of w changes |N(F)|, so T1's
      assertion really does depend on the window width.
  T3  the bound is on N(F), not on F: a burst-then-silence stream has a
      frozen-point rate far below k/w while its N(F) rate clears the floor.
      This is the claim the module docstring makes in prose.
  T4  premise audit fires in BOTH directions -- a frozen flag the rule does
      not justify, and a rule hit the run did not freeze on. A check that can
      only fail one way is not evidence (working rule 3).
  T5  a violated premise suppresses the floor and exits non-zero, rather than
      reporting a bound whose derivation does not hold.
  T6  vacuity is flagged: at an alpha above the floor the tool says the floor
      establishes nothing instead of quietly reporting it.
  T7  --exclude-cases and --trim-case really drop rows, and the dropped count
      is reported. REVERSE: the untrimmed run reports no drop. This is the
      case-93 defect that lived in a config comment for a day.
  T8  randomised: over many streams the inequality holds, and with a
      deliberately inflated coefficient it is violated. If the inequality
      could not fail, checking it would prove nothing.

    python3 scripts/selftest_alarm_selection_floor.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
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
TOOL = os.path.join(HERE, "diagnose_alarm_selection_floor.py")

K = 6
W = 18
START = datetime(2023, 1, 1, 0, 0, 0)


def alarm_states(exceeds, k=K, w=W):
    """The ratified rule, written independently of the tool under test."""
    states = []
    for t in range(len(exceeds)):
        if t < w - 1:
            states.append(False)
        else:
            states.append(sum(exceeds[t - w + 1:t + 1]) >= k)
    return states


def write_case(path, exceeds, frozen=None, n_warmup=0):
    """One per-case CSV in the shape the calibration layer writes.

    `n_warmup` leading rows carry an empty exceed, as a bin below
    min_bin_samples does. They must not shift the alarm indexing.
    """
    if frozen is None:
        frozen = alarm_states(exceeds)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["timestamp", "wind_speed", "regime_bin", "score",
                     "p_value", "exceed", "work_order_alarm", "frozen"])
        row = 0
        for _ in range(n_warmup):
            ts = (START + timedelta(minutes=10 * row)).strftime("%Y-%m-%d %H:%M:%S")
            wr.writerow([ts, 6.0, "bin2_4_8", 1.0, "", "", 0, 0])
            row += 1
        for e, fr in zip(exceeds, frozen):
            ts = (START + timedelta(minutes=10 * row)).strftime("%Y-%m-%d %H:%M:%S")
            wr.writerow([ts, 6.0, "bin2_4_8", 1.0, 0.5, e,
                         1 if fr else 0, 1 if fr else 0])
            row += 1


def write_metadata(path, case_ids, label="normal"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["case_id", "farm_id", "turbine_id", "label",
                     "start_timestamp", "end_timestamp", "n_records"])
        for cid in case_ids:
            wr.writerow([cid, "Wind Farm X", cid, label,
                         START.strftime("%Y-%m-%d %H:%M:%S"),
                         START.strftime("%Y-%m-%d %H:%M:%S"), 0])


def run(ours_dir, metadata, out_path, alpha=0.01, extra=None):
    cmd = [sys.executable, TOOL, "--ours-dir", ours_dir,
           "--case-metadata", metadata, "--alpha", str(alpha),
           "--output", out_path]
    cmd += extra or []
    proc = subprocess.run(cmd, capture_output=True, text=True)
    payload = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            payload = json.load(f)
    return proc, payload


def dilate(frozen, w):
    """Reference implementation of N(F), written directly from the definition."""
    covered = set()
    for t, fr in enumerate(frozen):
        if fr:
            covered.update(range(max(0, t - w + 1), t + 1))
    return covered


def main():
    failures = []
    checks = [0]

    def check(name, condition, detail=""):
        checks[0] += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            failures.append(name)
            print("  FAIL  %s   %s" % (name, detail))

    with tempfile.TemporaryDirectory() as root:

        # ---- T1 / T2 -------------------------------------------------------
        # A single freeze, hand-checkable. Six exceedances at positions
        # 12..17 make S_17 = 6, so index 17 is the first frozen point. The
        # freeze holds while those six stay inside the window, i.e. through
        # index 29 (when e_12 leaves). Nothing exceeds after 17.
        print("\nT1/T2  hand-computed fixture")
        exceeds = [0] * 60
        for i in range(12, 18):
            exceeds[i] = 1
        frozen = alarm_states(exceeds)
        d1 = os.path.join(root, "t1")
        os.makedirs(d1)
        write_case(os.path.join(d1, "0.csv"), exceeds, frozen)
        meta = os.path.join(root, "meta.csv")
        write_metadata(meta, ["0"])
        proc, rep = run(d1, meta, os.path.join(root, "t1.json"))

        expected_F = [t for t, f in enumerate(frozen) if f]
        expected_N = dilate(frozen, W)
        check("T1 the fixture freezes exactly indices 17..29",
              expected_F == list(range(17, 30)), "got %s" % expected_F)
        check("T1 tool's |F| matches",
              rep and rep["totals"]["n_frozen"] == len(expected_F),
              "got %s want %d" % (rep and rep["totals"]["n_frozen"],
                                  len(expected_F)))
        check("T1 tool's |N(F)| matches the definition, dilated by w=%d" % W,
              rep and rep["totals"]["n_neighbourhood"] == len(expected_N),
              "got %s want %d" % (rep and rep["totals"]["n_neighbourhood"],
                                  len(expected_N)))
        floor_hand = (K / W) * len(expected_F) / len(expected_N)
        check("T1 floor equals (k/w)|F|/|N(F)| computed by hand",
              rep and abs(rep["floor"]["floor_rate_on_neighbourhood"]
                          - floor_hand) < 1e-12,
              "got %s want %.6f" % (rep and rep["floor"]["floor_rate_on_neighbourhood"],
                                    floor_hand))
        check("T1 the inequality holds on the fixture",
              rep and rep["checks"]["inequality_holds"])
        # REVERSE: if the tool dilated by w-1 the neighbourhood would be
        # smaller, so T1's assertion is not satisfied by any window width.
        check("T2 REVERSE: dilating by w-1 gives a different |N(F)|",
              len(dilate(frozen, W - 1)) != len(expected_N),
              "both %d -- T1 would pass with the wrong width"
              % len(expected_N))

        # ---- T3 ------------------------------------------------------------
        # The same fixture is the counter-example the docstring cites: its
        # frozen-point rate is 1/13, far below k/w = 1/3.
        print("\nT3  the bound is on N(F), not on F")
        far_frozen = rep["observed"]["far_frozen"]
        check("T3 frozen-point rate is below k/w (so no floor exists there)",
              far_frozen < K / W, "got %.4f" % far_frozen)
        check("T3 but the N(F) rate clears the floor",
              rep["observed"]["rate_on_neighbourhood"]
              >= rep["floor"]["floor_rate_on_neighbourhood"] - 1e-12,
              "%.4f vs %.4f" % (rep["observed"]["rate_on_neighbourhood"],
                                rep["floor"]["floor_rate_on_neighbourhood"]))

        # ---- T4 / T5 -------------------------------------------------------
        # Premise audit, both directions.
        print("\nT4/T5  premise audit fires in both directions")
        d_extra = os.path.join(root, "t4a")
        os.makedirs(d_extra)
        bad = list(frozen)
        bad[45] = True                      # frozen where the rule says no
        write_case(os.path.join(d_extra, "0.csv"), exceeds, bad)
        proc_a, rep_a = run(d_extra, meta, os.path.join(root, "t4a.json"))
        check("T4 a frozen flag the rule does not justify is counted",
              rep_a and rep_a["premise"]["frozen_without_rule"] == 1,
              "got %s" % (rep_a and rep_a["premise"]["frozen_without_rule"]))

        d_miss = os.path.join(root, "t4b")
        os.makedirs(d_miss)
        bad2 = list(frozen)
        bad2[20] = False                    # rule says freeze, run did not
        write_case(os.path.join(d_miss, "0.csv"), exceeds, bad2)
        proc_b, rep_b = run(d_miss, meta, os.path.join(root, "t4b.json"))
        check("T4 a rule hit the run did not freeze on is counted",
              rep_b and rep_b["premise"]["rule_without_frozen"] == 1,
              "got %s" % (rep_b and rep_b["premise"]["rule_without_frozen"]))
        check("T4 REVERSE: the honest fixture reports zero in both directions",
              rep["premise"]["frozen_without_rule"] == 0
              and rep["premise"]["rule_without_frozen"] == 0,
              "got %s/%s" % (rep["premise"]["frozen_without_rule"],
                             rep["premise"]["rule_without_frozen"]))
        check("T5 a violated premise withdraws the floor",
              rep_a and rep_a["floor"]["applies"] is False)
        check("T5 and exits non-zero", proc_a.returncode != 0,
              "exit %d" % proc_a.returncode)
        check("T5 REVERSE: the honest fixture exits zero and applies the floor",
              proc.returncode == 0 and rep["floor"]["applies"] is True,
              "exit %d, applies %s" % (proc.returncode,
                                       rep["floor"]["applies"]))

        # ---- T6 ------------------------------------------------------------
        print("\nT6  vacuity is flagged, not hidden")
        _, rep_vac = run(d1, meta, os.path.join(root, "t6.json"), alpha=0.9)
        check("T6 a floor at or below alpha is marked vacuous",
              rep_vac and rep_vac["floor"]["vacuous_at_this_alpha"] is True)
        check("T6 and the floor is withdrawn",
              rep_vac and rep_vac["floor"]["applies"] is False)
        check("T6 REVERSE: at alpha=0.01 the same floor is not vacuous",
              rep["floor"]["vacuous_at_this_alpha"] is False)

        # ---- T7 ------------------------------------------------------------
        print("\nT7  exclusion and trim actually drop rows")
        d7 = os.path.join(root, "t7")
        os.makedirs(d7)
        write_case(os.path.join(d7, "0.csv"), exceeds, frozen)
        write_case(os.path.join(d7, "1.csv"), exceeds, frozen)
        write_case(os.path.join(d7, "2.csv"), exceeds, frozen)
        write_metadata(meta, ["0", "1", "2"])
        _, plain = run(d7, meta, os.path.join(root, "t7a.json"))
        _, cut = run(d7, meta, os.path.join(root, "t7b.json"),
                     extra=["--exclude-cases", "2",
                            # the ratified trims are quoted with a 'T'
                            # separator while the CSVs use a space; if the
                            # tool compared raw strings this would drop
                            # nothing and report nothing.
                            "--trim-case", "1=2023-01-01T05:00:00"])
        check("T7 excluding a case reduces the case count",
              plain["population"]["n_cases_used"] == 3
              and cut["population"]["n_cases_used"] == 2,
              "%s then %s" % (plain["population"]["n_cases_used"],
                              cut["population"]["n_cases_used"]))
        dropped = (cut["population"]["trimmed_cases"].get("1") or {}).get("n_rows_dropped")
        check("T7 the trim drops rows and reports how many",
              dropped == 30, "got %s (want 30: rows at/after 05:00 of 60)" % dropped)
        check("T7 REVERSE: the untrimmed run records no trim at all",
              not plain["population"]["trimmed_cases"],
              "got %s" % plain["population"]["trimmed_cases"])
        check("T7 REVERSE: the trim changed the totals",
              cut["totals"]["n_calibrated"] != 2 * plain["totals"]["n_calibrated"] / 3,
              "trim dropped nothing measurable")

        # ---- T7b: warm-up rows must not shift the indexing -----------------
        print("\nT7b  warm-up rows do not shift the alarm indexing")
        d7b = os.path.join(root, "t7b")
        os.makedirs(d7b)
        write_case(os.path.join(d7b, "0.csv"), exceeds, frozen, n_warmup=25)
        write_metadata(meta, ["0"])
        _, warm = run(d7b, meta, os.path.join(root, "t7c.json"))
        check("T7b premise still holds with 25 uncalibrated leading rows",
              warm["premise"]["holds"] is True)
        check("T7b |N(F)| is unchanged by the warm-up rows",
              warm["totals"]["n_neighbourhood"] == rep["totals"]["n_neighbourhood"],
              "%s vs %s" % (warm["totals"]["n_neighbourhood"],
                            rep["totals"]["n_neighbourhood"]))

        # ---- T8 ------------------------------------------------------------
        print("\nT8  randomised: the inequality holds, and can fail")
        rng = random.Random(20260820)
        violations = 0
        inflated_violations = 0
        n_streams = 200
        for _ in range(n_streams):
            p = rng.choice([0.02, 0.1, 0.25, 0.4])
            seq = [1 if rng.random() < p else 0 for _ in range(500)]
            fr = alarm_states(seq)
            F = sum(1 for f in fr if f)
            if F == 0:
                continue
            N = dilate(fr, W)
            got = sum(seq[i] for i in N)
            if got < (K / W) * F - 1e-9:
                violations += 1
            # An inflated coefficient is not implied by the rule. If nothing
            # ever violates it either, then "the inequality holds" is a
            # statement about arithmetic that no data could contradict, and
            # checking it would prove nothing about the indexing.
            if got < 1.0 * F - 1e-9:
                inflated_violations += 1
        check("T8 the k/w bound is never violated over %d streams" % n_streams,
              violations == 0, "%d violations" % violations)
        check("T8 REVERSE: an inflated coefficient IS violated",
              inflated_violations > 0,
              "0 violations -- the check cannot fail in either direction")

        # ---- T9 ------------------------------------------------------------
        # T8 exercises the mathematics with a reference implementation. It
        # would still pass if the tool's own neighbourhood were wrong, because
        # the tool never runs in T8. The tool walks maximal runs instead of
        # dilating point by point; those agree in principle, but "in
        # principle" is how the [FARM:] prefix bug got in. Multi-run streams
        # with runs close enough to overlap are where they would diverge.
        print("\nT9  the tool's own N(F) equals the point-by-point definition")
        d9 = os.path.join(root, "t9")
        os.makedirs(d9)
        rng9 = random.Random(97)
        want_total = 0
        ids = []
        for i in range(6):
            seq = [1 if rng9.random() < 0.22 else 0 for _ in range(800)]
            fr = alarm_states(seq)
            want_total += len(dilate(fr, W))
            write_case(os.path.join(d9, "%d.csv" % i), seq, fr)
            ids.append(str(i))
        write_metadata(meta, ids)
        _, rep9 = run(d9, meta, os.path.join(root, "t9.json"))
        n_runs = rep9["totals"]["n_frozen_runs"]
        check("T9 the fixture really has many runs (%d), not one" % n_runs,
              n_runs >= 10, "only %d runs -- overlap is untested" % n_runs)
        check("T9 tool |N(F)| equals the summed point-by-point dilation",
              rep9["totals"]["n_neighbourhood"] == want_total,
              "%s vs %s" % (rep9["totals"]["n_neighbourhood"], want_total))
        check("T9 REVERSE: |N(F)| is strictly larger than |F| here",
              rep9["totals"]["n_neighbourhood"] > rep9["totals"]["n_frozen"],
              "equal -- the dilation added nothing, so T9 would pass without it")

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
