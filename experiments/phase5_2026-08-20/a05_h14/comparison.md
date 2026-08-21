# Comparison (alpha = 0.05)

| method | worst-bin dev (unfrozen) | frozen % | FAR frozen | pooled dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|---|---|
| ours | 0.0144 | 23.4% | 0.7068 | 0.1514 | 44/44 (100%) | 13.80 | 13.80 | -3.34 | yes |
| w1acas | 0.0532 | — | — | 0.0149 | 43/44 (98%) | 10.64 | 10.63 | -0.18 | yes |
| aci | 0.0716 | — | — | 0.0003 | 44/44 (100%) | 12.20 | 12.20 | -1.74 | yes |
| dtaci | 0.0803 | — | — | 0.0022 | 44/44 (100%) | 11.82 | 11.82 | -1.36 | yes |
| static | 0.2379 | — | — | 0.0633 | 43/44 (98%) | 10.46 | 10.26 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**False-alarm figures are three numbers, not one** (protocol three-number-far-v1.0, ratified 2026-08-17). `worst-bin dev (unfrozen)` is the conditional-coverage claim; `frozen %` is what the freeze costs and must be read with it; `FAR frozen` lets you rebuild the pooled rate. This method suspends calibration while its own work order stands, and the 6-of-18 entry condition means the frozen points are selected by a local exceedance rate of at least 1/3 -- so a pooled rate over both populations reports the alarm policy under the name of the calibration layer. A method with no freeze mechanism shows `—`, not 0%, because nothing was measured there. See per_method[*].false_alarm_report.pooled_reconstruction for the identity check.

Detection horizon: 14.00 days, the ratified primary (R27). An alarm earlier than that before event_start is counted as a false alarm, not a detection. The protocol reports the primary alongside the declared sweep; a horizon shown on its own is what R27 exists to prevent.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
