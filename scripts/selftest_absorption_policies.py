#!/usr/bin/env python3
"""
Self-test for the alarm-time absorption policies in
regime_conditional_calibration.py.

WHY A SEPARATE FILE
-------------------
The ratified behaviour is pinned by selftest_regime_conditional.py and must
stay pinned. This file tests the opt-in ablations that were added to answer a
design question the real data raised, and its first job is to prove the
ablations changed nothing about a default run.

THE DISCRIMINATING PAIR
-----------------------
The design problem has two failure modes pulling in opposite directions, and
a policy that passes only one of them is not a candidate. So the tests come
in a pair over the SAME calibrator, differing only in what happened to the
machine:

  A  PROGRESSIVE FAULT. Scores ramp and stay high because the turbine is
     degrading. The calibrator must NOT absorb this: absorbing it re-baselines
     onto the fault and the alarm dissolves. This is self-masking, and it is
     what Freeze-on-Alert exists to prevent.

  B  BENIGN LEVEL SHIFT. Scores step up and stay up on a healthy machine --
     an operating change, a season, a sensor recalibration. The calibrator
     MUST absorb this. Refusing to means the reference goes stale, every
     later point exceeds against it, and the alarm never clears. This is the
     lock-in measured on CARE v6 on 2026-08-16: 4.9% of points frozen, 0.68
     conditional false-alarm rate on them, pooled rate dragged from 0.0113 to
     0.0445.

The two reference policies fail on opposite sides, which is what makes the
pair evidence rather than decoration: `freeze` passes A and fails B, `none`
fails A and passes B. T_PAIR asserts exactly that, so if a future change made
one fixture toothless the suite would say so instead of quietly passing
everything.

Both fixtures are synthetic, with a constructed ground truth. They show which
policies are worth spending a real run on. They are NOT CARE v6 results and
nothing here should be quoted as one.

    python3 scripts/selftest_absorption_policies.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_conditional_calibration as R   # noqa: E402

ALPHA = 0.01
WINDOW = 1440
MIN_BIN = 500
N_ROWS = 26000

_failures = []
_checks = 0


def check(label, ok, detail=""):
    global _checks
    _checks += 1
    print("    %s %s%s" % ("PASS" if ok else "FAIL", label,
                           "" if ok else "  <- " + detail))
    if not ok:
        _failures.append(label)


def make_stream(rng, n=N_ROWS):
    """A healthy stream. Wind cycles through all four regimes so every bin
    reaches the minimum sample count; the score is regime-independent so any
    behaviour seen later is the absorption policy and not the binning."""
    scores, winds = [], []
    for i in range(n):
        phase = (i // 40) % 4
        w = (2.0, 6.0, 10.0, 14.0)[phase] + rng.gauss(0.0, 0.4)
        winds.append(max(0.0, w))
        scores.append(rng.gauss(5.0, 1.0))
    return scores, winds


def tail_alarm_rate(records, start):
    tail = records[start:]
    return sum(1 for r in tail if r["work_order_alarm"]) / float(len(tail))


def tail_exceed_rate(records, start):
    tail = [r for r in records[start:] if r["exceed"] is not None]
    if not tail:
        return None
    return sum(r["exceed"] for r in tail) / float(len(tail))


def main():
    print("=" * 68)
    print("Absorption policy self-test")
    print("=" * 68)

    # ---------------- T0 the default did not move ----------------
    print("\nT0  adding the ablations changed nothing about a default run")
    rng = random.Random(101)
    s0, w0 = make_stream(rng, 9000)
    base, base_diag = R.run_stream(s0, w0, ALPHA, WINDOW, MIN_BIN)
    explicit, _ = R.run_stream(s0, w0, ALPHA, WINDOW, MIN_BIN, absorption="freeze")
    thawed_old, _ = R.run_stream(s0, w0, ALPHA, WINDOW, MIN_BIN, freeze_on_alert=False)
    thawed_new, _ = R.run_stream(s0, w0, ALPHA, WINDOW, MIN_BIN, absorption="none")

    check("T0 default equals the ratified policy, record for record",
          base == explicit)
    check("T0 the old freeze_on_alert=False equals absorption='none'",
          thawed_old == thawed_new)
    check("T0 the default records itself as the ratified policy",
          base_diag["absorption_policy"] == R.RATIFIED_ABSORPTION,
          "got %r" % base_diag["absorption_policy"])

    bad = None
    try:
        R.run_stream(s0[:600], w0[:600], ALPHA, WINDOW, MIN_BIN, absorption="nonsense")
    except ValueError as exc:
        bad = str(exc)
    check("T0 an unknown policy is refused, not silently defaulted",
          bad is not None and "nonsense" in bad, "got %r" % bad)

    # ---------------- T1 the cap is the value it claims to be -------------
    print("\nT1  winsorising cap is the largest value that would not exceed")
    buf = [float(i) for i in range(1, 1001)]        # 1..1000
    cap = R.winsorising_cap(buf, ALPHA)
    # k = floor(0.01*1001 - 1) = 9, so the cap is the 11th largest = 990.
    check("T1 cap is the 11th largest element", cap == 990.0, "got %r" % cap)
    check("T1 a point AT the cap does not exceed",
          R.conformal_p_value(buf, cap) > ALPHA,
          "p=%r" % R.conformal_p_value(buf, cap))
    check("T1 the next value up DOES exceed",
          R.conformal_p_value(buf, 991.0) <= ALPHA,
          "p=%r" % R.conformal_p_value(buf, 991.0))
    check("T1 an empty buffer returns None rather than inventing a cap",
          R.winsorising_cap([], ALPHA) is None)
    check("T1 the cap tracks the buffer rather than being a constant",
          R.winsorising_cap([v + 100.0 for v in buf], ALPHA) == 1090.0,
          "got %r" % R.winsorising_cap([v + 100.0 for v in buf], ALPHA))

    # ---------------- Fixture A: progressive fault ----------------
    # Two ramp rates, because the answer turned out to depend on the rate and
    # a single rate would have hidden that. SLOW is 2000 steps to plateau,
    # about fourteen days at ten-minute sampling -- the rate a bearing or a
    # gearbox actually degrades at, and therefore the one that counts. FAST is
    # 200 steps, roughly a day and a half.
    print("\nA   progressive fault -- the alarm must survive it (self-masking guard)")
    rng = random.Random(3003)
    a_scores, a_winds = make_stream(rng)
    fault_start = 12000

    def with_fault(ramp_len):
        out = list(a_scores)
        for i in range(fault_start, len(out)):
            out[i] += 6.0 * min(1.0, (i - fault_start) / float(ramp_len))
        return out

    faulted_slow = with_fault(2000)
    faulted_fast = with_fault(200)
    a_tail = fault_start + 8000

    # ---------------- Fixture B: benign level shift ----------------
    # +3.0 sigma. Below about +2.5 the shift does not reach the 6-of-18 rule
    # at all, so no policy is ever tested; the fixture has to clear that bar
    # to discriminate, and this was measured rather than assumed.
    print("B   benign level shift on a healthy machine -- the alarm must clear")
    rng = random.Random(4004)
    b_scores, b_winds = make_stream(rng)
    shift_start = 12000
    shifted = list(b_scores)
    for i in range(shift_start, len(shifted)):
        shifted[i] += 3.0          # a step, not a ramp, and it never worsens
    b_tail = shift_start + 8000

    results = {}
    print("\n    %-14s %12s %12s %12s %10s"
          % ("policy", "A slow", "A fast", "B alarm", "B exceed"))
    for policy in R.ABSORPTION_POLICIES:
        rec_slow, _ = R.run_stream(faulted_slow, a_winds, ALPHA, WINDOW, MIN_BIN,
                                   absorption=policy)
        rec_fast, _ = R.run_stream(faulted_fast, a_winds, ALPHA, WINDOW, MIN_BIN,
                                   absorption=policy)
        rec_b, _ = R.run_stream(shifted, b_winds, ALPHA, WINDOW, MIN_BIN,
                                absorption=policy)
        results[policy] = {
            "a_slow": tail_alarm_rate(rec_slow, a_tail),
            "a_fast": tail_alarm_rate(rec_fast, a_tail),
            "b": tail_alarm_rate(rec_b, b_tail),
            "b_exceed": tail_exceed_rate(rec_b, b_tail),
        }
        r = results[policy]
        print("    %-14s %12.3f %12.3f %12.3f %10s"
              % (policy, r["a_slow"], r["a_fast"], r["b"],
                 "n/a" if r["b_exceed"] is None else "%.4f" % r["b_exceed"]))

    # A policy is a candidate only if it holds the fault alarm AND lets the
    # benign one go. Thresholds are deliberately loose -- this fixture ranks
    # candidates for a real run, it does not certify any of them.
    DETECTS = 0.90       # alarm coverage well after a fault plateaus
    RECOVERS = 0.10      # alarm coverage well after a benign shift settles

    print("\nT_PAIR  the two fixtures disagree, which is what makes them evidence")
    check("T_PAIR freeze holds the fault alarm",
          results["freeze"]["a_slow"] > DETECTS,
          "got %.3f" % results["freeze"]["a_slow"])
    check("T_PAIR freeze locks in on the benign shift (the measured defect)",
          results["freeze"]["b"] > 0.5, "got %.3f" % results["freeze"]["b"])
    check("T_PAIR none recovers from the benign shift",
          results["none"]["b"] < RECOVERS, "got %.3f" % results["none"]["b"])
    check("T_PAIR none loses the fault alarm to self-masking",
          results["none"]["a_slow"] < results["freeze"]["a_slow"] - 0.3,
          "freeze %.3f vs none %.3f"
          % (results["freeze"]["a_slow"], results["none"]["a_slow"]))

    print("\nT_CAND  judged on both fixtures at once -- the finding is that")
    print("        nothing here passes both, so none of these is the fix")
    for policy in R.ABSORPTION_POLICIES:
        r = results[policy]
        verdict = "CANDIDATE" if (r["a_slow"] > DETECTS and r["b"] < RECOVERS) else "no"
        print("        %-14s A_slow=%.3f B=%.3f  -> %s"
              % (policy, r["a_slow"], r["b"], verdict))

    survivors = [p for p in R.ABSORPTION_POLICIES
                 if results[p]["a_slow"] > DETECTS and results[p]["b"] < RECOVERS]
    check("T_CAND no absorption rule separates a slow fault from a benign shift",
          not survivors,
          "these now pass both, which would overturn the written conclusion: %s"
          % survivors)

    # Each of the four candidates fails for a reason that was predicted before
    # it was run. Pinning the reason, not just the failure, is what makes a
    # later change legible: if one of these starts passing, the argument in
    # the docstring is what has to be revisited.
    check("T_CAND bin_local locks in: the shift is not confined to one bin",
          results["bin_local"]["b"] > RECOVERS,
          "got %.3f" % results["bin_local"]["b"])
    check("T_CAND gated locks in: the points it admits are the low ones",
          results["gated"]["b"] > RECOVERS, "got %.3f" % results["gated"]["b"])
    check("T_CAND winsor_alpha locks in, as the fixed-point argument predicts",
          results["winsor_alpha"]["b"] > RECOVERS,
          "got %.3f -- if this now recovers the docstring is wrong"
          % results["winsor_alpha"]["b"])
    check("T_CAND winsor_max clears the benign shift",
          results["winsor_max"]["b"] < RECOVERS,
          "got %.3f" % results["winsor_max"]["b"])
    check("T_CAND but winsor_max self-masks on a SLOW fault: between alarms "
          "the raw ramp lifts the envelope it caps against",
          results["winsor_max"]["a_slow"] < RECOVERS,
          "got %.3f" % results["winsor_max"]["a_slow"])
    check("T_CAND winsor_max does survive a FAST fault, which locates the "
          "boundary rather than just failing it",
          results["winsor_max"]["a_fast"] > DETECTS,
          "got %.3f" % results["winsor_max"]["a_fast"])

    # ---------------- T2 determinism, as C5 requires ----------------
    print("\nT2  identical input -> identical output, for every policy")
    for policy in R.ABSORPTION_POLICIES:
        x, _ = R.run_stream(a_scores[:7000], a_winds[:7000], ALPHA, WINDOW,
                            MIN_BIN, absorption=policy)
        y, _ = R.run_stream(a_scores[:7000], a_winds[:7000], ALPHA, WINDOW,
                            MIN_BIN, absorption=policy)
        check("T2 %s is deterministic" % policy, x == y)

    print("\n%d checks, %d failed" % (_checks, len(_failures)))
    if _failures:
        for f in _failures:
            print("  FAILED: %s" % f)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
