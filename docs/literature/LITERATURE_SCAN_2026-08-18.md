# 文獻掃描記錄 — 2026-08-18

**執行者：排程自動化研究助理　　時間：2026-08-18（Asia/Taipei）**
**性質：例行掃描。本文件全部內容為二手（搜尋摘要），沒有一條看過全文。**

`docs/PROJECT_STATUS.md` 第 7 節把文獻掃描列為每次排程的固定項目，理由是
W1-ACAS 與 2026-05 那篇都是**偶然**掃到的，沒有機制保證會掃到。本文件是這個
固定項目的第一次執行記錄——**沒有新發現也要留一筆，讓下次知道上次掃到哪裡。**
這次有新發現，而且其中一項比 2026-05 那篇更靠近本論文的貢獻邊界。

---

## 零、先說結論

| 編號 | 文獻 | 等級 | 為什麼 |
|---|---|---|---|
| **F1** | arXiv **2606.00419** *Parameter-Free and Group Conditional Online Conformal Prediction*（2026-06） | **紅旗（方法層）** | 「group-conditional + online conformal prediction」正是本方法的**方法名詞本身**，且早於本論文投稿 |
| **F2** | arXiv **2606.20115** *When Average Calibration Fails: Site-Conditional Federated Conformal Risk Control* | 監看（修辭層） | 「平均校準會失敗 → 改條件化」這個**開場論證**已被佔用 |
| **F3** | ScienceDirect S2666827025001951（digital twin water forecasting） | 監看（詞彙層） | 文中出現 **regime-aware calibration** 一詞，在別的領域 |
| **F4** | arXiv 2607.26577 *Simultaneous Coverage and Efficiency Guarantee in Online CP* | 一般相關 | 線上保形的效率／覆蓋權衡，可引用 |
| **F5** | 2026-05 風機 temporal conformal（R23 紅旗） | **狀態不一致，待釐清** | Drive 索引 v1.5 同時把它列在「已結案」與「尚未裁決」 |
| **F6** | CARE 原始論文（Gück et al.） | **Q6 有二手答案** | adaptive threshold 疑似是**方法元件**而非標註工具，且綁在 autoencoder 上 |

**沒有一項可以據此改稿或改程式。** F1、F2 需要走 R17 的 Mandatory Overlap
Check；F6 需要全文逐字核對（`CARE_PAPER_ACQUISITION.md` 第三節的八題）。

---

## 一、本次掃描的通道限制（先講清楚，因為它決定了結論的強度）

雲端這側**只有搜尋可用，抓取全部被封**。本輪逐一實測（不是沿用 2026-08-16
的記錄），WebFetch 與 shell curl 兩條路都試過：

| 目標 | 結果 |
|---|---|
| `arxiv.org` / `export.arxiv.org` | EGRESS_BLOCKED |
| `www.mdpi.com` | EGRESS_BLOCKED |
| `zenodo.org` | EGRESS_BLOCKED |
| `www.sciencedirect.com` | EGRESS_BLOCKED |
| `publica-rest.fraunhofer.de`（直接的 PDF bitstream） | EGRESS_BLOCKED |
| `www.researchgate.net` | EGRESS_BLOCKED |
| `api.crossref.org` / `api.openalex.org` / `api.semanticscholar.org` | 不可達 |
| `doi.org` | 不可達 |
| 第三方評述站（themoonlight.io、ouci.dntb.gov.ua、ideas.repec.org、goatstack.ai） | EGRESS_BLOCKED／不可達 |

shell 端 `curl` 對以上全部回 `000`（連線根本沒建立），與 WebFetch 的
`EGRESS_BLOCKED` 一致。**這不是暫時性錯誤，也不是換一個鏡像站就能繞過。**

**所以本輪能做的上限是「知道有這篇、知道要查什麼」，不是「知道它寫了什麼」。**
全文一律要本機端取得。這條限制本身值得寫進交接，免得下一個 session 再花一輪
去重新發現它。

---

## 二、F1 — 方法名詞被佔用（本次最重要的一項）

```
Parameter-Free and Group Conditional Online Conformal Prediction
arXiv:2606.00419（另見 HTML 版 v4）
```

**為什麼這比 2026-05 那篇更該擔心。**

2026-05 那篇（R23／PROJECT_STATUS 6.6）佔的是**應用層**語彙：
conformal + wind turbine + conditional。本論文與它的差異是「條件化在哪個對象」
——跨機組分群 vs 機組內運轉區間——這個差異寫得出來。

