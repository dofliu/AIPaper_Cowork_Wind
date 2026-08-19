# Contribution statement — draft under the R25 claim firewall

> **Draft — not approved.** Written 2026-08-19 under the repositioning ratified
> in R25 (PI, 2026-08-18 21:52): this paper is a **wind-turbine O&M
> protocol-and-evidence contribution**, not an algorithmic one. The wording
> below is a first draft of the sentences that go into the abstract and the
> end of the introduction. It is **not** cleared for submission; see
> `docs/manuscript/README.md` boundary four for what may and may not be said.
>
> Related work remains frozen (R23 / `PROJECT_STATUS.md` 6.6 unresolved), so
> this file states our claims and their evidence; it does not position them
> against individual prior papers beyond the two firewall exclusions below.

---

## 1. What this paper claims

**One sentence.** We report an evaluation-and-reporting protocol, and the
empirical characterisation that motivates it, for online conformal calibration
of a frozen wind-turbine anomaly score under real work-order alarm semantics,
measured on 91 cases of the CARE v6 SCADA dataset.

**Three claims, in the order the evidence supports them.**

**C1 — Conditioning on operating regime is what the wind-turbine case needs,
and pooled false-alarm rate is the wrong ruler for measuring it.**
A score stream can hold its nominal false-alarm rate on average while
over-alarming in one wind-speed regime and under-alarming in another, because
the score distribution differs by regime. Calibrating per regime removes that
gap: at α = 0.01 the worst-regime deviation on unfrozen points is 0.0036,
against 0.0111 for the strongest baseline and 0.1295 for static split
conformal. The same underlying run, read as a single pooled rate, ranks the
method fourth — not because the calibration is worse, but because the pooled
rate averages over points at which the calibrator was deliberately not
calibrating.

**C2 — Alarm-suppression policy and calibration guarantee interact, and the
interaction is a selection effect rather than staleness.**
Freeze-on-Alert — stopping buffer updates while an alarm stands, which is what
keeps a progressive fault from being absorbed into the reference distribution —
makes the frozen points a subpopulation *selected by exceedance*: the 6-of-18
work-order rule enters exactly when the local exceedance rate is at least 1/3.
Measured on CARE v6, the false-alarm rate inside frozen points is 0.6819 at
α = 0.01 and is already 0.589 in the first eighteen steps of a freeze, before
any reference distribution could have gone stale; it moves by less than 0.09
while α moves by a factor of 50 and freeze occupancy by a factor of 47. Any
calibration guarantee reported over those points is measuring the alarm policy,
not the calibration layer.

**C3 — Therefore the false-alarm figure must be reported as three numbers, and
the cost of the freeze must be a first-class number.**
We report the unfrozen worst-regime deviation, the fraction of points frozen,
and the false-alarm rate inside frozen points; the pooled rate is exactly
recoverable from the three (reconstruction residual ~7e-18 at α = 0.01) and is
still emitted, never as a headline on its own. Freeze occupancy is the guard
that stops the first number from becoming a self-serving definition: it is
0.5% / 4.9% / 23.4% at α = 0.001 / 0.01 / 0.05, and at α = 0.05 nearly a
quarter of all points sit inside a freeze.

**Supporting negative result (reported, not claimed as a solution).**
Six absorption policies were tested on synthetic fixtures with known ground
truth; none passes both directions. Four lock in on a benign level shift; two
self-mask on a slow fault. The slow-fault column and the benign-shift column
are **identical across all six**, which is the stronger statement: within the
score stream alone, a sustained benign shift and a sustained degradation are
the same signal. Separating them requires information from outside the score —
we identify work-order closure as the candidate channel and state why CARE v6
cannot evaluate it without leakage.

---

## 2. What this paper does **not** claim — the R25 claim firewall

These are prohibited wordings, ratified 2026-08-18. They are not stylistic
preferences; each corresponds to territory already held by prior work.

