# POGO Compatibility Gate — 版控版本

**狀態：`GATE_SPEC_RATIFIED` / `EXECUTION_NOT_STARTED`（G0 已嘗試，見第 3 節）**

**規格來源**：Drive《[方法] 2026-08-18 R26 — POGO Compatibility Gate v1.0 —
2026-08-18 2152 — 排程自動化研究助理》
（`docs.google.com/document/d/1u97DL7mwqNoLs7Cb1QNH0tYh1mxElvOeu9ersjYJTLw`）
**裁決來源**：R25，劉老師 2026-08-18 21:52 批准改定位並指示建立本 gate。

---

## 0. 為什麼這份文件要進版控

R26 規格 2026-08-18 建立在 Drive 上，同一天 R25 也在 Drive 上被批准。
到 2026-08-19 為止，`main` 上的 `docs/PROJECT_STATUS.md` 仍寫著
「6.7 ⋯ **建議**列為 R25 裁決請求」——**一個已經拍板、而且會改寫 abstract
第一句的裁決，在版控裡看起來還沒發生。**

這正是 `PROJECT_STATUS.md` 8.0a 記載的那條規則所指的情況：
狀態放版控才算數，而裁決放 Drive 不會自己走進版控。
所以本文件不是 Drive 的副本備份，而是**把可執行的部分變成 repo 裡可被引用、
可被測試、可被 PR 檢查的東西**；Drive 那份仍是規格正本與裁決留痕。

規格若與本文件分歧，**以 Drive 的 R26 正本為準**，並請立刻回報分歧。

---

## 1. 這個 gate 在防什麼

POGO（Bharti, Pal, Teneggi, Sulam 2026, arXiv:2606.00419v4，
*Parameter-Free and Group Conditional Online Conformal Prediction*）
與本研究的方法在**語彙上**高度重疊：group-conditional + online conformal。
R25 的全文核對已確認：generic group-conditional OCP 與其 coverage guarantee
不得再作為本研究的演算法新穎性。

接下來自然會有人問「那就把 POGO 當基線比一下」。**本 gate 的存在就是為了
擋住那個動作被草率執行。** 兩個方法的輸入語義、group 定義、時間狀態、
輸出介面與 O&M 決策語義若不同義，跑出來的比較表會**看起來完全正常**——
沒有例外、沒有警告、每一格都有數字——只是那些數字不代表任何東西。
這是 `PROJECT_STATUS.md` 第 5 節那張清單的典型模式。

**總原則（fail-closed）**：任一關鍵 mapping 無法由原始碼、論文定義與
逐時間點 receipt 證明，即標記 `NOT_COMPARABLE`。
不得用 outcome label、TEST set、人工調參或事後閾值把不相容的方法湊成基線。

---

## 2. Source lock（G0 的要求）

| 項目 | 標的 | 現況 |
|---|---|---|
| 論文 | arXiv:2606.00419**v4**（版本必須釘死在 v4） | 全文已於 2026-08-18 由另一 session 讀過並完成四欄核對；**本 repo 內無副本** |
| 作者程式 | `github.com/beepulbharti/pogo` | **未取得**（見 3.2） |
| 本研究程式 | `scripts/regime_conditional_calibration.py` | commit SHA 見 PR / `git log`；本文件所引行號以下方第 4 節標註的版本為準 |

版本鎖要求：作者程式必須鎖定 commit SHA、license、dependency lock 與取得時間，
並留 SHA-256 receipt；本研究程式亦須鎖定 commit SHA。**缺一項，G0 不得 PASS。**

---

## 3. G0 執行紀錄 — 2026-08-19（雲端這側）

### 3.1 本輪實測（不是沿用舊記錄）

| 端點 | HTTP | 意義 |
|---|---|---|
| `https://arxiv.org/abs/2606.00419` | `000` | egress 封鎖，連不上 |
| `https://arxiv.org/html/2606.00419v4` | `000` | 同上——**論文全文雲端取不到** |
| `https://github.com/beepulbharti/pogo` | `403` | proxy 拒絕 |
| `https://api.github.com/repos/beepulbharti/pogo` | `403` | 同上 |
| `https://codeload.github.com/.../tar.gz/refs/heads/main` | `403` | 打包下載被拒 |
| `https://raw.githubusercontent.com/beepulbharti/pogo/main/README.md` | **`200`** | 端點可達 |

