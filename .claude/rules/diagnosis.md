# 快速診斷：本環境三大失效模式與修法

> 寫於 2026-07-03，由 Fable 5 session 建立。這份是其他規則檔的依據；
> 修改本檔前先讀 [maintenance.md](maintenance.md)。
> 環境事實：Windows 11 + PowerShell 5.1 + VSCode 擴充版 Claude Code；
> 專案是小型 Python 專案（無測試、無 venv 檢出紀錄）；GitHub Actions 每小時
> 會自動 commit `processed_ids.txt` 回 main（訊息含 `[skip ci]`）。

## 第 1 名：最漏 token — 主對話親自大量讀檔、掃描、重讀

**症狀**：主對話直接 Read 整個檔案（其實只需要一個函式）、為了找一個符號連續
grep + Read 五六個檔案、Edit 之後再 Read 一次「確認有改到」、把長長的 JSON
或指令輸出原文留在對話裡。每一項都把 context 塞滿無用內容，後果是更早觸發
壓縮、遺忘早期的驗收條件。

**修法（可執行判準）**：
1. 「不知道東西在哪」→ 一律派 Explore subagent 去找，主對話只收
   `檔案:行號 + 一句結論`。判準：預估要開 **3 個以上檔案**才能回答的問題，
   就不要自己找。本專案是小型 repo（核心 Python 檔不到 10 個，以當下
   `ls *.py` 為準，不要背數字），讀 1–2 個已知檔案可以自己來。
2. Read 已知檔案時，超過 200 行的檔先用 Grep 定位行號，再帶 offset/limit 讀
   需要的區段。
3. **禁止** Edit/Write 成功後重讀同一檔案來「驗證」——工具失敗會直接報錯。
   驗證要交給 fresh-context agent（見 [dispatch.md](dispatch.md) 的驗證節）。
4. 超過 50 行的產出（報告、資料 dump、log）寫進檔案，對話裡只留路徑和三行摘要。

## 第 2 名：最容易失焦 — 規格漂移與邊界漂移

**症狀**：使用者問「為什麼會這樣？」，模型直接動手改 code；處理 A 檔時順手
重構旁邊的 B 檔；長任務做到一半忘記一開始的驗收條件，交出「做了很多事但
沒解原問題」的結果。本專案還有一個特有陷阱：CI 機器人每小時 commit
`processed_ids.txt`，git log 上滿是 bot commit，容易誤判「有人在改 code」
或誤把 bot 的變更捲進自己的 commit。

**修法（可執行判準）**：
1. 動手前先分類請求：**疑問句／「為什麼」／「分析」→ 只回報發現，不改任何
   檔案**，等使用者說「修吧」才動手。祈使句（幫我改、實作、修好）才直接做。
2. 多步驟任務開工第一件事：用 TodoWrite 把驗收條件寫成**可判定真假的句子**
   （例：「`python main.py` 在無新活動時正常結束、exit code 0」），收尾逐條核對。
3. 改動範圍以使用者指名的問題為界。看到界外的問題 → 記下來，在總結裡回報，
   **不動手**。
4. git 紅線：commit 前 `git status` + `git diff --staged` 確認只含自己的變更；
   訊息含 `[skip ci]` 的 commit 是機器人的，不要 revert、rebase 或歸因給使用者。

## 第 3 名：最容易出錯 — Windows/PowerShell 語法坑與本專案機密

**症狀**：在 PowerShell 5.1 用 `&&`（parser error）、用 `Out-File` 寫出
UTF-16 檔害 Python 讀不了、把 bash 語法丟進 PowerShell、同一條壞指令換皮重試
四五次。加上本專案的高危物：`tokens.json`（Strava/未來 Garmin 的 OAuth token，
在 .gitignore 內）絕不能 commit、print 到 log、或貼進對話。

**修法（可執行判準）**：
1. Shell 選擇：POSIX 語法（管線、heredoc、`&&`）一律用 **Bash tool**；
   Windows 專屬操作（registry、服務、`Test-Path`）才用 PowerShell。不要混用語法。
2. PowerShell 5.1 三禁：禁 `&&`／`||`；寫檔必加 `-Encoding utf8`；
   禁 `2>&1` 重導 native 執行檔的 stderr。
3. **兩振規則**：同一目的的指令改寫兩次仍失敗 → 停止盲試，改讀文件或換工具
   （例如改用 Python 一行腳本），第三次盲試視為違規。
4. 機密紅線：任何工具呼叫的參數或輸出**不得包含 `tokens.json` 的內容**、
   API key、Discord webhook URL。需要確認 token 狀態時只看檔案是否存在與
   `expires_at` 欄位。

## 這三條落在哪裡

- 第 1 名 → 制度化在 [dispatch.md](dispatch.md)（指揮官不下場）
- 第 2 名 → 制度化在 [judgment.md](judgment.md)（完成定義、方向錯訊號）
- 第 3 名 → 精簡版直接寫在 CLAUDE.md（每個 session 都要看到）
