import base64
import json

import easyocr
from openai import OpenAI

from app_settings import load_openai_api_key, load_google_api_key, load_settings

try:
    from manga_ocr import MangaOcr
except ImportError:
    MangaOcr = None


class OCREngine:
    def __init__(self):
        self.easy_reader = None
        self.manga_reader = None

    def get_openai_client(self):
        api_key = load_openai_api_key()
        if not api_key:
            return None
        return OpenAI(api_key=api_key)

    def read_easyocr(self, image_path):
        if self.easy_reader is None:
            self.easy_reader = easyocr.Reader(["ja", "en"])

        result = self.easy_reader.readtext(image_path)

        texts = []
        for item in result:
            texts.append(item[1])

        return "".join(texts)

    def read_mangaocr(self, image_path):
        if MangaOcr is None:
            return "Manga-OCR 尚未安裝，請先執行：python -m pip install manga-ocr"

        if self.manga_reader is None:
            self.manga_reader = MangaOcr()

        return self.manga_reader(image_path)

    def parse_gpt_ocr_response(self, raw_text):
        raw_text = str(raw_text).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`").strip()
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()

        try:
            return json.loads(raw_text)
        except Exception:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw_text[start:end + 1])
            raise

    def read_gemini_ocr(self, image_path):
        """使用 Gemini Vision 進行 OCR 辨識與翻譯。需要 Google API Key。"""
        api_key = load_google_api_key()
        if not api_key:
            return {
                "source_text": "",
                "translated_text": "Gemini OCR 失敗：尚未設定 Google API Key"
            }

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            settings = load_settings()
            model_name = settings.get("gemini_ocr_model", "gemini-2.5-flash")
            model = genai.GenerativeModel(model_name)

            with open(image_path, "rb") as f:
                image_bytes = f.read()

            import PIL.Image
            import io
            pil_image = PIL.Image.open(io.BytesIO(image_bytes))

            prompt = (
                "請辨識圖片中的主要原文，並翻譯成繁體中文。"
                "如果有多段文字，保留合理換行。"
                "請只回傳 JSON，格式為："
                "{\"source_text\":\"...\",\"translated_text\":\"...\"}"
            )

            response = model.generate_content([prompt, pil_image])
            raw_text = response.text.strip()
            data = self.parse_gpt_ocr_response(raw_text)

            if not isinstance(data, dict):
                raise ValueError("Gemini OCR 回傳格式不是 JSON object")

            return {
                "source_text": str(data.get("source_text", "")).strip(),
                "translated_text": str(data.get("translated_text", "")).strip()
            }

        except Exception as e:
            print(f"[OCR] Gemini OCR 失敗：{e}")
            return {
                "source_text": "",
                "translated_text": f"Gemini OCR 失敗：{e}"
            }

    def read_gpt_ocr(self, image_path):
        client = self.get_openai_client()
        if client is None:
            return {
                "source_text": "",
                "translated_text": "GPT OCR 失敗：尚未設定 OPENAI_API_KEY"
            }

        settings = load_settings()
        model = settings.get("gpt_ocr_model", "gpt-4.1")

        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")

        image_url = f"data:image/png;base64,{image_base64}"

        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "請辨識圖片中的主要原文，並翻譯成繁體中文。"
                                    "如果有多段文字，保留合理換行。"
                                    "請只回傳 JSON，格式為："
                                    "{\"source_text\":\"...\",\"translated_text\":\"...\"}"
                                )
                            },
                            {
                                "type": "input_image",
                                "image_url": image_url
                            }
                        ]
                    }
                ]
            )

            raw_text = response.output_text.strip()
            data = self.parse_gpt_ocr_response(raw_text)
            if not isinstance(data, dict):
                raise ValueError("GPT OCR 回傳格式不是 JSON object")

            return {
                "source_text": str(data.get("source_text", "")).strip(),
                "translated_text": str(data.get("translated_text", "")).strip()
            }
        except Exception as e:
            return {
                "source_text": "",
                "translated_text": f"GPT OCR 失敗：{e}"
            }

    def read(self, image_path, mode):
        print("目前 OCR 模式：", mode)

        if mode == "easyocr":
            print("使用 EasyOCR")
            return self.read_easyocr(image_path)

        elif mode == "mangaocr":
            print("使用 Manga-OCR")
            return self.read_mangaocr(image_path)

        elif mode == "gpt":
            print("使用 GPT OCR")
            result = self.read_gpt_ocr(image_path)
            if result.get("translated_text"):
                return f"{result.get('source_text', '')}\n\n{result.get('translated_text', '')}".strip()
            return result.get("source_text", "")

        elif mode == "gemini":
            print("使用 Gemini OCR")
            result = self.read_gemini_ocr(image_path)
            if result.get("translated_text"):
                return f"{result.get('source_text', '')}\n\n{result.get('translated_text', '')}".strip()
            return result.get("source_text", "")

        else:
            return "未知 OCR 模式"
