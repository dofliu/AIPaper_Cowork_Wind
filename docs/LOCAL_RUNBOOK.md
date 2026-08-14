# 本機執行手冊 v1.0 — D0 manifest 與 C0–C6 gate

給有 CARE v6 資料的本機執行者。雲端協作者無法處理 5.5GB archive，這份手冊把
每一步的指令寫死，執行者不需要自己組指令。

**分階段執行，不要一次做完。** 每個 Phase 結束就把指定的檔案回傳，
確認無誤再進下一個 Phase。Phase 1 失敗的話 Phase 3 做再多都是白做。

指令同時提供 **Linux/macOS (bash)** 與 **Windows (PowerShell)** 兩種寫法。
Windows 使用者請用 PowerShell，不要用 CMD（換行接續符號不同）。

---

## Phase 0 — 環境準備（5 分鐘）

### 0.1 取得程式

```bash
git clone -b claude/lucid-hypatia-rnqwj0 https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
```

```powershell
git clone -b claude/lucid-hypatia-rnqwj0 https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
```

### 0.2 確認 Python

需要 Python 3.8 以上。**不需要安裝任何套件**，兩支腳本只用標準函式庫。

```bash
python3 --version
```

```powershell
python --version
```

> Windows 上如果 `python` 指到 Microsoft Store 的空殼，請改用 `py -3`。
> 以下 PowerShell 指令一律用 `python`，若不通請自行換成 `py -3`。

### 0.3 先跑自我測試（重要）

在碰真實資料之前，先確認工具在你的環境行為正確：

```bash
python3 scripts/selftest_c0_c6_gate.py
```

```powershell
python scripts/selftest_c0_c6_gate.py
```

**預期輸出結尾**：

```
47 checks, 0 failed
ALL SELF-TESTS PASSED
```

若不是 47/0，**先停下來**把完整輸出回傳，不要繼續。這代表工具在你的環境
行為與雲端不同，之後所有結果都不可信。

---

## Phase 1 — D0：CARE v6 manifest（最高優先，現在就能跑）

這是整個專案從 v2.4 卡到現在的關鍵路徑。**這個 Phase 不需要 base scorer、
不需要 score stream、不需要任何其他東西**，只要 archive 本體。

### 1.1 檔案身分核對（先做這個，30 秒）

```bash
ls -l CARE_To_Compare_v6.zip
sha256sum CARE_To_Compare_v6.zip
```

```powershell
Get-Item CARE_To_Compare_v6.zip | Select-Object Name, Length
certutil -hashfile CARE_To_Compare_v6.zip SHA256
```

**預期 size 為 5,503,439,673 bytes。** 若不符，先回報，不要繼續 —— 表示
本機檔案與 Drive receipt 記錄的不是同一份，D0 的前提就不成立。

SHA-256 目前**專案內沒有任何已知值可比對**（這正是 D0 未關閉的原因之一），
所以你算出來的這個值就是第一份權威記錄，請務必回傳。

### 1.2 磁碟空間

解壓需要約 archive 的 2～3 倍空間。5.5GB 的 zip 請預留 **至少 20GB**。

### 1.3 執行 manifest

```bash
python3 scripts/care_v6_manifest.py \
  --archive    /path/to/CARE_To_Compare_v6.zip \
  --workdir    /path/to/extract_dir \
  --output-dir ./manifest_out
```

```powershell
python scripts/care_v6_manifest.py `
  --archive    C:\path\to\CARE_To_Compare_v6.zip `
  --workdir    C:\path\to\extract_dir `
  --output-dir .\manifest_out
```

**若你已經解壓過**，加上 `--skip-extract`，並讓 `--workdir` 直接指向解壓後的根目錄：

```bash
python3 scripts/care_v6_manifest.py \
  --archive    /path/to/CARE_To_Compare_v6.zip \
  --workdir    /path/to/already_extracted_root \
  --output-dir ./manifest_out \
  --skip-extract
```

### 1.4 檢查自動偵測是否正確（不可略過）

腳本會自動猜測哪一欄是 timestamp、哪一欄是風速、哪一欄是標籤。
**沒有人在雲端看過 CARE v6 的真實內部結構**，所以這些猜測必須由你確認。

打開 `manifest_out/detection_notes.json`，檢查兩件事：

1. 隨機抽 3～5 筆 `status=detected` 的項目，對照原始檔案，確認欄位猜對了。
2. 看有沒有 `status=undetected` 的項目 —— 這些 case 會被排除在所有統計之外
   （不會被靜默亂猜，但也不會被計入）。數量多的話要處理。

**如果欄位猜錯或 case 檔案根本沒被找到**，用旗標覆寫後重跑：

```bash
python3 scripts/care_v6_manifest.py \
  --archive    /path/to/CARE_To_Compare_v6.zip \
  --workdir    /path/to/extract_dir \
  --output-dir ./manifest_out \
  --skip-extract \
  --case-glob      "**/datasets/*/*.csv" \
  --timestamp-col  "time_stamp" \
  --wind-speed-col "wind_speed_3_avg" \
  --label-col      "status_type_id"
