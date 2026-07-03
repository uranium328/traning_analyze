# 派工 prompt 模板

> 用法：複製對應模板，填 `【】` 內的空格，貼進 Agent tool 的 prompt。
> `model` 依 dispatch.md 第 1 節的表指定。所有模板都已內建回報合約，
> 不要刪掉回報段。`<scratchpad>` 指系統提示裡列出的 scratchpad 目錄路徑。

## 1. 搜尋（subagent_type: Explore；model: haiku，撲空一次後 sonnet）

```
目標：找出【要找的符號/行為/設定】的所在位置，我需要它來【動機】。
範圍：【目錄或 glob，例如 *.py 與 .github/**】。
可能的別名或變形：【例如 processed / mark_as_processed / PROCESSED_IDS】。

驗收條件：
- 每個命中點以「路徑:行號 — 一句話說明」列出。
- 明確說「除上述外，範圍內沒有其他命中」或「以下位置不確定」。

回報要求：只回清單與結論，不貼程式碼區塊；找不到就說找不到，
並列出你查過的範圍讓我能判斷是否要擴大。上限 300 字。
```

## 2. 實作（subagent_type: general-purpose；model: sonnet）

```
目標：在【檔案】實作【功能】。動機：【為什麼要做、上游是誰要用】。
規格：【輸入/輸出/邊界情況。有既有模式可抄就指出來，例如
「錯誤處理照 strava_client.py 的 fetch_activity_detail 寫法」】。
禁區：不要動【檔案/區塊】；不要 commit；機密紅線見 CLAUDE.md。

驗收條件（做完自己先核對，但最終驗收由另一個 verifier 執行，不必你做）：
- 【可判定的行為描述，例：clean_activity_data 對缺少 avgPower 的輸入
  回傳 None 而不是 KeyError】
- python -c "import 【模組】" 通過。
- 用假資料呼叫【函式】一次，貼出實際輸出（這是唯一允許貼的輸出）。

回報要求：改了哪些檔案（路徑:行號範圍）、驗收條件逐條打勾或打叉、
未解決的事項明列。上限 300 字。
```

## 3. 重構（subagent_type: general-purpose；model: sonnet；範圍大或跨模組時 opus）

```
目標：把【範圍】從【現狀】重構為【目標形態】。動機：【】。
不變式（重構後必須依然成立的行為）：
- 【例：main.py 的 process_activity 流程順序不變】
- 【例：processed_ids.txt 的讀寫格式不變，一行一個 id】
禁區：行為變更、順手修 bug、改公開介面命名——發現問題記下來回報，不要修。

驗收條件：
- 不變式逐條驗證（說明你用什麼方法驗的：實跑/對照輸出）。
- 全部被改檔案 import 成功。
- diff 裡沒有範圍外的檔案。

回報要求：改動摘要（每檔一行）、不變式驗證結果、發現但未動手的問題清單。
上限 300 字。
```

## 4. 研究（subagent_type: general-purpose；查 Claude Code/Anthropic 文件改用
claude-code-guide；model: sonnet）

```
問題：【要回答什麼】。動機：【答案會決定什麼後續行動】。
已知：【已經確認的事實，避免重查】。
來源優先序：官方文件 > 官方 GitHub repo（README/issues）> 其他。

驗收條件：
- 每個結論附出處 URL。
- 區分「文件明說」與「你的推論」。
- 查不到的部分明說查不到，禁止用訓練記憶充當查證結果。

回報要求：每個問題一段，先結論後出處。超過 30 行的整理寫到
<scratchpad>/research-【主題】.md，回報只給路徑+摘要。上限 600 字。
```

## 5. 審查／驗收（subagent_type: verifier；model 已固定在定義檔）

```
待驗物：【檔案清單或 diff 範圍】。
背景：執行者聲稱完成了【任務一句話】。你是 fresh-context 驗收者，
不要信任聲稱，只信你自己觀察到的。

逐條驗收：
- 【驗收條件 1，含驗法。例：讀 docs/garmin-refactor-plan.md 全文，
  確認包含「認證」「欄位對應」「CI」三節且結尾完整】
- 【驗收條件 2。程式碼類必須實跑，不接受目測 code 說「看起來對」】

回報要求：每條 PASS/FAIL/無法驗證 三選一；FAIL 要附證據（輸出原文或
路徑:行號）；不要動手修任何東西，包括你覺得順手的小錯。上限 300 字。
```

## 通用附註

- 派工前自問：這件事自己做是不是更便宜？（dispatch.md 第 1 節例外條款）
- 同一批可平行的派工（例如三個互不相依的搜尋）在同一則回覆裡一起發。
- subagent 回報回來後，主對話要做的事：對照驗收條件、決定收下/重派/升級，
  然後**只把結論**寫給使用者，不要轉貼整份回報。
