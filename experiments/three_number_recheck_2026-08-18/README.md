# 三數字誤報呈報（R24）對既有實驗輸出的重算 — 2026-08-18

**執行者：排程自動化研究助理　　性質：重算既有輸出，未重跑任何模型**

---

## 一、為什麼要做這件事

R24 於 2026-08-17 裁決並實作：誤報率改為三數字呈報。實作動的是**評估尺規**
（`evaluate_experiment.py`、`regime_conditional_calibration.py`），
已簽核的模型參數一律未動。

但 `experiments/MD_2022_a*_evaluation/` 底下已提交的
`comparison.md` 與 `evaluation.json` 是 **2026-08-16 產生的**，
早於 R24。它們的表頭沒有 `frozen %` 與 `FAR frozen` 兩欄，
頭號數字仍是**混算凍結與未凍結之後的 pooled 值**。

**後果是具體的，不是形式上的。** 以 α=0.01 為例，已提交的表格長這樣：

| method | worst-bin dev |
|---|---|
| w1acas | 0.0111 |
| aci | 0.0165 |
| dtaci | 0.0198 |
| **ours** | **0.0602** ← 五個方法裡排第四 |
| static | 0.1295 |

任何今天點進 `experiments/` 的人——協作者、未來的自己、拿到 repo 連結的
審稿人——讀到的是「本方法在條件覆蓋率上輸給三個基線」。
而 R24 裁定那個數字**不得作為頭號數字**，因為它把「方法刻意暫停校準的期間」
算進了校準保證裡。

這是 `docs/PROJECT_STATUS.md` 第 5 節那份清單的同型事件：
**不會報錯，跑得完，數字也是真的算出來的，只是它回答的不是我們要問的問題。**

---

## 二、做了什麼

用**現在 main 上的** `evaluate_experiment.py`（含 R24 三數字實作），
對**既有的逐案輸出**重新計算。沒有重跑 base scorer，沒有重跑校準層，
沒有重跑任何基線——輸入完全是版控裡已經有的那些 CSV。

```
scripts/evaluate_experiment.py \
  --scores-dir ./scores_MD_2022_run1 --wind-col wind_speed --timestamp-col timestamp \
  --g3-case-metadata ./manifest_out/g3_case_metadata.csv \
  --alpha <0.001|0.01|0.05> --window 1440 \
  --method ours=./experiments/MD_2022_a<A>_ours:p_value:pvalue \
  --method w1acas=./experiments/MD_2022_w1acas:beta:pvalue \
  --method aci=./experiments/MD_2022_a<A>_baselines:aci_alarm:alarm \
  --method dtaci=./experiments/MD_2022_a<A>_baselines:dtaci_alarm:alarm \
  --method static=./experiments/MD_2022_a<A>_baselines:static_split_conformal_alarm:alarm \
  --reference static --output-dir <此目錄>/a<A> \
  --exclude-cases 32,56,72,87 --trim-case 93=2023-08-24T13:00:00
```

與 2026-08-16 那次的差別**只有兩處**：`--output-dir`，以及
**沒有 `--event-info-root`**（原因見第四節）。排除案、裁切、α、W、
工單規則、參照方法全部相同。

---

## 三、結果：頭號數字換了，名次也換了

`worst-bin dev`，n = 47 個正常案例，逐 α：

| α | 方法 | 舊表（pooled，含凍結） | **新表（未凍結）** | 凍結佔比 | 凍結點誤報率 |
|---|---|---|---|---|---|
| 0.001 | w1acas | 0.0010 | 0.0010 | — | — |
| 0.001 | **ours** | 0.0114（第 4） | **0.0017（第 2）** | 0.5% | 0.7711 |
| 0.001 | aci | 0.0026 | 0.0026 | — | — |
| 0.001 | dtaci | 0.0040 | 0.0040 | — | — |
| 0.001 | static | 0.0635 | 0.0635 | — | — |
| **0.01** | **ours** | **0.0602（第 4）** | **0.0036（第 1）** | 4.9% | 0.6819 |
| 0.01 | w1acas | 0.0111 | 0.0111 | — | — |
| 0.01 | aci | 0.0165 | 0.0165 | — | — |
| 0.01 | dtaci | 0.0198 | 0.0198 | — | — |
| 0.01 | static | 0.1295 | 0.1295 | — | — |
| **0.05** | **ours** | **0.2100（第 4）** | **0.0144（第 1）** | **23.4%** | 0.7068 |
| 0.05 | w1acas | 0.0532 | 0.0532 | — | — |
| 0.05 | aci | 0.0716 | 0.0716 | — | — |
| 0.05 | dtaci | 0.0803 | 0.0803 | — | — |
| 0.05 | static | 0.2379 | 0.2379 | — | — |

