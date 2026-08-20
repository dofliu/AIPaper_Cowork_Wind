# 例行文獻掃描 — 2026-08-20（第三次執行）

**執行者：排程自動化研究助理**
**性質：例行掃描。所有判斷均為二手（搜尋結果摘要），依 R17 不得直接寫入稿件。**

前兩次：`LITERATURE_SCAN_2026-08-18.md`、`LITERATURE_SCAN_2026-08-19.md`。
沒有新發現也要記一筆，讓下一輪知道上一輪掃到哪裡。

**本輪有新發現，而且是三次掃描裡最重要的一次。**

---

## 一、本輪掃了哪三個軸

08-19 建議的三個軸，本輪執行第二、第三軸；第一軸雲端仍做不到。

| 軸 | 執行 | 結果 |
|---|---|---|
| CARE v6 的被引用清單 | ❌ **雲端仍做不到（第三輪）** | 見第五節，本輪重新實測 |
| `selection bias in conditional coverage evaluation` | ✅ | **F10，紅旗，需 Mandatory Overlap Check** |
| 工單／維修單作為監督訊號 | ✅ | F12，無紅旗，但對 FINDINGS 4.3 有用 |
| （加掃）告警抑制政策 × conformal 校準 | ✅ | F11，語彙／先例參照，非新穎性風險 |

---

## 二、F10【紅旗・需裁決程序】選擇效應在保形推論裡已經有名字，而且有一整支文獻

**這是本輪最重要的一件事，而且它同時是好消息與壞消息。**

本專案 C2 主張的核心是：

> 6-of-18 的**進入條件**就是局部超越率 ≥ 1/3，所以凍結點是**依超越率被挑出來的**。
> 在一個依超越率挑出來的子母體上量超越率，量到的不會是 α。

2026-08-20 同一輪的新結果（`experiments/alarm_selection_floor_2026-08-20/`）
把這件事從觀察升級成代數下界。而本輪掃描發現：**這個現象在保形推論文獻裡
有既定名稱、既定形式化，並且有專門的錯誤率控制方法。**

| 文獻 | 出處 | 與本論文的關係 |
|---|---|---|
| *Confidence on the Focal: Conformal Prediction with Selection-Conditional Coverage* | arXiv:2403.03868；**JRSSB 87(4):1239, 2025** | 明確處理「被某個程序挑中的單位」的條件覆蓋率，含以 conformal p-value 為選擇規則的情形 |
| *CAP: A General Algorithm for Online Selective Conformal Prediction with FCR Control* | arXiv:2403.07728 | **線上**選擇 + 即時 FCR 控制。與本論文的設定形狀最接近的一篇 |
| *Online Selective Conformal Prediction: Errors and Solutions* | arXiv:2503.16809 | 指出線上選擇會**破壞可交換性**，並指出前人保證裡的錯誤 |
| *Selective conformal inference with false coverage-statement rate control* | arXiv:2301.00584 | FCSR 控制 |
| *Selecting Informative Conformal Prediction Sets with an Optimized FCR-Controlled Approach* | arXiv:2605.22004（2026-05） | 同軸的最新一篇 |
| *Online Control of the False Coverage Rate and False Sign Rate* | arXiv:1905.01059 | 線上 FCR 的源頭 |

### 為什麼是好消息

1. **C2 的論證從此有標準語彙可用**：`selection-conditional coverage`、
   `post-selection inference (POSI)`、`false coverage rate (FCR)`。
   Discussion 可以直接接上一支成熟文獻，而不是自創說法。
2. arXiv:2503.16809 的核心觀察——**線上選擇破壞被選點與校準集之間的可交換性**
   ——正是本專案 Freeze-on-Alert 的處境的一般化敘述。這是一個很強的外部佐證。

### 為什麼是壞消息

