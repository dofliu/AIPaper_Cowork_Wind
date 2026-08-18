# Evaluation protocol

> **Draft — not approved, and not final.** One protocol parameter (the
> detection horizon *H*, Section 4) is still awaiting a decision; the section
> cannot be finalised before it is set. See `docs/manuscript/README.md`.

## 1. What is being compared, and on what ruler

The contribution is a calibration layer applied on top of a **frozen,
already-published anomaly detector**. The comparison is therefore between
calibration strategies applied to the same score stream, not between
detectors. The methods compared are:

| Method | Role |
|---|---|
| Operating-regime-conditional calibration (ours) | proposed layer |
| Static split conformal | reference for non-inferiority |
| Adaptive conformal inference, fixed step size | baseline |
| DtACI | baseline |
| W1-ACAS (re-implementation) | baseline; post-hoc, model-agnostic |
| CARE adaptive threshold | **not implemented** — see Section 6 |

Every method emits its output in its own natural form: the proposed layer
emits a per-regime *p*-value, W1-ACAS emits β, ACI and DtACI emit point alarms.
Comparing those directly would compare output conventions as much as
behaviour. The evaluator converts each to a common point-exceedance series and
then applies **identical downstream rules to all of them**: the same work-order
alarm rule, the same regime binning, the same rolling window, and the same
event windows.

This matters more than it appears. A baseline that alarms on isolated points
would appear to detect earlier than a method requiring a sustained alarm,
purely as an artefact of the alarm convention. Any comparison in which the
baselines are reported under their own alarm conventions is not the comparison
this protocol produces.

The W1-ACAS figures come from **our re-implementation, not author code**, and
are labelled as such in every artefact (`is_author_code: false`).

## 2. Alarm semantics and operating regimes

An alarm is raised at the **work-order** level: six exceedances within the last
eighteen 10-minute points. This is the unit of action in operations — a
maintenance ticket, not a flagged sample — and it is applied uniformly to
every method.

Operating regimes are wind-speed bins of `<4`, `4–8`, `8–12` and `≥12` m/s,
with a minimum of 500 samples per bin required for a bin to be evaluated.
Miscalibration is measured **per regime**, because a marginally calibrated
method can hold its pooled false-alarm rate at the nominal level while being
badly miscalibrated in the regimes that matter operationally.

Target miscoverage is α = 0.01, with α = 0.05 and α = 0.001 as secondary
settings; the rolling window is W = 1440 points (≈10 days), with 720 and 4320
as secondary settings. These values were signed off before any score stream
existed.

## 3. Metrics

**False-alarm calibration** — measured on **normal cases only**. An alarm
inside a fault window is a detection, not a false alarm, and including faulted
cases in false-alarm statistics penalises exactly the detector that works
best.

| Metric | Definition |
|---|---|
| `worst_bin_deviation` | max over regime bins of \|FAR − α\| — **primary metric** |
| `marginal_deviation` | \|FAR − α\| pooled — what a marginal method optimises |
| `rolling_deviation` | max \|FAR − α\| over rolling windows of W points |

The pooled figure is reported alongside the per-regime one specifically so
that the gap between them is visible rather than argued.

**Three numbers, not one.** The proposed layer suspends its own calibration
updates while a work order it raised is still open, so a single pooled
false-alarm rate would average two populations that the method treats
differently by design. Worse, the two are not independent: a point enters the
frozen population only when six of the last eighteen points exceeded, so the
frozen population is selected by the very quantity a false-alarm rate measures.
A pooled rate over both therefore reports the alarm policy under the name of
the calibration layer.

The protocol (`three-number-far-v1.0`) is to report, always adjacent and never
one without the others:

| Number | What it is |
|---|---|
| worst-bin deviation on **unfrozen** points | the conditional-coverage claim itself |
| **fraction of points frozen** | what the freeze costs, in first-class position |
| FAR on **frozen** points | lets the reader rebuild the pooled rate |

The third number exists to keep the first from becoming a self-serving
definition: the pooled rate is exactly reconstructible from the three, and the
evaluator records the reconstruction residual rather than asserting the
identity. A method with no freeze mechanism reports a dash in the second and
third columns, not a zero — nothing was measured there, which is not the same
as a measured zero.