F1 佔的是**方法層**語彙。本方法用一句話講就是：
「線上保形校準，覆蓋率按分組條件化」。而 F1 的標題就是這句話。
二手摘要所述其貢獻為：既有 OCP 方法必須在 group-wise error control 與
learning-rate 無關性之間二選一，該文提出免參數演算法同時拿到兩者，並主張
取得「最好的 group-conditional 覆蓋保證」。

**初步差異（二手，僅供裁決參考，不得寫入稿件）：**

| 面向 | F1（據二手摘要） | 本論文 |
|---|---|---|
| 分組怎麼來 | 一般化的 group 抽象，理論保證為主 | **物理定義的運轉區間**（風速分箱），來自與分數不同的一條協變數串流 |
| 對象 | 預測器的輸出，一般設定 | **既有已發表、凍結的異常分數**，不改動偵測器 |
| 主要貢獻型態 | **演算法與後悔／覆蓋保證** | **實證協定**：最差分箱偏差 + 三數字誤報呈報 + 工單規則下的非劣性 |
| 與告警政策的交互 | 未涉及 | Freeze-on-Alert 的鎖死幾何與其呈報後果（本專案的實測主軸） |
| 資料 | 一般 benchmark | CARE v6，91 案，真實 SCADA |

**如果這個差異成立，本論文的貢獻應該被重新定位成「協定與實證」而不是
「演算法」。** 這件事的影響大於一段 related work：它會動到 abstract 的第一句。
但這是**二手分析，不是裁決**——依 R17 程序須先取得全文、填完 Mandatory
Overlap Check 四欄。

> **建議列為 R25 裁決請求。** 這比 6.6 更優先，因為 6.6 只擋住 related work，
> F1 可能擋住 contribution statement。

---

## 三、F2 — 開場論證被佔用

```
When Average Calibration Fails: Site-Conditional Federated Conformal Risk Control
arXiv:2606.20115（v3）
```

二手摘要的說法是：pooled（平均）的做法在個別機構上會顯著違反覆蓋率，因此
改為 site-conditional。**這正是本論文 abstract 的開場動作**——「誤報率只在
平均上守住，不代表在每個風速區間內守住」。

領域完全不同（聯邦式醫療 vs 風機 SCADA），方法也不同（conformal risk control
vs 線上保形校準），**所以這不是重疊，是修辭撞車**。但審稿人讀到「average
calibration fails 所以要 conditional」時，會覺得這個開場眼熟。

**建議（詞彙限制第五條，提案）**：開場論證不要停在「平均會失敗」這個一般命題
上，要**立刻落到本論文特有的那一層**——失敗發生在**運轉區間**上，而運轉區間是
風機領域裡有物理意義、且運維人員本來就在用的切分方式。一般命題誰都能講，
落到這個切分上才是本論文的。

---

## 四、F3 — `regime-aware calibration` 一詞已在別的領域出現

digital twin 的用水量預測研究（ScienceDirect S2666827025001951）在二手摘要中
被描述為使用 domain-adaptive conformity scores、meta-learning 與
**regime-aware calibration**。

這不影響新穎性（不同領域、不同問題），但它影響**檢索時的可辨識度**：
如果本論文也叫 regime-aware，未來搜尋這個詞會撈到兩件不相干的東西。

《研究方向與方法論筆記 v4》第四節目前指定可用主詞為
`operating-regime-conditional ...`。**本輪的建議是維持這個選擇，不要簡寫成
`regime-aware`**——`operating-regime` 這個前綴同時做兩件事：與 F3 區隔，
以及與 F1／2026-05 那篇的「group / cluster」區隔（我們條件化的不是機組群體，
是同一台機組隨時間走過的運轉狀態）。

---

## 五、F5 — 2026-05 那篇的狀態，Drive 與 GitHub 對不上

Drive 索引《文件索引與版本命名規範 v1.5》（2026-08-17 2300）在同一份文件裡：

- 【已結案】欄寫：「《[警示] 2026-08-16 R23》—— 已由 Gemini Spark 完成
  Mandatory Overlap Check 四欄，標記 **NOVELTY_RESOLVED**」
- 【尚未裁決】欄寫：「PROJECT_STATUS **6.6** 的新穎性紅旗：需取得 2026-05
  文獻全文才能結案」

