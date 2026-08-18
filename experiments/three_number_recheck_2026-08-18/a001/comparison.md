# Comparison (alpha = 0.001)

| method | worst-bin dev (unfrozen) | frozen % | FAR frozen | pooled dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|---|---|
| w1acas | 0.0010 | — | — | 0.0010 | n/a | n/a | n/a | n/a |  |
| ours | 0.0017 | 0.5% | 0.7711 | 0.0044 | n/a | n/a | n/a | n/a |  |
| aci | 0.0026 | — | — | 0.0003 | n/a | n/a | n/a | n/a |  |
| dtaci | 0.0040 | — | — | 0.0010 | n/a | n/a | n/a | n/a |  |
| static | 0.0635 | — | — | 0.0184 | n/a | n/a | n/a | n/a |  |

Work-order rule 6-of-18 applied identically to every method.

**False-alarm figures are three numbers, not one** (protocol three-number-far-v1.0, ratified 2026-08-17). `worst-bin dev (unfrozen)` is the conditional-coverage claim; `frozen %` is what the freeze costs and must be read with it; `FAR frozen` lets you rebuild the pooled rate. This method suspends calibration while its own work order stands, and the 6-of-18 entry condition means the frozen points are selected by a local exceedance rate of at least 1/3 -- so a pooled rate over both populations reports the alarm policy under the name of the calibration layer. A method with no freeze mechanism shows `—`, not 0%, because nothing was measured there. See per_method[*].false_alarm_report.pooled_reconstruction for the identity check.

**Detection horizon: UNSET.** Lead time is unbounded, so an alarm raised before the fault began is still counted as early warning. Run with --detection-horizon-days to bound it. See scripts/diagnose_earliness_gap.py for a fixture where this inflates a baseline by 6.11 of its 16.53 reported days.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