### 3.2 為什麼 G0 仍然是 NOT PASS —— 兩個不同的原因，不要混為一談

**(a) 論文全文：技術性封鎖。** arXiv 兩個 URL 都是 `000`，
與 2026-08-18 的實測一致。雲端這側取不到 v4 全文，**本機約一分鐘可下載**。

**(b) 作者程式：權限範圍，不是網路。** 上表最後一列是 `200`——端點其實通。
但本 session 的 GitHub 授權範圍**僅限 `dofliu/aipaper_cowork_wind`**，
讀取第三方 repository 不在授權內，因此**本輪沒有讀取任何 POGO 程式內容**
（只量測了端點回應碼）。

這個區別很重要：若把 (b) 記成「網路封鎖」，下一個人會在本機試一次、
發現下載得到，然後合理推論前一輪的記錄不可信——**而其他被記為封鎖的項目
其實是真的封鎖。** 一個錯誤的封鎖標籤會污染整份封鎖清單的可信度。

**G0 狀態：`BLOCKED_IMPLEMENTATION`（cloud）。**
解除方式：由本機端、或由具第三方 repo 授權的 session 執行 2.1 的 source lock。

---

## 4. 本研究這一側的 mapping — **已可填，且已填**

G1／G2／G4 是**兩欄**對照表。POGO 那一欄需要全文與程式（3.2 已封鎖），
但**本研究那一欄的權威來源就在這個 repo 裡**，不需要等任何人。

先把自己這一欄釘死有兩個作用：一是本機拿到 POGO 後只需填另一欄，
二是**任何要求「請你改一下這邊的定義好讓兩邊對得上」的提議，都會立刻現形**——
那是把本研究往別人的介面上湊，正是 fail-closed 原則要擋的方向。

下列全部出自 `scripts/regime_conditional_calibration.py`（本 PR 之版本）。

### 4.1 G1 — 輸入語義

| POGO 的概念 | 本研究對應物 | 出處 |
|---|---|---|
| `X_t`（協變數） | `wind_speed`，**外生**，與分數不同的一條串流 | `--wind-col`，`run_stream()` |
| `Y_t`（標籤） | **不存在，且刻意不存在。** 校準層完全不使用事件標籤 | 模組 docstring「using no event labels」 |
| base prediction set / radius | **不存在**。本方法輸出的是 per-bin conformal *p*-value，不是集合半徑 | `conformal_p_value()` |
| miscoverage event | point exceedance：`p_value < alpha` | `record["exceed"]` |
| — | **work-order alarm**：最近 18 點中至少 6 點 exceedance（POGO 無對應物） | `ALARM_OF=6`, `ALARM_WINDOW=18` |
| — | **frozen**：告警成立期間校準緩衝停止吸收（POGO 無對應物） | `record["frozen"]`, Freeze-on-Alert |

> **G1 的第一個紅旗已經在這張表上**：POGO 以 `Y_t` 與 prediction set 為中心，
> 本研究**沒有 `Y_t`**。若要讓 POGO 產出與本研究同義的 alarm event 而必須
> 虛構一個 `Y_t`，依 R26 第 7 節 stop rule，應直接判 `NOT_COMPARABLE`。
> 這一點在拿到 POGO 程式之前就可以預告，但**不能在此結案**——
> 判定要有全文與程式為據，這裡只標記「預期會撞到哪裡」。

### 4.2 G2 — group mapping

本研究的 group 是**四個互斥的硬性運轉區間**，只由外生風速決定
（`REGIME_BINS`，參數協定 v1.0 第 3 節，2026-08-11 已簽核）：

```
bin1_lt_4    wind < 4 m/s
bin2_4_8     4 <= wind < 8
bin3_8_12    8 <= wind < 12
bin4_ge_12   wind >= 12
```

