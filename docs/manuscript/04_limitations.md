# Limitations

> **Draft — not approved.** Written 2026-08-18. Every limitation below is
> backed by a measurement in this repository, not by anticipation of what a
> reviewer might ask. Where a limitation is still open, the open decision is
> named rather than smoothed over.

## 1. The freeze is a real cost, and it grows with α

The proposed layer suspends its own calibration updates while a work order it
raised is still open. This protects detection — without it, a slow degradation
is absorbed into the reference distribution and the method masks the fault it
is meant to find — but it means that a fraction of the operating record is not
calibrated at all.

That fraction is not small and it is not constant:

| α | Fraction of points frozen | FAR on frozen points |
|---|---|---|
| 0.001 | 0.5 % | 0.771 |
| 0.01 | 4.9 % | 0.682 |
| 0.05 | 23.4 % | 0.707 |

At the paper's primary setting the method leaves 4.9 % of points uncalibrated;
at α = 0.05 it leaves nearly a quarter. **We do not regard α = 0.05 as a
setting at which this paper's conditional-coverage claim is meaningful**, and
we report it as a sensitivity boundary rather than as a supported operating
point.

## 2. The lock-in is structural, not a tuning failure

The false-alarm rate on frozen points is close to 0.7 at every α. It would be
convenient to attribute this to a stale reference distribution and fix it by
bounding the freeze duration. Two measurements rule that out.

**Staleness is real but is not the dominant term.** Resolving the frozen points
by how long the freeze has been running gives 0.589 in the first eighteen
steps, rising to 0.945 beyond 576 steps. The rate does climb with staleness —
but it starts at 0.589 before anything has had time to go stale.

**The floor comes from the entry condition.** A point enters the frozen
population only when at least six of the previous eighteen points exceeded,
that is, when the local exceedance rate is at least 1/3. Measuring an
exceedance rate on a population selected by its exceedance rate is conditioning
on the outcome; it cannot return α. This also explains why the frozen rate is
invariant to α while the frozen fraction moves by a factor of 47: the 6-of-18
rule does not depend on α.

**Bounding the freeze has a ceiling, and the ceiling is far from nominal.** A
static counterfactual that cuts every freeze at step *D* and returns the
released points to the unfrozen rate — an upper bound, not a prediction, since
a real cut would change every subsequent buffer, *p*-value and alarm — gives:

| Cut at | Pooled FAR would become |
|---|---|
| 36 steps (6 h) | 0.0275 |
| 144 steps (1 d) | 0.0368 |
| 288 steps (2 d) | 0.0401 |
| no bound (current) | 0.0445 |

Even a six-hour cut — shorter than any realistic work-order response time —
leaves the pooled rate at 2.4 times the unfrozen floor of 0.0113.

## 3. Six absorption policies were falsified, and the reason generalises

We implemented six policies for what the calibrator should absorb while an
alarm stands, and tested each against two fixtures that fail in opposite
directions: a gradual fault, where the alarm must persist, and a benign level
shift on a healthy turbine, where it must clear. **No policy passed both.**
`freeze`, `bin_local`, `gated` and `winsor_alpha` all locked in on the benign
shift; `none` and `winsor_max` both self-masked on the slow fault.

The informative part is not the failures but their pattern: **the value in the
slow-fault column and the value in the benign-shift column are identical for
all six policies.** Within the score stream alone, a sustained benign shift and
a sustained fault-driven shift are the same signal. Any absorption rule that
looks only at scores must either absorb both — and mask the fault — or absorb
neither — and lock in.

The consequence for this paper is a boundary on the contribution: separating
the two cases requires information from outside the score stream, such as the
closure of the work order that caused the freeze. Whether that can be evaluated
on this dataset without leaking label information is an open question we do not
answer here.

> Section 3 rests on synthetic fixtures. It rules four directions out; it does
> not establish that any direction works.

## 4. One detector, so the cross-detector requirement is not met

Every figure in the results section is computed on a single frozen detector.
Our evaluation contract requires the claim to hold on two independent
detectors, and the second (a main-bearing SCADA framework) is not implemented.
Until it is, the results support "this calibration layer improves conditional
coverage on this detector's scores", not "on anomaly scores generally".

## 5. Baselines that are absent, and why

The CARE adaptive-threshold baseline, the CARE score and the CARE Reliability
metric are named in our evaluation contract and are **not implemented**.
Their definitions are in a publication we have not obtained in full text.
Calling the baseline raises an exception rather than returning an
approximation, and the omission is recorded in every artefact.

Reporting a baseline as missing is the lesser error. An approximation
published under the original's name is a claim about another group's method
that we could not defend.

## 6. Lead time is reported without a bounded detection horizon

The lead-time metric is unbounded below: an alarm raised before the fault
window opens is still counted as early warning, and a method that alarms early
and often harvests lead time from alarms that detected nothing. On a synthetic
fixture with a known onset this inflates the static reference by 6.11 of its
16.53 reported days. On CARE the physical onset is unknown, so nothing flags
it.

The reported medians near 350 days should be read in that light: they are close
to the length of a case and are dominated by the earliest alarm in the record.
They support the relative comparison between methods under one identical rule.
**They do not support any statement about how much warning an operator would
receive**, and no such statement is made.

> **Open decision.** The detection horizon *H* is a protocol parameter that has
> not been set, and the evaluator refuses to default it. Once set, the
> lead-time table must be regenerated.

## 7. Dataset limitations that constrain what can be claimed

- **No main-bearing measurement on Wind Farm A.** The channel dictionary for
  that farm carries gearbox high-speed-shaft and generator DE/NDE bearings,
  which are different components. Main-bearing faults on Wind Farm A are
  therefore invisible to the detector used here, and the absence is declared
  explicitly rather than left silent.
- **Sentinel values in main-bearing channels on Wind Farms B and C.** Both
  farms carry a fault code in the main-bearing pair, with different failure
  patterns: the two Wind Farm C channels fail almost simultaneously (67,896 vs
  67,871 rejected rows), while the two Wind Farm B channels fail independently
  (4,012 vs 464). Filtering is applied **per channel, before averaging**, so
  rows where one channel was rejected and the other was not carry a
  single-channel value rather than a two-channel mean. This affects roughly
  0.47 % of Wind Farm B rows. It is negligible in magnitude, but it means the
  preprocessing cannot be described as "the mean of two channels" without
  qualification.
- **Active power is per-unit, not kilowatts**, despite the dictionary's
  declared unit. The method is unaffected — a per-unit signal is still a valid
  feature and the convention is consistent across farms — but no absolute power
  figure can be quoted.
- **Version drift in the archive.** The published description of this dataset
  reports 44 anomaly and 51 normal time frames; the copy used here carries 45
  and 50. The discrepancy is recorded and unexplained. Our evaluation runs on
  91 cases after the leakage remediation, and every count in this paper refers
  to the copy we hold.

## 8. Two aspects of the evaluation are not ratified

The compatibility checks that the detector satisfied are recorded with
`gate_definitions_ratified: false`: the checks ran and passed as currently
specified, but their specification has not been approved. Independently, the
false-alarm reporting protocol used in the results section was ratified on
2026-08-17, after the score streams were produced; the calibration figures were
recomputed under it from the stored per-case outputs, while the lead-time
figures come from the earlier run. Both artefacts are retained and the
provenance of each column is stated in the results section.
