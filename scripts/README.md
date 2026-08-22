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

---

## `diagnose_alarm_selection_floor.py` — 告警選擇效應的代數下界（`alarm-selection-floor-v1.0`）

```bash
python3 scripts/diagnose_alarm_selection_floor.py \
  --ours-dir ./experiments/MD_2022_a01_ours \
  --case-metadata ./manifest_out/g3_case_metadata.csv \
  --alpha 0.01 --exclude-cases 32,56,72,87 \
  --trim-case 93=2023-08-24T13:00:00 \
  --output experiments/alarm_selection_floor_2026-08-20/a01.json
```

回答 `FREEZE_LOCKIN_FINDINGS` 2.2／2.3 之後審稿人一定會問的下一題：
**6-of-18 這條規則本身強制出多高的超越率？** 答案是一個**代數下界**，
不是量測——推導不用到分數串流的任何性質、不需要校準層是對的、
也不限於 CARE v6。完整推導在模組 docstring，結果在
`experiments/alarm_selection_floor_2026-08-20/README.md`。

**讀既有逐案輸出，不重跑任何模型。**

| 它報什麼 | 意義 |
|---|---|
| 前提稽核（雙向） | `frozen` 是否真的等於 `S_t >= 6`。**兩個方向都查**，一次違反就撤回下界 |
| `floor_rate_on_neighbourhood` | `(k/w)·\|F\| / \|N(F)\|`，規則強制的下界 |
| `observed.rate_on_neighbourhood` | 實測值。與下界的比值才是有意義的量 |
| `far_frozen` / `far_unfrozen` / `far_pooled` | 順帶重現 R24 三數字，供交叉比對 |

**三個容易誤讀的地方**（工具本身也拒絕這三種讀法）：

1. 下界是 `N(F)` 的，**不是凍結集的**。凍結集沒有下界——連續 6 次超越後靜默，
   18 個凍結點只含 1 次超越（`selftest` T3 就是這個反例）。
2. 它**不是分解**。「實測減下界」不是「停滯的那一份」。
3. 下界 ≤ α 時它什麼都沒證明，所以會標 `vacuous_at_this_alpha` 並撤回。

退出碼：`0` 正常 · `1` 前提被違反（不報下界）· `2` 不等式被違反（工具有 bug，
代數上不可能發生）。

## `selftest_alarm_selection_floor.py`

```bash
python3 scripts/selftest_alarm_selection_floor.py    # 35 checks
```

T1 手算 fixture、T2 反向（差一格的膨脹會讓 T1 失敗）、T3 釘住「下界不在凍結集上」、
T4／T5 前提稽核雙向都會觸發且會撤回下界、T6 vacuity、T7 排除與裁切真的丟掉列
（含 `T` 對空白的時間戳陷阱）、T7b 暖機列不位移索引、T8 隨機串流下不等式恆成立
但膨脹係數會被違反、T9 工具自己的 `N(F)` 等於逐點定義（多 run 重疊情形）、
**T10 claim firewall 第七條隨輸出走**（2026-08-21 新增）。

**已反向驗證**：把膨脹改成 `w-1`，T1 兩項與 T9 一項共 3 個 check 失敗；
把 `claim_constraint` 從 payload 拿掉，T10 六項全數失敗；
只把其中的 `permitted`（仍然可以寫什麼）清空，T10 的反向那一項失敗。

> **為什麼第七條要進輸出，而不是只寫在 `docs/manuscript/README.md`。**
> 這個限制**在數字裡看不出來**——一個不得稱為新的下界，長得跟可以稱為新的
> 下界一模一樣；而寫稿的人讀的是這份 JSON，不是 README。
> 同理，輸出裡**必須同時寫明什麼仍然可以寫**（呈報、推導、用來論證選擇效應），
> 否則下一個讀到禁令的人會把整段量測一起刪掉，那是另一種錯。
> **寫成方法的一部分可以，寫成貢獻不行。**

## `diagnose_group_occupancy.py` — 逐案 × 逐分箱的占用率（`group-occupancy-v1.0`）

```bash
python3 scripts/diagnose_group_occupancy.py \
  --ours-dir ./experiments/MD_2022_a01_ours \
  --exclude-cases 32,56,72,87 \
  --trim-case "93=2023-08-24T13:00:00" \
  --alpha 0.01 --k 4 \
  --output experiments/pogo_g3_2026-08-21/occupancy_a01.json
```

