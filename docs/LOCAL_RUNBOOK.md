# 本機執行手冊 v1.1 — D0 manifest、C0–C6 gate 與實驗

給有 CARE v6 資料的本機執行者。雲端協作者無法處理 5.5GB archive，這份手冊把
每一步的指令寫死，執行者不需要自己組指令。

> **先讀 [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)。** 那份文件說明專案現在
> 卡在哪、哪些資料事實已經確立、哪些參數已簽核不得更動。這份手冊只講怎麼跑。

**分階段執行，不要一次做完。** 每個 Phase 結束就把指定的檔案回傳，
確認無誤再進下一個 Phase。Phase 1 失敗的話 Phase 3 做再多都是白做。

指令同時提供 **Linux/macOS (bash)** 與 **Windows (PowerShell)** 兩種寫法。
Windows 使用者請用 PowerShell，不要用 CMD（換行接續符號不同）。

---

## Phase 0 — 環境準備（5 分鐘）

### 0.1 取得程式

```bash
git clone https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
```

```powershell
git clone https://github.com/dofliu/AIPaper_Cowork_Wind.git
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

在碰真實資料之前，先確認**整套**工具在你的環境行為正確。十二支測試一次跑完：

```bash
for t in scripts/selftest_*.py; do echo "== $t"; python3 "$t" | tail -2; done
```

```powershell
Get-ChildItem scripts\selftest_*.py | ForEach-Object {
  Write-Host "== $($_.Name)"; python $_.FullName | Select-Object -Last 2 }
```

**預期**：十二支全部以 `ALL SELF-TESTS PASSED` 結尾，合計 **344 checks**。

| 測試 | checks |
|---|---|
| `selftest_c0_c6_gate.py` | 59 |
| `selftest_sensor_identification.py` | 21 |
| `selftest_end_to_end.py` | 20 |
| `selftest_w1_acas.py` | 17 |
| `selftest_regime_conditional.py` | 16 |
| `selftest_md2022.py` | 40 |
| `selftest_online_baselines.py` | 13 |
| `selftest_signal_map_builder.py` | 48 |
| `selftest_unit_consistency.py` | 29 |
| `selftest_earliness_metric.py` | 28 |
| `selftest_absorption_policies.py` | 26 |
| `selftest_freeze_lockin_diagnostic.py` | 27 |

任何一支不是 0 failed，**先停下來**把完整輸出回傳，不要繼續。這代表工具在
你的環境行為與雲端不同，之後所有結果都不可信。

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

> **2026-08-15 更新：MD_2022 的這一整節完全不用手做。**
> `base_scorer_md2022.py` 在 fit 當下就會把**四份**證據檔全部寫進
> `--evidence-dir`：`fit_provenance.json`、`artifact_manifest.json`、
> `freeze_receipt.json`，以及 `signal_map.json`。
>
> 最後一份特別說明：C0 要的 signal map 指的是 **score CSV 的欄名**，
> 和 builder 產出的那份（指向 archive 原始欄名）是兩份不同的東西。
> 手寫第二份正是操作者最容易填到不存在欄位的地方，所以改由評分器
> 依「實際寫出去的欄」自動產生，單位則從 builder 那份沿用。
>
> 以下手動流程只剩 **MainBearing_2026** 需要。

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

## Phase 3 — 產生 score stream

> **2026-08-15 更新：Base Scorer 1（MD_2022）已由雲端這側實作完成，
> 不再是你的工作。** 先前把它列為「你的實作，我無法代勞」是誤派。
> 執行方式見 3.0。
>
> **Base Scorer 2（MainBearing_2026）**仍然只能由你這側提供 —— 它需要
> 主軸承 SCADA 框架論文的實作，雲端這側沒有。3.1 之後的檔案格式契約
> 是給它用的。

### 3.0 Base Scorer 1（MD_2022）— 三行指令

**先做 signal map。** 三個風場各一份，依已簽核的選點決定
（51/52 取平均、Farm C 其餘取平均、Farm A 風速取 header 的 `wind_speed_3_avg`）：

```bash
python3 scripts/care_v6_signal_map_builder.py \
  --workdir    /path/to/extract_dir \
  --output-dir ./signal_map_out \
  --average-ties \
  --header-override "A:wind_speed=wind_speed_3_avg" \
  --override-unit  "m/s" \
  --pick "C:active_power=power_6" \
  --pick "C:wind_speed=wind_speed_236" \
  --unit-override "A:ambient_temperature=degC" \
  --unit-override "A:pitch_angle=deg" \
  --unit-override "B:main_bearing_temperature=degC" \
  --exclude-sensor "C:rotor_speed=sensor_146,sensor_147" \
  --unit-override "active_power=p.u." \
  --not-available "A:main_bearing_temperature=Farm A's feature_description.csv names no main or rotor bearing channel; only gearbox HSS and generator DE/NDE bearings exist, which are different components." \
  --ratified-by "劉老師" --ratified-on "2026-08-15"