對到 POGO 的 `c_j(X_t)` 時必須是 **one-hot**：POGO 允許 soft、可相交的
group membership `c_j(X)∈[0,1]`，本研究不允許。
每個 bin 仍須滿足 `min_bin_samples = 500`（D4，已簽核）；
不足時 fail-closed 為 `UNCALIBRATED`，**不得**改用較寬鬆的門檻去遷就對照。

**禁止的 mapping**：以異常分數、故障標籤或 TEST 結果形成 group。

### 4.3 G3 — 狀態、重置與時間

兩方法必須用**同一條** frozen score stream、同一組 case 邊界、同一個
chronological order 與 warm-up 排除規則。本研究的狀態是三件事：
per-bin rolling buffer（`W = 1440`，bin-local）、`exceed_history`（18 點）、
以及 `frozen` 旗標。case 之間不跨越攜帶。
POGO 的 wealth process 若跨 case 攜帶而本研究不攜帶，**該差異必須先寫下來**，
不得在看到結果後才決定。

### 4.4 G4 — 逐時間點輸出介面

本研究每個 timestamp 實際寫出的欄位（`main()` 的 CSV writer）：

```
timestamp, wind_speed, regime_bin, score, p_value, exceed, work_order_alarm, frozen
```

R26 要求的共通 schema 另需 `case_id`、`validity`（是否 `UNCALIBRATED`）
與 `reason code`。前者由目錄結構帶、後者可由 `p_value` 空值推得，
但**共通 schema 應該明寫而不是推得**——這是本機做 adapter 時要補的一欄。

若 POGO 的 prediction-set 輸出無法誠實轉成 anomaly alarm 介面，
標記 `RELATED_WORK_ONLY`，**不得**為了湊出一張表而發明 set size 或 alarm metric。

### 4.5 G5–G8

規格見 Drive R26 第 4 節，本文件不重述以免兩份分歧。三個要點留在這裡：

- **G5（calibration-only 層）**：所有方法一律關閉 Freeze-on-Alert，
  比較 unfrozen worst-group |FAR−α|、pooled deviation、rolling max deviation、
  最長 miscoverage streak。
- **G6（O&M-policy 層）**：只有 G1–G5 全 PASS 才能進入；所有方法套**同一套**
  6-of-18 與 Freeze-on-Alert。**禁止只替本方法套 policy** ——
  那會讓本方法獨自承擔凍結代價、或獨自享有凍結帶來的偵測保留，兩個方向都失真。
- **G7／G8**：DEVELOPMENT 上先跑兩次確認可重複，TEST 不得用於挑 variant、
  learning rate、mapping 或 tolerance；全 PASS 才 `BASELINE_ELIGIBLE`，
  且是否納入正式 confirmatory baseline **仍須劉老師另行裁決**。

---

## 5. 現在的正確狀態，一句話

**POGO 目前既不是基線，也還不是 related work 的定稿內容。**
它是一篇已完成 Mandatory Overlap Check 的文獻（R25），
以及一個**尚未開跑**的相容性檢查（R26）。

在 G8 回報之前，稿件不得出現任何形式的「我們優於／相當於 POGO」，
也不得出現「POGO 不適用於本問題」——**後者同樣是一個未經檢查的結論。**

---

## 6. 下一個可執行的動作（依序）

1. **本機**：下載 arXiv 2606.00419v4 全文與作者程式，完成第 2 節 source lock
   → G0。（同趟建議一併下載 CARE 期刊版與 arXiv 2606.20115，見
   `docs/literature/CARE_PAPER_ACQUISITION.md` 第四節。）
2. **本機或雲端**：拿到全文後填 4.1／4.2／4.4 的 POGO 欄。
   **先填完再寫 adapter** ——mapping 不成立的話 adapter 是白工，
   而且寫了 adapter 之後人會捨不得丟。
3. G1/G4 若判 `NOT_COMPARABLE` 或 `RELATED_WORK_ONLY`：到此為止，
   把結論寫進 Related Work，**不做 performance 比較**。
4. 只有全部同義才進 G5 → G6 → G7 → G8。

**執行 owner：TBD**（R26 第 8 節；截至 2026-08-19 未指派）。

---

*建立：2026-08-19，排程自動化研究助理。狀態變動請同步更新
`docs/PROJECT_STATUS.md` 6.8 與 Drive 的 R26 正本。*
