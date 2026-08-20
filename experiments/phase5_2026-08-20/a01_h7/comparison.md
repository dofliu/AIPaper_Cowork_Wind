# Comparison (alpha = 0.01)

| method | worst-bin dev (unfrozen) | frozen % | FAR frozen | pooled dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|---|---|
| ours | 0.0036 | 4.9% | 0.6819 | 0.0345 | 43/44 (98%) | 2.65 | 2.55 | -2.33 | yes |
| w1acas | 0.0111 | — | — | 0.0057 | 16/44 (36%) | -4.39 | 0.00 | 4.72 | NO |
| aci | 0.0165 | — | — | 0.0003 | 37/44 (84%) | -0.42 | 0.00 | 0.74 | yes |
| dtaci | 0.0198 | — | — | 0.0018 | 39/44 (89%) | -1.02 | 0.00 | 1.35 | yes |
| static | 0.1295 | — | — | 0.0370 | 34/44 (77%) | 0.33 | 0.00 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**False-alarm figures are three numbers, not one** (protocol three-number-far-v1.0, ratified 2026-08-17). `worst-bin dev (unfrozen)` is the conditional-coverage claim; `frozen %` is what the freeze costs and must be read with it; `FAR frozen` lets you rebuild the pooled rate. This method suspends calibration while its own work order stands, and the 6-of-18 entry condition means the frozen points are selected by a local exceedance rate of at least 1/3 -- so a pooled rate over both populations reports the alarm policy under the name of the calibration layer. A method with no freeze mechanism shows `—`, not 0%, because nothing was measured there. See per_method[*].false_alarm_report.pooled_reconstruction for the identity check.

Detection horizon: 7.00 days, part of the ratified sweep (R27); not the primary. An alarm earlier than that before event_start is counted as a false alarm, not a detection. The protocol reports the primary alongside the declared sweep; a horizon shown on its own is what R27 exists to prevent.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
