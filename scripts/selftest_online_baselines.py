#!/usr/bin/env python3
"""
Self-test for baselines_online_calibration.py.

Each baseline is checked against the behaviour its paper claims, so a
comparison against it means something. A baseline that quietly fails to
adapt would flatter our method, which is the failure mode worth guarding.

  T1  Stationary null. Every method's realised alarm rate should sit near
      the target alpha.
  T2  Distribution shift. ACI and DtACI must recover; static split
      conformal must not. If static did recover, the fixture would not be
      testing what it claims to.
  T3  DtACI's reason to exist: robustness to a badly chosen step size. A
      single ACI at a bad gamma should be beaten by DtACI holding that same
      bad gamma among its experts.
  T4  Determinism, as C5 will require.
  T5  The missing baseline stays missing: CARE's adaptive threshold must
      raise rather than silently approximate.

    python3 scripts/selftest_online_baselines.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import baselines_online_calibration as B  # noqa: E402


def alarm_rate(alarms):
    values = [a for a in alarms if a is not None]
    return (sum(values) / len(values)) if values else None


def rate_after(alarms, start):
    values = [a for a in alarms[start:] if a is not None]
    return (sum(values) / len(values)) if values else None


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

    ALPHA = 0.05          # a rate a 6000-point fixture can actually resolve
    N_CAL = 500
    WINDOW = 500

    # ---------------- T1 stationary ----------------
    print("\nT1  stationary null -> realised alarm rate near alpha")
    rng = random.Random(101)
    scores = [rng.gauss(0.0, 1.0) for _ in range(6000)]

    _, st_al, _ = B.static_split_conformal(scores, ALPHA, N_CAL)
    _, ac_al, ac_d = B.aci(scores, ALPHA, 0.005, N_CAL, window=WINDOW)
    _, dt_al, dt_d = B.dtaci(scores, ALPHA, [0.001, 0.005, 0.02, 0.1], N_CAL,
                             window=WINDOW)
    for name, alarms in (("static", st_al), ("ACI", ac_al), ("DtACI", dt_al)):
        rate = alarm_rate(alarms)
        print("      %-7s realised %.4f (target %.2f)" % (name, rate, ALPHA))
        check("T1 %s within 0.02 of alpha" % name, abs(rate - ALPHA) < 0.02,
              "got %.4f" % rate)

    # ---------------- T2 shift ----------------
    print("\nT2  scale jumps mid-stream -> adaptive recovers, static does not")
    rng = random.Random(202)
    half = 3000
    shifted = ([rng.gauss(0.0, 1.0) for _ in range(half)]
               + [rng.gauss(0.0, 4.0) for _ in range(half)])
    _, st_s, _ = B.static_split_conformal(shifted, ALPHA, N_CAL)
    _, ac_s, _ = B.aci(shifted, ALPHA, 0.005, N_CAL, window=WINDOW)
    _, dt_s, _ = B.dtaci(shifted, ALPHA, [0.001, 0.005, 0.02, 0.1], N_CAL,
                         window=WINDOW)

    settle = half + 1000
    st_rate = rate_after(st_s, settle)
    ac_rate = rate_after(ac_s, settle)
    dt_rate = rate_after(dt_s, settle)
    print("      post-shift rates: static %.4f | ACI %.4f | DtACI %.4f (target %.2f)"
          % (st_rate, ac_rate, dt_rate, ALPHA))
    check("T2 static is badly off after the shift", abs(st_rate - ALPHA) > 0.05,
          "static %.4f -- fixture may not be shifting enough" % st_rate)
    check("T2 ACI recovers", abs(ac_rate - ALPHA) < 0.03, "got %.4f" % ac_rate)
    check("T2 DtACI recovers", abs(dt_rate - ALPHA) < 0.03, "got %.4f" % dt_rate)
    check("T2 both adaptive methods beat static",
          abs(ac_rate - ALPHA) < abs(st_rate - ALPHA)
          and abs(dt_rate - ALPHA) < abs(st_rate - ALPHA))

    # ---------------- T3 DtACI's reason to exist ----------------
    print("\nT3  a badly chosen step size -> DtACI beats a single ACI holding it")
    BAD_GAMMA = 0.5      # wildly too large: alpha_t thrashes
    rng = random.Random(303)
    drifting = []
    for t in range(6000):
        scale = 1.0 + 3.0 * (t / 6000.0)          # slow continuous drift
        drifting.append(rng.gauss(0.0, scale))
    _, bad_al, _ = B.aci(drifting, ALPHA, BAD_GAMMA, N_CAL, window=WINDOW)
    _, mix_al, _ = B.dtaci(drifting, ALPHA, [BAD_GAMMA, 0.005, 0.001], N_CAL,
                           window=WINDOW)
    bad_rate = rate_after(bad_al, N_CAL + 500)
    mix_rate = rate_after(mix_al, N_CAL + 500)
    print("      ACI(gamma=%.2f) %.4f | DtACI holding it %.4f (target %.2f)"
          % (BAD_GAMMA, bad_rate, mix_rate, ALPHA))
    check("T3 DtACI is closer to target than the bad single ACI",
          abs(mix_rate - ALPHA) < abs(bad_rate - ALPHA),
          "DtACI %.4f vs ACI %.4f" % (mix_rate, bad_rate))

    # ---------------- T4 determinism ----------------
    print("\nT4  identical input -> identical output (C5 requirement)")
    a1 = B.aci(scores[:2000], ALPHA, 0.005, N_CAL, window=WINDOW)[1]
    a2 = B.aci(scores[:2000], ALPHA, 0.005, N_CAL, window=WINDOW)[1]
    d1 = B.dtaci(scores[:2000], ALPHA, [0.001, 0.005], N_CAL, window=WINDOW)[1]
    d2 = B.dtaci(scores[:2000], ALPHA, [0.001, 0.005], N_CAL, window=WINDOW)[1]
    check("T4 ACI deterministic", a1 == a2)
    check("T4 DtACI deterministic", d1 == d2)

    # ---------------- T5 the missing baseline stays missing ----------------
    print("\nT5  CARE's adaptive threshold refuses to be approximated")
    try:
        B.care_adaptive_threshold(scores, ALPHA)
        check("T5 raises rather than returning a guess", False,
              "it returned something")
    except NotImplementedError as exc:
        check("T5 raises NotImplementedError", True)
        check("T5 the reason names the missing definition",
              "CARE" in str(exc) and "definition" in str(exc))
    check("T5 recorded in machine-readable form",
          B.MISSING_BASELINES["care_adaptive_threshold"]["status"] == "NOT_IMPLEMENTED")

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
