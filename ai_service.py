"""
ai_service.py
封裝所有 GPT API 呼叫，供 dictionary_manager 與 dictionary_home 使用。

主要函式：
  - enrich_word_with_gpt(word)     → dict  結構化補資料（讀音/詞性/中文/例句）
  - generate_cloze_question(word)  → dict  AI 情境克漏字
  - validate_cloze_answer(...)     → dict  驗證克漏字答案
"""

import json
import threading
from app_settings import load_openai_api_key, load_google_api_key, load_settings

# ── 延遲匯入 openai，避免啟動時拖慢速度 ──────────────────────────────
_openai_client = None
_openai_lock = threading.Lock()


def _get_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    with _openai_lock:
        if _openai_client is not None:
            return _openai_client

        try:
            import openai
            api_key = load_openai_api_key()
            if not api_key:
                raise ValueError("找不到 OpenAI API Key，請在設定中填入。")
            _openai_client = openai.OpenAI(api_key=api_key)
            return _openai_client
        except Exception as e:
            raise RuntimeError(f"OpenAI 初始化失敗：{e}")


def _reset_client():
    """重新建立 client（當 API Key 更新後呼叫）"""
    global _openai_client
    with _openai_lock:
        _openai_client = None


def _call_openai_json(system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> dict:
    client = _get_client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=800
    )

    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def _call_google_json(system_prompt: str, user_prompt: str, model: str = "gemini-2.5-flash") -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("請安裝 google-genai 套件以使用 Google API")

    api_key = load_google_api_key()
    if not api_key:
        raise ValueError("找不到 Google API Key，請在設定中填入。")

    client = genai.Client(api_key=api_key)
    
    # Configure JSON response type
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7,
            max_output_tokens=4000
        )
    )
    
    content = response.text or "{}"
    return _clean_and_parse_json(content)


