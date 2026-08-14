# CARE v6 Manifest & C0–C6 Gate Tooling

Run in this order:

1. `care_v6_manifest.py` — G1–G6 archive integrity + case manifest (closes **D0**).
2. `sensor_identification_profile.py` — proposes candidates for the four CARE v6
   signals that are anonymised and therefore unnameable, so a C0 signal map can
   be built at all.
3. `base_scorer_compatibility_check.py` — the **C0–C6** frozen-base-scorer gate,
   which consumes the outputs of steps 1 and 2.

Both self-tests run anywhere, with no CARE v6 data:

```bash
python3 scripts/selftest_c0_c6_gate.py            # 47 checks
python3 scripts/selftest_sensor_identification.py # 15 checks
```

---

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
without crashing and produces sane JSON/CSV. This is **not** a substitute for running it
against the actual archive — it only proves the tool is functional.

### Fixes applied after the 2026-08-14 real run

The first run against the real archive surfaced three defects, all fixed here:

- **G6 was saturated and uninformative.** It grouped by farm only and compared
  just *adjacent* pairs after sorting by start time, so it reported exactly
  `n_cases − 1` overlaps per farm — every adjacent pair overlapped, because
  cases within a farm are different turbines monitored over the same calendar
  period. Calendar overlap is expected and is not leakage. G6 now groups by
  `(farm_id, turbine_id)`, compares all pairs, and measures real overlap
  duration, separating cross-label (anomaly × normal on the same asset) pairs.
- **The official train/test split was reported as "not determinable".** It is a
  per-row `train_test` column, not a root manifest file. G6 now detects it.
- **`manifest_summary.md` was mojibake on Windows.** Every text file is now
  opened with an explicit `encoding="utf-8"`.

---

## `sensor_identification_profile.py` — anonymised-channel profiler

CARE v6 ships almost every channel anonymised: Farm A has 86 columns of which
60 are `sensor_<n>_*`, Farm B 257/228, Farm C 957/908. Only `power_<n>_*`,
`wind_speed_<n>_*` and `reactive_power_<n>_*` carry meaning, and the numbering
differs per farm. Of C0's six core signals, only active power and wind speed
can be named; **rotor speed, main bearing temperature, pitch angle and ambient
temperature cannot**. That blocks C0, and it blocks Base Scorer 2 outright —
the main-bearing framework needs main bearing temperature.

This profiler ranks candidates using physical signatures:

| Signal | Signature |
|---|---|
| rotor speed | non-negative; rises with wind then saturates; high corr with wind *and* power |
| ambient temperature | strong annual cycle; near-independent of power; outdoor-air range |
| main bearing temperature | warmer than ambient; rises with power *and* with ambient |
| pitch angle | large mass at 0 below rated; corr with wind jumps in the top wind quintile; right-skewed |

```bash
python3 scripts/sensor_identification_profile.py \
  --workdir ./extract_dir --output-dir ./sensor_profile_out
```

**It proposes, it does not decide.** Output carries
`"status": "CANDIDATE_UNRATIFIED"` and units are written as `<CONFIRM: …>`
placeholders, so the draft is deliberately *not* accepted by C0 until a human
confirms each column and fills in the real unit. A statistical signature is
circumstantial; a data dictionary from the CARE authors beats it every time.

`selftest_sensor_identification.py` plants known identities in a synthetic farm
plus two decoys — a power-derived channel that correlates with power at r=1.0,
and pure noise — and asserts the profiler recovers all four signals, keeps the
anchors out of the candidate pool, and lets neither decoy win.

---

## `base_scorer_compatibility_check.py` — C0–C6 gate (`c0c6-gate-v2.0`)

Audits the per-case score streams of each frozen base scorer against C0–C6 before those
streams may be handed to the calibration pilot.

> **The gate definitions are still a PROPOSAL.** They are this project's synthesis of R15
> section 1 and PI directive v1.0. Merged tooling is not gate ratification. `gate_status`
> describes *evidence*, not authority — do not write "C0–C6 passed" into a manuscript
> before the PI or a collaborator ratifies the definitions **and** a real run reports
> `gate_status=PASS`.

### v2.0 — what changed and why

v1 (commit `484c60a`) was audited at source level by Codex B; six defects are recorded in
Drive doc *進度更新 2026-08-13 v2.8*. v2.0 closes all of them:

