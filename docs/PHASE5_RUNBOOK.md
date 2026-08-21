# Phase 5 執行手冊 — 給執行者的完整清單

**版本 1.0 — 2026-08-20　　適用協定：`detection-horizon-v1.0`（R27）**

這份文件是自足的：照著做完，不需要先讀懂整個專案。
但**第七節「絕對不要做的事」請務必先讀完再開始**，那一節列的每一項
在本專案都真的發生過，而且**沒有一項會報錯**。

---

## 零、你要做的事，一句話

> 專案的實驗數字**已經算完並存在版控裡**，唯獨缺**提前預警天數（lead time）**。
> 缺的原因只有一個：算 lead time 需要 CARE v6 裡的 `event_info.csv`，
> 而那個檔案不在版控裡（資料集本身太大且有授權問題）。
>
> **你的工作是：在有 CARE v6 資料的機器上，把評估步驟重跑一次。**

**你不需要重跑異常分數器、不需要重跑校準層、不需要重跑任何基線。**
那些的逐案輸出全都已經在 repo 裡了。這一點很重要——
以為要重跑全部，會白花一到兩小時，而且**會覆蓋掉唯一一份既有輸出**。

---

## 一、需要準備的材料

### 1.1 必備

| 材料 | 說明 | 從哪裡來 |
|---|---|---|
| **CARE v6 資料集** | 只需要裡面的 **`event_info.csv`**（每個風場一份） | 劉老師處；或 Zenodo DOI `10.5281/zenodo.14006163`（CC BY-SA 4.0） |
| **本專案 repo** | 公開，不需申請權限 | `https://github.com/dofliu/AIPaper_Cowork_Wind` |
| **Python 3.8 以上** | **不需要安裝任何套件**，全部用標準函式庫 | — |

> **關於 CARE v6 的大小**：完整 archive 是 5.5 GB，解壓後約 15–20 GB。
> **但這一步只需要三個 `event_info.csv`**，每個只有幾 KB。
> 如果機器上已經有解壓好的資料，直接指過去就好；
> 如果沒有，**只解壓那三個檔案就夠了**，不必解整包。

### 1.2 磁碟空間

| 項目 | 需要 |
|---|---|
| clone repo（含歷史與既有輸出） | **約 4.2 GB**（實測） |
| 本次產出 | 約 200 MB |
| CARE v6（若要完整解壓） | 20 GB |
| **最少** | **5 GB**（只取 `event_info.csv` 的話） |

### 1.3 不需要準備的

- ❌ 不需要 GPU
- ❌ 不需要 conda／virtualenv／pip install
- ❌ 不需要 Base Scorer 2（MainBearing_2026）——那是另一件事，與本手冊無關
- ❌ 不需要重新產生 signal map、不需要重跑 C0–C6 閘門

---

## 二、環境準備

```bash
git clone https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
python3 --version        # 需要 3.8 以上
```

```powershell
git clone https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
python --version
```

> Windows 上如果 `python` 指到 Microsoft Store 的空殼，改用 `py -3`。
> **請用 PowerShell，不要用 CMD**——換行接續符號不同，指令會壞掉。

---

## 三、步驟 0：先跑自我測試（不可略過）

在碰真實資料之前，先確認整套工具在**你的環境**行為正確。

```bash
for t in scripts/selftest_*.py; do echo "== $t"; python3 "$t" | tail -2; done
```

```powershell
Get-ChildItem scripts\selftest_*.py | ForEach-Object {
  Write-Host "== $($_.Name)"; python $_.FullName | Select-Object -Last 2 }
```

**預期：十七支全部以 `ALL SELF-TESTS PASSED` 結尾，合計 498 checks，0 failed。**

支數與 checks 數以 `docs/LOCAL_RUNBOOK.md` Phase 0.3 的表為準
（那份會隨新增工具更新，本手冊可能落後）。

> **任何一支不是 0 failed，請立刻停下來**，把完整輸出回報，不要繼續。
> 那代表工具在你的環境行為與雲端不同，之後所有結果都不可信。
> 這不是形式主義：本專案發生過「同一支程式在兩個環境給出不同結果」的情況。