def _clean_and_parse_json(text: str) -> dict:
    """清洗 LLM 回傳的 JSON 字串，處理 markdown 包裝與截斷問題。"""
    import re
    text = text.strip()

    # 移除 ```json ... ``` 或 ``` ... ``` 包裝
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # 嘗試直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 找到第一個 { 的位置，截取後再試
    start = text.find("{")
    if start > 0:
        text = text[start:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 若 JSON 被截斷，嘗試補上結束括號
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1

    if depth > 0:
        repaired = text + ("}" * depth)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    # 最後放棄，回傳空 dict
    print(f"[ai_service] JSON 解析失敗，原始回應：{text[:200]}")
    return {}




def _call_llm_json(system_prompt: str, user_prompt: str) -> dict:
    """
    通用 LLM 呼叫，強制回傳 JSON。
    根據設定決定呼叫 OpenAI 或 Google Gemini。
    """
    settings = load_settings()
    provider = settings.get("ai_provider", "openai")
    
    if provider == "google":
        return _call_google_json(system_prompt, user_prompt)
    else:
        return _call_openai_json(system_prompt, user_prompt)


# ═══════════════════════════════════════════════════════════════════════
# 1. 結構化 AI 補資料
# ═══════════════════════════════════════════════════════════════════════

ENRICH_SYSTEM_PROMPT = """\
你是日文語言學家，也精通中文和英文。
使用者給你一個日文單字（可能是漢字、假名或混合）。
請嚴格回傳以下 JSON 格式，不加任何額外說明或 markdown：
{
  "読音": "假名讀音（多個讀音用 / 分隔）",
  "詞性": "詞性（名詞/動詞/形容詞等，中文標示）",
  "中文": "中文意思（精簡扼要，多義用 ; 分隔）",
  "例句": [
    {
      "ja": "包含該單字的自然日文例句",
      "romaji": "例句的羅馬拼音（Hepburn 式）",
      "zh": "例句的中文翻譯"
    }
  ]
}
例句請提供 1~2 句，難度適中，貼近日常或學習情境。
若輸入不是日文單字，請仍盡量回傳合理資料。
"""


def enrich_word_with_gpt(word: str) -> dict:
    """
    呼叫 GPT 為 word 補充結構化資料。
    回傳 dict，key 為：読音、詞性、中文、例句（list）
    失敗時回傳空 dict。
    """
    word = str(word).strip()
    if not word:
        return {}

    try:
        result = _call_llm_json(
            system_prompt=ENRICH_SYSTEM_PROMPT,
            user_prompt=f"請分析這個單字：{word}"
        )

        # 標準化欄位名稱（相容繁簡/全半角差異）
        normalized = {}
        for k, v in result.items():
            key_clean = k.strip()
            # 読音 → 讀音
            if key_clean in ("読音", "讀音", "読み"):
                normalized["讀音"] = str(v).strip()
            elif key_clean in ("詞性", "品詞", "词性"):
                normalized["詞性"] = str(v).strip()
            elif key_clean in ("中文", "意思", "中文意思", "中文翻譯"):
                normalized["中文"] = str(v).strip()
            elif key_clean in ("例句", "examples", "例文"):
                if isinstance(v, list):
                    normalized["例句"] = v
                else:
                    normalized["例句"] = []

        return normalized

    except Exception as e:
        print(f"[ai_service] enrich_word_with_gpt 失敗（{word}）：{e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════
# 2. AI 情境克漏字生成
# ═══════════════════════════════════════════════════════════════════════

CLOZE_SYSTEM_PROMPT = """\
你是日文語言教師，專門出填空題。
使用者給你一個日文單字和可選的情境標籤。
請生成一道「情境填空題」，嚴格回傳以下 JSON，不加任何額外說明：
{
  "sentence_display": "將目標單字替換成 ＿＿＿ 的日文句子（顯示用）",
  "sentence_full": "完整的日文句子（含正確答案）",
  "answer": "應填入的正確單字",
  "distractors": ["錯誤選項1", "錯誤選項2", "錯誤選項3"],
  "hint_zh": "這個句子的中文大意（讓學習者理解語境）",
  "hint_pos": "目標單字的詞性提示",
  "romaji": "完整句子的羅馬音（Hepburn 式）",
  "difficulty": "easy / medium / hard"
}
句子要自然，貼近真實使用場景（日常對話、新聞、動漫、文學等）。
目標單字必須在句子中出現，且語法正確。
distractors 必須具有干擾力，例如：發音相近、詞性相同或容易混淆的字。
"""


def generate_cloze_question(word: str, context_tag: str = "") -> dict:
    """
    為 word 生成一道情境克漏字題目。
    context_tag 為情境標籤提示（如「動漫台詞」「新聞用語」）。
    回傳 dict，含 sentence_display / answer / hint_zh 等欄位。
    失敗時回傳空 dict。
    """
    word = str(word).strip()
    if not word:
        return {}

    tag_hint = f"（請以「{context_tag}」的語境出題）" if context_tag else ""

    try:
        result = _call_llm_json(
            system_prompt=CLOZE_SYSTEM_PROMPT,
            user_prompt=f"請為以下單字出一道填空題：{word} {tag_hint}"
        )
        return result

    except Exception as e:
        print(f"[ai_service] generate_cloze_question 失敗（{word}）：{e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════
# 3. 驗證克漏字答案
# ═══════════════════════════════════════════════════════════════════════

VALIDATE_SYSTEM_PROMPT = """\
你是嚴謹但有彈性的日文老師。
使用者在句子填空中填入了一個單字，請判斷是否正確或可接受。
正確答案是固定的，但語意接近的同義詞也可給部分評分。
嚴格回傳以下 JSON，不加任何額外說明：
{
  "is_correct": true / false,
  "is_acceptable": true / false,
  "score": 0 ~ 100,
  "explanation_zh": "用中文解釋對或錯的原因（1~2句）",
  "correct_answer": "正確答案"
}
"""


def validate_cloze_answer(sentence_full: str, correct_answer: str, user_answer: str) -> dict:
    """
    呼叫 GPT 判斷克漏字答案是否正確。
    回傳 dict，含 is_correct / score / explanation_zh。
    """
    try:
        user_prompt = (
            f"完整句子：{sentence_full}\n"
            f"正確答案：{correct_answer}\n"
            f"學生的答案：{user_answer}\n"
            f"請評分並解釋。"
        )
        result = _call_llm_json(
            system_prompt=VALIDATE_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )
        return result

    except Exception as e:
        print(f"[ai_service] validate_cloze_answer 失敗：{e}")
        # fallback：本地比對
        is_correct = str(user_answer).strip() == str(correct_answer).strip()
        return {
            "is_correct": is_correct,
            "is_acceptable": is_correct,
            "score": 100 if is_correct else 0,
            "explanation_zh": "LLM 驗證失敗，使用本地比對。",
            "correct_answer": correct_answer
        }


# ═══════════════════════════════════════════════════════════════════════
# 4. 翻譯微調與評分
# ═══════════════════════════════════════════════════════════════════════

TRANSLATION_QUESTION_PROMPT = """\
你是日文語言教師。
使用者給你一個日文單字，請你用這個單字造一個自然、實用的日文句子，讓使用者練習翻譯成中文。
嚴格回傳以下 JSON，不加任何額外說明：
{
  "japanese_sentence": "你造的日文句子",
  "reference_translation": "這個句子的標準中文翻譯"
}
"""

def generate_translation_question(word: str) -> dict:
    word = str(word).strip()
    if not word:
        return {}
    try:
        return _call_llm_json(
            system_prompt=TRANSLATION_QUESTION_PROMPT,
            user_prompt=f"請使用單字「{word}」出題。"
        )
    except Exception as e:
        print(f"[ai_service] generate_translation_question 失敗：{e}")
        return {}

EVALUATE_TRANSLATION_PROMPT = """\
你是嚴格但充滿鼓勵的語言老師。
使用者翻譯了一句日文為中文，請給予 1-10 分的評分，並提供詳細的老師講評。
嚴格回傳以下 JSON，不加任何額外說明：
{
  "score": 8,
  "feedback": "點出翻譯哪裡不夠道地，或者漏掉了原句的細微語氣（約 2-3 句話）"
}
"""

def evaluate_translation(japanese_sentence: str, reference_translation: str, user_translation: str) -> dict:
    try:
        user_prompt = (
            f"日文原句：{japanese_sentence}\n"
            f"標準翻譯參考：{reference_translation}\n"
            f"使用者的翻譯：{user_translation}\n"
            f"請給分並講評。"
        )
        return _call_llm_json(
            system_prompt=EVALUATE_TRANSLATION_PROMPT,
            user_prompt=user_prompt
        )
    except Exception as e:
        print(f"[ai_service] evaluate_translation 失敗：{e}")
        return {"score": 0, "feedback": "評分系統暫時無法使用。"}


# ═══════════════════════════════════════════════════════════════════════
# 5. 換句話說 / 語意重構 (Paraphrasing)
# ═══════════════════════════════════════════════════════════════════════

PARAPHRASE_QUESTION_PROMPT = """\
你是日語學習教練，負責訓練大腦的深度思考。
使用者會給你一個「進階單字」，請你設計一個情境：
給定一個「意思相近，但用非常簡單的日文表達的句子」，要求學習者使用該「進階單字」來重構這句話。
嚴格回傳以下 JSON，不加任何額外說明：
{
  "simple_sentence": "用簡單字彙表達的日文句子",
  "simple_meaning": "這句話的中文意思",
  "target_word": "要求學習者必須使用的進階單字",
  "reference_answer": "使用 target_word 改寫後的標準日文句子"
}
"""

def generate_paraphrasing_question(word: str) -> dict:
    word = str(word).strip()
    if not word:
        return {}
    try:
        return _call_llm_json(
            system_prompt=PARAPHRASE_QUESTION_PROMPT,
            user_prompt=f"請針對進階單字「{word}」設計語意重構題。"
        )
    except Exception as e:
        print(f"[ai_service] generate_paraphrasing_question 失敗：{e}")
        return {}

EVALUATE_PARAPHRASE_PROMPT = """\
你是專業的日語改寫（Paraphrasing）指導老師。
使用者被要求用指定的單字，改寫原本簡單的句子。
請檢查使用者的改寫是否語法正確、語意相符，且確實使用了指定單字。
嚴格回傳以下 JSON，不加任何額外說明：
{
  "is_correct": true / false,
  "feedback": "解釋改寫得好不好，指出文法錯誤，或給出更道地的寫法（2-3 句話）"
}
"""

def evaluate_paraphrasing(simple_sentence: str, target_word: str, user_sentence: str) -> dict:
    try:
        user_prompt = (
            f"原意簡單句：{simple_sentence}\n"
            f"規定必須使用的單字：{target_word}\n"
            f"使用者重構的句子：{user_sentence}\n"
            f"請評估是否成功重構並給予回饋。"
        )
        return _call_llm_json(
            system_prompt=EVALUATE_PARAPHRASE_PROMPT,
            user_prompt=user_prompt
        )
    except Exception as e:
        print(f"[ai_service] evaluate_paraphrasing 失敗：{e}")
        return {"is_correct": False, "feedback": "評估系統暫時無法使用。"}
