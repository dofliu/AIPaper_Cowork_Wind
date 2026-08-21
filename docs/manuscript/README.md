# 手稿英文草稿（manuscript drafts）

**語言政策**：討論與進度文件用中文，**投稿文件一律英文**。本目錄下的 `.md`
檔案是投稿稿件的段落草稿，因此內容為英文；只有本說明檔是中文。

**狀態：草稿，未經劉老師審定。** 這些段落之所以現在就寫，是因為
`docs/PROJECT_STATUS.md` 第 2 節的資料事實是**跑真實資料才發現的**，
若不趁記憶還新時寫成投稿語言，日後很容易寫成「三個風場一律取兩通道平均」
這類與事實不符的敘述。

---

## 目前有哪些檔案

| 檔案 | 對應稿件章節 | 狀態 |
|---|---|---|
| `00_contribution_statement.md` | Abstract／Introduction 的貢獻句 | **2026-08-19 新增**，依 R25 新定位起草 |
| `01_dataset_and_preprocessing.md` | Section: Dataset and preprocessing | 草稿，數字齊備 |
| `02_evaluation_protocol.md` | Section: Evaluation protocol | 草稿，**待 H 裁決**才能定稿；2026-08-18 補入 R24 三數字協定 |
| `03_results.md` | Section: Results | **2026-08-18 新增**，CARE v6 真實數字，兩處 `[PENDING]` |
| `04_limitations.md` | Section: Limitations | **2026-08-18 新增** |

---

## 寫作時必須遵守的四條界線

這四條不是文體偏好，是本專案已經發生過的錯誤（與已經被別人佔走的語彙）所訂下的。
界線四底下的 claim firewall 已累積到**七條**（2026-08-21 新增第七條，
它是唯一一條**有期限**的，見該節）。

**一、不得寫「C0–C6 通過」。**
Base Scorer 1 在三個風場都 `gate_status=PASS` 是事實，但
(a) C0–C6 的**定義本身尚未批准**（程式仍輸出 `gate_definitions_ratified: false`），
(b) D5 要求主張在**兩個** scorer 上都成立，Base Scorer 2 尚未實作。
在這兩件事完成之前，稿件只能寫「Base Scorer 1 satisfied the compatibility
checks as currently specified」，不能寫成已通過的閘門。

**二、不得寫「三個風場」而不加限定詞。**
Farm A 沒有主軸承測點，Base Scorer 2 的範圍只有 Farm B/C。
凡是涉及主軸承的敘述，都必須指名風場。

**三、任何新穎性主詞都要帶條件性限定詞。**
`adaptive conformal anomaly detection`、`post-hoc conformal calibration for
anomaly scores`、`SCADA fault detection framework`、`early fault warning
framework` 皆已被既有文獻佔據（見《研究方向與方法論筆記 v4》第四節）。
可用的主詞是 `operating-regime-conditional ...` 這一類。

**四、【2026-08-18 劉老師裁決 R25】本文不得主張演算法新穎性。**

貢獻定位已正式由「演算法」改為
**wind-turbine O&M protocol-and-evidence contribution**。
這條界線與前三條不同：前三條管的是**怎麼寫**，這一條管的是**能不能寫**。

以下寫法一律禁止，理由是 arXiv:2606.00419v4 的全文核對（R25 四欄）已確認
該領土屬於既有文獻：

| 禁止 | 說明 |
|---|---|
| first／new **group-conditional online conformal prediction** | 已被 Bharti et al. 2026 佔據 |
| **parameter-free** 線上最佳化（任何變體） | 同上 |
| 任何形式的 **group-conditional coverage guarantee**（有限樣本或漸近） | 同上；且本文不證明任何定理 |
| `regime-aware`／`regime-weighted`／`regime-dependent` 作為本文主詞 | 2026 年已有三篇獨立使用 `regime-*` + conformal calibration，見 `docs/literature/LITERATURE_SCAN_2026-08-19.md` |
| 「我們優於／相當於／不需要 POGO」 | 相容性 gate 尚未執行；**「POGO 不適用於本問題」同樣是未經檢查的結論** |
| **【2026-08-20 已裁決】**「我們發現／首次指出選擇效應會使條件覆蓋率主張失真」 | 選擇後推論（POSI）、`selection-conditional coverage` 與 **FCR 控制**是既有文獻（JRSSB 2025、CAP、arXiv:2503.16809 等）。可守的是**這個特定運維機制**（6-of-18 + Freeze-on-Alert）的選擇幾何、其代數下界與三數字呈報協定，**不是選擇效應這個概念**。見 `docs/literature/LITERATURE_SCAN_2026-08-20.md` 第二、四節 |
| **【2026-08-21 已裁決・第七條】**「本文（首次）證明／指出 6-of-18 強制的超越率下界」，或任何等價於**該下界是新的**的寫法 | 6-of-18 **就是一條 run rule**，而 Shewhart supplementary runs rules 的 run-length 性質可用 **Markov chain 精確求得**（F13）。「告警成立期間的超越率」很可能早有精確解，果真如此，本專案的代數下界只是它的寬鬆特例。見 `docs/literature/LITERATURE_SCAN_2026-08-21.md` 第二節 |