---

## 四、步驟 1：找到 `event_info.csv`

評估器會**遞迴**搜尋你指定目錄底下所有的 `event_info.csv`，
所以目錄結構不必完全照原樣，只要那些檔案在裡面就好。

典型位置（解壓後的 CARE_To_Compare）：

```
CARE_To_Compare/
├── Wind Farm A/
│   ├── event_info.csv      ← 需要
│   └── datasets/           ← 不需要（很大）
├── Wind Farm B/
│   └── event_info.csv      ← 需要
└── Wind Farm C/
    └── event_info.csv      ← 需要
```

**確認一下檔案內容長這樣**（分隔符號是分號 `;`，不是逗號）：

```
asset;event_id;event_label;event_start;event_start_id;event_end;event_end_id;event_description
```

關鍵欄位是 **`event_id`** 與 **`event_start`**。前者對應 case 編號，
後者是提前預警天數的計算起點。

> **只想解壓這三個檔案的話**（Linux/macOS）：
> ```bash
> unzip -j CARE_To_Compare_v6.zip "*/event_info.csv" -d ./event_info_only
> ```
> 這樣三個檔案會平鋪在同一層——**沒關係**，遞迴搜尋照樣找得到，
> 但這樣就分不出是哪個風場的了，所以**建議保留目錄結構**：
> ```bash
> unzip CARE_To_Compare_v6.zip "*/event_info.csv" -d ./care_event_info
> ```

---

## 五、步驟 2：先預演，再實跑

### 5.1 預演（幾秒鐘，不會寫任何檔案）

```bash
python3 scripts/run_phase5_evaluation.py \
  --event-info-root /你的路徑/CARE_To_Compare \
  --output-root ./experiments/phase5_2026-08-21 \
  --dry-run
```

```powershell
python scripts\run_phase5_evaluation.py `
  --event-info-root C:\你的路徑\CARE_To_Compare `
  --output-root .\experiments\phase5_2026-08-21 `
  --dry-run
```

**預期輸出開頭：**

```
event_info.csv found in 3 location(s): Wind Farm A, Wind Farm B, Wind Farm C
plan: 3 alphas x 5 horizons = 15 runs
horizons come from R27 (detection-horizon-v1.0); primary is 14 days
```

**看到 `found in 3 location(s)` 才往下走。**
若看到 `no event_info.csv anywhere under ...`，是路徑指錯了，回到步驟 1。

> `--output-root` 的日期請改成**你實際執行的日期**，不要照抄。

### 5.2 實跑

把 `--dry-run` 拿掉，其餘完全相同：

```bash
python3 scripts/run_phase5_evaluation.py \
  --event-info-root /你的路徑/CARE_To_Compare \
  --output-root ./experiments/phase5_2026-08-21
```

**會跑 15 次**（3 個 α × 5 個偵測門檻）。

### 5.3 要跑多久（重要，否則會以為當機）

單次評估**實測 138 秒**（91 案、約 250 萬個評分點，雲端測試機）。
**15 次合計約 35 分鐘。** 一般桌機通常更快。

> 若你在別處看到「Phase 5 要跑 1.5–2 小時」，那是指**完整**流程
> （含分數器、校準層、W1-ACAS）。**你不跑那些**，見第零節。

**它每完成一次會印一行**，像這樣：

```
[ 1/15] alpha=0.01  H=h7        -> ./experiments/phase5_2026-08-21/a01_h7
[ 2/15] alpha=0.01  H=h10       -> ./experiments/phase5_2026-08-21/a01_h10
```

**看得到那些行就代表沒當機。** 單次約 2–3 分鐘，
若超過 10 分鐘完全沒有新行出現，再考慮中斷並回報。

> **中途失敗不會停下來。** 某一次失敗會印 `FAILED rc=...` 並繼續跑下一個，
> 最後彙總。這是刻意的：一次壞掉不該掩蓋其他十四次的狀態。

---

## 六、步驟 3：驗收（一道指令）

**不要用肉眼看 JSON。** 這一批有 15 個目錄，要確認的事項有 35 項，
而且每一項漏掉都不會報錯——只會產出「看起來完整、數字是錯的」結果。
所以有一支專門的驗收程式：

```bash
python3 scripts/verify_phase5_output.py ./experiments/phase5_2026-08-21
```

```powershell
python scripts\verify_phase5_output.py .\experiments\phase5_2026-08-21
```

**成功時會印：**

```
35 checks, 0 failed

