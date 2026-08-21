# 文獻掃描 2026-08-21（第四輪）

**執行者**：排程自動化研究助理
**證據等級**：**全部二手**（`arxiv.org`、`openreview.net` 雲端皆封鎖，實測見第六節）。
其中期刊摘要一段來自出版社頁面的轉述，其餘為搜尋引擎摘要。
**依 R17，本份任何一項都不得直接寫進稿件；要進稿件必須先取得全文。**

**本輪有新發現，而且方向與前三輪不同**：前三輪的紅旗都落在「保形推論的方法層」
（POGO）與「風機應用層」（2026-05 那篇）。**本輪落在中間那一層**——
校準集受污染時怎麼辦。那正是 Freeze-on-Alert 與六個吸收政策所在的位置，
也就是本論文三項可守主張裡的兩項。

---

## 一、本輪掃了哪一軸，為什麼

08-20 第八節建議的下一輪三軸：

| 軸 | 本輪 |
|---|---|
| 1. CARE v6 被引用清單 | **第四次做不到**（引用索引 API 全部 `000`）。「first on CARE v6」的禁令繼續有效 |
| 2. F10 全文核對 | 做不到（arXiv 封鎖），仍在本機清單 |
| 3. **可靠度工程／SPC 那側對「在警報成立期間量誤報率」的名字** | **做了，有發現（F13）** |

軸 3 是本輪的主軸。順著它又撈到兩個沒預期到的（F14、F15）。

**已用過的關鍵詞**：見 08-18 第七節、08-19 第一節、08-20 第一節。
本輪新用：`conditional average run length`、`run rules false alarm not constant`、
`conditional false alarm rate control chart`、`calibration set contamination conformal`、
`rejection mechanism conformal anomaly detection`、`self-masking calibration`。

---

## 二、F13【引用義務＋一個新的新穎性問題】SPC 的 run rules 早就說過「α 不是常數」

**這一軸是本專案自己找上門的**：已簽核的工單告警規則 **6-of-18 就是一條 run rule**。
Shewhart 管制圖那側對 run rules 的行為有數十年的文獻，本專案三輪掃描都沒碰。

搜尋到的（二手）敘述：

1. **「使用 run rules 時，某一觀測點發生誤報的機率取決於前面的觀測值，
   因此 α 不是常數。」**
2. 疊加多條 run rule 會**顯著膨脹** FAR：Western Electric 規則使
   in-control ARL 從 **370.4 掉到 94.75**。
3. 帶 supplementary runs rules 的 Shewhart 圖，其 run-length 的**精確**性質
   可用 **Markov chain** 求得。
4. 另有一支 **CFAR（conditional false alarm rate）** 文獻，
   且其中提到 CFAR 在**製程剛啟動時、以及從 out-of-control 訊號恢復之後**
   行為特別不穩定。

### 對本論文的意義，分兩件事，不要混起來

**（a）引用義務——與 F10／FCR 同型，成立。**
`FREEZE_LOCKIN_FINDINGS` 與 `PROJECT_STATUS` 1.00 的核心敘述是
「在一個依超越率挑出來的子母體上量超越率，量到的不會是 α」。
第 1 點是同一句話的 SPC 版本，而且比 FCR 那一支**更接近本專案的機制**
（我們的選擇裝置就是一條 run rule，不是一般的 selection event）。
談 6-of-18 造成的選擇效應而完全不引 run rules 文獻，
送到可靠度工程那側的審稿人手上（RESS、IEEE TR 這類 Q1 都很可能）第一輪就會被要求補。

**（b）一個新的新穎性問題——不成立也不排除，必須查。**
第 3 點才是要緊的：既然 supplementary runs rules 的 run-length 性質可以用
Markov chain **精確**求得，那麼「6-of-18 成立期間的超越率」這個量
**可能早就有人算過精確值**，而不只是像本專案那樣給一個代數下界
（`experiments/alarm_selection_floor_2026-08-20/`，`k/w = 1/3` on `N(F)`）。
若真有，本專案那個下界就是別人精確結果的一個寬鬆特例。

> **這一項與 claim firewall 第六條不是同一件事。** 第六條禁的是
> 「我們發現選擇效應會使條件覆蓋率主張失真」。這裡問的是更窄、更具體的一句：
> **6-of-18 這條 run rule 所強制的超越率下界，是不是新的。**
> 兩者範圍不同，所以第六條擋不住這一項。
>
> **處置：標記 `NOVELTY_UNRESOLVED`。** 在取得 run rules／Markov chain 那支的
> 代表性文獻全文之前，`alarm_selection_floor` 的結果**可以呈報為量測**，
> **但不得以任何形式宣稱該下界是新的、首次的、或先前未被指出的**。
> 建議把這條加進 `docs/manuscript/README.md` 界線四，作為 firewall 第七條的候選
> （**需劉老師裁決**）。

