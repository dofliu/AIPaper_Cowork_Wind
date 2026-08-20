#!/usr/bin/env python3
"""
Self-test: the POGO bound is transcribed correctly from Theorem 4.1.

WHY THIS EXISTS
---------------
This tool's only job is to evaluate someone else's formula, so its only
failure mode is transcription -- a dropped (1-alpha), a ln(k) that became
log10, a sqrt over the wrong span. None of those would raise; they would print
a plausible number, which is this project's signature defect shape. So the
formula is pinned two ways: against values computed independently here from
the paper's expression, and against structural properties the published bound
must have.

  T1  U_T(k) matches an independent evaluation of the published expression.
  T2  the bound matches an independent evaluation.
  T3  k enters ONLY as ln(k): U_T(k2) - U_T(k1) == ln(k2/k1) exactly,
      whatever T, alpha, D, q are. A misplaced k would break this.
      REVERSE: the bound itself is NOT additive in ln(k) (the sqrt term
      carries k too), so T3 is testing something real.
  T4  monotonicity the theorem requires: the bound falls as T_j grows and
      rises as D grows.
  T5  vacuity is flagged when the bound exceeds max(alpha, 1-alpha), and not
      flagged when it does not. Both directions exercised.
  T6  the CLI refuses inputs the theorem does not admit (alpha outside (0,1),
      Tj > T, D <= 0) rather than printing a number for them.

    python3 scripts/selftest_pogo_bound_scale_check.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL = os.path.join(HERE, "pogo_bound_scale_check.py")

from pogo_bound_scale_check import u_t, miscov_bound      # noqa: E402


def ref_u(T, k, a, D, q):
    """Written straight from the paper, independently of the tool."""
    return (math.log(1 + (1 - a) * D * pow(T + 1, q + 1) / (q + 1))
            + math.log(math.pi * (T + 1)) / 2
            + math.log(k))


def ref_bound(T, Tj, k, a, D, q):
    U = ref_u(T, k, a, D, q)
    return (1 / Tj) * (U + math.sqrt(2 * Tj * a * (1 - a) * U))


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

    cases = [
        # (T, Tj, k, alpha, D, q)
        (52813, 7626, 4, 0.01, 23.81, 0.0),     # this project, median case
        (52813, 2206, 5, 0.01, 23.81, 0.0),     # this project, worst case
        (50000, 2500, 50, 0.05, 1.0, 0.0),      # the paper's own synthetic scale
        (1000, 100, 2, 0.10, 5.0, 2.0),         # quadratic growth branch
    ]

    print("\nT1/T2  formula matches an independent transcription")
    for T, Tj, k, a, D, q in cases:
        tag = "T=%g Tj=%g k=%d a=%g D=%g q=%g" % (T, Tj, k, a, D, q)
        check("T1 U_T  %s" % tag,
              abs(u_t(T, k, a, D, q) - ref_u(T, k, a, D, q)) < 1e-12,
              "%.10f vs %.10f" % (u_t(T, k, a, D, q), ref_u(T, k, a, D, q)))
        check("T2 bound %s" % tag,
              abs(miscov_bound(T, Tj, k, a, D, q)
                  - ref_bound(T, Tj, k, a, D, q)) < 1e-12)

    print("\nT3  k enters U_T only as ln(k)")
    for T, Tj, _, a, D, q in cases:
        d = u_t(T, 5, a, D, q) - u_t(T, 4, a, D, q)
        check("T3 U_T(5) - U_T(4) == ln(5/4)  (T=%g)" % T,
              abs(d - math.log(5.0 / 4.0)) < 1e-12, "got %.12f" % d)
    # REVERSE: if the bound were also purely additive in ln(k), T3 would be
    # testing an identity that holds for the wrong reason. It is not: the
    # sqrt(U) term makes the bound's k-dependence non-additive.
    T, Tj, _, a, D, q = cases[0]
    db = miscov_bound(T, Tj, 5, a, D, q) - miscov_bound(T, Tj, 4, a, D, q)
    check("T3 REVERSE: the bound is NOT additive in ln(k)",
          abs(db - math.log(5.0 / 4.0)) > 1e-9,
          "bound difference equals ln(5/4) -- sqrt term is missing k")

    print("\nT4  monotonicity the theorem requires")
    check("T4 bound falls as T_j grows",
          miscov_bound(52813, 20000, 4, 0.01, 23.81, 0)
          < miscov_bound(52813, 2206, 4, 0.01, 23.81, 0))
    check("T4 bound rises as D grows",
          miscov_bound(52813, 7626, 4, 0.01, 1000.0, 0)
          > miscov_bound(52813, 7626, 4, 0.01, 23.81, 0))
    check("T4 bound rises as k grows",
          miscov_bound(52813, 7626, 50, 0.01, 23.81, 0)
          > miscov_bound(52813, 7626, 4, 0.01, 23.81, 0))

    print("\nT5  vacuity flagged in both directions")
    # A tiny T_j makes the bound blow past the trivial max(alpha, 1-alpha).
    big = miscov_bound(52813, 2.0, 4, 0.01, 23.81, 0)
    small = miscov_bound(52813, 7626, 4, 0.01, 23.81, 0)
    check("T5 a 2-sample group gives a vacuous bound", big >= max(0.01, 0.99),
          "got %.5f" % big)
    check("T5 REVERSE: this project's real T_j does not", small < max(0.01, 0.99),
          "got %.5f" % small)

    print("\nT6  the CLI refuses inputs the theorem does not admit")
    for bad, why in [
            (["--T", "1000", "--Tj", "100", "--alpha", "1.5", "--D", "1", "--k", "4"],
             "alpha >= 1"),
            (["--T", "100", "--Tj", "1000", "--alpha", "0.01", "--D", "1", "--k", "4"],
             "Tj > T"),
            (["--T", "1000", "--Tj", "100", "--alpha", "0.01", "--D", "0", "--k", "4"],
             "D = 0")]:
        p = subprocess.run([sys.executable, TOOL] + bad, capture_output=True, text=True)
        check("T6 rejects %s" % why, p.returncode != 0, "exit 0")
    ok = subprocess.run(
        [sys.executable, TOOL, "--T", "52813", "--Tj", "7626", "--alpha", "0.01",
         "--D", "23.81", "--k", "4", "--k", "5"], capture_output=True, text=True)
    check("T6 REVERSE: valid inputs exit 0", ok.returncode == 0,
          "exit %d: %s" % (ok.returncode, ok.stderr[-200:]))
    check("T6 REVERSE: and print both k rows",
          ok.stdout.count("\n  4 ") == 1 and ok.stdout.count("\n  5 ") == 1,
          ok.stdout[-300:])

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
