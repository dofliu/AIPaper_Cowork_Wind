# POGO Compatibility Gate — 版控版本

**狀態：`GATE_SPEC_RATIFIED` / `EXECUTION_NOT_STARTED`**
**G0：`SOURCE_RECEIPT_COMPLETE / ENVIRONMENT_BUILD_NOT_RUN`** — 論文 SHA-256
已由本 session 獨立複驗（3.3）；作者程式的兩個雜湊仍為轉錄
**G1：`PASS`（`SEMANTIC_EQUIVALENCE_ESTABLISHED`）** — 2026-08-20 依**一手全文**
核對定理與證明，紅旗解除（3.4a）。**先前 3.4／4.1 的相反預測是錯的，已標註**
**G3：`CONTRACT_DRAFTED / RATIFICATION_PENDING`**（2026-08-21）——
`NOT_COMPARABLE` 的風險由 G1 轉移到這裡（3.4a 末），
三項狀態契約已寫成
[`docs/method/POGO_G3_STATE_CONTRACT.md`](POGO_G3_STATE_CONTRACT.md)，
待 **R28** 裁決其中唯一的取捨

**規格來源**：Drive《[方法] R26 — POGO Compatibility Gate **v2.0**（規格正本）—
2026-08-21 1740 — 排程自動化研究助理》
（`docs.google.com/document/d/1QnnRAfxvilLRJwzm7Rf5d8qMfiR3VV21DxA8unafHdQ`）
v1.0（`…1u97DL7mwqNoLs7Cb1QNH0tYh1mxElvOeu9ersjYJTLw`）已標為取代，保留未刪。
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

> **【2026-08-21】暫時反轉已結束，上面那條規則恢復為唯一規則。**
> 08-20 晚間 G1 判 `PASS`、劉老師裁決兩項 pre-run contract 之後，
> Drive 正本一度落後（寫著「G1 未判、兩項契約待決」），
> 所以當時刻意把「以正本為準」暫時反轉成「以版控為準」。
>
> 2026-08-21 已依劉老師授權發佈 **R26 正本 v2.0**，
> G1 `PASS`、兩項裁決與 G3 契約都已進正本，反轉隨之取消。
> v1.0 已改標題為【已被 v2.0 取代】，未刪除。

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

**G0 狀態（雲端這側，2026-08-19）：`BLOCKED_IMPLEMENTATION`。**
解除方式：由本機端、或由具第三方 repo 授權的 session 執行 2.1 的 source lock。
**該封鎖已於 2026-08-20 由另一位協作者從別的環境解除，見 3.3。**

### 3.3 【2026-08-20】協作者回報 G0 已完成 —— 轉錄，未經本 session 驗證

**出處**：Drive《進度更新 2026-08-19 v4.5》文末 2026-08-20 追加段落，
以及《風能運維論文協作開發日誌 v4.9 — 2026-08-20 0045 — Gemini Spark》。
**本 session 沒有、也不可能複驗**：arXiv 與第三方 repo 在雲端這側仍封鎖
（3.1 的實測 2026-08-20 重跑，結果相同）。以下是轉錄，不是本 repo 的驗證結果。

| 項目 | 協作者回報值 |
|---|---|
| 論文 | arXiv:2606.00419**v4** \[stat.ML\]（Bharti, Pal, Teneggi, Sulam, 2026） |
| 論文 PDF SHA-256 | `7ab6c1c619d2cfe929ced4e0dd26b42f4dad9a66300991cb299ce31653e440d3` |
| 作者程式 | `github.com/beepulbharti/pogo` |
| commit | `95a8487568460561acd63f07d3feaa8a4bfce999` |
| license | MIT |
| dependency lock | Python `>= 3.11`，`uv.lock` revision 3 |
| exact-commit archive SHA-256 | `f608bdafe53dc3ac6acf727e4bcd0a9c54ee76952933bc07cf84dfa309941d58` |
| 已靜態檢視 | README、pyproject.toml、uv.lock、pogo.py、synthetic/runner.py、mimic/run_experiment.py |
| 已執行 | **無** |

