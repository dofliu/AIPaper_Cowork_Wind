# R26 執行手冊 — 給執行 owner

**狀態：`OWNER_ASSIGNED / EXECUTION_NOT_STARTED`**
**執行 owner：automation-4**（劉老師 2026-08-22 00:42 指派，留痕在
Drive《開發日誌 v5.3》文末的「裁決補記」段）
**建立：2026-08-22，排程自動化研究助理**

R26 從 2026-08-21 起**不再有任何裁決擋在前面**（R28 是最後一個）。
G0／G1／G3 都已完成，但**三者都是閱讀、核對與規格工作**。
從這裡開始需要的是建環境與實作，這份文件就是那一段的順序。

---

## 0. 這份文件是什麼，不是什麼

**是**：一份**順序清單**——先做什麼、每一關的驗收條件、跑完要交什麼回來。

**不是規格。** 這裡**刻意不重述任何規格值**：`k` 跑哪幾個、凍結期間 POGO 做什麼、
`burn_in` 是多少、G5／G6 各比哪些指標——一個都不寫在這裡，只寫「權威在哪一份」。

理由就是本專案吃過最大的虧：**同一件事寫在兩個地方，它們一定會分歧，
而讀到舊的那一份的人不會知道自己讀到的是舊的。**
若本文件與下表任何一份不一致，**以下表那一份為準，然後回來改本文件。**

| 你要決定的事 | 權威 |
|---|---|
| R26 全局規格（G0–G8 的定義） | **Drive《[方法] R26 — POGO Compatibility Gate v2.0》（正本）** |
| G3 三項狀態契約、執行矩陣、receipt 欄位、G3 驗收條件 | [`POGO_G3_STATE_CONTRACT.md`](POGO_G3_STATE_CONTRACT.md) |
| G1／G2／G4 兩欄 mapping、G5／G6 的三個要點、source lock | [`POGO_COMPATIBILITY_GATE.md`](POGO_COMPATIBILITY_GATE.md) |
| 專案現況、已簽核參數、踩過的坑 | [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) |
| 哪些句子不得寫進稿件 | [`../manuscript/README.md`](../manuscript/README.md) 的四條界線 |

**本文件由排程 session 寫成，不是由 owner 寫的。** 你在執行中發現順序有錯、
或某一步在真實環境裡做不到，請直接改這份文件並說明——
**一份與實際執行不符的手冊比沒有手冊更糟。**

---

## 1. 開跑前（全部是讀與跑，不需要任何下載）

1. **讀上表前三份。** G3 契約請整份讀完，尤其第 3 節那句紅線與第 6 節的 receipt。
2. **跑自我測試**（`../LOCAL_RUNBOOK.md` Phase 0.3 有一鍵指令）。
   十八支全部 `ALL SELF-TESTS PASSED`、合計 583 checks、0 failed。
   **任何一支不是 0 failed 就先停下來**——那代表工具在你的環境與雲端行為不同，
   之後所有結果都不可信。
3. **確認你手上有什麼、沒有什麼**：G0 的 source receipt 已由協作者完成
   （論文雜湊已獨立複驗，作者程式的兩個雜湊**仍是轉錄**，gate 3.3）；
   **環境尚未建置**，那正是你的第一步。

> ⚠️ **雲端這側取不到論文與作者程式**（arXiv `000`、第三方 repo 無授權，
> gate 3.1／3.2）。這份手冊之後的每一步都**假設你在有第三方存取的環境**執行。

---

## 2. 執行順序總覽

| 步 | 做什麼 | 完成的判準（不是「跑完了」） |
|---|---|---|
| **G0b** | 建隔離環境、鎖 lockfile、跑作者自己的範例一次 | 雜湊逐項相符，且作者範例在你的環境跑得出來 |
| **A** | 寫最小 adapter | 兩側欄位對得上，且 `frozen` 旗標由 POGO 自己產生 |
| **G5** | calibration-only 層，關閉 Freeze-on-Alert | 四組宣告設定各一份 receipt，checker 全 PASS |
| **G6** | O&M-policy 層，兩方法套同一套告警政策 | 同上，且循環檢查通過 |
| **G7** | DEVELOPMENT 上重跑一次，確認可重複 | 兩次逐位相符 |
| **G8** | eligibility 判定 | 呈報給劉老師，**是否納入正式基線仍須另行裁決** |