| Must not be claimed | Why |
|---|---|
| first / new **group-conditional online conformal prediction** | held by Bharti et al. 2026 (arXiv:2606.00419v4), verified against the full text in R25's Mandatory Overlap Check |
| **parameter-free** online optimisation, or any variant of that claim | same source |
| a **general group-conditional coverage guarantee** (any finite-time or asymptotic coverage theorem) | same source — and this paper proves no theorem at all |
| `conditional conformal prediction for wind turbines` as a bare subject | held at the application layer (`PROJECT_STATUS.md` 6.6); the object of conditioning must always be named |
| `regime-aware` / `regime-weighted` / `regime-dependent` calibration as our subject | three independent 2026 uses of `regime-*` + conformal calibration (see `docs/literature/LITERATURE_SCAN_2026-08-19.md`) |

**The permitted subject remains `operating-regime-conditional`, spelled out.**
The prefix does two jobs at once: it separates us from the `regime-*` cluster
above, and it separates us from the group/cluster line of work — we condition
on the operating state a single turbine passes through over time, not on which
group of turbines a unit belongs to.

**Also not claimed, for evidence reasons rather than novelty reasons:**

- Any statement of the form "we outperform / match / do not need POGO."
  The compatibility gate (`docs/method/POGO_COMPATIBILITY_GATE.md`) has not
  been run. "POGO does not apply here" is equally an unchecked conclusion.
- Validity across **two** base scorers. D5 requires it; Base Scorer 2 is not
  implemented. `[PENDING — Base Scorer 2]`
- "C0–C6 passed." The gate definitions are not ratified
  (`gate_definitions_ratified: false`).
- Any lead-time or earliness claim on real data before the detection horizon
  *H* is ratified. `[PENDING — H]`
- Offshore validity. CARE v6 is onshore.

---

## 3. Draft sentences

**For the abstract (contribution sentences only):**

> We study online conformal calibration of a frozen, already-published anomaly
> score for wind-turbine operations and maintenance, where alarms are raised
> under a work-order rule and calibration is suspended while an alarm stands.
> We show that in this setting the pooled false-alarm rate is not an
> interpretable measure of the calibration layer, because the suspended points
> are selected by the very quantity being measured, and we give the
> three-number report — unfrozen worst-regime deviation, freeze occupancy, and
> false-alarm rate inside freezes — that is exactly reconcilable with it.
> On 91 cases of the CARE v6 SCADA dataset, conditioning on physically defined
> wind-speed operating regimes holds the worst-regime deviation at 0.0036 at a
> nominal 0.01, against 0.1295 for static split conformal. We further
> characterise the geometry of alarm-induced calibration lock-in and falsify
> six candidate absorption policies, showing that a sustained benign shift and
> a sustained degradation are indistinguishable within the score stream alone.

**For the end of the introduction (the "we contribute" list):**

> Our contributions are (i) an evaluation protocol for calibration layers that
> operate under alarm-suppression policies, in which the false-alarm figure is
> reported as three reconcilable numbers rather than one; (ii) an empirical
> characterisation, on real SCADA data, of the selection effect that makes the
> pooled figure uninterpretable, including its invariance to the nominal level;
> (iii) a falsification of six absorption policies together with the reason
> they all fail; and (iv) a reproducible operating-regime-conditional
> calibration protocol on CARE v6, with the per-case evidence and the
> compatibility checks that a reviewer needs to re-derive every number.
> We do not propose a new conformal algorithm and prove no coverage theorem.

**The last sentence is deliberate.** Stating the boundary explicitly is
cheaper than having a reviewer discover it, and under R25 it is now the
accurate description of the work.

---

## 4. Open items blocking finalisation

| Item | Blocks | Owner |
|---|---|---|
| Detection horizon *H* (R22) | every earliness sentence | 劉老師 |
| Base Scorer 2 | any "both scorers" wording; D5 | 本機 |
| Formal Phase 5 re-run with `--event-info-root` | the lead-time column of Results | 本機 |
| C0–C6 ratification | the compatibility-check wording | 劉老師 |
| Related work (R23 / 6.6, and POGO gate G8) | positioning against named prior work | 本機取全文後 |

None of these blocks Section 1 or Section 2 of this file: those state what we
measured and what we are forbidden to say, and both are settled.

---

*建立：2026-08-19，排程自動化研究助理。內容為投稿語言（英文），依語言政策；
本說明段落與檔案標題以外的中文只出現在本目錄的 README。*
