# CARE v6 G1-G6 Manifest — auto-generated summary

Generated: 2026-08-15T06:26:14.480721Z

## G1 — Archive Integrity
- SHA-256: `ca61379e98956d891041ad45c885109bd8a14199fde0688d0184a11c2d4194f1` (matches expected: True)
- Size: 5503439673 bytes (expected 5503439673, match=True)
- Extracted files: 254, total bytes: 25490925920

## G2 — Case Inventory / Version Drift
- Detected: 95 / undetected: 0 (glob found 95)
- anomaly=45, normal=50
- Matches paper (44/51): False
- Matches v6 metadata (45/50): True
- Matches expected total 95: True

## G5 — Regime Bin Feasibility
- Excluded cells (<500 samples): 0 / 380 (0.0% )

## G6 — Leakage Gate
- Distinct assets: 36; assets appearing in >1 case: 30
- Asset-level overlapping case pairs: 108 (cross-label anomaly x normal: 73)
- Overlap duration: median 291.44 d, max 386.0 d
- ⚠️ Asset-period isolation cannot be assumed. Calibration/evaluation splits must be built at the asset level, not the case level.
- Official train/test split: found as column:train_test (existence only; value distribution not yet tabulated)

## Caveat (read before trusting G2-G6)
G2-G6 rely on best-effort auto-detection of timestamp/wind-speed/label columns (see detection_notes in each JSON file / g3 CSV `source_file` column). Spot-check a handful of `status=detected` cases against the raw files before using these numbers as D0 gate evidence, and inspect any `status=undetected` entries — they are excluded from all counts above, not silently assumed normal.