> **【2026-08-21 已裁決】第七條與前六條有兩點不同，都很重要。**
>
> **一、它是有期限的。** 前六條是永久的（領土已確認被佔）。第七條是
> **舉證責任倒置下的暫時禁止**：run rules 那一支的全文**尚未取得**，
> 所以我們既不知道那個精確解存在，也不知道它不存在。
> 在不知道的期間，**保守的一邊是不主張**。
> 取得全文並完成核對之後，這一條可能解除、可能改寫、也可能升格為永久——
> **但在那之前它全額有效。**
>
> **二、它禁的是新穎性主張，不是那個量本身。** 這一點必須講清楚，
> 否則下一個人會過度保守地把整段刪掉，那會是另一種錯。**仍然可以寫的**：
>
> - 把下界**當成量測與推導**呈報：「在本協定下，`N(F)` 上的超越數
>   必然 ≥ `(6/18)·|F|`」——這是算術，寫出來沒有問題。
> - 用它**解釋**凍結期 0.6819 不是停滯造成的（那是 C2 的論證主體）。
> - 呈報實測／下界的比值（2.40–2.58），以及 α 不變性。
>
> **不可以寫的**只有一句話的形狀：**「這是我們發現的／這是第一次被指出」**。
> 換句話說，**把它寫成方法的一部分可以，寫成貢獻不行。**
>
> 這一條同時帶來一項**引用義務**（與第六條的 FCR 同型）：
> 談 6-of-18 造成的選擇效應而完全不引 run rules 文獻，
> 送到可靠度工程那側的審稿人手上第一輪就會被要求補。
> 已列入本機下載清單第 3 順位（PROJECT_STATUS 第 7 節）。

> **【2026-08-20 已裁決】上表最後一列同時帶來一個引用義務，不只是禁止。**
> 談「凍結期覆蓋率量不準」而不引 FCR／selection-conditional coverage，
> 在保形推論那側的審稿人眼中是引用缺口。**這個缺口現在補得起來，投出去之後補很貴。**
> 那六篇的全文尚未取得（arXiv 雲端封鎖），所以**現階段不動任何主張句**，
> 只把義務記在這裡，並列入本機下載清單（PROJECT_STATUS 第 7 節）。
>
> **附帶一段必須寫的答辯（建議放 Discussion 或 Limitations）。**
> 審稿人幾乎一定會問「既然有 FCR 控制，為什麼你們用三個數字而不用它」。
> 可守的答案是：
>
> > FCR 控制是「**在被選中的單位上把保證救回來**」的方法。本論文**刻意不救**
> > ——凍結期間暫停校準正是 Freeze-on-Alert 存在的目的（R21 實測：關閉凍結後，
> > 合成故障資料上的工單告警覆蓋率由 1.000 掉到 0.000）。
> > 要在凍結點上恢復覆蓋率，等於要求校準器在凍結期間繼續適應，
> > 那會把凍結機制本身拆掉。三數字協定是**呈報側**的對應物，不是控制側的。
>
> 這段話讓 R24 的三數字看起來是**有原則的選擇**而不是權宜之計。
> **但它必須等全文核對後才能定稿**——現在寫下來是為了不遺漏，不是為了照抄。

可以主張的三件事寫在 `00_contribution_statement.md` 第 1 節，
每一條都有量測支撐。**貢獻句已解凍**（R25 裁決明文允許在此 claim firewall
下起草），但 Related Work 仍凍結（R23／6.6 未結案）。

---

## 還沒寫的段落，以及為什麼

- ~~**Results**：等 Phase 5 的真實數字。~~ **2026-08-18 已寫**，見
  `03_results.md` 與 `04_limitations.md`。誤報率欄位取自
  `experiments/three_number_recheck_2026-08-18/`（以 R24 三數字協定重算），
  lead-time 欄位仍取自 `experiments/MD_2022_a*_evaluation/`（唯一算得出來的那輪）。
  **兩個來源必須寫在表註裡**，理由見該重算目錄的 README 第四、五節。
  兩處 `[PENDING]`（偵測門檻 H、Base Scorer 2）在文中已標示，不是遺漏。
- **Related work**：CARE 原始論文尚未取得全文（見
  `docs/literature/CARE_PAPER_ACQUISITION.md`），且有一篇 2026-05 的新文獻
  待重疊查核（見同目錄的紅旗文件）。在全文核對完成前寫 related work，
  等於用二手摘要描述別人的方法，這正是 R17 已經禁止的做法。

  **2026-08-18 追加一項，且這一項比前兩項更嚴重**：例行掃描撈到
  arXiv 2606.00419 *Parameter-Free and Group Conditional Online Conformal
  Prediction*（2026-06）。前兩項擋住的是 related work，這一項可能擋住
  **contribution statement**——「group-conditional online conformal
  prediction」幾乎就是本方法的一句話定義。詳見
  `docs/literature/LITERATURE_SCAN_2026-08-18.md` 第二節。

  **2026-08-19 更新：這一項已結案，結果是「重疊成立」。**
  R25 依全文完成 Mandatory Overlap Check 四欄，劉老師 2026-08-18 21:52
  批准改定位。**貢獻句因此解凍，但解凍後能寫的東西變了**——
  見上方界線四與 `00_contribution_statement.md`。
  Related Work 仍凍結（R23／6.6 未結案，且 POGO 相容性 gate 未執行）。

---

*建立：2026-08-16，排程自動化研究助理。*