**稿件不得再暗示「注意到選擇效應會破壞條件覆蓋率主張」本身是新的。** 它不是。
目前 `00_contribution_statement.md` 的 C2 沒有明說這一點，但
「that is a selection effect, not staleness」這種寫法容易被讀成在主張發現。
**這一條建議升格為 claim firewall 的第六條禁止項**（見第四節）。

更實際的風險是**引用缺口**：Q1 期刊若送到保形推論那一側的審稿人手上，
一篇談「凍結期覆蓋率量不準」卻不引 FCR／selection-conditional coverage 的稿子，
第一輪就會被要求補。這個缺口今天補得起來，投出去之後補很貴。

### 差異在哪裡（**初步、二手，不是裁決**）

| | 既有文獻 | 本論文 |
|---|---|---|
| 選擇規則 | 為了**節省資源**而刻意設計的挑選（top-K、conformal p-value 門檻） | **不是為了選擇而存在**的告警抑制政策，選擇是它的副作用 |
| 目標 | 在被選單位上**恢復**覆蓋率保證（FCR／selection-conditional） | **不恢復**。凍結期本來就刻意暫停校準；本論文主張的是**呈報方式**（R24 三數字） |
| 被選集合 | 測試單位 | 校準層自己的內部狀態（凍結旗標） |
| 領域 | 一般設定 | 風機運維工單規則 6-of-18 |

差異看起來成立，**但這正是 R25 那次的形狀**：語彙撞車時，初步差異總是寫得出來，
全文核對之後才知道站不站得住。**依 R17 程序，本節維持
`NOVELTY_UNRESOLVED`，不得據此改寫稿件的任何主張句。**

### 一個必須明說的方法層問題（**裁決題，不是工程題**）

既有文獻提供了一條本專案沒有走的路：**對被選中的點做 FCR 控制**，
而不是像 R24 那樣把它們切出來、三個數字並列呈報。

**本輪不主張哪一條比較好，也不建議改。** R24 已由劉老師裁決並實作，
評估尺規已釘在自我測試上。但**審稿人幾乎一定會問「為什麼不用 FCR 控制」**，
所以稿件需要一段明確的回答。建議把這一段的撰寫排進 Limitations 或 Discussion，
內容待全文核對後再定。

---

## 三、F11【語彙／先例參照・不需裁決】look-elsewhere effect

```
Conformal calibration and look-elsewhere effect in anomaly detection
for new-physics searches
arXiv:2606.13780（2026-06）
```

高能物理那側把「在很多地方找，總會找到一個看起來顯著的」稱為
**look-elsewhere effect**，並且已經在做「conformal 校準 + trials-factor 修正」。

**不是新穎性風險**：領域、機制、被選的對象都不同（它選的是搜尋空間裡的位置，
本論文選的是時間點，而且是被運維政策而非搜尋程序選的）。

**但它是第二個有用的先例**（第一個是 08-19 記的 CALIBURN）：
「刻畫一個把保形校準的保證打破的既有實務機制」本身就是可發表的貢獻型態。
R25 之後本論文正是這個形狀。

---

## 四、對 claim firewall 的建議（新增第六條，**待追認**）

現行五條見 `docs/manuscript/README.md` 界線四。建議新增：

> **禁止**任何形式的「我們發現／首次指出選擇效應會使條件覆蓋率主張失真」。
> 選擇後推論（post-selection inference）、selection-conditional coverage 與
> FCR 控制是既有文獻。本論文可守的是：**這個特定的既有運維機制
> （工單規則 6-of-18 + Freeze-on-Alert）產生選擇效應的幾何、其代數下界、
> 以及由此導出的三數字呈報協定**，不是選擇效應這個概念。

理由與 R25 同型：語彙層的領土已被佔用，貢獻要退到「這個機制、這個領域、
這個協定」那一層才守得住。**與 R25 不同的是這次不必改定位**——
R25 已經把定位改成 protocol-and-evidence，F10 落在那個定位裡面，只需加一條禁止。

---

