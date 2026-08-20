# Comparison (alpha = 0.01)

| method | worst-bin dev (unfrozen) | frozen % | FAR frozen | pooled dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|---|---|
| ours | 0.0036 | 4.9% | 0.6819 | 0.0345 | 44/44 (100%) | 348.50 | 348.50 | 1.97 | yes |
| w1acas | 0.0111 | — | — | 0.0057 | 44/44 (100%) | 340.57 | 340.57 | 9.89 | NO |
| aci | 0.0165 | — | — | 0.0003 | 44/44 (100%) | 344.70 | 344.70 | 5.76 | NO |
| dtaci | 0.0198 | — | — | 0.0018 | 44/44 (100%) | 346.49 | 346.49 | 3.98 | NO |
| static | 0.1295 | — | — | 0.0370 | 44/44 (100%) | 350.46 | 350.46 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**False-alarm figures are three numbers, not one** (protocol three-number-far-v1.0, ratified 2026-08-17). `worst-bin dev (unfrozen)` is the conditional-coverage claim; `frozen %` is what the freeze costs and must be read with it; `FAR frozen` lets you rebuild the pooled rate. This method suspends calibration while its own work order stands, and the 6-of-18 entry condition means the frozen points are selected by a local exceedance rate of at least 1/3 -- so a pooled rate over both populations reports the alarm policy under the name of the calibration layer. A method with no freeze mechanism shows `—`, not 0%, because nothing was measured there. See per_method[*].false_alarm_report.pooled_reconstruction for the identity check.

**Detection horizon: UNSET.** Lead time is unbounded, so an alarm raised before the fault began is still counted as early warning. Run with --detection-horizon-days to bound it. See scripts/diagnose_earliness_gap.py for a fixture where this inflates a baseline by 6.11 of its 16.53 reported days.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