```

```powershell
python scripts\care_v6_signal_map_builder.py `
  --workdir    C:\path\to\extract_dir `
  --output-dir .\signal_map_out `
  --average-ties `
  --header-override "A:wind_speed=wind_speed_3_avg" `
  --override-unit  "m/s" `
  --pick "C:active_power=power_6" `
  --pick "C:wind_speed=wind_speed_236" `
  --unit-override "A:ambient_temperature=degC" `
  --unit-override "A:pitch_angle=deg" `
  --unit-override "B:main_bearing_temperature=degC" `
  --exclude-sensor "C:rotor_speed=sensor_146,sensor_147" `
  --unit-override "active_power=p.u." `
  --not-available "A:main_bearing_temperature=Farm A's feature_description.csv names no main or rotor bearing channel; only gearbox HSS and generator DE/NDE bearings exist, which are different components." `
  --ratified-by "劉老師" --ratified-on "2026-08-15"
```

**兩件事在這道指令裡一起解決了，不需要再手改 JSON。**

**（一）Farm A 沒有主軸承通道。** 這不是缺陷，是該風場的事實——字典裡只有
齒輪箱與發電機軸承（三個），工具依設計拒絕拿它們冒充主軸承。
`--not-available` 會直接寫出 C0 要的 ratified 宣告區塊。
C0 gate 接受這個宣告；**靜默缺席仍然會 FAIL**，所以不能省。
（若該訊號其實有解出來，工具會拒絕覆寫並告訴你，除非加
`--force-not-available`。）

**（二）Farm A 字典裡的度數符號是壞的。** 這不是我們讀錯編碼——
**檔案裡的位元組本身就已經被破壞了**，存的是 U+FFFD 的 UTF-8 位元組。
用 utf-8 讀會得到 U+FFFD，用 cp1252 讀會得到字面上的 `ï¿½`。原字元
已經救不回來。所以工具現在會把這種單位標成 `UNREADABLE_IN_SOURCE`
而**不是**假裝它是真的單位寫進 C0 map，再由 `--unit-override` 明確宣告。

> 若你在輸出看到某個單位是 `UNREADABLE_IN_SOURCE` 而上面指令沒涵蓋，
> 照樣加一條 `--unit-override "風場:訊號=單位"`。單位是 C0 的必要欄位，
> 而且 Phase 5.1 的單位一致性檢查靠它。

**接著跑評分器。** 每個風場、每個 run 各一次（run1 / run2 是 C5 要的兩次
獨立執行，不是複製目錄）：

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONHASHSEED=0
for FARM in A B C; do
  for RUN in 1 2; do
    python3 scripts/base_scorer_md2022.py \
      --workdir      /path/to/extract_dir \
      --farm         "Wind Farm $FARM" \
      --signal-map   ./signal_map_out/signal_map_Wind_Farm_$FARM.json \
      --output-dir   ./scores_MD_2022_run$RUN \
      --evidence-dir ./evidence_MD_2022_run$RUN
  done
done
```

