# Results

> **Draft — not approved.** Calibration figures follow the R24 three-number
> protocol (ratified 2026-08-17); lead-time figures follow the R27 horizon
> protocol (ratified 2026-08-20) and come from the Phase 5 evaluation of
> 2026-08-20 over the committed score streams. One **[PENDING]** item remains —
> Base Scorer 2 — and it is a scope limit, not a missing number: every figure
> here rests on a single frozen detector. See `docs/manuscript/README.md` for
> the writing boundaries this section is held to.

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

Lead time is reported at the ratified primary horizon *H* = 14 days together
with the declared sweep 7 / 10 / 14 / 21 days and unbounded (protocol
`detection-horizon-v1.0`, R27; see `02_evaluation_protocol.md` Section 4). All
figures in this section come from the Phase 5 evaluation of 2026-08-20 over the
committed per-case score streams, and reproduce the calibration figures of
Tables 1–3 to the digit — this run adds lead time and changes nothing else.
Artefacts are in `experiments/phase5_2026-08-20/`.

**Table 4. Median lead time at the primary horizon, *H* = 14 days, on the 44
anomaly cases.** `miss = 0` scores an undetected case as zero days of warning;
lead lost is against the static reference at the same α.

| α | Method | Detected | Median lead (d) | miss = 0 (d) | Lead lost vs static | Non-inferior (2 d) |
|---|---|---|---|---|---|---|
| 0.01 | **Ours** | **44/44** | **7.90** | **7.90** | **−2.19** | **yes** |
| 0.01 | Static | 34/44 | 5.71 | 0.11 | 0.00 | — |
| 0.01 | ACI | 39/44 | 6.72 | 5.52 | −1.00 | yes |
| 0.01 | DtACI | 40/44 | 4.95 | 4.35 | +0.76 | yes |
| 0.01 | W1-ACAS | 18/44 | −2.56 | 0.00 | +8.27 | no |
| 0.05 | **Ours** | **44/44** | **13.80** | **13.80** | **−3.34** | **yes** |
| 0.05 | Static | 43/44 | 10.46 | 10.26 | 0.00 | — |
| 0.001 | **Ours** | **19/44** | **−2.49** | **0.00** | **+6.60** | **no** |
| 0.001 | Static | 27/44 | 4.11 | 0.00 | 0.00 | — |
| 0.001 | ACI / DtACI / W1-ACAS | 0/44 | — | 0.00 | — | — |

At the main level α = 0.01 the proposed method **detects every anomaly case
(44/44)** and does so **2.19 days earlier** than the static reference, the only
reference that also detects all 44; it is non-inferior with room to spare. At
α = 0.05 it again detects all 44 and is 3.34 days earlier. These are the
headline numbers.

At α = 0.001 the proposed method **does not meet the non-inferiority margin**,
and we report that rather than qualifying it away. The cause is a detection gap,
not a lateness: the very tight level suppresses alarms across the board, and the
freeze then withholds calibration on cases the method does detect, so it catches
19 of 44 against the static reference's 27. This is a real cost of the method at
an extreme operating point and belongs in Limitations. Two facts frame it
without softening it: the same tightening removes the three adaptive baselines
entirely (ACI, DtACI and W1-ACAS all detect **0 of 44**), so the proposed method
remains second only to the non-adaptive static reference; and the paper's claim,
after the R25 repositioning, is not that the calibrator detects best but that
the reporting protocol is correct — a claim the α = 0.001 column supports, since
its false-alarm figures reconstruct exactly (Table 3).

**Table 5. Non-inferiority across the declared horizon sweep** (Ours vs static;
negative lead-lost means the proposed method is *earlier*). The verdict does not
depend on the horizon at α = 0.01 or 0.05 — it holds at every one, including the
unbounded case — which is the property R27 exists to display.

| α | H = 7 | H = 10 | H = 14 | H = 21 | unbounded |
|---|---|---|---|---|---|
| 0.01 | −2.33 ✓ | −1.19 ✓ | **−2.19 ✓** | −1.31 ✓ | +1.97 ✓ |
| 0.05 | −0.50 ✓ | −2.81 ✓ | **−3.34 ✓** | −1.50 ✓ | −1.58 ✓ |
| 0.001 | +3.56 ✗ | +4.55 ✗ | **+6.60 ✗** | +13.03 ✗ | +88.23 ✗ |

The unbounded column is retained deliberately and must not be read as
early-warning performance: with *H* unset, an alarm raised before the fault
window opens is still counted, so the α = 0.01 medians there run to 348 days —
close to a full case length, dominated by the earliest alarm in the record
rather than by detection of the fault. That the α = 0.01 and 0.05 verdicts
survive even this most permissive setting is the point; that the absolute
numbers there are meaningless is why the primary is 14 days. The α = 0.001 row
fails at every horizon, consistent with the detection gap above rather than with
any horizon artefact.

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
