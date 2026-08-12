# CARE v6 Manifest Tooling

## `care_v6_manifest.py`

Implements the G1–G6 checks from **[交辦] CARE v6 Manifest 交付規格（給 Codex B，本機執行）**
(Drive doc `1tHS6nYO2mkwr3_o6I79Vib7_Qm1tTDxHIhZEV3mSodc`), so that whichever collaborator
has local disk access to `CARE_To_Compare_v6.zip` (5,503,439,673 bytes, Drive file id
`1188sErzQonZPE9EcDRudBBPoa-dlQ7C8`) does not need to hand-implement the spec.

**Why this exists here and wasn't run against the real archive**: cloud-based collaborator
sessions in this project cannot download/process a 5.5GB archive (see spec doc section 0 and
the project's Evaluation Contract). This script is the missing piece to make that local
step fast and reproducible — run it once you have the archive extracted locally.

### Quick start

```bash
python3 care_v6_manifest.py \
  --archive /path/to/CARE_To_Compare_v6.zip \
  --workdir /path/to/scratch_or_extract_dir \
  --output-dir ./manifest_out
```

If you've already extracted the archive, pass `--skip-extract` and point `--workdir` at
the extracted root.

### Output

`manifest_out/` will contain `g1_archive_integrity.json` through `g6_leakage_gate.json`,
`g3_case_metadata.csv`, `g5_regime_bin_matrix.csv`, `detection_notes.json`, and a
paste-ready `manifest_summary.md` — copy that summary directly into a new Drive doc named
per spec section 7 (`[數據] YYYY-MM-DD R13 — CARE v6 G1–G6 Manifest 執行結果`).

### What's trustworthy out of the box vs. what needs a human spot-check

- **G1 (hash / size / top-level tree / file count)** makes no assumptions about internal
  layout — trust it as-is.
- **G2–G6** auto-detect the timestamp / wind-speed / label columns per case file using
  name-hint matching (`--timestamp-col`, `--wind-speed-col`, `--label-col` default to
  `auto` but can be overridden). Nobody on the cloud side has seen the real internal
  structure of CARE v6, so **spot-check a few `status=detected` entries in
  `detection_notes.json` against the raw files before treating G2–G6 numbers as D0 gate
  evidence**, and look at any `status=undetected` entries — those cases are excluded from
  all counts rather than silently guessed.
- If the case files aren't flat CSVs matching `**/*.csv`, pass `--case-glob` to match the
  real layout (e.g. `"**/data/*.csv"`).

### Tested against

A synthetic 2-case fixture (not the real archive) to confirm the script runs end-to-end
without crashing and produces sane JSON/CSV. See the manifest summary format above for
what a real run's `manifest_summary.md` will look like. This is **not** a substitute for
running it against the actual archive — it only proves the tool is functional.