**G6 才是這個 gate 最有價值的一關，不是 G5**（理由見 gate 3.4a 末段：
若一個演算法完全不同、且帶有已證明保證的方法，在同一套告警政策下呈現
相同的凍結鎖死幾何，那就直接證明該現象是**政策的性質**，不是本方法的缺陷）。
**G5 輸給 POGO 不致命**，三項可守主張都不依賴「本方法的校準器最好」。

---

## 3. G0b — 把 G0 從 `SOURCE_RECEIPT_COMPLETE` 推到環境已建置

source lock 的四項（commit、license、dependency lock、取得時間）已完成，
**缺的是可重現性證據**。所以這一步的產出不是數字，是「這個環境是活的」。

1. 依 gate 3.3 記載的 commit 與 dependency lock 建**隔離**環境
   （不要裝進任何既有環境——版本漂移之後無法歸因）。
2. **逐項比對雜湊**：論文 PDF、作者程式 archive。
   **任一項對不上就停**，不要以「應該是同一版」往下走。
3. **先跑作者自己的合成範例一次**，確認環境能重現作者的結果。
   **在碰本專案任何資料之前做這件事**：若之後 POGO 的數字很難看，
   你需要能區分「方法如此」與「環境沒建對」，而那個區分**事後做不到**。
4. 留下環境 receipt（Python 版本、lockfile 雜湊、建置時間、跑範例的輸出）。

> 本 repo 內**沒有**論文與作者程式的副本，也不要提交進來（授權與體積）。
> 提交的是 receipt，不是原始碼。

---

## 4. A — 最小 adapter

介面欄位見 **gate 4.4**（本研究側每個 timestamp 實際寫出的欄位）與
**R26 正本第 9 節**的 adapter 草案；共通 schema 另需 `case_id`、`valid`
與 `reason_code`——**共通 schema 要明寫，不要從空值推得**。

三條紅線，全部出自已裁決的契約：

1. **`frozen` 旗標必須由 POGO 自己的 exceed 序列產生**，套同一條告警規則。
   **絕對不可以沿用本方法算出來的 `frozen` 欄。**
   沿用等於把本方法的鎖死幾何餵給 POGO，再宣稱獨立重現了它——
   G6 會從獨立檢驗變成循環論證，**而且跑起來一切正常、數字漂亮**。
2. **不得為了讓兩邊對得上而修改本研究側的任何定義。**
   本研究側的 mapping 已經釘死（gate 第 4 節），且那些參數是 2026-08-11 簽核的。
   任何「請你改一下這邊的定義好讓兩邊對上」的提議，方向就是錯的——
   fail-closed 要擋的正是把本研究往別人的介面上湊。
3. **不得動作者的暖機設定**（契約第 4 節）。調大或調小都會讓之後任何一個
   難看的數字無法歸因：是方法差，還是我們動了它的暖機？
   **不可歸因的比較沒有價值。**

---

## 5. 每跑一次都要留下 receipt，並讓工具檢查它

契約第 6 節要求每次執行連同結果寫出一份 receipt。
**這份 receipt 不是文書工作**：`frozen_flag_source` 與 `carry_across_farms`
兩欄恆為固定值，留在 receipt 裡是刻意的——這兩件事一旦被違反，
數字會照樣產生而且看起來正常，所以要在輸出裡留一個**會被人看到的**證據，
不是靠實作者記得。

本輪新增的 [`../../scripts/check_pogo_receipt.py`](../../scripts/check_pogo_receipt.py)
把契約的每一條做成機器檢查（78 checks 釘住，含反向驗證）：

```bash
# 1. 先拿一份空白 receipt，欄位用抄的，不要用記的
python3 scripts/check_pogo_receipt.py --emit-template > receipt_k4_none.json

# 2. 四組都跑完之後一次檢查（--ours-window 直接吃既有的 occupancy 報告）
python3 scripts/check_pogo_receipt.py \
  --receipt receipt_k4_none.json     --receipt receipt_k4_within.json \
  --receipt receipt_k5_none.json     --receipt receipt_k5_within.json \
  --require-matrix \
  --ours-window experiments/pogo_g3_2026-08-21/occupancy_a01.json \
  --json-out experiments/pogo_r26_<日期>/g3_acceptance_a01.json

# 3. G6 那一層額外做循環檢查
python3 scripts/check_pogo_receipt.py ... \
  --ours-frozen <本方法逐案凍結列數的 JSON>
```

