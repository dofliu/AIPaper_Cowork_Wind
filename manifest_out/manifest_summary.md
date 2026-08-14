# CARE v6 G1-G6 Manifest ¡X auto-generated summary

Generated: 2026-08-14T13:21:50.849867Z

## G1 ¡X Archive Integrity
- SHA-256: `pre_extracted_from_local_storage`
- Size: 5503439673 bytes (expected 5503439673, match=True)
- Extracted files: 103, total bytes: 19987485991

## G2 ¡X Case Inventory / Version Drift
- Detected: 95 / undetected: 0 (glob found 95)
- anomaly=45, normal=50
- Matches paper (44/51): False
- Matches v6 metadata (45/50): True
- Matches expected total 95: True

## G5 ¡X Regime Bin Feasibility
- Excluded cells (<500 samples): 0 / 380 (0.0% )

## G6 ¡X Leakage Gate
- Cross-case time overlaps detected: 92
- Official train/test split: NOT auto-determined ¡X verify manually against archive root files.

## Caveat (read before trusting G2-G6)
G2-G6 rely on best-effort auto-detection of timestamp/wind-speed/label columns (see detection_notes in each JSON file / g3 CSV `source_file` column). Spot-check a handful of `status=detected` cases against the raw files before using these numbers as D0 gate evidence, and inspect any `status=undetected` entries ¡X they are excluded from all counts above, not silently assumed normal.