**要下載的**（本機清單）：Shewhart + supplementary runs rules 的 Markov chain
精確 run-length 代表作（Champ & Woodall 1987 一系列是這一支的起點），
以及 CFAR 那支的綜述。**優先序：與 F10 同級**，因為它同時是引用缺口與新穎性問題。

---

## 三、F14【紅旗候選，`NOVELTY_UNRESOLVED`】Freeze-on-Alert 可能已經有名字了

```
Conformal machine learning for reliable anomaly detection in
industrial cyber-physical systems
Shuaiqi Yuan, Jipu Li, Chunjin Wang, Xiaoge Zhang
Reliability Engineering & System Safety, 274 (2026)
DOI 10.1016/j.ress.2026.112417
```

出版社頁面的摘要（二手，未讀全文）指出該框架含三個元件：

| 他們的元件 | 本專案的對應物 |
|---|---|
| **sliding calibration set** | `W = 1440` 的滾動緩衝 |
| **temporal quantile adjustment (TQA)** | 線上校準的門檻調整（ACI／DtACI 那一族的位置） |
| **rejection mechanism**：把「顯著的異常」排除在校準集之外，以在提升偵測力的同時維持 FAR 保證 | **Freeze-on-Alert**：告警成立期間緩衝停止吸收 |

**第三列是本輪最重要的一件事。** Freeze-on-Alert 在本專案裡一直被當成
「這個運維系統既有的機制，我們套上去而已」，從來沒有被當成新東西主張——
**R25 之後的定位剛好保護了這一點**。但「不主張新」與「不必引用」是兩回事：
一個目的相同、且發表在 Q1 可靠度期刊上的機制，稿件裡完全不提，
本身就是審稿人會抓的缺口。

### 初步差異（**二手，不是裁決**）

| | RESS 2026 | 本論文 |
|---|---|---|
| 保證的形狀 | **邊際** FAR | **每個風速區間內**的 FAR（條件覆蓋率） |
| 評估指標 | Precision / Recall / F1 / AUROC | worst-bin \|FAR−α\|＋**三數字誤報協定**＋工單規則下的非劣性 |
| 排除的單位 | **點**（顯著異常個別排除） | **整個校準器凍結**，由 6-of-18 工單規則觸發 |
| 排除期間發生什麼 | 摘要**沒有提到**測量過 | **本論文的主要實證內容**（鎖死幾何、0.6819、代數下界） |
| 資料 | 公開 ICPS 資料集 | CARE v6 風機運維 |

若這五列成立，本論文的可守主張**不受影響，甚至更清楚**：
他們做的是**控制側**（把污染排掉以保住 FAR 保證），
本論文做的是**呈報側**（凍結期間刻意不救，改為三數字揭露）——
與 6.9 對 FCR 的答辯是同一個形狀，可以合寫一段。

**但這五列全部出自摘要。** 依 R17 必須取得全文、填完 Mandatory Overlap Check
四欄才能結案。**在此之前：`NOVELTY_UNRESOLVED`，Related Work 仍不動筆。**

**本機下載優先序：僅次於 CARE 期刊版，與 F10 同級。** RESS 需要機構訂閱。

---

## 四、F15【引用義務】校準集污染／裁切這一支，正對著六個吸收政策

同一軸撈到兩篇，都直接坐在 `FINDINGS` 第 4 節那六個吸收政策底下：

| 文獻 | 為什麼相關 |
|---|---|
| **Robust Conformal Outlier Detection under Contaminated Reference Data**（arXiv:2502.04807，ICML 2025） | 摘要（二手）稱：在**非對抗性**的實際情境下，用受污染的參考資料校準會得到**保守的** type-I error 控制。**這正對著本專案 `--no-freeze-on-alert` 消融的結果**：關掉凍結後 worst-bin 從 0.0616 掉到 0.0150，校準反而變好。本專案把它當成一個經驗觀察，這篇可能已經給了理論說明 |
| **When Does Trimming Help Conformal Prediction? A Retained-Law Diagnostic under Calibration Contamination**（arXiv:2605.06204） | 標題就是本專案 `winsor_alpha` 與 `winsor_max` 兩個吸收政策的問題。六政策否證是三項可守主張之一，**這篇的存在使「什麼時候該裁切」不能寫成本論文自己問出來的問題** |

**這兩篇不動 R25 定位**（它們是一般設定下的保形推論結果，沒有運轉區間、
沒有工單規則、沒有風機），**但都是引用義務**。
第一篇還可能讓 Limitations 裡「關掉凍結校準會變好」那段從觀察升級成有文獻支撐的解釋。

---

## 五、F16／F17【只需監看】

