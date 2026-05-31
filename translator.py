from deep_translator import GoogleTranslator
from openai import OpenAI

from app_settings import load_openai_api_key, load_google_api_key, load_settings


def get_openai_client():
    api_key = load_openai_api_key()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def translate_local(text):
    text = text.strip()

    if not text:
        return "沒有可翻譯的文字"

    try:
        return GoogleTranslator(source="auto", target="zh-TW").translate(text)
    except Exception as e:
        return f"本地翻譯失敗：{e}"


def translate_gpt(text):
    text = text.strip()

    if not text:
        return "沒有可翻譯的文字"

    client = get_openai_client()
    if client is None:
        return "GPT翻譯失敗：尚未設定 OPENAI_API_KEY"

    settings = load_settings()
    model = settings.get("gpt_translation_model", "gpt-5.2")

    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "請將使用者提供的日文、英文或其他語言翻譯成自然流暢的繁體中文。只輸出翻譯結果。"
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )
        return response.output_text.strip()
    except Exception as e:
        return f"GPT翻譯失敗：{e}"


def translate_gemini(text):
    text = text.strip()

    if not text:
        return "沒有可翻譯的文字"

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "Gemini翻譯失敗：請安裝 google-genai 套件"

    api_key = load_google_api_key()
    if not api_key:
        return "Gemini翻譯失敗：尚未設定 Google API Key"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"請將以下文字翻譯成自然流暢的繁體中文。只輸出翻譯結果，不要加任何說明：\n\n{text}",
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000
            )
        )
        return (response.text or "").strip()
    except Exception as e:
        return f"Gemini翻譯失敗：{e}"


def translate(text, mode):
    if mode == "local":
        return translate_local(text)
    if mode == "gpt":
        return translate_gpt(text)
    if mode == "gemini":
        return translate_gemini(text)
    return "未知翻譯模式"


def translate_default(text):
    settings = load_settings()
    return translate(text, settings.get("translation_mode", "local"))