| Id | v1 defect | v2.0 behaviour |
|----|-----------|----------------|
| P0-1 | `gate_all_pass_mechanically_checkable` merged only C0/C1/C4/C6 and was a bare boolean | Per-gate enum `PASS/FAIL/UNVERIFIED/NOT_APPLICABLE`; `gate_status` is PASS only if **all seven** are PASS; process exits non-zero otherwise, so it works as a CI fail-closed gate |
| P0-2 | C4 compared file **count** against `n_detected`, so a wrong case set of the right size passed | C4 compares case **identity** against `g3_case_metadata.csv`, reporting `missing_case_ids`, `unexpected_case_ids`, `duplicate_case_ids_*` |
| P0-3 | C3 "passed" when the score CSV header had no label column | Header scan is retained only as a secondary red flag; PASS requires `--fit-provenance` (fit partition, files opened during fit + hashes, verification method, verifier). Absent → UNVERIFIED |
| P0-4 | C5 was a prose note; re-hashing one directory proves nothing | C5 requires `--score-dir-run2` **and** `--freeze-receipt`; comparison mode is an explicit `--determinism-mode bit_identical\|tolerance` |
| P0-5 | C1 counted consecutive blank **rows** and ignored timestamps; C6 demanded every score finite, contradicting ">3h ⇒ non-evaluable" | C1 measures gaps in **wall-clock time** and writes a per-case evaluability mask CSV; C6 checks finiteness **only on evaluable timestamps** and reports non-evaluable coverage separately |
| P0-6 / P1 | No status enum, no exit code, no receipts; C0 guessed columns by substring; `--score-glob`, `--case-id-from`, `--workdir` were documented but unimplemented | Input/output SHA-256 receipts, `gate_version` stamp, exit codes; C0 requires an explicit `--signal-map` with units and only *suggests* a mapping otherwise; all documented flags implemented and used |

### Quick start

```bash
# 1. generate blank evidence templates
python3 base_scorer_compatibility_check.py --emit-templates ./evidence_md2022

# 2. fill them in, then run the gate
python3 base_scorer_compatibility_check.py \
  --workdir           /path/to/extracted_care_v6 \
  --g2-inventory      ./manifest_out/g2_case_inventory.json \
  --g3-case-metadata  ./manifest_out/g3_case_metadata.csv \
  --score-dir         ./scores_md2022_run1 \
  --score-dir-run2    ./scores_md2022_run2 \
  --scorer-name       "MD_2022" \
  --output-dir        ./compat_out_md2022 \
  --timestamp-col     timestamp \
  --score-col         anomaly_score \
  --signal-map        ./evidence_md2022/signal_map.json \
  --artifact-manifest ./evidence_md2022/artifact_manifest.json \
  --fit-provenance    ./evidence_md2022/fit_provenance.json \
  --freeze-receipt    ./evidence_md2022/freeze_receipt.json \
  --determinism-mode  bit_identical
```

Run it once per scorer (`MD_2022`, `MainBearing_2026`). The manuscript's compatibility
claim needs `gate_status=PASS` for **both**.

### The four evidence files

The gate cannot invent evidence, so four gates stay UNVERIFIED until the operator supplies
a side-car file. `--emit-templates` writes all four blanks:

| File | Gate | Must contain |
|------|------|--------------|
| `signal_map.json` | C0 | each of the 6 core signals → column (or `derived_from` + `derivation`) **and** a declared unit |
| `artifact_manifest.json` | C2 | implementation source, version/commit, parameter provenance, artifact SHA-256 |
| `fit_provenance.json` | C3 | fit partition (must be the CARE **normal** reference partition), files read during fit + hashes, excluded label columns, verification method, verifier |
| `freeze_receipt.json` | C5 | environment, seed, config SHA-256, artifact SHA-256 |

### Output

`--output-dir` receives `compatibility_summary.json` (per-gate status + input receipts),
`per_case_c0_c6.json`, `evaluability_masks/<case_id>_evaluability_mask.csv`, and
`output_receipt.json` (SHA-256 of everything written).

### Exit codes

`0` PASS · `1` FAIL · `2` UNVERIFIED · `3` usage/IO error. Anything other than `0` means
the gate has **not** been cleared — fail closed.

---

## `selftest_c0_c6_gate.py`

```bash
python3 scripts/selftest_c0_c6_gate.py     # 47 checks, needs no CARE v6 data
```

The v1 defects survived review because the checker was read but never executed — no
collaborator could run it without the 5.5GB archive. This self-test removes that excuse:
it builds synthetic fixtures in a temp dir and drives the real checker as a subprocess,
asserting per-gate statuses *and* exit codes. Each scenario is a regression test for one
audited defect:

| Test | Asserts |
|------|---------|
| T1 | no evidence files → UNVERIFIED (exit 2), never PASS |
| T2 | complete evidence, clean data → PASS (exit 0), all seven gates PASS |
| T3 | wrong case set of the **right size** → C4 FAIL, names the missing/unexpected ids **[P0-2]** |
| T4 | >3h gap with absent scores → C1 masks 25 rows, C6 still PASS, coverage reported **[P0-5]** |
| T5 / T5b | run2 diverges → C5 FAIL naming the case; single run → C5 UNVERIFIED **[P0-4]** |
| T6 | clean header, no fit evidence → C3 UNVERIFIED, not PASS **[P0-3]** |
| T7 | no `--signal-map` → C0 UNVERIFIED plus a suggestion for review **[P1]** |
| T8 | `--emit-templates` writes all four evidence templates |

Passing the self-test proves the **tool** behaves as specified. It says nothing about the
CARE v6 data, the scorers, or D0 — those still require a local run.
