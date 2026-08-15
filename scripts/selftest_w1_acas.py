#!/usr/bin/env python3
"""
Self-test for baseline_w1_acas.py.

A reimplementation of someone else's method is worth nothing unless it
demonstrably reproduces the behaviour the method claims. This checks the
three properties the paper asserts, on synthetic streams whose ground truth
is known, so the baseline can be trusted before it is compared against.

  T1  Calibration under a stationary null. The p-values should be close to
      uniform: P(beta <= a) ~ a. This is exactly what Eq 9 minimises.
  T2  Adaptation under distribution shift. When the score scale jumps
      mid-stream, a static split-conformal calibrator degrades badly while
      W1-ACAS should recover. This is the paper's central claim, and if our
      reimplementation cannot show it, the comparison is not usable.
  T3  Determinism. Two runs on identical input must agree exactly, since
      C5 requires it of anything feeding the pilot.
  T4  Resolution floor and warm-up. The floor is 1/(|w|+1) with the CURRENT
      weight mass, not the initial alpha_c: the constraint is |w| > n_c, so
      the learned weights may carry more mass than n_c and buy finer
      resolution. A p-value below alpha_c is therefore correct, not a bug --
      an earlier version of this test asserted otherwise and was wrong. What
      must hold is that the mass constraint is never violated and that the
      warm-up region reports nothing rather than guessing.
  T5  The rank selector equals the strict comparison the implementation
      substitutes for it, ties included -- the one place the code departs
      in form from Algorithm 1.

    python3 scripts/selftest_w1_acas.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import baseline_w1_acas as W  # noqa: E402


def static_split_conformal(scores, n_cal):
    """The comparison point: calibrate once on the first n_cal scores and
    never update. Its p-value for S is (#{cal > S} + 1) / (n_cal + 1)."""
    cal = sorted(scores[:n_cal])
    out = [None] * n_cal
    for s in scores[n_cal:]:
        above = sum(1 for c in cal if c > s)
        out.append((above + 1.0) / (n_cal + 1.0))
    return out


def calib_err(betas, lo=None, hi=None):
    values = [b for b in betas if b is not None]
    if lo is not None:
        values = values[lo:hi]
    return W.calibration_error(values) if values else None


def main():
    failures, checks = [], 0

    def check(name, condition, detail=""):
        nonlocal checks
        checks += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s %s" % (name, detail))
            failures.append(name)

    ALPHA_C = 0.01
    N_C = int(round(1 / ALPHA_C)) - 1

    # ---------------- T1 stationary null ----------------
    print("\nT1  stationary null -> p-values near uniform")
    rng = random.Random(11)
    scores = [rng.gauss(0.0, 1.0) for _ in range(4000)]
    betas, diag = W.run_stream(scores, ALPHA_C, 10, 0.001, 500)
    err = W.calibration_error(betas)
    check("T1 produced p-values", diag["n_scored"] > 3000, "got %d" % diag["n_scored"])
    check("T1 calibration error below 0.05", err is not None and err < 0.05,
          "got %s" % err)
    values = [b for b in betas if b is not None]
    for a in (0.01, 0.05, 0.10, 0.25, 0.50):
        rate = sum(1 for b in values if b <= a) / len(values)
        check("T1 P(beta<=%.2f) within 0.05 of %.2f" % (a, a), abs(rate - a) < 0.05,
              "got %.4f" % rate)

    # ---------------- T2 distribution shift ----------------
    print("\nT2  score scale jumps mid-stream -> adapts where static does not")
    rng = random.Random(23)
    n_half = 3000
    shifted = ([rng.gauss(0.0, 1.0) for _ in range(n_half)]
               + [rng.gauss(0.0, 4.0) for _ in range(n_half)])
    ad_betas, _ = W.run_stream(shifted, ALPHA_C, 10, 0.001, 500)
    st_betas = static_split_conformal(shifted, 500)

    # Judge only well after the shift, once both have seen the new regime.
    post = slice(n_half + 500, None)
    ad_post = [b for b in ad_betas[post] if b is not None]
    st_post = [b for b in st_betas[post] if b is not None]
    ad_err = W.calibration_error(ad_post)
    st_err = W.calibration_error(st_post)
    print("      post-shift calibration error: W1-ACAS %.4f | static %.4f"
          % (ad_err, st_err))
    check("T2 both calibrators produced post-shift p-values",
          len(ad_post) > 1000 and len(st_post) > 1000)
    check("T2 W1-ACAS beats static split conformal after the shift",
          ad_err < st_err, "adaptive %.4f vs static %.4f" % (ad_err, st_err))
    check("T2 W1-ACAS post-shift error still below 0.10", ad_err < 0.10,
          "got %.4f" % ad_err)

    # ---------------- T3 determinism ----------------
    print("\nT3  identical input -> identical output (C5 requirement)")
    a1, _ = W.run_stream(scores[:1500], ALPHA_C, 10, 0.001, 300)
    a2, _ = W.run_stream(scores[:1500], ALPHA_C, 10, 0.001, 300)
    check("T3 two runs bit-identical", a1 == a2)

    # ---------------- T4 resolution floor and warm-up ----------------
    print("\nT4  resolution floor and honest warm-up")
    check("T4 warm-up reports nothing rather than guessing",
          all(b is None for b in betas[:N_C]))
    smallest = min(values)
    # The real invariant: the projection keeps sum(w) >= n_c, so the floor is
    # 1/(mass+1) <= alpha_c. Values under alpha_c mean the weights learned to
    # carry more effective samples, which is the mechanism working.
    check("T4 weight mass never drops below n_c",
          diag["final_weight_mass"] >= N_C - 1e-9,
          "mass %.4f vs n_c %d" % (diag["final_weight_mass"], N_C))
    absolute_floor = 1.0 / (diag["max_past"] + 1.0)
    check("T4 no p-value below the buffer's absolute floor",
          smallest >= absolute_floor - 1e-12,
          "smallest %.6g vs floor %.6g" % (smallest, absolute_floor))
    check("T4 finer-than-alpha_c resolution came from extra mass, not a bug",
          (smallest >= ALPHA_C - 1e-12) or (diag["final_weight_mass"] > N_C),
          "smallest %.6g with mass %.4f" % (smallest, diag["final_weight_mass"]))
    check("T4 p-values stay within [0,1]", all(0.0 <= b <= 1.0 for b in values))

    # ---------------- T5 the one formal deviation ----------------
    print("\nT5  rank selector == strict comparison, ties included")
    rng = random.Random(37)
    mismatches = 0
    for _ in range(5000):
        n = rng.randint(3, 12)
        past = [round(rng.gauss(0, 1), 1) for _ in range(n)]   # coarse -> many ties
        test = round(rng.gauss(0, 1), 1)
        j = sum(1 for x in past if test < x)
        order = sorted(range(n), key=lambda i: past[i])
        rank = [0] * n
        for position, index in enumerate(order):
            rank[index] = position + 1
        via_rank = {k for k in range(n) if rank[k] >= n - j + 1}
        via_cmp = {k for k in range(n) if past[k] > test}
        if via_rank != via_cmp:
            mismatches += 1
    check("T5 equivalent over 5000 trials with ties", mismatches == 0,
          "%d mismatches" % mismatches)

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
