# Results

> **Draft — not approved.** Written 2026-08-18 against the R24 three-number
> false-alarm protocol (ratified 2026-08-17). Two numbered items below are
> marked **[PENDING]** and depend on decisions that have not been taken; they
> are placeholders, not results. See `docs/manuscript/README.md` for the three
> writing boundaries this section is held to.

## 1. Experimental setting

All figures in this section come from the CARE v6 SCADA archive, scored by a
single frozen detector (Base Scorer 1, a Mahalanobis-distance model, version
`md2022-v1.2`). The calibration layers — ours and every baseline — are applied
post hoc to that one score stream, so any difference between rows of the tables
below is a difference between calibration strategies and nothing else. The
detector is never retrained, and no method sees the detector's internals.

After the leakage remediation described in the preprocessing section (four
cases excluded outright, one case trimmed at the timestamp where it overlaps
another case on the same turbine under the opposite label), the evaluation
runs on **91 cases: 47 normal and 44 anomaly**. False-alarm statistics are
computed on the 47 normal cases only; early-detection statistics on the 44
anomaly cases only. Both denominators are stated with every figure they
produce.

The nominal miscoverage level is α = 0.01, with α = 0.05 and α = 0.001 reported
as sensitivity settings. The rolling window is W = 1440 ten-minute points, and
every method is converted to point exceedances and then passed through the
same work-order rule — six exceedances in the last eighteen points — before any
metric is computed.

## 2. Conditional calibration

The primary metric is the **worst-bin deviation**: the largest absolute gap
between the realised false-alarm rate and α across the four operating-regime
bins. It is reported on unfrozen points, together with the fraction of points
the method froze and the false-alarm rate on those frozen points, following the
three-number protocol described in the evaluation section.

**Table 1. Worst-bin deviation at α = 0.01 (47 normal cases, 2,490,340
calibrated points).**

| Method | Worst-bin deviation (unfrozen) | Frozen points | FAR on frozen points | Pooled worst-bin deviation |
|---|---|---|---|---|
| **Operating-regime-conditional (ours)** | **0.0036** | 4.9 % | 0.682 | 0.0602 |
| W1-ACAS (re-implementation) | 0.0111 | — | — | 0.0111 |
| Adaptive conformal inference | 0.0165 | — | — | 0.0165 |
| DtACI | 0.0198 | — | — | 0.0198 |
| Static split conformal | 0.1295 | — | — | 0.1295 |

A dash denotes a method with no freeze mechanism: nothing was measured on
frozen points because no point was frozen, which is not the same as a measured
zero.

Two readings of this table are both correct and must be kept apart. On the
points where the proposed layer is calibrating, its worst regime bin is within
0.0036 of nominal — **3.1 times closer than the best baseline and 36 times
closer than the static reference**, which is the conditional-coverage claim of
this paper. On the 4.9 % of points where it has suspended calibration to hold
an open work order, the false-alarm rate is 0.682, and pooling the two
populations gives 0.0602. The pooled figure is recoverable from the three
reported numbers exactly (residual 7 × 10⁻¹⁸), and we report it so that the
cost is not hidden by the choice of protocol.

**Table 2. Per-bin false-alarm rate on unfrozen points, proposed method,
α = 0.01.**

| Operating regime | Points | FAR | Deviation from α |
|---|---|---|---|
| < 4 m s⁻¹ | 472,073 | 0.0107 | 0.0007 |
| 4–8 m s⁻¹ | 987,806 | 0.0116 | 0.0016 |
| 8–12 m s⁻¹ | 566,843 | 0.0113 | 0.0013 |
| ≥ 12 m s⁻¹ | 340,613 | 0.0114 | 0.0014 |

The deviation is of the same order in all four regimes, including the two
sparsest. This is the behaviour the method is designed to produce, and it is
what a marginal calibrator does not deliver: the static reference holds its
pooled rate near nominal while its worst regime bin is off by 0.1295.

Tables 1 and 2 aggregate differently and their headline figures are therefore
not the same number. Table 1 reports the **mean over the 47 normal cases of
each case's own worst-bin deviation** (0.0036); Table 2 pools every unfrozen
point across all 47 cases before taking the per-bin rate, and its worst bin is
0.0016. Both are recorded in the artefact
(`mean_worst_bin_deviation_unfrozen` and
`pooled_worst_bin_deviation_unfrozen`). The per-case mean is the one used
throughout this paper, because it does not let a few long cases dominate the
population; the point-pooled figure is given so that the per-bin denominators
are visible.

## 3. Sensitivity to α

**Table 3. All three nominal levels (47 normal cases).**

| α | Ours (unfrozen) | W1-ACAS | ACI | DtACI | Static | Frozen points | FAR frozen |
|---|---|---|---|---|---|---|---|
| 0.001 | 0.0017 | **0.0010** | 0.0026 | 0.0040 | 0.0635 | 0.5 % | 0.771 |
| 0.01 | **0.0036** | 0.0111 | 0.0165 | 0.0198 | 0.1295 | 4.9 % | 0.682 |
| 0.05 | **0.0144** | 0.0532 | 0.0716 | 0.0803 | 0.2379 | 23.4 % | 0.707 |

