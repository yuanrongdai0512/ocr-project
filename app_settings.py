import json
import os
from pathlib import Path


SETTINGS_PATH = "app_settings.json"
USER_CONFIG_DIR = Path.home() / ".ocr_test_app"
OPENAI_KEY_PATH = USER_CONFIG_DIR / "openai_key.txt"

GOOGLE_KEY_PATH = USER_CONFIG_DIR / "google_key.txt"

DEFAULT_SETTINGS = {
    "translation_mode": "local",
    "gpt_ocr_enabled": False,
    "gpt_translation_model": "gpt-5.2",
    "gpt_ocr_model": "gpt-4.1",
    "ai_provider": "openai"
}


def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return dict(DEFAULT_SETTINGS)

    if not isinstance(data, dict):
        return dict(DEFAULT_SETTINGS)

    settings = dict(DEFAULT_SETTINGS)
    settings.update(data)

    if settings.get("translation_mode") not in {"local", "gpt", "gemini"}:
        settings["translation_mode"] = DEFAULT_SETTINGS["translation_mode"]

    if settings.get("ai_provider") not in {"openai", "google"}:
        settings["ai_provider"] = DEFAULT_SETTINGS["ai_provider"]

    settings["gpt_ocr_enabled"] = bool(settings.get("gpt_ocr_enabled", False))

    return settings


def save_settings(settings):
    data = dict(DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        data.update(settings)

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def load_openai_api_key():
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    try:
        return OPENAI_KEY_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_openai_api_key(api_key):
    api_key = str(api_key).strip()
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if api_key:
        OPENAI_KEY_PATH.write_text(api_key, encoding="utf-8")
    elif OPENAI_KEY_PATH.exists():
        OPENAI_KEY_PATH.unlink()


def load_google_api_key():
    env_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if env_key:
        return env_key

    try:
        return GOOGLE_KEY_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_google_api_key(api_key):
    api_key = str(api_key).strip()
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if api_key:
        GOOGLE_KEY_PATH.write_text(api_key, encoding="utf-8")
    elif GOOGLE_KEY_PATH.exists():
        GOOGLE_KEY_PATH.unlink()