**回報的 G0 狀態：`SOURCE_RECEIPT_COMPLETE / ENVIRONMENT_BUILD_NOT_RUN`
（明確不宣稱 G0 PASS）。** 這個克制是對的，第 2 節的 source lock 要求
「取得時間」也要留痕，而環境未建置就還沒有可重現性證據。

> **【2026-08-20 稍晚】論文 PDF 的 SHA-256 已由本 session 獨立複驗，逐字相符。**
> 劉老師把全文提供給本 session，實測
> `sha256sum` = `7ab6c1c619d2cfe929ced4e0dd26b42f4dad9a66300991cb299ce31653e440d3`，
> 與上表協作者回報值完全相同。**論文那一列因此從「轉錄」升級為「已驗證」**；
> 作者程式的兩個雜湊仍是轉錄（雲端無第三方 repo 授權，未取得）。
> 兩者狀態不同，不要一起記成「已驗證」。

> **為什麼要把它寫進版控。** 到 2026-08-20 為止，`main` 上的這一節寫著
> G0 `BLOCKED_IMPLEMENTATION`，而封鎖其實已經解除了。今天照版控讀狀態的人
> 會去重做一次已經做完的 source receipt，或是繼續向劉老師呈報「還卡著」。
> 這是 8.0a 那條規則的第四種形態：撞號、`main` 落後、裁決卡在 Drive，
> 現在是**進度卡在 Drive**。四種形態的共同點都是沒有任何一邊會報錯。

---

## 3.4 【2026-08-20】G1 紅旗的狀態：**沒有解除，但被縮小了**

協作者同輪回報 G1/G4 的靜態 mapping 草案：

```
frozen anomaly score        → POGO 的 S_t
當期更新前的 self.radius     → threshold_t
wind-speed group vector     → c_t
alarm exceedance            → empirical exceedance indicator
```

並附一句結論：「`POGO.update(S_t, c_t)` 直接接受 scalar score 與 group vector，
因此本研究 adapter **不需要捏造 `Y_t`**。」

**這句話就介面而言是對的，但它回答的不是 4.1 提出的那個紅旗。**
兩件事必須分開，混起來就會把一個未解的語義問題記成已解：

| | 狀態 |
|---|---|
| **實作障礙**：adapter 是否必須合成一個 `Y_t` 才能呼叫 POGO | **已解除**（若回報屬實）。API 吃 scalar，不吃標籤。 |
| **語義紅旗**：POGO 的 `S_t` 是否與本研究的分數同義 | **未解除。** |

理由：POGO 的 `S_t` 在原文裡是 residual `|Y_t − f(X_t)|`，它的 `radius`
是一個**預測區間半徑**，而 `S_t > radius` 這個事件的意義是**miscoverage**。
本研究餵進去的是 Mahalanobis 距離，它不是任何預測的殘差，
所以更新後的 `radius` **不再是任何區間的半徑**，超越事件也**不再是 miscoverage**。

**「這個函式接受一個 float」不等於「這個 float 是同一個東西」。**
函式簽章相容是語義相容的必要條件，不是充分條件。R26 第 7 節的 stop rule
問的是後者。

因此 G1 的判定維持 **`SEMANTIC_RATIFICATION_PENDING`**，
必須由**論文對 `S_t` 的定義**（不是程式的型別註記）為據。

> 這一節的存在理由，就是 `PROJECT_STATUS.md` 8.1 在 2026-08-18 記下的那條：
> **「這一輪撞到的不是版號，是轉述時掉了限定詞。」** 從「API 不需要 `Y_t`」
> 到「不需要 `Y_t`」只差兩個字，但後者會讓下一個人以為 4.1 的紅旗已經結案。