Two observations, in order of importance.

**The frozen fraction grows steeply with α, the frozen false-alarm rate does
not.** Between α = 0.001 and α = 0.05 the fraction of frozen points rises by a
factor of 47, while the false-alarm rate measured on those points stays in the
narrow band 0.68–0.77. A mechanism that degraded with the duration or the
prevalence of freezing would not behave this way. The explanation is a
selection effect: the work-order rule admits a point to the frozen population
only when at least six of the last eighteen points exceeded, so the frozen
population is *defined* by a locally high exceedance rate. Measuring an
exceedance rate on a subpopulation selected by its exceedance rate cannot
return α. Section 4 of the limitations reports the falsification experiments
that this explanation survived.

**At α = 0.05 the freeze absorbs 23.4 % of all points.** The conditional
calibration figure of 0.0144 is genuine, and so is that fraction; neither is
reportable without the other. We regard α = 0.05 as the setting at which the
freeze-on-alert policy, not the calibration layer, dominates the method's
behaviour.

At the strictest level, α = 0.001, the proposed method is second rather than
first, behind the W1-ACAS re-implementation at 0.0010. We note this rather than
omitting it: at that level the deviations of all four adaptive methods are
within a factor of four of each other and small in absolute terms, and the
separation the paper claims is not visible there.

## 4. Early detection and non-inferiority

The early-detection figures come from the 2026-08-16 evaluation run, which is
the only run in which event onset times were available; the calibration figures
in Tables 1–3 were recomputed under the R24 protocol on 2026-08-18 from the
same per-case outputs. **The two halves of the results therefore come from two
executions of the evaluator over one set of score streams**, and the artefacts
for both are retained.

**Table 4. Median lead time on the 44 anomaly cases, detection horizon unset.**

| α | Method | Detected | Median lead (days) | Lead lost vs static | Non-inferior (2-day margin) |
|---|---|---|---|---|---|
| 0.01 | Ours | 44/44 | 348.50 | 1.97 | yes |
| 0.01 | Static | 44/44 | 350.46 | 0.00 | — |
| 0.01 | DtACI | 44/44 | 346.49 | 3.98 | no |
| 0.01 | ACI | 44/44 | 344.70 | 5.76 | no |
| 0.01 | W1-ACAS | 44/44 | 340.57 | 9.89 | no |
| 0.05 | Ours | 44/44 | 355.44 | −1.58 | yes |
| 0.001 | Ours | 43/44 | 250.10 | 88.23 | no |
| 0.001 | Static | 43/44 | 338.33 | 0.00 | — |

At α = 0.01 the proposed method is the only adaptive method that meets the
pre-registered two-day non-inferiority margin against the static reference, and
at α = 0.05 it detects *earlier* than the reference. At α = 0.001 it does not:
it loses 88 days, and this is reported as a failure of the non-inferiority
constraint at that setting, not qualified away.

**These lead times must not be read as absolute early-warning performance.**
The detection horizon *H* is unset in this run, so lead time is unbounded below
and an alarm raised before the fault window opens is still counted as early
warning. The medians near 350 days are a direct consequence: they are close to
the full length of a case, which means they are dominated by the earliest alarm
in the record rather than by any detection of the fault. What the column
supports is the *relative* comparison under one identical rule; what it does
not support is a claim about how many days of warning an operator would
receive.

> **[PENDING — Phase 5 re-run]** The detection horizon is no longer open: R27
> ratified a primary of **14 days** with a declared sweep of 7 / 10 / 14 / 21 /
> unbounded (see `02_evaluation_protocol.md` Section 4). What remains is
> mechanical — this table must be regenerated from the CARE score streams at
> the primary, with the sweep reported beside it, and the absolute lead times
> in the abstract and conclusion taken from that run. The numbers above are the
> **unbounded** run and are labelled as such in every artefact. Note that the
> unbounded column is itself part of the declared sweep, so it is not discarded
> when the bounded runs arrive; it becomes the most permissive column.

> **[PENDING — Base Scorer 2]** Every figure in this section rests on one
> frozen detector. The evaluation contract requires the claim to hold on two
> independent detectors; the second is not yet implemented. Until it is, the
> results are single-detector results and the section must say so.

## 5. What is not claimed here

- No claim is made about the compatibility gate. Base Scorer 1 satisfied the
  compatibility checks as currently specified on all three wind farms, but the
  gate definitions are not ratified and the artefacts still record
  `gate_definitions_ratified: false`.
- No CARE-score or CARE-Reliability figure is reported, and no CARE
  adaptive-threshold baseline appears in any table. Those definitions are in a
  publication this work has not read in full; the baseline raises an exception
  rather than returning an approximation.
- The synthetic fixture results reported in the evaluation section establish
  that the metrics measure what their names claim. They are not results on
  CARE and are not cited as such.
