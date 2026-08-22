#!/usr/bin/env python3
"""
Self-test: the frozen-row audit catches a copied flag and a forged one.

WHY THIS EXISTS
---------------
This tool's job is to decide whether two frozen columns were produced
independently. Both ways it can fail are silent:

  * too lax -- it passes a copied column, and G6's headline result becomes a
    circular argument that reads as the strongest evidence in the paper;
  * too strict -- it fails genuinely independent columns that happen to agree,
    and the one measurement G6 exists to make gets thrown away as "suspicious".

So every rule is exercised in BOTH directions, and the distinction the tool
rests on -- agreement is the result, identity everywhere is the copy -- is
tested from both sides.

  T1   the reader agrees with the existing calibrated-stream reader on the
       same file. REVERSE: it must not silently include warm-up rows.
  T2   provenance: frozen that IS 6-of-18 over its own exceed passes; a single
       flipped row fails, in each of the two directions separately.
  T3   independence: identical in every non-trivial case fails; differing in
       one single row of one case passes.
  T4   quiet cases (neither side ever freezes) are identical by arithmetic and
       must NOT count as evidence of copying -- nor as evidence of
       independence.
  T5   alignment: length mismatch, duplicate timestamps and diverging order
       each fail, rather than being compared row-by-row anyway.
  T6   a case POGO did not hand back is a FAIL, not a skip.
  T7   the ratified trim actually drops rows (the 'T' vs space trap this
       project has been bitten by twice).
  T8   the reported agreement and Jaccard match hand-computed values.
  T9   the CLI: exit codes, JSON payload, and the claim constraint carrying
       both what may not and what may be written.
  T10  against real data: this project's own frozen column passes the
       provenance audit with zero violations in both directions, which is the
       control -- an audit that reported zero everywhere would pass a forgery
       too.

    python3 scripts/selftest_audit_pogo_frozen_rows.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL = os.path.join(HERE, "audit_pogo_frozen_rows.py")

from audit_pogo_frozen_rows import (                                # noqa: E402
    CLAIM_CONSTRAINT, compare_case, read_rows)
from diagnose_alarm_selection_floor import read_calibrated_stream    # noqa: E402

K, W = 6, 18


def ref_frozen(exceeds):
    """6-of-18, written independently of the tool and of the run under test."""
    out = []
    for t in range(len(exceeds)):
        if t < W - 1:
            out.append(False)
            continue
        out.append(sum(exceeds[t - W + 1:t + 1]) >= K)
    return out


def ts_at(i):
    return "2023-01-%02d %02d:%02d:00" % (1 + i // 1440, (i // 60) % 24, i % 60)


def write_case(path, exceeds, frozen, warmup=0, first=0):
    """One case CSV. `warmup` leading rows carry no verdict, as real ones do."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("timestamp,wind_speed,regime_bin,score,p_value,exceed,"
                 "work_order_alarm,frozen\n")
        for i in range(warmup):
            fh.write("%s,5.0,bin2_4_8,1.0,,,0,0\n" % ts_at(first + i))
        for i, (e, f) in enumerate(zip(exceeds, frozen)):
            fh.write("%s,5.0,bin2_4_8,1.0,0.5,%d,%d,%d\n"
                     % (ts_at(first + warmup + i), e, 1 if f else 0, 1 if f else 0))


def stream(exceeds, frozen):
    return ([ts_at(i) for i in range(len(exceeds))], list(exceeds), list(frozen))


