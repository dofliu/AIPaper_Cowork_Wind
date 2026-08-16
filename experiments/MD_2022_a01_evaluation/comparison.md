# Comparison (alpha = 0.01)

| method | worst-bin dev | marginal dev | detected | median lead (d) | lead, miss=0 (d) | lead lost | non-inferior |
|---|---|---|---|---|---|---|---|
| w1acas | 0.0111 | 0.0057 | 44/44 (100%) | 340.57 | 340.57 | 9.89 | NO |
| aci | 0.0165 | 0.0003 | 44/44 (100%) | 344.70 | 344.70 | 5.76 | NO |
| dtaci | 0.0198 | 0.0018 | 44/44 (100%) | 346.49 | 346.49 | 3.98 | NO |
| ours | 0.0602 | 0.0345 | 44/44 (100%) | 348.50 | 348.50 | 1.97 | yes |
| static | 0.1295 | 0.0370 | 44/44 (100%) | 350.46 | 350.46 | 0.00 | yes |

Work-order rule 6-of-18 applied identically to every method.

**Detection horizon: UNSET.** Lead time is unbounded, so an alarm raised before the fault began is still counted as early warning. Run with --detection-horizon-days to bound it. See scripts/diagnose_earliness_gap.py for a fixture where this inflates a baseline by 6.11 of its 16.53 reported days.

`median lead (d)` is a median over DETECTED cases only; read it with the `detected` column. `lead, miss=0` scores a missed fault as zero days of warning, over one denominator for every method.

CARE score and Reliability are not implemented; see missing_metrics.
