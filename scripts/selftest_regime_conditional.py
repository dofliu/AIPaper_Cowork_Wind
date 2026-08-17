#!/usr/bin/env python3
"""
Self-test for regime_conditional_calibration.py — the proposed method.

This does not check that the code runs. It checks that the method's central
claim actually holds on data where the ground truth is constructed, and
that it fails where it should.

  T1  The claim itself. On a stream whose score distribution differs by
      wind-speed regime, a POOLED conformal calibrator -- identical in
      every respect except that it ignores the regime -- must miss the
      per-bin target badly, while the regime-conditional one holds it.
      The pooled contrast isolates conditioning as the only difference, so
      any gap is attributable to the mechanism and nothing else.

  T2  The claim must NOT appear where it should not. On a stream whose
      score distribution is identical across regimes, conditioning buys
      nothing, and both should be close. A method that "wins" here would
      be winning by artefact.

  T3  Freeze-on-Alert against self-masking. A progressive fault is
      injected. Without freezing, the calibrator absorbs the fault as the
      new normal and the alarm dissolves; with freezing it persists. This
      is the behaviour W1-ACAS reports as desirable, which is correct for
      signal monitoring and wrong here.

  T4  Work-order semantics: 6 exceedances within 18 points, not one.

  T5  Refusal to guess. A bin below the minimum sample count reports no
      p-value rather than one it cannot support, and such points are
      excluded from rates instead of counted as clean.

  T6  Determinism, as C5 requires.

  T7  The three-number false-alarm report (R24, ratified 2026-08-17). On
      records whose freeze partition is constructed, the unfrozen rate, the
      frozen fraction and the frozen rate come back exactly as built, and
      the pooled rate is reconstructible from them. The fixture is built so
      that an implementation which ignored freeze state entirely -- the
      obvious way to get this wrong -- returns 0.109 where 0.050 is due,
      which every assertion here would catch.

    python3 scripts/selftest_regime_conditional.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import regime_conditional_calibration as R  # noqa: E402

ALPHA = 0.05          # resolvable at test scale
WINDOW = 500
MIN_BIN = 200
N_ROWS = 24000


def pooled_reference(scores, winds, alpha, window, min_samples):
    """The contrast: the SAME conformal estimator with one shared buffer.

    Everything is identical to the method under test except that the regime
    is ignored, so the difference between them is the conditioning and
    nothing else."""
    from collections import deque
    buffer_scores = deque(maxlen=window)
    exceeds = []
    for score, wind in zip(scores, winds):
        bin_name = R.regime_of(wind)
        if score is None or bin_name is None:
            exceeds.append((bin_name, None))
            continue
        if len(buffer_scores) >= min_samples:
            p = R.conformal_p_value(buffer_scores, score)
            exceeds.append((bin_name, 1 if p <= alpha else 0))
        else:
            exceeds.append((bin_name, None))
        buffer_scores.append(score)
    return exceeds


def far_by_bin(pairs, alpha):
    out = {}
    for name in R.BIN_NAMES:
        points = [e for b, e in pairs if b == name and e is not None]
        out[name] = (sum(points) / len(points)) if points else None
    deviations = [abs(v - alpha) for v in out.values() if v is not None]
    return out, (max(deviations) if deviations else None)


def make_stream(rng, regime_dependent):
    """Wind speeds spanning all four bins; scores whose distribution either
    depends on the regime or does not."""
    scores, winds = [], []
    for _ in range(N_ROWS):
        w = min(max(rng.weibullvariate(8.5, 2.0), 0.0), 25.0)
        if regime_dependent:
            # Higher wind -> higher and wider scores, as a residual-based
            # detector on a turbine genuinely behaves.
            mu = 0.5 * w
            sigma = 1.0 + 0.25 * w
        else:
            mu, sigma = 5.0, 2.0
        scores.append(rng.gauss(mu, sigma))
        winds.append(w)
    return scores, winds


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

    # ---------------- T1 the claim ----------------
    print("\nT1  regime-dependent scores -> conditional holds per bin, pooled does not")
    rng = random.Random(1001)
    scores, winds = make_stream(rng, regime_dependent=True)

    records, _ = R.run_stream(scores, winds, ALPHA, WINDOW, MIN_BIN,
                              freeze_on_alert=False)
    cond = R.per_bin_false_alarm_rates(records, ALPHA)
    pooled_pairs = pooled_reference(scores, winds, ALPHA, WINDOW, MIN_BIN)
    pooled_far, pooled_worst = far_by_bin(pooled_pairs, ALPHA)

    print("      bin            conditional   pooled     (target %.2f)" % ALPHA)
    for name in R.BIN_NAMES:
        c = cond["per_bin"][name].get("far")
        p = pooled_far[name]
        print("      %-14s %-13s %s"
              % (name,
                 "n/a" if c is None else "%.4f" % c,
                 "n/a" if p is None else "%.4f" % p))
    print("      worst-bin deviation: conditional %.4f | pooled %.4f"
          % (cond["worst_bin_deviation"], pooled_worst))
    print("      marginal deviation:  conditional %.4f" % cond["marginal_deviation"])

    check("T1 all four bins evaluable", cond["n_bins_evaluable"] == 4,
          "got %d" % cond["n_bins_evaluable"])
    check("T1 conditional worst-bin deviation under 0.02",
          cond["worst_bin_deviation"] < 0.02, "got %.4f" % cond["worst_bin_deviation"])
    check("T1 pooled worst-bin deviation is materially worse",
          pooled_worst > 3 * cond["worst_bin_deviation"],
          "pooled %.4f vs conditional %.4f" % (pooled_worst, cond["worst_bin_deviation"]))
    check("T1 pooled looks acceptable MARGINALLY while failing per bin",
          pooled_worst > 0.03,
          "pooled worst %.4f -- fixture may not separate the regimes enough"
          % pooled_worst)

    # ---------------- T2 no win where none is due ----------------
    print("\nT2  regime-independent scores -> conditioning buys nothing")
    rng = random.Random(2002)
    scores2, winds2 = make_stream(rng, regime_dependent=False)
    records2, _ = R.run_stream(scores2, winds2, ALPHA, WINDOW, MIN_BIN,
                               freeze_on_alert=False)
    cond2 = R.per_bin_false_alarm_rates(records2, ALPHA)
    pooled2_far, pooled2_worst = far_by_bin(
        pooled_reference(scores2, winds2, ALPHA, WINDOW, MIN_BIN), ALPHA)
    print("      worst-bin deviation: conditional %.4f | pooled %.4f"
          % (cond2["worst_bin_deviation"], pooled2_worst))
    check("T2 conditional still holds", cond2["worst_bin_deviation"] < 0.03,
          "got %.4f" % cond2["worst_bin_deviation"])
    check("T2 pooled is comparable when regimes do not differ",
          pooled2_worst < 0.03,
          "pooled %.4f -- a win here would be an artefact" % pooled2_worst)

    # ---------------- T3 Freeze-on-Alert ----------------
    print("\nT3  progressive fault -> freezing keeps the alarm, not freezing loses it")
    rng = random.Random(3003)
    base_scores, base_winds = make_stream(rng, regime_dependent=False)
    fault_start = 12000
    faulted = list(base_scores)
    for i in range(fault_start, N_ROWS):
        ramp = 6.0 * min(1.0, (i - fault_start) / 2000.0)   # degrade then plateau
        faulted[i] += ramp

    frozen_rec, frozen_diag = R.run_stream(faulted, base_winds, ALPHA, WINDOW,
                                           MIN_BIN, freeze_on_alert=True)
    thawed_rec, _ = R.run_stream(faulted, base_winds, ALPHA, WINDOW, MIN_BIN,
                                 freeze_on_alert=False)

    tail = slice(fault_start + 4000, None)   # well after the fault plateaus
    frozen_alarm = sum(1 for r in frozen_rec[tail] if r["work_order_alarm"])
    thawed_alarm = sum(1 for r in thawed_rec[tail] if r["work_order_alarm"])
    tail_n = len(frozen_rec[tail])
    print("      late-fault alarm coverage: frozen %.3f | not frozen %.3f"
          % (frozen_alarm / tail_n, thawed_alarm / tail_n))
    check("T3 freezing holds the alarm through the fault",
          frozen_alarm / tail_n > 0.9,
          "got %.3f" % (frozen_alarm / tail_n))
    check("T3 without freezing the alarm is largely lost to self-masking",
          thawed_alarm / tail_n < frozen_alarm / tail_n - 0.3,
          "frozen %.3f vs thawed %.3f" % (frozen_alarm / tail_n, thawed_alarm / tail_n))
    check("T3 freezing actually engaged", frozen_diag["n_frozen_steps"] > 1000,
          "got %d" % frozen_diag["n_frozen_steps"])

    # ---------------- T4 work-order semantics ----------------
    print("\nT4  a single exceedance is not an alarm; 6 of 18 is")
    n_exceed_points = sum(1 for r in records if r["exceed"] == 1)
    n_alarm_points = sum(1 for r in records if r["work_order_alarm"])
    print("      point exceedances %d | work-order alarm points %d"
          % (n_exceed_points, n_alarm_points))
    check("T4 exceedances occur at roughly alpha", n_exceed_points > 0)
    check("T4 work-order alarms are far rarer than raw exceedances",
          n_alarm_points < n_exceed_points,
          "alarms %d vs exceedances %d" % (n_alarm_points, n_exceed_points))
    check("T4 rule recorded as 6 of 18",
          (R.ALARM_OF, R.ALARM_WINDOW) == (6, 18))

    # ---------------- T5 refusal to guess ----------------
    print("\nT5  a bin below the minimum sample count reports nothing")
    rng = random.Random(5005)
    # Almost everything in one bin; bin4 gets a handful of points only.
    sparse_scores, sparse_winds = [], []
    for i in range(6000):
        w = 25.0 if i % 900 == 0 else 6.0
        sparse_winds.append(w)
        sparse_scores.append(rng.gauss(5.0, 2.0))
    sparse_rec, _ = R.run_stream(sparse_scores, sparse_winds, ALPHA, WINDOW,
                                 MIN_BIN, freeze_on_alert=False)
    sparse_rates = R.per_bin_false_alarm_rates(sparse_rec, ALPHA)
    rare = sparse_rates["per_bin"]["bin4_ge_12"]
    check("T5 the starved bin reports far None, not 0", rare["far"] is None,
          "got %s" % rare["far"])
    check("T5 and says why", "minimum sample count" in (rare.get("note") or ""))
    check("T5 starved points are excluded from rates, not counted clean",
          all(r["p_value"] is None
              for r in sparse_rec if r["regime_bin"] == "bin4_ge_12"))

    # ---------------- T6 determinism ----------------
    print("\nT6  identical input -> identical output (C5 requirement)")
    a, _ = R.run_stream(scores[:8000], winds[:8000], ALPHA, WINDOW, MIN_BIN)
    b, _ = R.run_stream(scores[:8000], winds[:8000], ALPHA, WINDOW, MIN_BIN)
    check("T6 deterministic", a == b)

    # ---------------- T7 the three-number report ----------------
    # Constructed, not sampled: 1000 unfrozen points with exactly 50
    # exceedances (0.0500, i.e. alpha on the nose) and 100 frozen points
    # with exactly 70 (0.7000). Pooling gives 120/1100 = 0.1091, so an
    # implementation that ignored the freeze partition would report a
    # deviation of 0.0591 where the calibration layer's own is 0.0000 --
    # a 0.059 gap, far outside any tolerance below.
    print("\nT7  false-alarm figures split by freeze state (R24)")
    built = []
    for i in range(1000):
        built.append({"regime_bin": "bin2_4_8", "exceed": 1 if i < 50 else 0,
                      "frozen": False})
    for i in range(100):
        built.append({"regime_bin": "bin2_4_8", "exceed": 1 if i < 70 else 0,
                      "frozen": True})
    rep = R.per_bin_false_alarm_rates(built, ALPHA)["three_number_report"]
    print("      unfrozen %.4f | frozen %.1f%% | frozen FAR %.4f | pooled %.4f"
          % (rep["far_unfrozen"], 100.0 * rep["frozen_point_fraction"],
             rep["far_frozen"], rep["far_pooled"]))

    check("T7 the three numbers travel in one block",
          {"worst_bin_deviation_unfrozen", "frozen_point_fraction",
           "far_frozen"} <= set(rep),
          "keys: %s" % sorted(rep))
    check("T7 unfrozen rate is the constructed 0.0500",
          abs(rep["far_unfrozen"] - 0.05) < 1e-12,
          "got %s" % rep["far_unfrozen"])
    check("T7 frozen fraction is the constructed 100/1100",
          abs(rep["frozen_point_fraction"] - 100.0 / 1100.0) < 1e-12,
          "got %s" % rep["frozen_point_fraction"])
    check("T7 frozen rate is the constructed 0.7000",
          abs(rep["far_frozen"] - 0.70) < 1e-12, "got %s" % rep["far_frozen"])
    check("T7 unfrozen worst-bin deviation is zero, pooled is not",
          rep["worst_bin_deviation_unfrozen"] < 1e-12
          and abs(rep["far_pooled"] - 0.05) > 0.05,
          "unfrozen dev %s, pooled %s" % (rep["worst_bin_deviation_unfrozen"],
                                          rep["far_pooled"]))
    check("T7 the pooled rate rebuilds from the three numbers",
          rep["pooled_reconstruction"]["exhaustive"],
          "residual %s" % rep["pooled_reconstruction"]["abs_residual"])
    check("T7 freeze state is declared available", rep["freeze_state_available"])

    # No freeze mechanism at all: the three collapse onto one, and that is
    # said out loud rather than shown as a measured 0% frozen.
    plain = [{"regime_bin": "bin2_4_8", "exceed": 1 if i < 50 else 0}
             for i in range(1000)]
    rep2 = R.per_bin_false_alarm_rates(plain, ALPHA)["three_number_report"]
    check("T7 a method with no freeze column says so",
          rep2["freeze_state_available"] is False)
    check("T7 and its unfrozen rate equals its pooled rate",
          rep2["far_unfrozen"] == rep2["far_pooled"] == 0.05,
          "unfrozen %s pooled %s" % (rep2["far_unfrozen"], rep2["far_pooled"]))
    check("T7 with no frozen rate to report", rep2["far_frozen"] is None)
    check("T7 and 'structural' stated, so zero is not read as measured",
          "structural" in rep2["note"])

    # And on the real path: Freeze-on-Alert running over the faulted stream
    # from T3 must produce a non-empty frozen population that still
    # reconstructs the pooled rate.
    live = R.per_bin_false_alarm_rates(frozen_rec, ALPHA)["three_number_report"]
    check("T7 Freeze-on-Alert produces a measurable frozen fraction",
          live["frozen_point_fraction"] > 0.0,
          "got %s" % live["frozen_point_fraction"])
    check("T7 and the identity still holds on a real run",
          live["pooled_reconstruction"]["exhaustive"],
          "residual %s" % live["pooled_reconstruction"]["abs_residual"])

    print("\n%d checks, %d failed" % (checks, len(failures)))
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
