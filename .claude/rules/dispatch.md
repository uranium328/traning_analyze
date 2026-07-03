# 模型調度守則

> 適用對象：擔任主對話的任何模型（Sonnet、Opus、Haiku 皆可執行）。
> 依據：[diagnosis.md](diagnosis.md) 第 1 名失效模式。
> 以下 model / effort 值已於 2026-07-03 對照官方文件查證。

## 0. 本環境可用的資源（查證過，不要憑印象改）

- **Agent tool 的 `model` 參數**：`sonnet` | `opus` | `haiku` | `fable`。
  不指定時繼承主對話模型。`fable` 只在使用者方案允許時可用，派工預設不要用它。
- **subagent 定義檔** `.claude/agents/*.md` frontmatter：`model`（同上，另有
  `inherit`）、`effort`（`low`|`medium`|`high`|`xhigh`|`max`）、`tools`（逗號分隔）。
- **內建 subagent 類型**：`Explore`（唯讀搜索）、`Plan`（規劃）、
  `general-purpose`（全工具）、`claude-code-guide`（查 Claude Code/API 文件）。
- **本專案自訂**：`verifier`（fresh-context 驗收，定義在
  `.claude/agents/verifier.md`）。
- 全域 `settings.json` 的 `effortLevel`：`low`|`medium`|`high`|`xhigh`（無 max）。

## 1. 指揮官不下場

主對話的工作是：理解需求、拆任務、派工、整合結論、對使用者負責。
以下四類工作**不要在主對話親自做**，一律派 subagent，主對話只收結論：

| 工作 | 派給 | model | 判準 |
|---|---|---|---|
| 大量讀取／找東西在哪 | Explore | haiku（找不到再 sonnet） | 預估要開 ≥3 個檔案才能回答 |
| 掃整個 repo（盤點、統計、找所有呼叫點） | Explore | sonnet | 涉及「所有」「每個」「盤點」字眼 |
| 查網頁／查外部文件 | general-purpose 或 claude-code-guide | sonnet | 需要 WebSearch/WebFetch 超過一次 |
| 批次改檔（同一模式改 ≥3 個檔案） | general-purpose | sonnet | 模式已由主對話定案、有範例可抄 |

**例外**：本專案是小型 repo（核心 Python 檔不到 10 個，以當下 `ls *.py`
為準）。讀 1–2 個已知路徑的檔案、做一次精準
Grep、改一個檔案——這些自己做比派工便宜，不要為了儀式感派 agent。
判斷式：**「派工說明 + 回報」的字數若可能超過自己做的 token，就自己做。**

## 2. 派工三件套（缺一不派）

每個 Agent prompt 必含三段，模板見 [templates.md](templates.md)：

1. **目標與動機**：要達成什麼、為什麼（讓 subagent 遇到岔路時能自行取捨）。
2. **驗收條件**：可判定真假的句子列表。壞例：「把搜尋做完整」。
   好例：「列出所有呼叫 `mark_as_processed` 的檔案與行號，並確認沒有遺漏
   `main.py` 以外的呼叫點」。
3. **回報格式**：明確規定回什麼、多長。預設合約見下節。

同時**顯式指定 `model`**（按第 1 節的表），需要非預設 effort 時用自訂 agent
定義檔（frontmatter `effort`），Agent tool 本身沒有 effort 參數。

## 3. 回報合約（寫進每個派工 prompt 的固定尾段）

```
回報要求：
- 只回結論與證據位置（檔案路徑:行號），不要貼大段程式碼或原始輸出。
- 超過 30 行的產物寫到 <指定路徑>，回報裡只給路徑與 3 行摘要。
- 找不到、做不到、不確定的部分明說，不要編造。
- 回報總長度上限 300 字（研究型任務放寬到 600 字）。
```

長產物的指定路徑：分析報告放 scratchpad（系統提示裡有路徑）；要留給未來
session 的放 `docs/` 或 `.claude/rules/`（先讀 maintenance.md）。

## 4. 升降級路徑

- **haiku 派工失敗一次**（驗收不過、回報明顯錯誤）→ 直接升 sonnet 重派，
  不要對 haiku 重試同一任務。
- **sonnet 同一子任務連錯兩次** → 升 opus，且 prompt 要附上**完整失敗軌跡**：
  兩次嘗試各做了什麼、驗收哪一條沒過、錯誤訊息原文。不附軌跡的升級等於重擲骰子。
- **opus 也解不了** → 停下來，把問題與失敗軌跡整理給使用者（見 judgment.md
  「何時該問使用者」）。
- **降級**：一旦某類問題被高階模型解出「可複製的模式」（例如：確定了 Garmin
  欄位對應表），後續同模式的批次套用降回 sonnet 甚至 haiku 執行。
- **重試上限**：同一子任務在**同一個模型**上最多兩輪完整嘗試；升級模型後
  計數歸零。第三輪之前必須換方法、換模型、或升級到「問使用者」，禁止原地再試。
  （注意：這是任務層級的計數；CLAUDE.md 的「兩振規則」是單一 shell 指令
  層級的計數，兩者分開算。）

## 5. 驗證不自驗

寫 code 或改檔的人（包含主對話自己）不做最終驗收。驗收一律派
**fresh-context 的 `verifier` agent**（`.claude/agents/verifier.md`，
model: sonnet），因為它沒有「我剛剛已經做對了」的偏見。
**保底條款**：若當下 session 的可用 agent 清單裡沒有 `verifier`（定義檔
未被載入），改派 `general-purpose`（model: sonnet），並把
`.claude/agents/verifier.md` 正文的 6 條規則原文貼進 prompt 開頭——
「驗證不自驗」不因 agent 註冊問題而豁免。

- **檔案類產出**：verifier read-back — 逐檔確認存在、完整（非空、非截斷）、
  內容與驗收條件相符。
- **程式碼類產出**：verifier 實跑 — 有測試跑測試；沒測試（本專案現況）至少
  `python -c "import <module>"` + 用假資料呼叫被改的函式，觀察行為而非只看 code。
- **高風險判斷**（架構選型、要不要刪東西、對外發送）：加第二意見 — 另派一個
  fresh agent 給同樣輸入獨立作答，兩答案不一致時把分歧點呈給使用者裁決；
  或產生 2–3 個候選答案後派 fresh agent 當評審選優。
- 驗收不過 → 回到原執行者修（計入第 4 節的重試次數），不要讓 verifier 順手修。

## 6. 誠實條款：這套制度補不了的事

拆解、驗證、多樣本評審能把「執行品質」拉到接近高階模型；但**模糊需求的解讀、
品味與取捨**（prompt 的語氣好不好、報告寫得動不動人、兩個都能跑的架構哪個對）
補不了。遇到這類問題：小事選保守選項並在總結標註「此處是品味判斷，可推翻」；
大事列 2–3 個選項附一句 trade-off 問使用者。不要假裝這類問題有客觀答案。