**⚠️ 本節上方的分析在同日稍晚被全文推翻，見 3.4a。保留原文是因為它記錄了
判斷是怎麼錯的——「限定詞不能掉」這個方法論意見仍然成立，
但它據以推論的那個事實前提（POGO 的保證需要 residual 語義）是錯的。**

---

## 3.4a 【2026-08-20 稍晚】G1 全文核對：**紅旗解除，`PASS`**

**證據等級：一手全文。** 劉老師取得 arXiv:2606.00419v4 PDF 並提供給本 session，
SHA-256 與 3.3 的協作者回報值逐字相符。以下引用均出自該 PDF。

### 我先前的判斷錯在哪裡

3.4（與 4.1 的紅旗、以及 08-19 首次提出時）都假設：POGO 的覆蓋率保證**需要**
`S_t = |Y_t − f(X_t)|` 這個 residual 結構。**全文顯示不需要。**

論文確實在第 2 節用 residual 引入 `S_t`，並用它建立那個樞紐等式
`1{Y_t ∈ I_t} = 1{S_t ≤ τ_t}`。我把「引入方式」讀成了「定理前提」。
但定理本身寫的是另一回事：

> **Theorem 4.1**（p.7）Let α∈(0,1), and let `(S_t, g_t, c_t)` be the sequences
> of non-conformity scores, subgradients, and group membership vectors observed
> by Algorithm 1. Let `D>0` and `q≥0`, and assume **`S_t ≤ D t^q`** ∀t≥1
> and `T_j > 0`. …

**定理的假設只有三條：`α∈(0,1)`、`S_t ≤ D t^q`、`T_j > 0`。**
沒有 `Y_t`，沒有預測器，沒有可交換性（論文明言
"We make no assumptions on the data stream, which may be arbitrarily changing"）。

而被保證的量 `MisCov_T(j)`（式 7）也只用到 `S_t`、`τ_t`、`c_t`：

```
MisCov_T(j) = | (1/T_j) Σ 1{S_t ≤ ⟨θ_t, c_t⟩} c_{t,j} − (1−α) |
```

逐步核對證明（附錄 A.1，pp.18–20）後，`S_t` 的結構只在**一個**地方進入：
式 (36) 經 **Lemma B.2** 得到 `1 − Σ⟨θ_t,g_t⟩ ≤ 1 + (1−α) Σ S_t`。
而 Lemma B.2 的證明（p.22–23）對 `S_t` 只用到一件事，且是明寫的：

> **Case 1**: Suppose `⟨θ_t,c_t⟩ < 0`. Then, **since `S_t ≥ 0` because it's a
> non-conformity score**, …

**所以整份證明對 `S_t` 的全部結構要求是：`S_t ≥ 0`，加上 `S_t ≤ D t^q`。**
兩者都不蘊含 residual 語義。

### 作者自己就是這樣用的

第 5.1 節（p.9）："Following prior work [2, 33], we **directly generate
non-conformity scores**"，式 (13)：

```
S_t = S_base_t + ⟨b(t), c(X_t)⟩ + ⟨ε_t, c(X_t)⟩ ,  S_base_t ~ Beta(1,20)
```

**沒有 `Y_t`、沒有預測器、沒有區間。** 式 (15)（帶位移）與式 (16)（二次成長）
同樣如此。這是作者親自示範 POGO 跑在裸分數串流上——比任何推論都強的證據。

### 本研究這一側的兩個條件已實測

| 定理要求 | 本研究實測（`scores_MD_2022_run1`，95 檔、5,240,974 個評分點） | 結果 |
|---|---|---|
| `S_t ≥ 0`（Lemma B.2 Case 1） | min = **0.4240**，負值 **0** 筆，非有限值 **0** 筆 | **滿足** |
| `S_t ≤ D t^q` | max = **23.8048** ⇒ 取 `q = 0`、`D = 23.81` | **滿足** |

Mahalanobis 距離本來就非負且有界（物理範圍過濾後），所以這兩條是實質滿足，
不是勉強湊上的。