**基線的數字一個都沒變**（它們沒有凍結機制，該欄印 `—`，不是 `0%`）。
變的只有 `ours`，因為只有 `ours` 有 `frozen` 欄可以切。
**這正是重算應該有的樣子**：如果基線的數字也跟著動了，那就代表改的不只是呈報。

三處交叉核對，都對上：

1. 新表的 `pooled dev` 欄與**舊表的 `marginal dev` 欄逐格相同**
   （α=0.01 的 ours 兩邊都是 0.0345）。
2. 新表的 `ours` pooled worst-bin（記在 JSON 的
   `comparison.ours.mean_worst_bin_deviation`）與**舊表的頭號欄相同**
   （0.0602400546…）。**舊數字沒有被否定，只是被移出頭號位置。**
3. 三數字反算 pooled 誤報率：`exhaustive: true`，
   α=0.01 殘差 **6.9e-18**，α=0.05 與 α=0.001 殘差 **0.0**。

α=0.05 那一列要一起讀凍結佔比：**23.4% 的點處於凍結狀態**。
0.0144 是真的，23.4% 也是真的，兩個必須並排——這正是 R24 護欄的用意。

---

## 四、這份重算**不能**取代已提交的評估輸出

**lead-time 相關的四欄（`detected`／`median lead`／`lead, miss=0`／`lead lost`）
在本目錄的檔案裡全部是 `n/a`。**

原因不是程式有問題，是**輸入缺一項**：lead time 要從 `event_info.csv` 取
`event_start`，而 CARE v6 原始資料不在版控裡（太大且有授權問題），
雲端這側沒有。`--event-info-root` 是選填參數，不給就不算 lead time——
不會報錯，只會把那些欄位留空並在 `evaluation.json` 記成 `null`。

因此：

- **本目錄只換掉誤報率那一半的呈報，另一半是空的。**
- **不要**用本目錄的檔案覆蓋 `experiments/MD_2022_a*_evaluation/`，
  那會把 2026-08-16 那輪唯一存在的 lead-time 證據刪掉，換成一排 `n/a`。
- 正確的收尾是**本機端重跑一次完整的 Phase 5 評估**（帶 `--event-info-root`），
  讓已提交的三份 `evaluation.json` 同時具備三數字誤報**與** lead time。
  指令與 2026-08-16 那次完全相同，因為尺規的改動不需要新參數；
  唯一要確認的是跑的是 main 上現在這版 `evaluate_experiment.py`。

在本機重跑完成之前，`experiments/MD_2022_a*_evaluation/` 的頭號數字仍是
舊協定的。**已在 `docs/PROJECT_STATUS.md` 標註，避免有人讀到舊排名而不知道
那是舊的**——那正是 8.0a 記載的失效模式（讀到舊狀態，而且沒有任何跡象提示）。

---

## 五、給稿件的一句話

Results 引用的 `worst-bin deviation` 一律取本目錄的**未凍結**值
（0.0017 / 0.0036 / 0.0144），並**在同一張表裡**列出凍結佔比
（0.5% / 4.9% / 23.4%）與凍結點誤報率（0.7711 / 0.6819 / 0.7068）。
lead-time 數字**仍取 `experiments/MD_2022_a*_evaluation/`**，
因為只有那一輪算得出來。

**兩個來源要在稿件的表註裡寫明**，不要讓讀者以為整張表出自同一次執行。

---

*建立：2026-08-18，排程自動化研究助理。*