**exit code 0 才算通過**，且要看 JSON 裡這三個欄位：

| 欄位 | 意思 |
|---|---|
| `g3_acceptance` | `MET` 才代表**共同評估視窗逐案相等**這條驗收成立。沒給 `--ours-window` 一律是 `NOT_MET`——**沒檢查不等於通過** |
| `matrix_complete` | 四組宣告設定是否到齊 |
| `headline_eligible` | **在它是 `true` 之前，不得從這批結果取任何頭號數字**。對一個不完整的矩陣取最大值，就是一個不說 N 的 max over N |

**這個工具檢查的是「可不可以比」，不是「比得怎樣」。**
receipt 全數通過只代表這批結果**有資格**被比較；比較的內容是 G5／G6 的事。

---

## 6. 四個會安靜出錯的地方

本專案第 5 節那張清單的共同點是：**到目前為止最嚴重的缺陷沒有一個會報錯**，
它們全部照常跑完、照常輸出漂亮的數字，只是數字是錯的。R26 這一段有四個：

| # | 出錯的樣子 | 為什麼看不出來 | 擋它的東西 |
|---|---|---|---|
| 1 | POGO 的 `frozen` 沿用本方法的欄 | 兩邊鎖死幾何當然一致，看起來像漂亮的獨立重現 | receipt 的 `frozen_flag_source` + `--ours-frozen` 逐案比對 |
| 2 | 暖機被「對齊」 | 數字照樣產生，只是不再可歸因 | receipt 的 `burn_in` 必須是作者預設 |
| 3 | 只跑兩組，報最大值 | 一個 max over 2 與 max over 4 長得一模一樣 | `--require-matrix` |
| 4 | 共同視窗只對總數 | 兩個不同的逐案切法可以有同一個總數 | 驗收條件寫的是**逐案**相等，工具照此檢查 |

第五個不在工具射程內，靠紀律：**TEST 不得用於挑 variant、learning rate、
mapping 或 tolerance**（G7）。用了不會報錯，也不會留下痕跡。

---

## 7. 跑完之後交回什麼

1. **輸出進版控**：`experiments/pogo_r26_<日期>/`，附 README 三節——
   做了什麼、怎麼重現（完整指令）、**有什麼是這批數字不能拿來宣稱的**。
2. **狀態同步三處**（缺一處就會出現本專案已經吃過四次的那種分歧）：
   - `docs/PROJECT_STATUS.md` 6.8 的 gate 狀態表
   - `POGO_COMPATIBILITY_GATE.md` 第 6 節
   - **Drive 的 R26 正本**——Drive 無內容編輯 API，
     **新建一份、版本號 +1、標明取代誰，舊版不要刪**
3. **開 draft PR**，把 receipt 與 checker 的 JSON 一起放進去。
4. **呈報 G8**：全 PASS 才是 `BASELINE_ELIGIBLE`，
   而**是否納入正式 confirmatory baseline 仍須劉老師另行裁決**——
   `BASELINE_ELIGIBLE` 不等於「已納入」。

---

## 8. 什麼時候必須停下來

- **G1–G5 沒有全 PASS，不得進 G6。**
- **任何一項 receipt 欄位缺失，G3 維持 `NOT_RUN`**，不得以「應該沒差」略過。
- **G8 回報之前，稿件不得出現任何形式的「我們優於／相當於 POGO」，
  也不得出現「POGO 不適用於本問題」**——後者同樣是一個未經檢查的結論。
- **契約要改任何一項，必須先出新的裁決請求。**
  **跑之後才改的契約，等於沒有契約。**

---

*建立：2026-08-22，排程自動化研究助理。
本文件不含任何規格值，只含順序、驗收與交回方式；規格分歧時一律以第 0 節的
權威表為準。*