回答 R26 G3 的一個是非題：**逐案重置會不會讓 POGO 的 Theorem 4.1 失效？**
該定理假設 `T_j > 0`，而重置把 `T_j` 從全案總數縮成逐案的數——
某一案的機組若整段都沒進到 12 m/s，`bin4_ge_12` 就是 0，
**定理對那一案的那個 group 什麼都沒說，而且不會報錯。**

**讀既有逐案輸出，不重跑任何模型。**

| 它報什麼 | 意義 |
|---|---|
| `raw` | 落在該分箱的列數，**POGO 看得到的 `T_j`**（它沒有分箱層級的暖機） |
| `calibrated` | 其中有 p-value 的列數，**共同評估視窗**能用的母體 |
| `empty_raw_bins` / `empty_calibrated_bins` | 逐案逐分箱列出空格，兩種占用率分開 |
| `worst_case_under_reset` | 最稀疏那一案，連同 Theorem 4.1 在該尺度上的值 |
| `carry_bound_at_min_Tj` | 同一個界在「全案攜帶」下的值，供對照 |

**兩件容易弄錯的事**：

1. `calibrated` **不是** `raw − min_bin_samples`。凍結期間緩衝停止吸收，
   所以它是量出來的，不是算出來的（`selftest` T3 釘住）。
2. `T_j = 0` 得到的是 `null`，**不是一個很小的界**。沒有界與界很鬆是兩回事。

⚠️ 印出來的界是 **POGO 的最壞情況上界**，不得與本研究實測的 worst-bin 偏差
並排（R25 claim firewall），也不是對它表現的預測。

## `selftest_group_occupancy.py`

```bash
python3 scripts/selftest_group_occupancy.py    # 18 checks
```

T1 raw 與 calibrated 是不同的數（含反向）、T2 空 group 逐案逐分箱被指出（含反向）、
T3 calibrated 是量的不是減出來的、T4 裁切比較 datetime 而非字串（含反向）、
T5 界接到最稀疏的**已占用** group 且與 `pogo_bound_scale_check` 一致（含反向）、
T6 `T_j = 0` 不給界（含反向）。

**已反向驗證兩處**：拿掉 `p_value` 判斷讓 calibrated 計數每一列 → 4 checks 失敗；
把裁切改回字串比較 → 3 checks 失敗且丟棄列數變成 0，
正是本專案已吃過兩次的那個缺陷（空白的 ASCII 小於 `T`，裁切靜默什麼都沒做）。

---

## `check_pogo_receipt.py` — R26 契約的機器檢查（`check_pogo_receipt`）

```bash
# 空白 receipt：欄位用抄的，不要用記的
python3 scripts/check_pogo_receipt.py --emit-template > receipt_k4_none.json

# 四組跑完後一次檢查（--ours-window 直接吃既有的 occupancy 報告）
python3 scripts/check_pogo_receipt.py \
  --receipt receipt_k4_none.json  --receipt receipt_k4_within.json \
  --receipt receipt_k5_none.json  --receipt receipt_k5_within.json \
  --require-matrix \
  --ours-window experiments/pogo_g3_2026-08-21/occupancy_a01.json \
  --json-out g3_acceptance_a01.json
```

G3 契約（`docs/method/POGO_G3_STATE_CONTRACT.md`，2026-08-21 `CONTRACT_RATIFIED`）
第 6 節要求每次 POGO 執行留一份 receipt。**一份沒有人檢查的 receipt 只是文書工作**，
這支工具是另外那一半：把契約每一條做成 **fail-closed** 的檢查——
**欄位缺失是 FAIL，不是套用預設值**。

擋的四件事，共同點是**違反了也不會報錯，數字照樣漂亮**：

| 檢查 | 沒有它會怎樣 |
|---|---|
| `frozen_flag_source` 恆為 `pogo_own_exceedances`；`--ours-frozen` 逐案比對，**全案完全相同即 FAIL** | POGO 的 `frozen` 若沿用本方法的欄，兩邊鎖死幾何當然一致，看起來像漂亮的獨立重現，G6 卻已是循環論證 |
| `burn_in` 必須是作者預設 | 動了它，之後任何難看的數字都無法歸因：是方法差，還是我們動了暖機 |
| `--require-matrix`：R28 四組到齊才 `headline_eligible` | 一個 max over 2 與 max over 4 長得一模一樣 |
| 共同評估視窗**逐案**相等 | 兩個不同的逐案切法可以有同一個總數 |