### 判定

**G1 = `PASS`（`SEMANTIC_EQUIVALENCE_ESTABLISHED`）。**
POGO 可以跑在本研究的凍結 Mahalanobis 串流上，且**其定理在該串流上仍然成立**。

它保證的是：每個 group 的 `1{S_t ≤ τ_t}` 經驗比率收斂到 `1−α`。
換成本研究的語彙——**每個風速分箱的超越率收斂到 α**。那正是本方法的目標。

**方向必須寫死，否則一定有人默默反過來：**

| POGO | 本研究 |
|---|---|
| `1{S_t ≤ τ_t}`（"cover"），目標比率 `1−α` | 不超越 |
| `1{S_t > τ_t}`（"miscover"），目標比率 `α` | **`exceed = 1`**，目標比率 `α` |
| `MisCov_T(j)` | **per-bin \|FAR − α\|** |
| longest consecutive `{S_t > τ_t}` run（該論文的 adaptivity 指標，p.9） | 本研究 G5 的「最長 miscoverage streak」 |

最後一列是意外的好消息：**論文自己的第三個指標與 G5 規格已經寫的那一項是同一個量**，
不需要為了對照而新增或修改任何指標。

### 但有一件事**沒有**因此解除

`RELATED_WORK_ONLY` 的風險消失了，**`NOT_COMPARABLE` 的風險轉移到 G3**（時間狀態）。
POGO 的 wealth process `W_{t,j}` 是**乘法累積**的持久狀態（式 9），
而本研究的狀態是 `W = 1440` 的滾動視窗 + 18 點 exceed history + `frozen` 旗標。
兩者的「記憶」形狀完全不同，且 4.3 已規定：
**POGO 的 wealth 是否跨 case 攜帶，必須在看到結果之前寫下來。**

同理，G6 要求所有方法套同一套 6-of-18 + Freeze-on-Alert，
對 POGO 而言就是「凍結期間跳過 `update`」。這一條也必須在 adapter 規格裡明寫，
**不能留給實作者臨場決定**——它直接決定 POGO 會不會呈現與本方法相同的鎖死幾何。

### 這件事對論文的意義（比「多一個基線」大）

R26 原本的目的是「檢查 POGO 能不能當基線」。G1 PASS 之後，它有一個更好的用途：

> **POGO 是目前可得的、對 C2 最強的獨立檢驗。**

如果一個**演算法完全不同、且帶有已證明保證**的方法，在同一套 6-of-18 +
Freeze-on-Alert 之下呈現**相同的凍結鎖死幾何**（凍結期超越率遠高於名目、
且落在 `experiments/alarm_selection_floor_2026-08-20/` 那個代數下界之上），
那就直接證明了該現象是**告警政策的性質，不是本方法的缺陷**。

**這也意味著 G6 才是有意思的那一關，不是 G5。**

順帶一個對定位的提醒：R25 之後，**POGO 在 G5 上贏過本方法並不致命**。
可守的三項主張（三數字協定、鎖死幾何與其下界、六政策否證）都不依賴
「本方法的校準器最好」。真正要避免的是稿件寫出任何比較性的優劣句——
firewall 那一條仍然全額有效，直到 G8 回報為止。

---

## 3.5 兩項 pre-run contract — **✅ 劉老師 2026-08-20 已裁決**

作者程式帶有兩個 pre-run contract 缺口。兩者都不是實作細節，
**都會改變比較的意義**，所以必須在建環境之前凍結。裁決如下：

| 項目 | 裁決 |
|---|---|
| **group 數** | **`k = 4` 與 `k = 5` 都跑。** 本研究已簽核的 `k = 4` group 定義**不動**；`k = 5`（作者 script 在四個 subgroup 前加一個 all-ones marginal group）記為 **POGO 那一側**的執行參數，即「照作者預設跑」。**POGO 的頭號數字取兩者中較好的那一個。** |
| **`binary_groups`** | **`True`。** 理由不是「作者預設如此」，而是**本研究的 group 本來就是硬性互斥的 one-hot**（見 4.2）。設 `False` 等於向 POGO 宣告我們的 group 是軟的——那是假的。這是符合資料實情的設定，不是調參。 |

