# R26 G1 全文核對 — 2026-08-20

**執行者：排程自動化研究助理　　證據等級：一手全文**
**結論：G1 `PASS`。先前 08-19／08-20 上午的相反預測是錯的。**

完整判定寫在 `docs/method/POGO_COMPATIBILITY_GATE.md` 3.4a，本目錄只放
可重現的計算與那次計算的輸入。

---

## 一、來源

劉老師 2026-08-20 取得 arXiv:2606.00419v4 PDF 並提供給雲端 session。

| 項目 | 值 |
|---|---|
| 論文 | Bharti, Pal, Teneggi, Sulam (2026), *Parameter-Free and Group Conditional Online Conformal Prediction*, arXiv:2606.00419v4 \[stat.ML\], 2026-07-07 |
| PDF SHA-256（**本 session 實測**） | `7ab6c1c619d2cfe929ced4e0dd26b42f4dad9a66300991cb299ce31653e440d3` |
| 協作者 08-20 回報值 | **同上，逐字相符** |

這是 G0 的論文那一列第一次由本 session 獨立複驗。
**作者程式的兩個雜湊仍是轉錄**（雲端無第三方 repo 授權），兩者狀態不同。

---

## 二、判定所依據的三處原文

1. **Theorem 4.1（p.7）的假設只有三條**：`α∈(0,1)`、`S_t ≤ D t^q`、`T_j > 0`。
   沒有 `Y_t`、沒有預測器、沒有可交換性。
2. **Lemma B.2（p.22–23）Case 1** 明寫對 `S_t` 的唯一結構要求：
   *"since `S_t ≥ 0` because it's a non-conformity score"*。
   這是整份證明中 `S_t` 的結構進入的**唯一**地方（經由式 36）。
3. **第 5.1 節（p.9）**：*"Following prior work, we **directly generate
   non-conformity scores**"*，式 (13)/(15)/(16) 沒有 `Y_t`、沒有預測器、沒有區間。
   **作者親自示範 POGO 跑在裸分數串流上。**

`Y_t` 只出現在第 2 節，作用是把 `1{S_t ≤ τ_t}` 翻譯成 `1{Y_t ∈ I_t}`。
**那是引入方式，不是定理前提。** 先前把兩者讀成同一件事，是這次判斷錯誤的來源。

---

## 三、本研究這一側的兩個條件 — 已實測

輸入：`scores_MD_2022_run1/*.csv`，95 檔。

| 定理要求 | 實測 | 結果 |
|---|---|---|
| `S_t ≥ 0`（Lemma B.2 Case 1） | 評分點 **5,240,974**；min **0.4240028498**；負值 **0** 筆；非有限值 **0** 筆 | **滿足** |
| `S_t ≤ D t^q` | max **23.80482948** ⇒ 取 `q = 0`、`D = 23.81` | **滿足** |

Mahalanobis 距離本來就非負且（物理範圍過濾後）有界，所以這兩條是**實質滿足**，
不是勉強湊上的。

---

## 四、尺度檢查 — 這個界在本專案的規模上是不是空話

工具：`scripts/pogo_bound_scale_check.py`（`pogo-bound-scale-check-v1.0`）
測試：`scripts/selftest_pogo_bound_scale_check.py`（23 checks）

**每個 case 是一條獨立串流**（狀態不跨 case），所以 Theorem 4.1 的 `T` 是
**每案**而不是總和。實測 91 案：

| | 中位數 | 最小 | 最大 |
|---|---|---|---|
| 每案已校準點 `T` | 52,813 | 50,083 | 64,154 |
| 每案最小分箱 `T_j` | 7,626 | 2,206 | — |

α=0.01、`D`=23.81、`q`=0 代入 Theorem 4.1：

| 情境 | k | `U_T(k)` | MisCov 上界 | 空話？ |
|---|---|---|---|---|
| 中位數案（`T_j`=7,626） | 4 | 21.431 | **0.01027** | 否 |
| 中位數案 | 5 | 21.654 | **0.01034** | 否 |
| 最不利案（`T_j`=2,206） | 4 | 21.351 | **0.02352** | 否 |
| 最不利案 | 5 | 21.574 | **0.02370** | 否 |

（「空話」的判準：`|rate − (1−α)|` 恆 ≤ `max(α, 1−α)` = 0.99，
與演算法無關。界若不小於它就什麼都沒說。0.0103 遠小於 0.99。）

### 這張表**只**能這樣讀

**`0.01027` 絕對不可以與本研究實測的 worst-bin 偏差 `0.0036` 並排。**
一個是最壞情況上界，一個是經驗平均值——並排等於做出「我們優於 POGO」的
主張，而 claim firewall 明文禁止，且這個算式在任何方向上都支持不了那句話。

**唯一的正當用途就是工具名稱寫的那個**：確認在本專案的尺度上這個界不是空話，
所以把 POGO 跑在這裡是有意義的。

### 而它同時支持了 `k` 的裁決

`k` 在 Theorem 4.1 中**只以 `ln(k)` 進入** `U_T(k)`，因此
`k=4` 與 `k=5` 的界只差 **0.66%**。**`k` 不是理論驅動的選擇，是經驗問題**
——正好就是劉老師「兩個都跑、取 POGO 較好者」裁決的理由。

另：Table 1 註腳 *"group-conditional coverage implies marginal coverage with
`k' = k+1`"* 證實那個 all-ones group **就是**取得邊際覆蓋率的裝置。
本方法沒有任何邊際覆蓋率成分，所以它在本研究這一側沒有對應物，
歸為 POGO 的執行參數是正確的歸屬。

---

## 五、重現指令

```bash
# 條件一與條件二（S_t >= 0 與有界）
#   逐檔掃 scores_MD_2022_run1/*.csv 的 anomaly_score 欄，見 gate 3.4a

# 尺度檢查
python3 scripts/pogo_bound_scale_check.py \
  --T 52813 --Tj 7626 --alpha 0.01 --D 23.81 --q 0 --k 4 --k 5 \
  --output experiments/pogo_g1_2026-08-20/bound_median_case.json

python3 scripts/pogo_bound_scale_check.py \
  --T 50083 --Tj 2206 --alpha 0.01 --D 23.81 --q 0 --k 4 --k 5 \
  --output experiments/pogo_g1_2026-08-20/bound_worst_case.json

python3 scripts/selftest_pogo_bound_scale_check.py
```

`.txt` 是同一次執行的 stdout。**本目錄沒有跑任何演算法**，
只有對既有分數串流的統計、以及對已發表公式的代入。

---

## 六、由此改變的下一步

風險**沒有消失，是轉移了**：`RELATED_WORK_ONLY` 的風險沒了，
`NOT_COMPARABLE` 的風險移到 **G3**（POGO 的 wealth process 是乘法累積的持久狀態，
本研究是滾動視窗）。三項必須在跑之前寫死：跨 case 攜帶與否、凍結期間是否跳過
`update`、warm-up 如何對齊。

而 R26 的**目的**也變了：從「檢查能不能當基線」變成
**「用 POGO 獨立檢驗 C2」**——若一個演算法完全不同、且帶有已證明保證的方法，
在同一套 6-of-18 + Freeze-on-Alert 下呈現相同的凍結鎖死幾何，
那就直接證明該現象是**告警政策的性質，不是本方法的缺陷**。
**因此 G6 才是有價值的那一關，不是 G5。**
