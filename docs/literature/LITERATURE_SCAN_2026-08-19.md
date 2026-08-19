# 例行文獻掃描 — 2026-08-19

**執行者**：排程自動化研究助理（雲端）
**這是第二次執行**（第一次見 `LITERATURE_SCAN_2026-08-18.md`）。
依 `PROJECT_STATUS.md` 第 7 節，文獻掃描是每次排程的固定項目，
**沒有新發現也要記一筆**，讓下一輪知道上一輪掃到哪裡。

**本輪有新發現：一項語彙撞車升級，一項可用工具，一項定位參照。**
**沒有**需要新開裁決請求的紅旗。

---

## 一、本輪掃了哪三個軸

上一輪（08-18）建議的下一輪三個新軸，本輪執行前兩個；第三軸雲端做不到。

| 軸 | 執行 | 結果 |
|---|---|---|
| 凍結／告警抑制 × conformal | ✅ | F7、F9（見下） |
| worst-group calibration error × 風機 SCADA | ✅ | 無新紅旗；只撈到既有已知文獻 |
| CARE v6 的被引用清單 | ❌ **雲端做不到** | 引用索引 API（crossref／openalex／semanticscholar）全部不可達，需本機執行 |

---

## 二、F7【語彙撞車升級・不需裁決・但要改寫法】

```
CALIBURN: Operationally Calibrated Streaming Intrusion Detection with
Regime-Dependent Conformal Risk Control
arXiv:2605.24696（2026-06；有 HTML v2）
```

**為什麼要記**：它把 `regime-dependent` 直接接在 `conformal risk control`
後面，而且是**串流偵測 + 告警預算 + 由預算導出決策門檻**的設定——
與本論文的組合形狀非常接近，只是領域是入侵偵測。

**差異寫得出來，而且是硬差異**（依摘要，二手）：

| | CALIBURN 的 "regime" | 本論文的 "operating regime" |
|---|---|---|
| 指什麼 | **攻擊盛行率**（5.2% / 22% / 64%，三個資料集） | 機組當下的**物理運轉狀態**（風速分箱） |
| 從哪來 | 資料集的標籤分布，是**事後才知道**的性質 | 外生協變數串流，**當下即可觀測**，不需要標籤 |
| 是不是條件化的對象 | 不是——它是「我們的方法在不同盛行率下表現不同」的意思 | 是——校準本身逐區間進行 |

**兩者對 "regime" 的用法根本不同**：它講的是 across-dataset 的敏感度，
本論文講的是 within-stream 的條件化。所以這不是新穎性紅旗。

**但它讓 `regime-*` 這個修飾語的擁擠程度升級了。** 目前已知三筆獨立用法：

1. `regime-aware calibration` — digital twin 用水預測（08-18 掃到）
2. `regime-dependent conformal risk control` — CALIBURN（本輪）
3. `regime-weighted conformal calibration` — *Taming Tail Risk*，
   arXiv:2602.03903，非平穩 VaR（本輪順帶撈到）

**結論（強化既有規範，不是新規範）**：`operating-regime-conditional`
**一定要寫全，不得簡寫成 `regime-aware` / `regime-conditional`**。
已寫進 `docs/manuscript/README.md` 界線四的禁止表。

**順帶一個定位上的好消息**：CALIBURN 的主張句是
「這類管線的行為對 regime 的依賴**先前未被刻畫**」——
也就是說，**「刻畫一個先前未被刻畫的行為」本身就是可發表的貢獻型態**。
這正是 R25 把本論文改成 protocol-and-evidence 之後的貢獻形狀，
是一個有用的先例（不是可以引用的證據，是寫作上的參照）。

---

## 三、F8【可用工具・非文獻風險】

```
Conformal Anomaly Detection in Python: Moving Beyond Heuristic Thresholds
with 'nonconform'
arXiv:2605.13642
```

一個 conformal anomaly detection 的 Python 套件。與本專案的關係有限
（本專案刻意只用標準函式庫，且方法已自行實作並有 370 checks 釘住），
**但如果將來需要第三方交叉驗證我們的 conformal p-value 實作，這是候選。**

**不建議引入為依賴**：會破壞「無第三方套件」這個刻意的設計，
而且它解決的是本專案已經解決的問題。記在這裡只是為了下次不用重找。

---

## 四、F9【已知文獻的再確認・無新事】

`Adaptive Conformal Anomaly Detection with Time Series Foundation Models for
Signal Monitoring`（arXiv:2604.20122，ICLR 2026）在本輪的兩個查詢都排在前面。

**這就是 W1-ACAS**——本專案已經重實作為基線
（`scripts/baseline_w1_acas.py`，`PAPER = "Martinez Gil et al., ICLR 2026,
arXiv:2604.20122v1, Algorithm 1"`）。不是新發現。

記一筆的理由：搜尋結果把它描述為「post-hoc、可解讀為誤報率的 p-value」，
與本專案對它的理解一致，**這是對既有理解的一次獨立確認**，
也再次確認 `post-hoc conformal calibration for anomaly scores` 這個主詞
確實被佔據（方法論筆記 v4 第四節既有記載）。

---

## 五、本輪**沒有**發現的東西（同樣要記）

- **沒有**新的 group-conditional／worst-group OCP 方法論文
  （R25 那篇之外）。方法層的領土狀況與 08-18 相同。
- **沒有**用 CARE v6 做 conformal 校準的論文。
  本專案在資料集層的位置目前仍是空的——**但這個結論的可信度受限於
  第一節第三軸做不到**：沒跑引用清單，就不能說「沒有人用 CARE v6 做過」。
  稿件不得寫「first on CARE v6」之類的話。
- **沒有**任何文獻處理「告警抑制期間的校準保證怎麼報」這個問題。
  這仍是本論文 C1–C3 主張的核心空白區。同樣受上一條的可信度限制。

---

## 六、通道狀況（本輪重新實測，不是沿用）

| 端點 | 結果 |
|---|---|
| WebSearch | ✅ 可用（本輪三個查詢都有結果） |
| arxiv.org（`/abs/`、`/html/`） | ❌ `000` |
| github.com、api.github.com、codeload | ❌ `403` |
| raw.githubusercontent.com | ⚠️ `200`（端點可達，但第三方 repo 不在本 session 授權範圍內，未讀取） |
| crossref／openalex／semanticscholar | ❌（08-18 實測，本輪未重測） |

**結論不變：雲端能搜尋、不能取全文。** 三份待下載全文（arXiv 2606.00419v4、
2606.20115、CARE 期刊版）與 POGO 作者程式，仍須本機執行。
詳見 `docs/method/POGO_COMPATIBILITY_GATE.md` 第 3 節。

---

## 七、下一輪建議的軸（給下一個排程）

1. **CARE v6 的被引用清單**（第三軸，本輪與上輪都做不到；**本機執行**）
2. `selection bias in conditional coverage evaluation` — 本論文 C2 的
   選擇效應論證，統計學那側可能早有對應的名字。找到的話 Discussion 會強很多。
3. `work order` / `maintenance ticket` 作為監督訊號 —— FINDINGS 4.3 那條
   唯一還可能修好機制的路徑，先看別人怎麼取得這種標註。
4. 已用過的關鍵詞見 08-18 那份第七節與本份第一節，**不要重掃**。

---

*建立：2026-08-19，排程自動化研究助理。所有判斷均為**二手摘要**，
依 R17 不得直接寫入稿件；要進稿件必須先取得全文。*