**「取較好者」為什麼不是選擇性呈報**：本方法**沒有任何可挑的自由設定**
（α、`W`、風速分箱、`min_bin_samples` 全部已簽核），所以這個不對稱
**只往對本方法不利的方向倒**。它同時擋掉兩個相反方向的審稿意見——
只跑 `k = 4` 會被指「把 baseline 跑在作者從未驗證過的設定上」；
只跑 `k = 5` 則可能在本研究的 worst-bin 指標上變相打折 POGO。

**這個裁決在看到任何結果之前做成，符合 G7。** 那正是它的價值：
跑完再選，無論選哪一個都會像是為了結果而選的。

> **【3.4a 之後補上的證據，與裁決方向一致】**
> 全文核對確認 `k` 在 Theorem 4.1 中**只以 `ln(k)` 進入** `U_T(k)`。
> 在本專案的實際尺度（每案 `T` 中位數 52,813、最小分箱 `T_j` 中位數 7,626、
> `D = 23.81`、`q = 0`、α=0.01），`k = 4` 與 `k = 5` 的界只差 **0.66%**
> （0.01027 對 0.01034）。**所以 `k` 不是理論驅動的選擇，是經驗問題**
> ——正好就是「兩個都跑」的理由。
> 計算工具 `scripts/pogo_bound_scale_check.py`（23 checks），
> 輸出見 `experiments/pogo_g1_2026-08-20/`。
>
> 另：Table 1 註腳明寫 "group-conditional coverage implies marginal coverage
> with `k' = k+1`"，證實那個 all-ones group **就是**取得邊際覆蓋率的裝置。
> 而本方法沒有任何邊際覆蓋率成分（per-bin buffer、per-bin p-value），
> 所以它在本研究這一側**沒有對應物**，歸為 POGO 的執行參數是正確的歸屬。

> **這個界是 POGO 的最壞情況上界，`0.01027` 這個數字絕對不可以與本研究實測的
> worst-bin 偏差 `0.0036` 並排放進同一張表。** 上界與經驗值是不同的東西，
> 並排等於做出「我們優於 POGO」的主張——firewall 明文禁止，
> 而這個算式在任何方向上都支持不了那句話。它唯一的正當用途就是工具名稱寫的那個：
> **確認在本專案的尺度上這個界不是空話**（0.0103 遠小於平凡上界 0.99），
> 所以把 POGO 跑在這裡是有意義的。

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

> ~~**G1 的第一個紅旗已經在這張表上**：POGO 以 `Y_t` 與 prediction set 為中心，
> 本研究**沒有 `Y_t`**。若要讓 POGO 產出與本研究同義的 alarm event 而必須
> 虛構一個 `Y_t`，依 R26 第 7 節 stop rule，應直接判 `NOT_COMPARABLE`。~~
>
> **【2026-08-20 全文核對後：這個紅旗不成立，G1 判 `PASS`。見 3.4a。】**
> Theorem 4.1 的假設只有 `α∈(0,1)`、`S_t ≤ D t^q`、`T_j > 0`；
> 整份證明對 `S_t` 的結構要求只有 `S_t ≥ 0`（Lemma B.2 Case 1 明寫）。
> `Y_t` 只用於第 2 節把 `1{S_t ≤ τ_t}` 翻譯成 `1{Y_t ∈ I_t}`，**不是定理前提**。
> 作者自己的合成實驗（式 13/15/16）就直接生成分數串流，沒有 `Y_t`。
> 上表「`Y_t` 不存在」那一列**仍然是事實**，只是它**不構成不相容**。
>
> **這一列保留刪除線而不是刪掉**，因為它示範了一個本專案該記住的讀法錯誤：
> 把論文「引入一個量的方式」讀成「定理對那個量的要求」。
> 前者是說明，後者才是假設，而兩者常常寫在不同的節裡。

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

