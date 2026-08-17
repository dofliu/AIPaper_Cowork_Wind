# CARE 原始論文取得記錄與待核對清單

**建立：2026-08-16　執行者：排程自動化研究助理**
**狀態：文獻身份已定位，全文未取得。本文件中的定義一律標記為二手，不得用於實作。**

---

## 零、這份文件要解決的問題

`docs/PROJECT_STATUS.md` 6.3 有三個項目同時卡在同一個原因上：

| 項目 | 現況 | 卡在哪 |
|---|---|---|
| CARE adaptive threshold 基線 | `NOT_IMPLEMENTED`，呼叫即拋例外 | 定義在 CARE 論文中 |
| CARE score | `NOT_IMPLEMENTED` | 同上 |
| CARE Reliability | `NOT_IMPLEMENTED` | 同上 |

三者都寫在 `scripts/evaluate_experiment.py` 的 `MISSING_METRICS`，
理由字串是 `definition is in the CARE To Compare paper, unread`。

**本輪已完成的是「定位」，不是「取得」。** 雲端這側的網路政策封鎖了
arxiv.org、mdpi.com、zenodo.org、publica.fraunhofer.de、
api.openalex.org、api.semanticscholar.org——實測全部回 403（CONNECT tunnel
failed），不是暫時性錯誤。全文只能由本機端取得。

---

## 一、文獻身份（本輪定位結果）

同一份工作有**兩個版本**，兩個都要拿，因為版本之間可能有定義差異：

**期刊版（優先，應以此為準）**
```
Gück, C.; Roelofs, C.M.A.; Faulstich, S.
CARE to Compare: A Real-World Benchmark Dataset for Early Fault Detection
in Wind Turbine Data.
Data (MDPI), 2024, 9(12), 138.
https://www.mdpi.com/2306-5729/9/12/138
```
　DOI 推定為 `10.3390/data9120138`（MDPI 標準格式，**未經核對，請下載時確認**）
　MDPI *Data* 為 open access，本機應可直接下載 PDF。

**預印本版**
```
arXiv:2404.10320 — "CARE to Compare: A real-world dataset for anomaly
detection in wind turbine data"（標題與期刊版不同）
https://arxiv.org/abs/2404.10320
```

**資料集本身**
```
Zenodo DOI: 10.5281/zenodo.14006163　授權 CC BY-SA 4.0
另有一筆 Zenodo 記錄 10958775「Wind Turbine SCADA Data For Early Fault
Detection」，疑為較早版本 —— 需確認與我們手上的 v6 的關係。
```

> **這一條直接回應 R10 留下的「CARE v6 DOI 疑義」。** 我們的 v6 標籤是
> anomaly 45 / normal 50，論文報告 44 / 51。取得全文時**務必一併確認
> 論文描述的是 Zenodo 上的哪一個版本**，否則「版本漂移」只是被記錄，
> 沒有被解釋。

---

## 二、二手來源目前指出的內容【全部未經核對，不得據此實作】

以下每一條都來自搜尋摘要與第三方評述，**沒有一條看過原文**。
列出來的用途是「拿到 PDF 後知道要翻哪幾頁」，不是拿來寫程式。

### CARE score 的四個分項

| 分項 | 二手描述 |
|---|---|
| **C**overage | 在標註異常事件的資料集上計算 F-beta |
| **A**ccuracy | 在純正常資料集上的 true negative 比例 |
| **R**eliability | event-based F-beta，**β = 1/2**（加重懲罰誤報），先以 criticality 演算法把時間序列收斂成二元告警 |
| **E**arliness | 分段線性權重：事件前半段偵測到給權重 1，後半段線性遞減到 0 |

總分為四項加權平均。二手來源給的權重是 `ω1 = ω2 = ω3 = 1, ω4 = 2`，
並說「give more weight to the accuracy score」。

> ⚠ **這裡有內部矛盾，正是必須核對原文的理由。**
> Accuracy 是四項中的第二項，若加權的是 accuracy，權重 2 應該落在 ω2，
> 而非 ω4。二手摘要至少有一處講錯。**在原文確認之前，權重一律視為未知。**

