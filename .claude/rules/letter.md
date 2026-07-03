# 給未來 session 的信

> 寫於 2026-07-03，Fable 5 建制 session。你（正在讀信的模型）大概率是
> Sonnet/Opus/Haiku。這封信講三件使用者沒問、但我認為對這個環境最重要的事，
> 以及這套制度最可能怎麼壞掉。

## 一、這個 repo 的真正風險在 CI 的機密流轉，不在程式碼

`coach.yml` 的設計是：GitHub secret 還原 `tokens.json` → 跑完 → 用
`GH_PAT`（一個有 secrets 寫入權的 PAT）把刷新後的 token 寫回 secret。
這條鏈有兩個脆弱點：(1) `GH_PAT` 權限很大，任何人建議「順便讓 workflow
多做點事」時要警惕權限擴散；(2) workflow log 若不小心 echo 出 token 就外洩了。
**Garmin 重構後這條鏈可以大幅簡化**（garth token 效期約一年，回寫步驟可拔掉）
——重構時主動提醒使用者拔掉 `GH_PAT`，這是降風險的免費機會。

## 二、這個專案沒有測試，你的「完成」比別的專案更容易是假的

沒有測試套件、沒有 CI 檢查、`main.py` 在本機因缺 `.env` 跑不完整——代表
你改壞東西不會有任何東西攔你，會直接在下一個整點於使用者的 Discord 炸開。
所以 judgment.md 第 5 節的「假資料實跑」不是儀式，是這個 repo 唯一的安全網。
更好的做法：如果你被派去做 Garmin 重構，**第一步先建一個最小 smoke test**
（假 activity dict 進 clean → 出欄位斷言），成本 20 行，之後每個 session 受益。

## 三、使用者的工作模式：一次到位的計畫型，不是碎步迭代型

從兩次互動看：使用者會先要完整構思、確認方向、再授權動手；動手後期望自主
完成、不要中途碎問（他明確說過「之後不再停下來等我」）。所以：前期多花
token 把計畫寫清楚是值得的；動手階段照 judgment.md 第 3 節，只有四類事
值得打斷他。溝通用繁體中文。Garmin 重構的完整計畫已落檔在
`docs/garmin-refactor-plan.md`，是使用者口頭認可過方向的版本，直接執行它，
不要重新發明。

## 這套制度最可能的退化方式與預防

1. **儀式化派工（最可能）**：把「指揮官不下場」執行成「任何小事都開 agent」，
   token 反而漏更兇，然後某個 session 覺得制度愚蠢就整個不遵守。
   預防：dispatch.md 第 1 節的例外條款和「派工說明超過自己做的成本就自己做」
   判斷式，與規則本體同等效力。制度的目的是省 token 和降錯誤率，
   當它明顯造成反效果，回報使用者而不是默默棄用。
2. **規則膨脹到沒人讀**：每次踩坑都加一條，兩個月後 CLAUDE.md 300 行，
   等於沒有規則。預防：maintenance.md 第 3 節的行數上限是硬性的，
   超標就精簡，精簡優先於新增。
3. **檔案與現實脫節後失去公信力**：某個路徑失效、某個參數改名，讀者發現
   一處錯誤就開始懷疑全部。預防：發現錯就照 maintenance.md 綠區立即修
   （這是所有 session 的義務，不是選項），修不動的標註「疑似過時」。
4. **驗證不自驗被偷懶掉**：趕時間的 session 會想「我自己看一眼就好」。
   預防：verifier 的成本刻意壓低（sonnet、只回 PASS/FAIL），讓守規矩比
   找藉口便宜。若真的跳過驗證，總結裡必須寫明「未經獨立驗證」。

## 交接狀態（建制 session 結束時）

- 已完成：CLAUDE.md、diagnosis / dispatch / judgment / templates /
  maintenance / letter、docs/garmin-refactor-plan.md、verifier agent、
  記憶檔（memory 目錄）。
- 未完成、留給你們：Garmin 重構本體（照計畫書執行）；smoke test（見本信
  第二點）；重構完成後更新 CLAUDE.md 狀態段與 `.env.example`、
  提醒使用者清理 Strava secrets 與 `GH_PAT`。
