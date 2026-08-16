# Comparison (alpha = 0.05)

| method | worst-bin dev | marginal dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|
| w1acas | 0.0532 | 0.0149 | 44/44 (100%) | 364.66 | 364.66 | -10.80 | yes |
| aci | 0.0716 | 0.0003 | 44/44 (100%) | 353.63 | 353.63 | 0.23 | yes |
| dtaci | 0.0803 | 0.0022 | 44/44 (100%) | 353.72 | 353.72 | 0.14 | yes |
| ours | 0.2100 | 0.1514 | 44/44 (100%) | 355.44 | 355.44 | -1.58 | yes |
| static | 0.2379 | 0.0633 | 44/44 (100%) | 353.86 | 353.86 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**Detection horizon: UNSET.** Lead time is unbounded, so an alarm raised before the fault began is still counted as early warning. Run with --detection-horizon-days to bound it. See scripts/diagnose_earliness_gap.py for a fixture where this inflates a baseline by 6.11 of its 16.53 reported days.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