Placing the frozen fraction anywhere but next to the deviation would hide a
denominator, which is the failure mode this protocol exists to prevent.

**Early detection** — measured on **anomaly cases only**, from the first
work-order alarm to `event_start`.

| Metric | Definition |
|---|---|
| `median_lead_days` | median lead time over **detected cases only** |
| `detection_rate` | fraction of anomaly cases on which any work-order alarm was raised |
| `median_lead_days_missed_as_zero` | same median with a missed detection scored as zero days of warning |

`median_lead_days` is never reported on its own. A median taken over the
detected subset has a denominator that **changes with the method**, so a method
that misses the difficult cases removes them from its own population and scores
better for it. Reporting `detection_rate` beside it makes the denominator
visible; `median_lead_days_missed_as_zero` is parameter-free and computed over a
denominator common to every method, which is what a fault one never alarms on
actually delivers to an operator.

**Non-inferiority** — median lead time may not fall more than **2 days** below
the static reference. The margin was signed off in advance.

## 4. The detection horizon, and why it has no default

Lead time as defined above is unbounded below: it is `event_start` minus the
first alarm, whenever that alarm falls. A method that alarms early and often
therefore *harvests* lead time from alarms raised before the fault existed, and
the metric records that as excellent early warning.

This is not hypothetical. On a synthetic fixture with a known onset index, the
static reference draws **6.11 of its 16.53 reported days** from an alarm raised
880 steps *before* the fault began, and ACI draws 8.28 of 18.70 the same way;
both report lead times exceeding the fixture's physical maximum of 10.42 days.
On CARE the physical onset is unknown, so nothing would have flagged it.

`--detection-horizon-days H` makes an alarm count as a detection only if it
falls within *H* days before `event_start`; anything earlier is a false alarm
rather than early warning. **H is deliberately not defaulted.** Left unset, the
evaluator retains the unbounded behaviour and records
`detection_horizon_days: null` together with an explicit caveat, so an unbounded
run can never be mistaken for a bounded one.

A sensitivity sweep on the synthetic fixture bounds the usable range from both
sides: too small an *H* truncates genuine lead time (at H = 3 every method
collapses to 3.00 days), while an *H* beyond the physical onset readmits the
pre-fault false alarms (at H = 14 one baseline's detection count rises again).

> **Open decision.** The value of *H*, and whether it enters the protocol at
> all, is a decision for the PI. Supporting evidence is in the R22 adjudication
> request; the code will not choose a value on its own.

## 5. What the synthetic fixture does and does not establish

Under the corrected evaluator, the proposed method passes non-inferiority at
every swept horizon on a 12-case synthetic fixture (unbounded −0.12; H = 3
0.00; H = 5 0.00; H = 7 −0.40; H = 10 −0.95; H = 14 −0.64, where negative
values indicate the proposed method detects *earlier*). Detection rates are
6/6 for the proposed method and for static, and lower for the remaining
baselines.

**This establishes that the metric now measures what its name claims, and
nothing about CARE.** The fixture exists to attribute a suspicious number to
its cause, not to produce results. Every performance claim in this paper rests
on the CARE score streams.

## 6. Metrics named in the evaluation contract but not implemented

The CARE score, the CARE Reliability metric and the CARE adaptive-threshold
baseline are named in our evaluation contract, and all three are currently
recorded as `NOT_IMPLEMENTED` with the reason stated in the artefacts. Their
definitions are given in the CARE To Compare publication, which this project
has not yet obtained in full text; calling the baseline raises an exception
rather than returning an approximation.

Reporting a baseline as missing is the lesser error. An approximation
presented under the original's name is a claim about someone else's method
that we would be unable to defend.

---

### Open items blocking this section from being final

1. The value of *H* (Section 4) is undecided.
2. The CARE metrics and baseline (Section 6) remain unimplemented pending
   full-text acquisition of the source publication.
3. ~~All reported numbers are from the synthetic fixture; the CARE results
   section is not yet written.~~ **Resolved 2026-08-18**: the CARE results are
   in `03_results.md` and the limitations in `04_limitations.md`. The fixture
   numbers in Section 5 remain fixture numbers and are labelled as such.