```

（上面的欄位名稱只是**範例**，請換成你在真實檔案裡看到的名稱。）

### 1.5 Phase 1 回傳清單

請把這些回傳：

- 1.1 算出的 **SHA-256 值與檔案 size**
- `manifest_out/manifest_summary.md` ← 最重要，人類可讀的總表
- `manifest_out/g1_archive_integrity.json`
- `manifest_out/g2_case_inventory.json`
- `manifest_out/g4_schema_quality.json`
- `manifest_out/g6_leakage_gate.json`
- `manifest_out/detection_notes.json`
- `manifest_out/g3_case_metadata.csv` 的**前 20 行**（不用整份）
- 你在 1.4 做的抽查結論：欄位猜對了嗎？有幾個 undetected？

**請不要回傳**：解壓後的資料、完整的 `g3_case_metadata.csv`、
`g5_regime_bin_matrix.csv`（可能很大）。需要時我們再另外要。

> **Phase 1 完成後請先停下來等回覆。** D0 若沒過，後面的 C0–C6 沒有意義。

---

## Phase 2 — 四份證據檔（D0 通過後）

C2/C3/C5 三個 gate 無法從資料本身推導，必須由你提供證據檔。
先產生空白樣板：

```bash
python3 scripts/base_scorer_compatibility_check.py --emit-templates ./evidence_MD_2022
python3 scripts/base_scorer_compatibility_check.py --emit-templates ./evidence_MainBearing_2026
```

```powershell
python scripts/base_scorer_compatibility_check.py --emit-templates .\evidence_MD_2022
python scripts/base_scorer_compatibility_check.py --emit-templates .\evidence_MainBearing_2026
```

每個目錄會產生四個檔案：

| 檔案 | Gate | 要填什麼 |
|---|---|---|
| `signal_map.json` | C0 | 六個核心訊號各自對應到 score CSV 的哪一欄，**且必須寫單位** |
| `artifact_manifest.json` | C2 | 實作來源、版本/commit、參數出處、凍結產物的 SHA-256 |
| `fit_provenance.json` | C3 | fit 用的 partition、fit 期間開過哪些檔案+雜湊、排除的標籤欄、驗證方式與驗證者 |
| `freeze_receipt.json` | C5 | 環境、seed、config SHA-256、artifact SHA-256 |

### ⚠️ 最容易出事的一點

`fit_provenance.json` 的 **`files_read_during_fit` 必須在 fit 當下記錄，事後補不回來**。

意思是：在你跑 scorer 的 fit 步驟時，就要同步記下它開過哪些檔案。
最簡單的做法是在 fit 前後包一層記錄，例如：

```python
# 在你的 scorer 訓練腳本裡
import hashlib, json

