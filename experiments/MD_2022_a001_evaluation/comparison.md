# Comparison (alpha = 0.001)

| method | worst-bin dev | marginal dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|
| w1acas | 0.0010 | 0.0010 | 0/44 (0%) | n/a | 0.00 | n/a |  |
| aci | 0.0026 | 0.0003 | 0/44 (0%) | n/a | 0.00 | n/a |  |
| dtaci | 0.0040 | 0.0010 | 0/44 (0%) | n/a | 0.00 | n/a |  |
| ours | 0.0114 | 0.0044 | 43/44 (98%) | 250.10 | 247.49 | 88.23 | NO |
| static | 0.0635 | 0.0184 | 43/44 (98%) | 338.33 | 338.25 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**Detection horizon: UNSET.** Lead time is unbounded, so an alarm raised before the fault began is still counted as early warning. Run with --detection-horizon-days to bound it. See scripts/diagnose_earliness_gap.py for a fixture where this inflates a baseline by 6.11 of its 16.53 reported days.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