~~1. **本機**：下載 arXiv 2606.00419v4 全文與作者程式，完成第 2 節 source lock → G0。~~
**✅ 2026-08-20 由協作者於別的環境完成（回報值見 3.3；本 repo 內仍無論文副本）。**

~~2. 先裁決 3.5 的兩項契約~~ **✅ 劉老師 2026-08-20 已裁決，見 3.5。**
~~3. 論文為據填 4.1 的 POGO 欄~~ **✅ 2026-08-20 完成，G1 判 `PASS`，見 3.4a。**

**由此，下一個動作的性質變了。原本是「檢查能不能比」，現在是「怎麼比」：**

~~1. **寫 G3 的狀態契約** —— 現在唯一還可能判 `NOT_COMPARABLE` 的一關。~~
**✅ 2026-08-21 已寫成 [`POGO_G3_STATE_CONTRACT.md`](POGO_G3_STATE_CONTRACT.md)**
（草案 v1.0，狀態 `RATIFICATION_PENDING`）。三項全部以文字寫死：

   | | 契約 |
   |---|---|
   | wealth 的 case 邊界 | 主要 `carry_across_cases = false`；宣告的次要 `carry_within_farm = true`；`carry_across_farms` **不是選項**。頭號數字取宣告設定中較好者 |
   | 凍結期間 | G5 無凍結；G6 **完全不呼叫 `update()`**、門檻沿用凍結前的 `τ`、`exceed` 照常記錄並送進 6-of-18。**`frozen` 旗標必須由 POGO 自己的 exceed 產生，不得沿用本方法的 `frozen` 欄** |
   | warm-up | 沿用作者預設 `burn_in = 500`；指標一律只算在共同評估視窗（＝本方法已校準的列） |

   量測證據見 `experiments/pogo_g3_2026-08-21/`：逐案重置**不會**讓
   Theorem 4.1 的 `T_j > 0` 失效（91 案 × 4 分箱，一格都沒空），
   但會讓界鬆約 20 倍——那是「重置必須連同攜帶一起跑」的理由。
   兩個 `burn_in = 500` 不會打架也是量過的（最早的首個已校準列在索引 641）。

   **唯一需要裁決的是宣告設定要 2 組還是 4 組**，見 Drive《[裁決請求]
   2026-08-21 R28》。**裁決之前不要建環境**——設定數決定 adapter 的執行矩陣。

2. **最小 adapter contract**（協作者已提草案，可直接採用）：
   輸入 `score_t`、`wind_bin`、`sample_id`；
   輸出 `threshold_before_update`、`alarm`、`radius_after_update`、
   `valid`、`reason_code`；並保存 source commit、config 與 stdout/stderr。

3. **G5 → G6 → G7 → G8。** 注意 **G6 才是這個 gate 現在最有價值的一關**，
   不是 G5——理由見 3.4a 末段。

**執行 owner：TBD**（R26 第 8 節；截至 2026-08-20 仍未指派）。
G0 與 G1 都已完成，但**兩者都是閱讀與核對工作**；
從第 1 項起需要的是**建環境與實作**，那才是真正需要指派的部分。

---

*建立：2026-08-19，排程自動化研究助理。
2026-08-20 更新：G0 論文雜湊獨立複驗、G1 依一手全文判 `PASS`（先前預測錯誤已標註）、
3.5 兩項契約經劉老師裁決。
2026-08-21 更新：G3 狀態契約寫成（`POGO_G3_STATE_CONTRACT.md`）、
Drive 正本更新為 v2.0、第 0 節的暫時反轉結束。
狀態變動請同步更新 `docs/PROJECT_STATUS.md` 6.8 與 Drive 的 R26 正本。*