opened = []
def tracked_open(path):
    with open(path, 'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()
    opened.append({"path": str(path), "sha256": h})
    return path

# ... fit 過程中，每次讀檔都走 tracked_open(...) ...
# fit 結束後
json.dump(opened, open("files_read_during_fit.json", "w"), indent=2)
```

`fit_partition` 欄位的字串**必須包含 "normal"**，且必須真的是 CARE 的
normal reference partition —— 這是 D1 標籤防火牆的底線，gate 會檢查。

---

## Phase 3 — 產生 score stream（你的實作，我無法代勞）

兩個 frozen base scorer 的實作是你的，我只能給**檔案格式契約**。

### 3.1 檔案格式要求

每個 case 一個 CSV，**檔名就是 case_id**（要和 `g3_case_metadata.csv` 的
`case_id` 完全一致）：

```
scores_MD_2022_run1/
    <case_id_1>.csv
    <case_id_2>.csv
    ...
```

每個 CSV 必須包含：

- 一個 **timestamp 欄**（ISO 8601 最佳，例如 `2026-01-01T00:10:00`）
- **六個核心訊號欄**（active power / wind speed / rotor speed /
  main bearing temp / pitch angle / ambient temp），欄名由你決定，
  但要寫進 `signal_map.json`
- 一個 **score 欄**（scorer 輸出的純量 s_t）

> 若 case_id 不方便放檔名，可以放在 CSV 的某一欄，執行時加
> `--case-id-from column --case-id-col <欄名>`。

### 3.2 兩次獨立執行（C5 需要）

**跑兩次，輸出到兩個不同目錄**：

```
scores_MD_2022_run1/
scores_MD_2022_run2/
```

「獨立」的意思是重新啟動一次完整流程，不是複製目錄。複製目錄會通過
bit-identical 比對，但那是假的證據。

### 3.3 執行前先固定執行緒數（重要）

多執行緒的浮點歸約順序不固定，會讓本來確定性的計算產生微小差異。
**兩次執行都要設定**：

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export PYTHONHASHSEED=0
```

```powershell
$env:OMP_NUM_THREADS=1
$env:MKL_NUM_THREADS=1
$env:OPENBLAS_NUM_THREADS=1
$env:PYTHONHASHSEED=0
```

---

## Phase 4 — 執行 C0–C6 gate

### 4.1 MD_2022（先用 bit_identical）

```bash
python3 scripts/base_scorer_compatibility_check.py \
  --workdir           /path/to/extract_dir \
  --g2-inventory      ./manifest_out/g2_case_inventory.json \
  --g3-case-metadata  ./manifest_out/g3_case_metadata.csv \
  --score-dir         ./scores_MD_2022_run1 \
  --score-dir-run2    ./scores_MD_2022_run2 \
  --scorer-name       "MD_2022" \
  --output-dir        ./compat_out_MD_2022 \
  --timestamp-col     <你的 timestamp 欄名> \
  --score-col         <你的 score 欄名> \
  --signal-map        ./evidence_MD_2022/signal_map.json \
  --artifact-manifest ./evidence_MD_2022/artifact_manifest.json \
  --fit-provenance    ./evidence_MD_2022/fit_provenance.json \
  --freeze-receipt    ./evidence_MD_2022/freeze_receipt.json \
  --determinism-mode  bit_identical
```

```powershell
python scripts/base_scorer_compatibility_check.py `
  --workdir           C:\path\to\extract_dir `
  --g2-inventory      .\manifest_out\g2_case_inventory.json `
  --g3-case-metadata  .\manifest_out\g3_case_metadata.csv `
  --score-dir         .\scores_MD_2022_run1 `
  --score-dir-run2    .\scores_MD_2022_run2 `
  --scorer-name       "MD_2022" `
  --output-dir        .\compat_out_MD_2022 `
  --timestamp-col     <你的 timestamp 欄名> `
  --score-col         <你的 score 欄名> `
  --signal-map        .\evidence_MD_2022\signal_map.json `
  --artifact-manifest .\evidence_MD_2022\artifact_manifest.json `
  --fit-provenance    .\evidence_MD_2022\fit_provenance.json `
  --freeze-receipt    .\evidence_MD_2022\freeze_receipt.json `
  --determinism-mode  bit_identical
```

### 4.2 MainBearing_2026

同上，把 `MD_2022` 換成 `MainBearing_2026`、路徑換成對應目錄。

**若主軸承框架含隨機初始化或平行歸約導致 bit_identical 失敗**，改用
已簽核的 tolerance 設定（見《C5 決定》文件）：

```bash
  --determinism-mode tolerance \
  --tolerance 1e-6
```

> **不要因為 bit_identical 失敗就直接改 tolerance。** 先看 gate 輸出的
> `max_abs_diff`。若差異 > 1e-3，那是真的不確定性（需要修，不是放寬容忍值）；
> 1e-6 這個值是事前決定的，不是看到結果才調的。

### 4.3 判讀結果

`gate_status` 只有 `PASS` 才算過。process 的 exit code：

| exit code | 意義 |
|---|---|
| `0` | PASS |
| `1` | FAIL —— 有 gate 明確失敗，看 `problems` 欄位 |
| `2` | UNVERIFIED —— 有 gate 缺證據，通常是四份證據檔沒填完 |
| `3` | 指令或檔案讀寫錯誤 |

查看 exit code：

```bash
echo $?
```

```powershell
$LASTEXITCODE
```

### 4.4 Phase 4 回傳清單

每個 scorer 各一份：

- `compat_out_<scorer>/compatibility_summary.json` ← 最重要
- `compat_out_<scorer>/output_receipt.json`
- 終端機看到的 `gate_status=` 那行與 exit code

**請不要回傳** `per_case_c0_c6.json` 與 `evaluability_masks/` 整個目錄
（case 數多的話會很大）。若某個 gate FAIL，我們再針對那幾個 case 要細節。

---

## 常見狀況

**Q: `--case-glob` 怎麼寫才對？**
先看解壓後的目錄長什麼樣，找到 case 檔案的相對路徑，把中間可變的部分換成 `*`。
例如檔案在 `extract_dir/CARE/datasets/WindFarmA/case_0001.csv`，
就寫 `--case-glob "**/datasets/*/*.csv"`。

**Q: C4 FAIL，說 `unexpected_case_ids` 一堆。**
表示 score CSV 的檔名和 `g3_case_metadata.csv` 的 `case_id` 對不起來。
看 `missing_case_ids` 和 `unexpected_case_ids` 的差異模式 —— 通常是
補零位數不同（`case_1` vs `case_0001`）或多了副檔名前綴。

**Q: C1 FAIL，說 `non_evaluable_fraction` 超過 30%。**
先不要急著調門檻。這代表該 case 有超過三成的時間處於 >3 小時的資料缺口，
可能是真的長期停機。把該 case 的 `non_evaluable_fraction` 回傳，
30% 這個門檻本來就預計在看到真實缺值分布後回頭校準。

**Q: 磁碟不夠解壓。**
可以用 `--skip-extract` 搭配外接硬碟上的既有解壓目錄，
`--workdir` 指向那裡即可，腳本不會再解壓一次。

---

*對應 gate 版本：`c0c6-gate-v2.0`。手冊有更新時會同步改版本號。*