```powershell
$env:OMP_NUM_THREADS=1; $env:MKL_NUM_THREADS=1
$env:OPENBLAS_NUM_THREADS=1; $env:PYTHONHASHSEED=0
foreach ($FARM in "A","B","C") {
  foreach ($RUN in 1,2) {
    python scripts\base_scorer_md2022.py `
      --workdir      C:\path\to\extract_dir `
      --farm         "Wind Farm $FARM" `
      --signal-map   .\signal_map_out\signal_map_Wind_Farm_$FARM.json `
      --output-dir   .\scores_MD_2022_run$RUN `
      --evidence-dir .\evidence_MD_2022_run$RUN
  }
}
```

三個風場寫進同一個 `scores_MD_2022_run1/`，因為 case_id 全域唯一。
輸出欄位固定是 `timestamp` / `wind_speed` / `anomaly_score`，後面接六個
`signal_*` 特徵欄，**三個風場一致**——這是評分器刻意正規化的，原始檔在
Farm A 叫 `wind_speed_3_avg`、Farm B 叫 `wind_speed_61_avg`、Farm C 叫
`wind_speed_236_avg`，不正規化的話 Phase 5 沒辦法用單一欄名跨風場跑。

> 特徵欄之所以加 `signal_` 前綴，是因為不加的話 `wind_speed` 會在表頭
> 出現兩次，而 `csv.DictReader` 只保留**後**一個。兩者在關鍵處不同：
> 某個感測器掉線、特徵向量不完整的那些列，風速其實量得好好的，但特徵
> 那一份是空的。實測 50 列掉線資料，50 列全被下游讀成空風速——那會讓
> 它們落不進正確的風速分箱，直接偏誤本論文主張的條件覆蓋率結果。
> 已修正並以測試釘住（`selftest_md2022.py` T7）。

`--evidence-dir` 裡的四份 C0–C6 佐證是 fit 當下寫的，不用手填。
每個風場另外寫一份 `scorer_summary_<farm>.json`（含 Phase 5.1 要的訊號範圍）。

### 3.1 檔案格式要求（給 MainBearing_2026）

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

**gate 分三次跑，每個風場一份，而且一定要加 `--farm`。**

三個風場的 signal map 不同（Farm A 沒有主軸承通道，以 `not_available` 宣告），
一次 gate 只檢查一份 map，所以它必須只看該風場的案子。

`--farm` 依 `g3_case_metadata.csv` 的 `farm_id` 限縮案子集合，run1 與 run2
兩側都套用。**少了它，score 目錄裡三個風場的案子會全部拿去比對同一份 map，
結果一定失敗**——而且失敗方向會隨你指哪一份 map 而反轉：用 Farm A 的 map，
B/C 的案子多出一欄；用 B 或 C 的 map，Farm A 的 22 案少一欄。
2026-08-15 兩個方向都實測過。

```powershell
foreach ($FARM in "A","B","C") {
Write-Host "== C0-C6 Farm $FARM"
python scripts/base_scorer_compatibility_check.py `
  --workdir           $WD `
  --g2-inventory      .\manifest_out\g2_case_inventory.json `
  --g3-case-metadata  .\manifest_out\g3_case_metadata.csv `
  --farm              "Wind Farm $FARM" `
  --score-dir         .\scores_MD_2022_run1 `
  --score-dir-run2    .\scores_MD_2022_run2 `
  --scorer-name       "MD_2022_Wind_Farm_$FARM" `
  --output-dir        .\compat_out_MD_2022_$FARM `
  --timestamp-col     timestamp `
  --score-col         anomaly_score `
  --signal-map        .\evidence_MD_2022_run1\signal_map_Wind_Farm_$FARM.json `
  --artifact-manifest .\evidence_MD_2022_run1\artifact_manifest_Wind_Farm_$FARM.json `
  --fit-provenance    .\evidence_MD_2022_run1\fit_provenance_Wind_Farm_$FARM.json `
  --freeze-receipt    .\evidence_MD_2022_run1\freeze_receipt_Wind_Farm_$FARM.json `
  --determinism-mode  bit_identical
Write-Host "  exit=$LASTEXITCODE"
}
```

> **這段先前留著 `<你的 timestamp 欄名>` 這類角括號佔位符。**
> 在 PowerShell 裡 `<` 是保留運算子，貼上去會直接語法錯誤——
> 這個缺陷 v3.7 已在 Phase 5 修過，Phase 4 漏了，現已補上。
>
> 欄名不需要代換：評分器輸出時已把三個風場正規化成同一組
> （`timestamp` / `wind_speed` / `anomaly_score` + `signal_*`），
> 所以這裡就是 `timestamp` 與 `anomaly_score`，三場通用。
> 證據取 run1 那份即可（run1／run2 的四份佐證內容相同，
> gate 比對的是兩份 score stream，不是兩份證據）。

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


---

## Phase 5 — 產生實驗數字

前四個 Phase 產出的是**閘門證據**，不是實驗結果。這個 Phase 才開始有數字。

### 5.0 先確認前置

| 前置 | 狀態 |
|---|---|
| D0 | ✅ 2026-08-15 關閉 |
| 三份 signal map | Phase 2，含 Farm A 的 `not_available` 區塊 |
| 單位一致 | 見 5.1 |
| score stream ×2 runs | Phase 3.0（MD_2022 已可一鍵產生）；MainBearing_2026 仍待你這側 |
| C0–C6 | Phase 4，兩個 scorer 各一份 |

**C0–C6 未通過之前不要跑 Phase 5。** 閘門存在的意義就是擋在這裡。

### 5.1 單位確認（一道指令，不用自己比對）

三個風場的單位標示不一致：溫度 Farm A/B 是 `degC`、Farm C 是 `Celsius`；
轉速 Farm A/B 是 `rpm`、Farm C 是 `1/min`。字面不同，實質**應該**相同。

但只要有一個其實不同（華氏、rad/s、標么值），Mahalanobis 的共變異數就會被
靜靜扭曲——不會報錯，只會給出錯的分數，而跨風場的主張就跟著錯。

`base_scorer_md2022.py` 在評分那一趟就已經把每個訊號的 p01/p50/p99 記進
`scorer_summary_<farm>.json`，所以這一步不必再讀一次 archive：

```bash
python3 scripts/check_unit_consistency.py ./scores_MD_2022_run1
```

```powershell
python scripts\check_unit_consistency.py .\scores_MD_2022_run1
```

exit code 0 表示各風場一致且落在物理合理範圍；1 表示有不一致，輸出會指出
是哪個訊號、哪兩個風場、差多少。**exit code 不是 0 就不要進 5.2。**

> `active_power` 不做跨風場中位數比較——額定功率本來就隨機型不同，
> 拿它比會是假警報。它只列出範圍供你看。

### 5.2 執行實驗（一個設定檔，一道指令）

> **2026-08-15 更新：本節先前列出的指令含 `<分數欄>` 這類角括號佔位符，
> 在 PowerShell 會直接語法錯誤（`<` 是保留運算子）。那是交付面的缺陷。
> 現在改成設定檔驅動，不需要任何手動代換。**

先產生設定檔：

```bash
python3 scripts/run_pipeline.py --emit-config pipeline_config.json
```

```powershell
python scripts\run_pipeline.py --emit-config pipeline_config.json
```

**只有 `paths` 區塊需要你填**，欄位名稱已經預先填好
（`anomaly_score` / `wind_speed` / `timestamp`，即 3.0 評分器的輸出）：

```json
"paths": {
  "g3_case_metadata": "./manifest_out/g3_case_metadata.csv",
  "event_info_root":  "填這裡：解壓後的 CARE v6 根目錄，底下有 Wind Farm A/B/C",
  "output_root":      "./experiments"
}
```

`scorers[0].score_dir` 填 `./scores_MD_2022_run1`。
`MainBearing_2026` 若尚未就緒，把整個項目留著 `FILL_ME` 即可，會被跳過。

**`experiment` 區塊不要動**，已簽核值都預先填好了，包含 D1/D6 的兩項處置：

```json
"exclude_cases": ["32", "56", "72", "87"],
"trim_cases":    {"93": "2023-08-24T13:00:00"}
```

> **裁切為什麼不能省。** case 93（normal）與 case 33（anomaly）是 Farm C
> 同一台機組 43，兩者評估視窗重疊 0.12 天——**同一台機、同一段期間、
> 相反標籤**。case 33 的視窗自 `2023-08-24T13:00:00` 開啟，所以 93 從那一刻
> 起的列必須丟棄。整案排除會白白丟掉 23 天可用資料，所以裁切而非排除。
>
> 這個裁切先前**只是設定檔裡的一句註解，沒有任何程式套用它**，而且不會
> 報錯——case 93 會被完整評估，把重疊帶進正常案例那側的誤報統計。
> 2026-08-16 已實作為 `--trim-case`，並記錄在 `evaluation.json` 的
> `trimmed_cases`（含丟棄列數）。跑完請確認那個欄位不是空的。

### 5.3 先預檢，再實跑

```powershell
python scripts\run_pipeline.py --config pipeline_config.json --preflight-only
```

看到 `preflight OK -- the pipeline would run` 才往下跑。預檢會擋掉路徑錯誤、
欄名對不上、`FILL_ME` 沒填完這類問題，不必等跑到一半才發現。

```powershell
python scripts\run_pipeline.py --config pipeline_config.json
```

### 5.4 這一步要跑多久（重要，否則會以為當機）

實測（一個 case 約 5.4 萬列，95 案）：

| 步驟 | 單一 case | 95 案 | 說明 |
|---|---|---|---|
| **W1-ACAS** | **約 51 秒** | **約 80 分鐘** | **瓶頸**，但與 α 無關，整個 scorer 只跑一次 |
| 本方法 RCC | 2.7 秒 | 約 4 分鐘 | 每個 α 各一次 |
| static/ACI/DtACI | 1.4 秒 | 約 2 分鐘 | 每個 α 各一次 |

所以整體約 **1.5～2 小時**，而且**跑三個 α 只比跑一個多約 15 分鐘**
——因為八成的時間花在只跑一次的 W1-ACAS 上。沒有理由為了省時間只跑一個 α。

> W1-ACAS 每處理完一個 case 就會印一行進度。若你看不到那些行，代表你的
> 版本早於 2026-08-16：當時 `run_pipeline` 用 `capture_output=True` 把子程序
> 輸出全吞掉，長步驟因此一小時毫無動靜，與當機無法分辨。已改為即時串流。

**先做預檢**（幾秒鐘，會逐一核對每個路徑與每個欄名是否真的在 CSV 裡）：

```bash
python3 scripts/run_pipeline.py --config pipeline_config.json --preflight-only
```

```powershell
python scripts\run_pipeline.py --config pipeline_config.json --preflight-only
```

預檢過了再正式跑：

```bash
python3 scripts/run_pipeline.py --config pipeline_config.json
```

```powershell
python scripts\run_pipeline.py --config pipeline_config.json
```

一道指令會依序跑完：提出方法（regime-conditional calibration）、W1-ACAS、
static / ACI / DtACI，以及共同評估尺規，三個 α（0.01 主要、0.05、0.001）
各一輪。**α 的三個值來自已簽核的參數協定，不是掃描**；`--max-past` 與
`W` 都已凍結為 1440，設定檔裡不要改。

`MainBearing_2026` 僅 Farm B/C（D5 範圍裁決）。

### 5.3 回傳什麼

- `experiments/comparison_index.json` ← 最重要，指向所有比較表
- 各 α 的 `comparison_*.json`
- `w1acas_*/w1acas_summary.json`、`baselines_*/baselines_summary.json`
- **不要**回傳每案的逐列 CSV，那會很大；需要時再針對特定 case 要

### 5.4 一件尚未就緒的事（誠實記錄）

**CARE 原始 adaptive threshold 缺席。** 它在評估契約的基線清單裡，但其定義在 CARE 論文中，本專案尚未讀取。archive 的 README.txt 可能有，但沒人萃取過。

```powershell
python scripts\baselines_online_calibration.py --list-missing
```

會把這個缺席以機器可讀形式印出來。**猜測競品的方法再贏過它，比沒有這個基線更糟。** 解法是先從 CARE 論文或 README 萃取定義、逐字記入 Drive 文件，再依該文字實作。

---

*對應 gate 版本：`c0c6-gate-v2.0`。手冊有更新時會同步改版本號。*

*v1.1（2026-08-15）：Phase 0.3 改為八支測試共 163 checks；Phase 2 註明
MD_2022 的三份佐證已自動產生；Phase 3.0 新增 Base Scorer 1 的完整指令
（先前誤列為「你的實作」）；Phase 5.2 改為設定檔驅動，移除所有角括號
佔位符；Phase 5.4 刪去「我們自己的方法還沒實作」——已實作。
另修正評分器輸出表頭 `wind_speed` 重複的缺陷（md2022-v1.1），並改由評分器
自動產生 C0 的 signal_map.json。*

*v1.1a（2026-08-15）：修正 signal map builder 在「有訊號取平均」的風場崩潰
（`KeyError: 'column'`——平均出來的條目帶的是 `derived_from`，沒有 `column`）；
新增 `--not-available` 與 `--unit-override`，Phase 3.0 不再需要手改 JSON。*

*v1.1b（2026-08-15）：修正 `[FARM:]` 前綴用子字串比對的缺陷——`A` 會命中
三個風場（`farm` 這個字裡有 a），導致 Farm A 的 `--header-override` 覆蓋掉
Farm B/C 的風速欄位。未解出的 active_power / wind_speed 現在會直接讀 case
檔表頭，列出真實欄位與可直接貼上的旗標。*

*v1.1c（2026-08-15）：Farm A 的 `active_power` 原本解到 power_29
「Possible grid active power」——那是 IEC 61400-24 意義下的**可能發電量**
（模型值），不是實測。改為實測通道優先，Farm A 轉為 power_30「Grid power」。
新增 `check_power_channel.py` 供本機核對。修正單位建議對 pitch_angle
誤建議 degC。*