`--ours-window` 接受兩種格式：明寫的視窗檔，或直接吃
`diagnose_group_occupancy.py` 的報告（讀 `n_calibrated`，**不是** `n_rows`）。
**少一個手動換算，就少一個「加總到一個大一點、完全合理的數字」的機會。**

輸出隨附 `CLAIM_CONSTRAINT`（R28 呈報義務 + R25 firewall），理由與
`diagnose_alarm_selection_floor.py` 同一條：**寫稿的人讀的是那份 JSON，不是 README**，
而一個「必須揭露為 4 組最大值」的數字，長得跟不必揭露的一模一樣。
它同時寫明**什麼仍然可以寫**——過度保守地把整段量測刪掉是另一種錯。

行為測試 `scripts/selftest_check_pogo_receipt.py`（**78 checks**），
每一條規則都做兩個方向。其中 T5 是關鍵的反向驗證：
**兩份逐案切法不同、總數相同的視窗必須 FAIL**——
那正是驗收條件寫成「逐案相等」而不是「總數相等」的理由。
T10 另以版控裡的 `occupancy_a01.json` 實跑：重算得 91 案、4,836,007 列，
與 G3 契約第 4 節記載的數字逐位相符。

**這支工具檢查的是「可不可以比」，不是「比得怎樣」。**
全數通過只代表那批結果**有資格**被比較。

**【R29・2026-08-22】** `freeze_layer = g6_same_policy` 的 receipt 另須含
`per_row_output_dir`，且 **G6 驗收還要跑 `audit_pogo_frozen_rows.py`**（見下一節）。
本工具的逐案凍結列數比對只是快篩，**不能代替逐列稽核**。

---

## `audit_pogo_frozen_rows.py` — G6 的逐列 `frozen` 稽核（`pogo-frozen-row-audit-v1.0`）

```bash
python3 scripts/audit_pogo_frozen_rows.py \
  --ours-dir experiments/MD_2022_a01_ours \
  --pogo-dir <POGO 逐列輸出目錄> \
  --exclude-cases 32,56,72,87 \
  --trim-case "93=2023-08-24T13:00:00" \
  --alpha 0.01 \
  --output experiments/pogo_r26_<日期>/frozen_row_audit_a01.json
```

**【R29・劉老師 2026-08-22 裁決】** G6 的執行 owner 必須交出 POGO 的逐列輸出，
`frozen` 逐列比對。在此之前，G3 契約第 3 節那條紅線
（**POGO 的 `frozen` 必須由它自己的 exceed 產生，不得沿用本方法那一欄**）
唯一的守門員是 receipt 上的 `frozen_flag_source` 欄——**那是實作者打上去的字串**。
一個寫著正確答案的欄位，不是「正確的事發生了」的證據。

這支工具把兩件事從宣告變成量測：

| | 查什麼 | 判準 |
|---|---|---|
| **來源** | 用 POGO 自己的 `exceed` 欄重算 6-of-18，與它寫出的 `frozen` **雙向**比對 | 兩個方向都必須 **0 違反** |
| **獨立性** | 與本方法的 `frozen` 向量逐列比對 | **每一個非平凡案例都完全相同 → 判定為抄的** |

**來源那一欄沿用 `diagnose_alarm_selection_floor.audit_premise()`**——
就是本專案 2026-08-20 對自己的 `frozen` 欄做過的同一個稽核
（約 250 萬點、雙向 0 違反）。**同一個問題不寫兩份實作**，
否則遲早有一份是錯的而沒人知道。

**判成抄襲的是「同一」，不是「相似」。**
高度一致正是 G6 想找的結果（若演算法完全不同的方法在同一套告警政策下
呈現相同的鎖死幾何，那就證明該現象是政策的性質）。工具**呈報**一致率與 Jaccard
而不懲罰它；只有「連一處都不差」才是複製。**兩側都從未凍結的案例不列入判定**
——那種一致是算術，不是來源。同理，若沒有任何非平凡案例，
輸出的 `independence_established` 為 `false`：**沒有可能不同的東西，就沒有查到什麼。**

行為測試 `scripts/selftest_audit_pogo_frozen_rows.py`（**38 checks**），每條規則兩個方向，
其中 **T10 是對照組**：本方法自己的 `frozen` 欄在真實資料上雙向 0 違反——
**一個到處都回報 0 的稽核也會放行偽造**，所以對照組不是裝飾。
另 T1 釘住新讀取器與既有 `read_calibrated_stream` 在同一份檔案上逐欄一致。

**G6 驗收是兩件事**：`check_pogo_receipt.py` 通過**且**本工具通過。
**前者不能代替後者。**