Batch accepted. The 3 primary runs (H = 14 d) are the headline numbers;
the rest are the declared sweep and must be reported beside them.
```

**退出碼 0 才算完成。** 非 0 就把完整輸出回報，**不要自行繞過**。

### 它在檢查什麼（供你理解，不必自己做）

| # | 檢查 | 為什麼 |
|---|---|---|
| 1 | 15 個目錄齊備，各含 `evaluation.json` 與 `comparison.md` | 少一個就不是完整的掃描 |
| 2 | **lead time 不是 `null`** | **這是本批次存在的唯一理由**。若 `event_info.csv` 沒被讀到，評估器仍會 exit 0 並寫出完整的比較表 |
| 3 | 四個排除案 + case 93 裁切掉 **18 列** | 那個裁切曾經整整一天只存在於設定檔註解裡，沒有任何程式套用，也不報錯 |
| 4 | 91 案、47 個正常案例 | 準則 7：統計量一律連同分母呈現 |
| 5 | 三數字協定生效、pooled 可窮盡反算、基線的凍結欄是「結構性缺席」而非 0% | `0%` 會讓人以為「有機制但沒觸發」 |
| 6 | 每次執行的門檻與 R27 的身分標記正確，且不設限那一格有跑 | 最寬鬆的一格最難通過，必須在檯面上 |
| 7 | **誤報率沒有跑掉**（α=0.01：0.0036／4.9%／0.6819） | 本批次唯一該變的是 lead time。誤報率變了代表**別的東西也被改了** |
| 8 | `comparison.md` 含 `frozen %`、`FAR frozen`，且標明門檻身分 | 只報一個門檻正是 R27 要防的事 |

> 這支程式**只讀不算**。它通過表示評估器自己的輸出符合協定，
> 不是表示這支程式跟自己一致。

> **這支程式本身也被反向驗證過**：它的自我測試會刻意造出九種壞掉的批次
> （lead time 是 null、裁切沒生效、分母錯、誤報率跑掉⋯），逐一確認它**真的會拒絕**。
> 只會通過的驗收程式，比沒有驗收更糟——它把「沒人看過」變成「已經驗證」。

---

## 七、絕對不要做的事

以下每一項在本專案都真的發生過，而且**沒有一項會報錯**。

| ❌ 不要 | 為什麼 |
|---|---|
| **不要覆蓋 `experiments/MD_2022_a*_evaluation/`** | 那是目前**唯一**一份既有輸出。寫進新目錄（`phase5_<日期>/`），讓兩份並存可比對。 |
| **不要重跑分數器或校準層** | 逐案 CSV 已在版控裡。重跑要一到兩小時，而且若參數有任何差異，新舊數字就不可比了。 |
| **不要「只跑主要值 14 天」** | R27 明文規定主要值**必須連同宣告掃描一起呈報**。只報一個數字正是這個協定要防的事。 |
| **不要改任何已簽核參數** | α、6-of-18、W=1440、風速分箱、`min_bin_samples`=500 全部經劉老師簽核。要改必須先出裁決請求。 |
| **不要省略 `--trim-case` 或 `--exclude-cases`** | runner 會自動帶上，所以**不要自己拼指令**。手拼漏掉不會報錯，只會讓誤報統計混進重疊資料。 |
| **不要在 15 次沒全過的情況下自行分析** | 部分結果看起來一樣正常。 |
| **不要修改 `pipeline_config.json` 裡的 `experiment` 區塊** | 那裡的值全部已簽核。 |

---

## 八、跑完要回傳什麼

### 8.1 一定要回傳

- `experiments/phase5_2026-08-21/phase5_index.json`　← 最重要，總表
- 每個目錄的 **`comparison.md`**（15 份，都是純文字，很小）
- 每個目錄的 **`evaluation.json`**（15 份）
- **`verify_phase5_output.py` 的完整輸出**（貼上即可，這是驗收憑證）
- 執行環境：作業系統、Python 版本、總共花了多久

### 8.2 不要回傳

- ❌ 逐案的 CSV（很大，需要時再單獨要特定 case）
- ❌ 解壓後的 CARE v6 資料
- ❌ 整個 `experiments/` 目錄

### 8.3 打包建議

```bash
cd experiments
tar czf phase5_2026-08-21_report.tar.gz \
  phase5_2026-08-21/phase5_index.json \
  phase5_2026-08-21/*/comparison.md \
  phase5_2026-08-21/*/evaluation.json