- **arXiv:2604.20122**（IBM Research，**ICLR 2026**）
  *Adaptive Conformal Anomaly Detection with Time Series Foundation Models for
  Signal Monitoring*，Martinez Gil, O'Donncha, Gifford, Zhou, Patel, Vaculin。
  post-hoc、model-agnostic、**把異常分數直接當成 p-value 型的誤報率讀**。
  與本論文不衝突（他們換的是底層偵測器，本論文的偵測器是凍結的），但
  「p-value 即 FAR」的敘述與本論文的 `conformal_p_value` 完全同義，**應引**。

  > ⚠️ **本輪自己犯了一次轉述錯誤，記在這裡當教材。**
  > 第一次搜尋的摘要合成把 F14 的 `rejection mechanism` 與 `self-masking`
  > **掛到了這一篇頭上**。追查原始出處後才發現那段屬於 RESS 那篇。
  > 這正是 `PROJECT_STATUS` 8.1 記的那個失效模式：**轉述時掉了出處**。
  > 若沒有追第二次，本專案就會把一個 ICLR 論文的內容記錯，
  > 而且錯得完全看不出來——它讀起來合理、來源看似有憑有據。
  > **教訓：搜尋引擎的「綜合摘要」會跨文獻合併敘述，逐篇回查才算數。**

- **arXiv:2505.01783** *Online Conformal Anomaly Detection with Prediction-Powered
  Data Acquisition*（C-PP-COAD）。摘要轉述中出現
  「calibrated to digital twin fidelity **in each operating regime**」。
  **這是 `regime-*` 語彙的第四筆獨立用法**（前三筆：CALIBURN 的
  `regime-dependent conformal risk control`、VaR 的 `regime-weighted conformal
  calibration`、digital twin 用水預測的 `regime-aware calibration`）。
  **禁止項不變，且證據又強一分**：主詞一律寫完整的
  `operating-regime-conditional`，不得簡寫。
  該篇是否構成應用層紅旗需全文才知道，本輪不判定。

---

## 六、雲端可達性 —— 本輪實測（不是沿用舊記錄）

| 端點 | HTTP |
|---|---|
| `https://arxiv.org/abs/2403.03868` | `000` |
| `https://openreview.net/forum?id=...` | `EGRESS_BLOCKED` |
| `https://api.crossref.org/works/...` | `000` |
| `https://api.openalex.org/works` | `000` |
| `https://api.semanticscholar.org/graph/v1/paper/search` | `000` |
| `https://www.mdpi.com/` | `000` |
| `https://raw.githubusercontent.com/` | `301`（可達） |
| `https://github.com/` | `400`（08-19／08-20 為 `403`；**回應碼變了但一樣取不到內容**） |

`github.com` 從 `403` 變成 `400` 是 proxy 的回應差異，**不是解封**。
記在這裡是因為下一輪若看到第三個回應碼，不會誤以為狀態改善了。

**因此仍然成立**：稿件不得寫「first on CARE v6」或任何等價的資料集層新穎性主張。
四輪掃描都沒跑過被引用清單。

---

## 七、本機下載清單（**本輪把順序改了**）

| 序 | 標的 | 理由 |
|---|---|---|
| 1 | **CARE 論文期刊版** | 6.3，未變 |
| 2 | **RESS 2026 `10.1016/j.ress.2026.112417`（F14）** | **新**。Freeze-on-Alert 的最近親，需 Mandatory Overlap Check |
| 3 | **Shewhart supplementary runs rules 的 Markov chain 精確 run-length（F13）** | **新**。同時是引用缺口與新穎性問題 |
| 4 | arXiv:2403.03868（JRSSB 2025 版更好）、2403.07728、2503.16809 | F10，未變 |
| 5 | **arXiv:2502.04807、2605.06204（F15）** | **新**。正對六政策否證與凍結消融 |
| 6 | arXiv:2604.20122、2505.01783 | 監看（F16／F17） |
| 7 | 次要：2605.22004、2301.00584、1905.01059、2606.13780 | 未變 |
| 8 | 既有：POGO 作者程式、2606.00419v4、2606.20115 | 未變 |

---

## 八、下一輪建議的軸

1. **CARE v6 被引用清單**（四輪都做不到；**只能本機執行**）
2. **F14 的全文核對**（填 Mandatory Overlap Check 四欄）—— 現在是最重要的一項
3. **F13 的 run rules 那一支**——目標是回答一個是非題：
   「6-of-18 成立期間的超越率，是否已有精確解？」
4. 尚未掃過：**維修決策那側**如何呈報提前預警（lead time）的分佈與分母。
   R27 的「主要值 + 宣告掃描」若在運維文獻裡已有慣例，應對齊而不是自創。
5. 不要重掃前三輪與本輪已用過的關鍵詞。

---

*建立：2026-08-21，排程自動化研究助理。全部二手，依 R17 不得直接寫入稿件。
本輪自身發生過一次跨文獻轉述錯誤並已更正，經過記在第五節。*