### criticality 與告警門檻

二手來源指出：演算法計算最大 criticality（一種計數器式度量），
**最大 criticality 低於 72 即判定為正常事件（不告警）**。

> 若屬實，這與我們的 6-of-18 工單規則是**兩套不同的告警語意**。
> D2（比較對象防火牆）要求比較必須在同一把尺上——所以拿到原文後要決定的
> 不只是「怎麼實作」，還有「CARE 基線要用它自己的 criticality 規則跑，
> 還是統一套用 6-of-18」。兩種做法都能辯護，但必須明寫是哪一種。
> 依目前 `evaluate_experiment.py` 的設計，所有方法一律套 6-of-18。

### adaptive threshold（最不可靠的一條）

搜尋回覆宣稱：風場 A/B 使用自適應門檻，以神經網路回歸模型學習輸入到重建誤差
L2-norm 的映射（3 層、隱藏層 20–40 units、ReLU、Adam）；風場 C 使用固定門檻，
以最大化 F1/2-score 選定。

> ⚠ **此條可信度最低，建議直接忽略。** 同一段回覆把輸入描述成
> 「acoustic emission (AE) input data」，但 CARE 是 SCADA 資料集，沒有聲射訊號。
> 這強烈暗示搜尋結果混入了另一篇論文。**這一條在原文核對前應視為錯誤資訊。**

---

## 三、拿到 PDF 後要回答的問題（逐項核對用）

拿到全文的人請照這張表逐項填答，填完的版本才可以拿去實作。
每一項都要能**逐字對照原文**（頁碼／式號），這是 6.3 一開始就設定的標準。

- [ ] **Q1** CARE 總分的公式與四個權重的確切值？（解決第二節的 ω 矛盾）
- [ ] **Q2** Coverage 的 F-beta 中 β 取多少？在什麼母體上計算？
- [ ] **Q3** Accuracy 的分母是「正常案例數」還是「正常案例中的時間點數」？
- [ ] **Q4** criticality 的**遞增／遞減規則**是什麼？門檻 72 是否為原文數值？
      單位是點數（10 分鐘取樣下 72 點 = 12 小時）還是別的？
- [ ] **Q5** Earliness 的分段線性權重，其「前半／後半」是相對 event window
      的哪兩個端點？（`event_start`／`event_end`？還是標註的異常起點？）
- [ ] **Q6** 論文中是否真的存在一個名為 "adaptive threshold" 的**基線方法**，
      還是那只是資料集構建時的標註工具？**這一題決定 6.3 是否存在。**
      若後者為真，6.3 應改為「撤銷該基線」而非「實作該基線」。
- [ ] **Q7** 論文描述的資料集版本，與 Zenodo `10.5281/zenodo.14006163`
      的哪一個 version 對應？44/51 對 45/50 的差異出自哪一次改版？
- [ ] **Q8** 論文自己報告的基線結果表，是否可作為我們的 sanity check？
      （若可，我們的 MD_2022 分數流應該落在合理範圍內）

---

## 四、給本機端的取得步驟（三分鐘）

1. 開 `https://www.mdpi.com/2306-5729/9/12/138`，下載 PDF（open access，免登入）。
2. 順手記下該頁顯示的正式 DOI，回填本文件第一節。
3. 開 `https://doi.org/10.5281/zenodo.14006163`，看 Versions 區塊，
   記下我們手上的 v6 對應哪一個 version 與其發布日期。
4. 把 PDF 放進共享資料夾，並在開發日誌記一筆。
5. 照第三節的八題逐項填答。

**填完之前，`evaluate_experiment.py` 的三個 `NOT_IMPLEMENTED` 維持原狀。**
寧可缺一個基線，不可拿近似值冒充原作——尤其在二手摘要已經被抓到至少
一處自相矛盾、一處疑似張冠李戴之後。

---

*排程自動化研究助理, 2026-08-16*