```

```powershell
Compress-Archive -Path `
  .\experiments\phase5_2026-08-21\phase5_index.json, `
  .\experiments\phase5_2026-08-21\*\comparison.md, `
  .\experiments\phase5_2026-08-21\*\evaluation.json `
  -DestinationPath .\phase5_report.zip
```

---

## 九、常見狀況與判讀

| 現象 | 意義 | 怎麼辦 |
|---|---|---|
| `no event_info.csv anywhere under ...` | 路徑指錯 | 回步驟 1；注意是指到**含有**那些檔案的目錄，不是檔案本身 |
| `found in 1 location(s)` | 只找到一個風場 | 另外兩個沒解壓出來。三個都要，否則部分 case 沒有 `event_start` |
| 驗收第 2 項 FAIL | `event_info` 沒讀到，或 `event_id` 對不上 case 編號 | 停下來回報，附上 `event_info.csv` 前 5 行 |
| 某一次 `FAILED rc=1` | 該次評估器報錯 | 把該次的 stderr 回報；其餘 14 次仍有效 |
| 跑很久沒有新行 | 可能正常（單次約 2–3 分鐘） | 超過 10 分鐘無新行才回報 |
| 自我測試某支 failed | **工具在你的環境行為不同** | **立刻停止**，回報完整輸出 |
| 驗收第 7 項 FAIL | 誤報率變了——**本批次唯一該變的是 lead time** | 停下來回報，這代表有別的東西被改動了 |

---

## 十、這一步跑完之後會解鎖什麼

Results 一節目前的 lead-time 欄位全是「不設限」那一輪的數字，
且標著 `[PENDING — Phase 5 重跑]`。你這一批跑完之後：

1. `docs/manuscript/03_results.md` 的 lead-time 表可以用真實數字定稿
2. abstract 與 conclusion 的絕對提前天數可以填上
3. 手稿在偵測門檻這一軸上不再有未決事項

**這是目前投稿路徑上的頭號待辦。** 其餘未決事項（Base Scorer 2、
POGO 相容性 gate、CARE 基線）都不擋這一步。

---

## 附錄：如果你想知道「為什麼是 15 次」

R27（2026-08-20 劉老師裁決）規定 lead time 以
**主要值加上宣告掃描**呈報，而不是挑一個數字：

| | 值 |
|---|---|
| 主要 H | **14 天** |
| 宣告掃描 | 7 ／ 10 ／ 14 ／ 21 ／ 不設限 |

理由是**非劣性在整個掃描範圍都成立，包括最寬鬆的不設限**——
既然結論不依賴 H，就不該假裝它依賴。3 個 α × 5 個門檻 = 15 次。

完整理由見 `docs/manuscript/02_evaluation_protocol.md` 第 4 節，
以及 Drive 上的《【已裁決】R27 — 2026-08-20 2115》。

---

*建立：2026-08-20。協定變動時請同步更新本文件與
`docs/LOCAL_RUNBOOK.md` Phase 5。*