而 `docs/PROJECT_STATUS.md` 6.6 與 `NOVELTY_WATCH_2026-08-16.md` 都記為
`NOVELTY_UNRESOLVED`，並明寫「**在此之前 Related Work 不應動筆**」。

**這兩件事不可能同時為真**：R17 程序要求四欄要以**全文**填寫，全文未取得就
不可能填完四欄。合理的解釋是 Gemini Spark 填的是**以二手摘要為據的初步四欄**，
而索引在轉述時把「初步」丟掉了。

**本輪不裁決，只把不一致記下來，並維持較保守的那一邊**：
Related Work 仍不動筆，6.6 維持 `NOVELTY_UNRESOLVED`。

> 這是本專案第 5 節那份清單的同型事件：沒有任何一邊會報錯，兩份文件都讀得很順，
> 只是它們說的不是同一件事。差別在於這次兩邊都在**文件**裡，所以只要有人同時
> 讀到就會發現——前提是有人同時讀到。

---

## 六、F6 — CARE 的 Q6 有了二手答案，而且方向與先前的猜測相反

`CARE_PAPER_ACQUISITION.md` 的核對問題 Q6 問：CARE 論文裡的 "adaptive
threshold" 是一個**基線方法**，還是資料集**標註時用的工具**？該文件當時判斷
「若是後者，6.3 的正確處置是**撤銷這個基線**，不是實作它」。

本輪搜尋摘要給出的描述（**二手，疑似轉引自論文正文，未經核對**）：

> For wind farms A and B, an adaptive threshold is used, inspired by previous
> work, where a neural network regression model is used to learn the mapping of
> the autoencoder input data to the L2-norm of reconstruction error. During
> prediction, the new input data are evaluated by the neural network and provide
> an expected reconstruction error, which is then compared to the actual
> reconstruction error of the autoencoder model.

**若屬實，三件事同時成立：**

1. 它是**方法元件**，不是標註工具 → Q6 的「撤銷基線」路徑不成立，6.3 要留著。
2. 它**只用在 Farm A 與 Farm B**，不是三場通用 → 基線的適用範圍本身就有邊界，
   而本專案的 D5 範圍已限縮至 Farm B/C（2026-08-15 追認），兩者**只在 Farm B
   重疊**。這會直接影響「CARE 基線能在幾個風場上比」。
3. 它**綁在 autoencoder 的重建誤差上**——它不是一個可以套在任意分數串流上的
   門檻政策，而是「用回歸模型預測 autoencoder 該有多少重建誤差」。
   **本專案的凍結分數是 Mahalanobis 距離，不是 autoencoder 重建誤差。**
   所以「把 CARE 的 adaptive threshold 套到我們的 base scorer 上」在定義上
   就不是原作做的事。

**第 3 點是本輪最有操作意義的一句。** 它把 6.3 從「還沒實作」變成
「實作它之前要先決定實作的是什麼」：是連 autoencoder 一起重現（等於多一個
base scorer），還是明確聲明本論文不含 CARE 基線並說明原因。
**這是裁決題，不是工程題。**

其餘二手事實（同樣未核對，但與既有記錄一致）：36 台機組、3 個風場、89 機組年、
**44 個異常時段 / 51 個正常時段**。與本專案手上的 v6（45/50）仍然對不上，
版本漂移的解釋依舊未取得。

---

## 七、下一輪掃描要從哪裡接下去

- **關鍵詞已用過**（避免重複）：`conformal prediction wind turbine anomaly
  detection 2026`、`regime-conditional online conformal calibration SCADA false
  alarm rate 2026`、`group-conditional coverage online conformal prediction
  operating regime binning covariate shift 2026`、`CARE to Compare ... adaptive
  threshold`。
- **下一輪建議加的軸**：
  1. `conformal` × `predictive maintenance` × `alarm suppression / alarm freeze`
     ——本專案的 Freeze-on-Alert 鎖死是目前最獨特的一段實證，要確認沒有人做過。
  2. `worst-group calibration error` × `time series` ——本論文的頭號度量。
  3. CARE v6 的**被引用清單**（誰在用這個 benchmark、用什麼協定報數字）。
     這一軸本輪做不了，因為引用索引 API 全部不可達；**本機端可做**。
- **本機端能做而雲端不能的**：F1、F2、F6 三份全文下載。F6 的下載步驟已寫在
  `CARE_PAPER_ACQUISITION.md` 第四節；F1、F2 為 arXiv，本機約各一分鐘。

---

*建立：2026-08-18，排程自動化研究助理。本文件不含任何裁決。*
