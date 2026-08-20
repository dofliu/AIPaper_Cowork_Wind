#!/usr/bin/env python3
"""Is POGO's Theorem 4.1 bound non-vacuous at this project's scale?

WHY THIS EXISTS
---------------
R26 G1 established (2026-08-20, from the arXiv:2606.00419v4 full text) that
POGO's guarantee is score-agnostic: Theorem 4.1 assumes only S_t >= 0 and
S_t <= D t^q, never that S_t is a residual. So POGO CAN run on this project's
frozen Mahalanobis stream, and the next question is whether doing so is worth
the build: a guarantee that evaluates to something larger than 1 is a true
statement about |FAR - alpha| that forbids nothing, and running a baseline to
confirm a vacuous bound is a poor use of anyone's week.

This tool evaluates the published bound at the T, T_j, D and alpha this
project actually has. It measures nothing and runs no algorithm -- it is
arithmetic on someone else's theorem, checked in so the eventual R26 run has a
pre-registered number to land against rather than a number chosen afterwards.

THE BOUND (Theorem 4.1, verbatim)
---------------------------------
    U_T(k)      = ln(1 + (1-a) D (T+1)^(q+1) / (q+1))
                  + 0.5 ln(pi (T+1))
                  + ln(k)

    MisCov_T(c_j) <= (1/T_j) ( U_T(k) + sqrt(2 T_j a (1-a) U_T(k)) )

WHAT THIS IS NOT
----------------
It is NOT a prediction of how POGO will perform, and it must never be compared
against this project's MEASURED worst-bin deviation. A worst-case upper bound
and an empirical average are different objects; putting them in one table would
be a claim of the form "we beat POGO", which the R25 claim firewall forbids and
which the arithmetic does not support in either direction. The only legitimate
reading is the one in the name: a scale check.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import json
import math
import sys


def u_t(T, k, alpha, D, q):
    """U_T(k) from Theorem 4.1."""
    growth = (1.0 - alpha) * D * (T + 1.0) ** (q + 1.0) / (q + 1.0)
    return math.log(1.0 + growth) + 0.5 * math.log(math.pi * (T + 1.0)) + math.log(k)


def miscov_bound(T, T_j, k, alpha, D, q):
    """The Theorem 4.1 bound on MisCov_T(c_j)."""
    U = u_t(T, k, alpha, D, q)
    return (U + math.sqrt(2.0 * T_j * alpha * (1.0 - alpha) * U)) / T_j


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--T", type=float, required=True,
                    help="calibrated points in one stream. This project runs one "
                         "stream PER CASE (state does not carry across cases), so "
                         "T is per case, not the total.")
    ap.add_argument("--Tj", type=float, required=True,
                    help="soft count of the rarest group in that stream")
    ap.add_argument("--alpha", type=float, required=True)
    ap.add_argument("--D", type=float, required=True,
                    help="growth constant: max score when q=0")
    ap.add_argument("--q", type=float, default=0.0,
                    help="growth exponent (0 for a bounded score stream)")
    ap.add_argument("--k", type=int, action="append", required=True,
                    help="group count, repeatable (this project: 4 and 5)")
    ap.add_argument("--output", help="optional path for a JSON report")
    args = ap.parse_args()

    if args.T <= 0 or args.Tj <= 0 or args.D <= 0 or not 0 < args.alpha < 1:
        raise SystemExit("need T, Tj, D > 0 and alpha in (0,1)")
    if args.Tj > args.T:
        raise SystemExit("Tj cannot exceed T")

    rows = []
    print("POGO Theorem 4.1 bound at this project's scale")
    print("  T = %g   T_j = %g   alpha = %g   D = %g   q = %g"
          % (args.T, args.Tj, args.alpha, args.D, args.q))
    print()
    print("  %-4s %10s %12s %10s" % ("k", "U_T(k)", "MisCov bound", "vacuous?"))
    for k in args.k:
        U = u_t(args.T, k, args.alpha, args.D, args.q)
        b = miscov_bound(args.T, args.Tj, k, args.alpha, args.D, args.q)
        # A bound on |rate - (1-alpha)| only says something if it is tighter
        # than what holds trivially: the rate lies in [0,1], so the deviation
        # never exceeds max(alpha, 1-alpha) whatever the algorithm does.
        trivial = max(args.alpha, 1.0 - args.alpha)
        vacuous = b >= trivial
        rows.append({"k": k, "U_T": U, "miscov_bound": b,
                     "trivial_bound": trivial, "vacuous": vacuous})
        print("  %-4d %10.3f %12.5f %10s" % (k, U, b, "YES" if vacuous else "no"))

    print()
    if len(rows) > 1:
        a, b = rows[0], rows[-1]
        print("  k enters U_T only as ln(k), so k=%d vs k=%d changes the bound by"
              % (a["k"], b["k"]))
        print("  %.2f%% -- the group count is NOT a theory-driven choice here."
              % (100.0 * (b["miscov_bound"] / a["miscov_bound"] - 1.0)))
        print("  Which k to run is therefore an empirical question, which is why")
        print("  the ratified answer is to run both and pre-declare the primary.")
    print()
    print("  Reminder: this is a worst-case upper bound on POGO. It must not be")
    print("  placed beside this project's measured worst-bin deviation.")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"tool": "pogo-bound-scale-check-v1.0",
                       "source": "arXiv:2606.00419v4 Theorem 4.1",
                       "inputs": {"T": args.T, "Tj": args.Tj, "alpha": args.alpha,
                                  "D": args.D, "q": args.q},
                       "rows": rows}, f, indent=2, sort_keys=True)
        print("\nwrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
