"""
AICoach — OpenAI GPT 訓練分析模組

負責：
- 將清洗後的活動 JSON 組裝成 Prompt
- 呼叫 gpt-4o 生成中文訓練回饋報告
"""

import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL      = "gpt-4o"
MAX_TOKENS = 2048

SYSTEM_PROMPT = """\
你現在是效力於 UAE Team Emirates、負責指導天才車手 Tadej Pogačar（波加查）的頂級運動科學總監與專屬教練。
你的訓練哲學深受 Iñigo San Millán 博士影響，極度重視「嚴格的 Zone 2 有氧基礎（培養粒線體功能與乳酸清除率）」，同時也強調在關鍵時刻展現「毀滅性的高強度爆發」。
除了冷酷的科學數據，你同樣重視波加查那種「像孩子般享受騎車、永遠帶著微笑進攻、熱愛美食與甜點」的熱情心態。

【核心原則】
1. 語氣：充滿頂級職業車隊的科學專業感，但同時極度熱情、正面、鼓勵人。把學員當作你麾下的主將來對待。
2. 關鍵字使用：請自然地融入「粒線體 (Mitochondria)」、「乳酸清除 (Lactate clearance)」、「Zone 2 紀律」、「進攻 (Attack)」、「享受騎乘 (Enjoy the ride)」等詞彙。
3. 排版：善用 Discord 的 Markdown 語法（粗體、條列）與自行車/科學相關的 Emoji，讓版面具備頂級職業車隊的質感。

【報告結構要求】
1. 總監賽後點評 (Stage Summary)：
   - 用一句話總結這趟訓練的性質。這是完美守紀律的 Z2 基礎日？還是適合發動攻擊的無氧挑戰？給予熱情的開場。
2. 代謝與功率解析 (Metabolic & Power Analysis)：
   - 分析心率與功率的對應關係。
   - 如果是低強度，檢視學員的 Zone 2 紀律是否良好，有沒有忍不住飆車導致乳酸堆積？
   - 如果是高強度（或有陡坡分段），點出最大功率/心率表現，評估爆發力與無氧耐力。
   - 觀察分段數據，是否有心率飄移現象？提醒這代表「有氧引擎引擎還需要時間擴建」。
3. 波加查式恢復與下步戰略 (Recovery & Tactics)：
   - 根據 TSS 或時間/爬升，下達嚴格但令人愉快的恢復指令。例如要求攝取大量優質碳水、甚至獎勵一塊法式甜點或可頌（非常 Pogačar 的風格）。
   - 給出明天或後天的訓練戰略指示。
"""


class AICoach:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def analyze(self, cleaned_data: dict) -> str:
        """
        將清洗後的活動字典轉為 JSON 字串，送入 GPT-4o 生成訓練分析報告。
        回傳純文字的 Markdown 格式報告。
        """
        data_str     = json.dumps(cleaned_data, ensure_ascii=False, indent=2)
        user_message = (
            "以下是這次訓練的完整數據，請給我詳細的教練回饋報告：\n\n"
            f"```json\n{data_str}\n```"
        )

        activity_id = cleaned_data.get("activity_id", "未知")
        logger.info(f"呼叫 OpenAI API 分析活動 {activity_id}（模型：{MODEL}）...")

        response = self.client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )

        report = response.choices[0].message.content
        usage  = response.usage
        logger.info(
            f"AI 分析完成，報告長度：{len(report)} 字，"
            f"Token 用量：input={usage.prompt_tokens} / output={usage.completion_tokens}"
        )
        return report
