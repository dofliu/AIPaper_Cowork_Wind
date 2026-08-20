# Phase 5 實驗執行報告

- 執行日期：2026-08-20（Asia/Taipei）
- Git commit：`cb9529ddf5b810847a8b2a73fe1c6a1c520ab2c9`
- 作業系統：Linux 6.18.35 x86_64
- Python：3.12.13
- 正式批次耗時：約 30 分鐘
- 協定：`detection-horizon-v1.0`（R27）
- 主要偵測門檻：14 天
- 宣告掃描：7、10、14、21 天與不設限

## 執行狀態

1. Dropbox 中 Wind Farm A、B、C 的三份 `event_info.csv` 均已取得。
2. 16 支 self-test 全數通過：480 checks、0 failed。
3. 正式 runner 完成 15/15 runs，退出碼 0。
4. 正式 verifier 通過，退出碼 0：21 checks、0 failed。
5. 所有 run 均為 91 cases，FAR 使用 47 個 normal cases。
6. 四個案例 32、56、72、87 均排除；case 93 均裁切 18 列。
7. 三數字 FAR 協定在每輪均可完整反算 pooled 值。
8. 三個 H=14 天的 primary runs 均已產出。

## H=14 天主要結果（本方法）

| α | worst-bin dev（unfrozen） | frozen % | FAR frozen | detected | median lead (d) | lead, miss=0 (d) | non-inferior |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 0.001 | 0.001738 | 0.470% | 0.771107 | 19/44（43.2%） | -2.49 | 0.00 | NO |
| 0.01 | 0.003575 | 4.939% | 0.681875 | 44/44（100%） | 7.90 | 7.90 | yes |
| 0.05 | 0.014424 | 23.387% | 0.706762 | 44/44（100%） | 13.80 | 13.80 | yes |

## 掃描判讀

- α=0.01：五個 H 全部 non-inferior；不設限時 lead loss = 1.965 天，接近但仍通過 2 天界線。
- α=0.05：五個 H 全部 non-inferior。
- α=0.001：五個 H 全部未通過 non-inferiority；H=14 天只偵測 19/44，median lead 為 -2.49 天。
- 因此，「整個 H 掃描範圍均 non-inferior」可支持 α=0.01 與 α=0.05，但不能泛化到三個 α 全部。

## 文件與實作差異

`docs/PHASE5_RUNBOOK.md`／附件預期驗收顯示 35 checks，但 commit
`cb9529d` 的 `scripts/verify_phase5_output.py` 實際把逐輪條件彙總計數，
正式輸出為 21 checks、0 failed。verifier 自身的 20-check self-test 已通過。
本批次依實際 verifier 的退出碼 0 判定 accepted，但文件中的 35 應另行修正，
避免未來執行者誤判。

## 正式指令

```bash
python3 scripts/run_phase5_evaluation.py \
  --event-info-root ../care_event_info \
  --output-root ./experiments/phase5_2026-08-20

python3 scripts/verify_phase5_output.py \
  ./experiments/phase5_2026-08-20
```

