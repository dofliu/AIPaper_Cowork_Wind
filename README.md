# AIPaper_Cowork_Wind

**風能運維的線上保形校準**（regime-conditional online conformal calibration）
——把一個凍結的異常分數包上一層校準，讓誤報率在**每一個風速區間內**都守住名目值，
而不是只在平均上守住，且不犧牲提前預警。資料集是 CARE v6。

這個 repo 放**程式與現況**。討論、裁決、日誌放 Google Drive。兩邊的分工見下方第四節。

> **這個 repo 是公開的**（public）。任何拿到連結的人都能讀、能 clone，
> 不需要先申請權限。要 push 才需要權限——請向劉老師（@dofliu）要。

---

## 一、先讀哪一份

**專案現況一律以 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) 為準。**
不是這份 README，也不是 Drive 上的日誌。

這份 README **刻意不寫任何會變動的數字**（測試數、案數、實驗結果、待裁決清單）。
理由就是本專案吃過最大的虧：同一個狀態存在兩個地方，它們一定會分歧，
而讀到舊的那份的人不會知道自己讀到的是舊的。要數字，去 PROJECT_STATUS。

| 你想知道 | 看哪一份 |
|---|---|
| 現在卡在哪、哪些事已確立、哪些待裁決 | [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) ← **狀態以此為準** |
| 我要在自己的機器上跑，指令是什麼 | [`docs/LOCAL_RUNBOOK.md`](docs/LOCAL_RUNBOOK.md) |
| 每支腳本各自在做什麼 | [`scripts/README.md`](scripts/README.md) |
| Freeze-on-Alert 鎖死是怎麼回事 | [`docs/FREEZE_LOCKIN_FINDINGS.md`](docs/FREEZE_LOCKIN_FINDINGS.md) |
| 這個專案踩過哪些坑（**新人請務必讀**） | PROJECT_STATUS 第 5 節 |

新協作者的建議順序：**本 README → PROJECT_STATUS 全文 → PROJECT_STATUS 第 5 節再讀一次**。
第 5 節是「最重要的一課」——到目前為止最嚴重的缺陷沒有一個會報錯，
它們全部照常跑完、照常輸出漂亮的數字，只是數字是錯的。

---

## 二、快速開始

```bash
git clone https://github.com/dofliu/AIPaper_Cowork_Wind.git
cd AIPaper_Cowork_Wind
```

只需要 **Python 3**，沒有任何第三方套件依賴（標準函式庫寫成，刻意如此）。

碰真實資料之前先跑自我測試，確認整套工具在你的環境行為正確：

```bash
for t in scripts/selftest_*.py; do echo "== $t"; python3 "$t" | tail -2; done
```

```powershell
Get-ChildItem scripts\selftest_*.py | ForEach-Object {
  Write-Host "== $($_.Name)"; python $_.FullName | Select-Object -Last 2 }
```

**預期全部以 `ALL SELF-TESTS PASSED` 結尾、0 failed。**
應有的支數與 checks 數記在 `docs/LOCAL_RUNBOOK.md` Phase 0.3——
任何一支不是 0 failed 就先停下來，把完整輸出回報，不要繼續往下跑。
那代表工具在你的環境與雲端行為不同，之後所有結果都不可信。

實驗本身是設定檔驅動的單一指令，見 LOCAL_RUNBOOK Phase 5。

---

## 三、目錄結構

```
docs/          現況、執行手冊、分析報告  ← 先讀這裡
scripts/       全部程式（提出方法、基線、閘門、診斷、自我測試）
experiments/   實驗輸出（逐案 CSV 與比較表）
manifest_out/  D0 manifest 與 case metadata
scores_*/      base scorer 產出的分數串流
*_out/         各檢查工具的輸出
```

`scripts/` 裡的檔案分四類，`scripts/README.md` 有逐支說明：

- **產生數字的**：`regime_conditional_calibration.py`（本論文提出的方法）、
  `base_scorer_md2022.py`、`baseline_w1_acas.py`、`baselines_online_calibration.py`、
  `evaluate_experiment.py`（共同評估尺規）、`run_pipeline.py`
- **資料準備與閘門**：manifest、signal map、C0–C6 gate、洩漏稽核、品質深掃
- **診斷**：回答「這個數字為什麼怪」的一次性工具，但都留在版控裡
- **`selftest_*.py`**：每支工具自己的行為測試

---

## 四、Drive 與 GitHub 的分工

| | 放什麼 | 為什麼 |
|---|---|---|
| **GitHub（這裡）** | 程式、**現況**、分析報告、手稿 | 有版控：唯一歷史、衝突偵測、可 diff |
| **Google Drive** | 裁決請求、開發日誌、討論紀錄 | 適合流水帳與需要劉老師簽核的往返 |

**Drive 上的日誌只記「某天做了什麼」，不記「現在是什麼狀態」。**

這不是潔癖。多位協作者（Gemini Spark、Codex B、Claude E、排程自動化研究助理，
外加不只一個同時執行的 session）在 Drive 上各自遞增版本號，
到 2026-08-15 已累積 **6 組撞號**，最嚴重的一次是 v4.0 已存在後又出現一份 v3.9
——**最新的紀錄反而掛著最舊的版號**。根因不是誰粗心：版本號是需要全域協調的
計數器，並行寫入必然碰撞。版控天生沒有這個問題。

判斷 Drive 上哪一份最新時：**看標題裡的時間戳，不要看版號。**
命名規範與完整原委見 PROJECT_STATUS 第 8.1 節。

---

## 五、怎麼參與

**分支與 PR**

- 不要直接 push 到 `main`。開自己的分支，發 PR。
- PR 先開成 **draft**，內文要寫清楚：做了什麼、**證據是什麼**、以及哪些是還沒驗證的。
- 合併由劉老師決定。

**寫程式的話，這個專案有幾條硬規矩**（完整版在 PROJECT_STATUS 第 5 節）：

1. 每支工具都要有自己的行為測試。
2. 新測試要**反向驗證**——把修正還原，確認測試真的會失敗。只會 PASS 的測試是裝飾。
3. 檢查要能**兩個方向都失敗**。只往一邊失敗的檢查不是證據。
4. 取樣要說明涵蓋率。
5. 物理範圍、閘門門檻這類定義只能有**一份**。
6. 任何要呈報為「方法限制」的負面結果，呈報前先在真值已知的合成資料上做一次歸因，
   確認那個限制不是量尺造成的。
7. **統計量一律連同分母一起呈現。**

**已簽核的參數不得擅動。** α、工單告警規則 6-of-18、視窗 W、風速分箱、
每格最少樣本數等等都經劉老師簽核，清單在 PROJECT_STATUS 第 3 節。
要改必須先出裁決請求。

**語言**：討論與進度文件用中文，實際投稿文件用英文。

---

## 六、目前不在這個 repo 裡的東西

- **CARE v6 原始資料**：資料集本身不放版控（太大，且有授權問題）。
  路徑由本機端提供，見 LOCAL_RUNBOOK。
- **Base Scorer 2（MainBearing_2026）**：需要主軸承 SCADA 框架論文的實作，
  雲端這側沒有，只能由本機提供。
- **CARE 論文本身**：尚未取得全文，所以 CARE 的 adaptive threshold 基線
  明確標記為 `NOT_IMPLEMENTED`，呼叫即拋例外。
  **寧可缺一個基線，不可拿近似值冒充原作。**