## 五、第三軸第三次做不到 —— 本輪重新實測，不是沿用舊記錄

| 端點 | HTTP |
|---|---|
| `arxiv.org/abs/2403.03868` | `000` |
| `api.crossref.org/works?query=...` | `000` |
| `api.openalex.org/works?search=...` | `000` |
| `api.semanticscholar.org/graph/v1/paper/search?query=...` | `000` |
| `api.datacite.org/dois/10.5281/zenodo.14006163` | `000` |

**全部 egress 封鎖**（`000`，不是 403，也不是授權問題——與 POGO 作者程式那件
`403 + 授權範圍` 是不同原因，見 `POGO_COMPATIBILITY_GATE.md` 3.2，不要混記）。

**因此仍然成立**：稿件不得寫「first on CARE v6」或任何等價的資料集層新穎性主張。
三輪掃描都沒跑過被引用清單，沒掃過就不知道有沒有人做過。

**注意**：本輪的 F10 全部來自搜尋引擎摘要，`arxiv.org` 本身不可達，
所以連 F10 那六篇的**摘要原文**都沒讀到，只讀到搜尋結果的轉述。
這比 08-18／08-19 那兩輪的證據等級**更低**，處理上要更保守。

---

## 六、本機清單（新增，接在 PROJECT_STATUS 第 7 節第 8 項之後）

依優先序：

1. **arXiv:2403.03868**（JRSSB 2025 版更好）— F10 的主文獻
2. **arXiv:2403.07728**（CAP）— 線上選擇 + FCR，形狀最接近
3. **arXiv:2503.16809** — 線上選擇破壞可交換性；本論文 C2 的一般化敘述
4. arXiv:2605.22004、2301.00584、1905.01059 — 同軸，次要
5. arXiv:2606.13780（look-elsewhere）— 只需摘要，寫 Discussion 用
6. （既有）POGO 作者程式、arXiv:2606.00419v4、2606.20115、CARE 期刊版

---

## 七、F12【無紅旗】工單／維修單作為監督訊號

`FINDINGS` 4.3 提過：要區分「良性位移」與「慢速故障」，資訊必須來自分數之外，
而工單結案是唯一的候選。本輪查了別人怎麼取得這種標註。

- *Weak Supervision: A Survey on Predictive Maintenance*（WIREs DMKD, 2025）
- *Labelling Drifts in a Fault Detection System for Wind Turbine Maintenance*（arXiv:2106.09951）

共同做法：以**元件更換紀錄的缺席**當作 normal 的弱標籤；維修工單提供日期與
更換元件，用來定 ground truth。

**對本專案的意義有限但明確**：這條路在別人那裡也是靠**外部維修紀錄**才走得通，
不是從 SCADA 訊號本身推得的——與 FINDINGS 4.3 的判斷一致。
而 CARE v6 是否帶有可用且不洩漏的工單／維修時間資訊，**仍然無解**，
且那是 4.3 的前置問題。本輪沒有推進這一項，只是確認了方向沒有更便宜的走法。

---

## 八、下一輪建議的軸

1. **CARE v6 被引用清單**（三輪都做不到；**只能本機執行**）
2. **F10 的全文核對**（本機下載後填 Mandatory Overlap Check 四欄）
3. `conditioning on the alarm` / `alarm-conditional error rate` —— 本輪用的是
   保形推論那側的語彙；可靠度工程與製程管制（SPC）那側對「在警報成立期間量
   誤報率」可能另有名字（例如 run rules 的 ARL 條件化）。若有，值得一併引。
4. 已用過的關鍵詞見 08-18 第七節、08-19 第一節、本份第一節，**不要重掃**。

---

*建立：2026-08-20，排程自動化研究助理。所有判斷均為二手（本輪甚至是搜尋摘要
的轉述，連摘要原文都未讀），依 R17 不得直接寫入稿件；要進稿件必須先取得全文。*