def main():
    failures = []
    checks = [0]

    def check(name, cond, detail=""):
        checks[0] += 1
        if not cond:
            failures.append(name)
            print("  FAIL %s   %s" % (name, detail))
        else:
            print("  ok   %s" % name)

    # The fixture has to contain BOTH frozen and unfrozen testable points: a
    # stream dense enough to freeze everywhere would make half these tests
    # unconstructible, and a stream that never freezes would make the other
    # half vacuous. A quiet baseline (1-in-5, below the 6-of-18 threshold)
    # plus one burst gives both.
    base = [1 if (i % 5 == 0 or 40 <= i <= 70) else 0 for i in range(200)]
    base_frozen = ref_frozen(base)
    assert any(base_frozen), "fixture must contain frozen rows"
    assert any(not f for i, f in enumerate(base_frozen) if i >= W), \
        "fixture must contain unfrozen testable rows"

    with tempfile.TemporaryDirectory() as td:
        print("T1  the reader agrees with the existing calibrated-stream reader")
        p = os.path.join(td, "t1.csv")
        write_case(p, base, base_frozen, warmup=5)
        ts, exc, fr, n_rows, _ = read_rows(p)
        old_exc, old_fr, old_rows, _ = read_calibrated_stream(p)
        check("T1 exceed column matches", exc == old_exc, "%d vs %d" % (len(exc), len(old_exc)))
        check("T1 frozen column matches", fr == old_fr, "")
        check("T1 row totals match", n_rows == old_rows, "%d vs %d" % (n_rows, old_rows))
        check("T1 REVERSE: warm-up rows are excluded from the window",
              len(ts) == len(base) and n_rows == len(base) + 5,
              "window %d, rows %d" % (len(ts), n_rows))

        print("\nT2  provenance: frozen must BE 6-of-18 over its own exceed")
        fails, res = compare_case(stream(base, base_frozen),
                                  stream(base, base_frozen))
        check("T2 a faithful column passes the audit", not fails, "; ".join(fails))
        check("T2 and the audit reports testable points",
              res["premise_audit"]["n_testable"] == len(base) - W + 1,
              repr(res["premise_audit"]))

        forged = list(base_frozen)
        flip = next(i for i, f in enumerate(base_frozen) if f)
        forged[flip] = False                       # rule fired, flag says no
        fails, _ = compare_case(stream(base, base_frozen), stream(base, forged))
        check("T2 rule-without-frozen is caught",
              any("rule-without-frozen" in f for f in fails), "; ".join(fails))

        forged = list(base_frozen)
        flip = next(i for i, f in enumerate(base_frozen) if not f and i >= W)
        forged[flip] = True                        # flag says yes, rule did not
        fails, _ = compare_case(stream(base, base_frozen), stream(base, forged))
        check("T2 frozen-without-rule is caught",
              any("frozen-without-rule" in f for f in fails), "; ".join(fails))

        print("\nT3/T4  independence, via the CLI (the copy verdict is global)")

        def run(cases, extra=None):
            """cases: {case_id: (ours_exceed, pogo_exceed)}; frozen derived."""
            root = tempfile.mkdtemp(dir=td)
            od, pd_ = os.path.join(root, "ours"), os.path.join(root, "pogo")
            os.makedirs(od)
            os.makedirs(pd_)
            for cid, (oe, pe) in cases.items():
                write_case(os.path.join(od, "%s.csv" % cid), oe, ref_frozen(oe), warmup=3)
                write_case(os.path.join(pd_, "%s.csv" % cid), pe, ref_frozen(pe), warmup=3)
            out = os.path.join(root, "out.json")
            argv = [sys.executable, TOOL, "--ours-dir", od, "--pogo-dir", pd_,
                    "--alpha", "0.01", "--output", out] + (extra or [])
            proc = subprocess.run(argv, capture_output=True, text=True)
            payload = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else None
            return proc, payload, od, pd_

        # POGO handed back exactly our own frozen geometry, in every case.
        proc, payload, _, _ = run({"0": (base, base), "1": (base, base)})
        check("T3 identical in every non-trivial case exits non-zero",
              proc.returncode == 1, "exit %d" % proc.returncode)
        check("T3 and names it a copy",
              any("copied flag" in f for f in payload["failures"]), repr(payload["failures"]))

        # POGO's own stream: the same quiet baseline, a burst ending four
        # steps earlier. The frozen columns then agree on 98% of rows and
        # differ on a handful -- which is exactly the shape a genuine
        # independent run is expected to produce, and must pass.
        other = [1 if (i % 5 == 0 or 40 <= i <= 66) else 0 for i in range(200)]
        proc, payload, _, _ = run({"0": (base, base), "1": (base, other)})
        check("T3 REVERSE: differing anywhere passes", proc.returncode == 0,
              proc.stdout[-300:] + proc.stderr[-200:])
        check("T3 REVERSE: independence is established",
              payload["independence_established"] is True, repr(payload))
        check("T3 REVERSE: and high agreement is still reported, not punished",
              payload["agreement"] > 0.9, repr(payload["agreement"]))

        quiet = [0] * 200
        proc, payload, _, _ = run({"0": (quiet, quiet)})
        check("T4 two never-freezing cases are not a copy verdict",
              proc.returncode == 0, proc.stdout[-300:])
        check("T4 and independence is NOT claimed from them",
              payload["independence_established"] is False
              and payload["n_cases_nontrivial"] == 0, repr(payload))

        print("\nT5  alignment failures are refused, not compared anyway")
        ours = stream(base, base_frozen)
        short = ([ts_at(i) for i in range(100)], base[:100], base_frozen[:100])
        fails, res = compare_case(ours, short)
        check("T5 length mismatch fails",
              any("window length differs" in f for f in fails), "; ".join(fails))
        check("T5 and no comparison is reported for it", res is None, repr(res))

        dupe = ([ts_at(0)] * len(base), list(base), list(base_frozen))
        fails, _ = compare_case(ours, dupe)
        check("T5 duplicate timestamps fail",
              any("duplicate timestamps" in f for f in fails), "; ".join(fails))

        shifted = ([ts_at(i + 1) for i in range(len(base))], list(base), list(base_frozen))
        fails, _ = compare_case(ours, shifted)
        check("T5 diverging order fails",
              any("timestamps diverge" in f for f in fails), "; ".join(fails))

        print("\nT6  a case POGO did not hand back")
        proc, payload, od, pd_ = run({"0": (base, base), "1": (base, other)})
        os.remove(os.path.join(pd_, "1.csv"))
        out = os.path.join(td, "missing.json")
        proc = subprocess.run([sys.executable, TOOL, "--ours-dir", od,
                               "--pogo-dir", pd_, "--alpha", "0.01",
                               "--output", out], capture_output=True, text=True)
        payload = json.load(open(out, encoding="utf-8"))
        check("T6 missing case is a FAIL", proc.returncode == 1,
              "exit %d" % proc.returncode)
        check("T6 and is named, not silently skipped",
              any("handed back no rows" in f for f in payload["failures"]),
              repr(payload["failures"]))

        print("\nT7  the ratified trim really drops rows")
        p = os.path.join(td, "t7.csv")
        write_case(p, base, base_frozen)
        _, _, _, _, dropped_none = read_rows(p)
        cut = ts_at(150).replace(" ", "T")          # quoted with 'T', as ratified
        ts_trim, _, _, _, dropped = read_rows(p, cut)
        check("T7 rows at or after the cut are dropped", dropped == 50,
              "dropped %d" % dropped)
        check("T7 REVERSE: without a cut nothing is dropped", dropped_none == 0,
              "dropped %d" % dropped_none)
        check("T7 and the window shortens accordingly", len(ts_trim) == 150,
              "%d rows" % len(ts_trim))

        print("\nT8  the reported numbers are the hand-computed ones")
        a = [True, True, False, False]
        b = [True, False, True, False]
        exc = [1, 1, 0, 0]
        fails, res = compare_case((["t%d" % i for i in range(4)], exc, a),
                                  (["t%d" % i for i in range(4)], exc, b))
        check("T8 agreement is 2/4", res["rows_agreeing"] == 2 and res["agreement"] == 0.5,
              repr(res))
        check("T8 jaccard is 1/3", res["jaccard"] == round(1 / 3.0, 6), repr(res["jaccard"]))
        check("T8 neither is trivial nor identical",
              res["trivial"] is False and res["identical"] is False, repr(res))
        check("T8 REVERSE: with only 4 rows nothing is testable, so the "
              "premise audit stays silent rather than inventing a verdict",
              res["premise_audit"]["n_testable"] == 0 and not fails,
              repr(res["premise_audit"]))

        print("\nT9  the CLI payload")
        proc, payload, _, _ = run({"0": (base, other)})
        check("T9 exits 0", proc.returncode == 0, proc.stdout[-200:])
        check("T9 records the alarm rule it audited against",
              payload["alarm_rule"] == "6 of last 18", repr(payload.get("alarm_rule")))
        check("T9 records that provenance was audited",
              payload["provenance_audited"] is True, repr(payload))
        check("T9 claim constraint rides along in the JSON",
              payload["claim_constraint"]["forbidden"]
              and payload["claim_constraint"]["permitted"], "")
        check("T9 and is printed to stdout",
              "CLAIM_CONSTRAINT" in proc.stdout and "MUST NOT" in proc.stdout,
              proc.stdout[-200:])
        check("T9 REVERSE: the constraint says what MAY be written",
              len(CLAIM_CONSTRAINT["permitted"]) >= 3, repr(CLAIM_CONSTRAINT))
        check("T9 REVERSE: including the agreement measurement itself",
              any("agreement" in s for s in CLAIM_CONSTRAINT["permitted"]),
              repr(CLAIM_CONSTRAINT["permitted"]))

    print("\nT10  control: this project's own frozen column, on real data")
    real = os.path.join(os.path.dirname(HERE), "experiments",
                        "MD_2022_a01_ours", "0.csv")
    if os.path.exists(real):
        ts, exc, fr, _, _ = read_rows(real)
        fails, res = compare_case((ts, exc, fr), (ts, exc, fr))
        check("T10 real case 0 has a non-empty window", len(ts) > 10000,
              "%d rows" % len(ts))
        check("T10 our own frozen passes the provenance audit, both directions",
              res["premise_audit"]["frozen_without_rule"] == 0
              and res["premise_audit"]["rule_without_frozen"] == 0,
              repr(res["premise_audit"]))
        check("T10 REVERSE: the audit is not vacuous -- the case has frozen rows",
              res["ours_frozen"] > 0, "%d frozen rows" % res["ours_frozen"])
    else:
        check("T10 real case present", False, "missing %s" % real)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
