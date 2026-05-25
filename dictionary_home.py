import random
import re
import hashlib
import os
import shutil
import threading
import tkinter as tk
import pyperclip
from datetime import datetime
from tkinter import filedialog
from tkinter import messagebox, ttk
from PIL import Image, ImageSequence, ImageTk
from app_settings import load_settings
from translator import translate
from dictionary_manager import (
    add_word_fast,
    enrich_word_data_async,
    enrich_word_with_gpt_async,
    load_dictionary,
    save_dictionary,
)


class DictionaryHome:
    def __init__(self, parent):
        self.parent = parent
        self.parent_window = getattr(parent, "root", parent)
        self.selected_language = None

        self.dictionary_data = []
        self.filtered_dictionary_data = []
        self.collection_flat_items = []
        self.current_entry = None
        self.tree_item_to_entry = {}
        self.collection_image_preview = None
        self.collection_image_frames = []
        self.collection_image_animation_job = None
        self.collection_image_frame_index = 0
        self.collection_image_cache = {}
        self.collection_current_image_path = ""
        self.collection_image_path_var = tk.StringVar()
        self.collection_autosave_job = None
        self.collection_detail_loading = False
        self.collection_has_unsaved_changes = False
        self.collection_split_apply_job = None
        self.collection_enrich_refresh_job = None
        self.collection_pages = []
        self.collection_resize_refresh_job = None

        self.collection_search_var = tk.StringVar()
        self.collection_tag_var = tk.StringVar(value="全部")
        self.collection_page = 1
        self.collection_page_size = 12
        self.exam_tag_var = tk.StringVar(value="未分類")
        self.exam_mode_var = tk.StringVar(value="reading_input")
        self.exam_candidates = []
        self.exam_current_question = None
        self.exam_recent_question_keys = []
        self.exam_answer_shown = False
        self.exam_score = 0
        self.exam_total = 0

        # 答題歷史記錄（錯題本與學習圖表）
        self.exam_history = []   # [{"word", "correct", "mode", "pos", "tag", "timestamp"}]
        self.exam_wrong_log = [] # 錯題列表

        # AI 克漏字狀態
        self.ai_cloze_current = None   # 目前的克漏字題目 dict
        self.ai_cloze_loading = False  # 是否正在呼叫 GPT

        self.window = tk.Toplevel(self.parent_window)
        self.window.title("字典主頁")
        self.window.geometry("1380x960+100+60")
        self.window.minsize(1200, 780)
        self.window.configure(bg="#F5EAD9")
        self.window.protocol("WM_DELETE_WINDOW", self.close_dictionary_window)

        self.main_frame = tk.Frame(self.window, bg="#F5EAD9")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.build_home_page()

    # =========================================================
    # 共用
    # =========================================================
    def clear_page(self):
        if hasattr(self, "stop_collection_image_animation"):
            self.stop_collection_image_animation()
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def create_soft_button(self, parent, text, command, width=12, big=False):
        font_size = 11 if not big else 15
        pady = 10 if not big else 16
        padx = 16 if not big else 24

        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Microsoft JhengHei", font_size, "bold"),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            width=width,
            cursor="hand2"
        )

    def create_footer_button(self, parent, text, command, primary=False):
        return self.create_soft_button(
            parent,
            text,
            command,
            width=14 if primary else 12,
            big=True
        )

    def open_toolbar_settings(self):
        if hasattr(self.parent, "open_settings"):
            self.parent.open_settings()

    def is_katakana_only(self, text):
        text = str(text).strip()
        if not text:
            return False

        has_katakana = False
        for char in text:
            if char in " 　・ー":
                continue

            code = ord(char)
            if 0x30A0 <= code <= 0x30FF:
                has_katakana = True
                continue

            return False

        return has_katakana

    def to_hiragana(self, text):
        result = []
        for char in str(text):
            code = ord(char)
            if 0x30A1 <= code <= 0x30F6:
                result.append(chr(code - 0x60))
            else:
                result.append(char)
        return "".join(result)

    def kana_to_romaji(self, text):
        text = self.to_hiragana(text).strip()
        if not text:
            return ""

        digraph_map = {
            "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
            "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
            "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
            "じゃ": "jya", "じゅ": "jyu", "じょ": "jyo",
            "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
            "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
            "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
            "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
            "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
            "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
            "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
            "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo",
            "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo",
            "てぃ": "ti", "でぃ": "di", "とぅ": "tu", "どぅ": "du",
            "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
            "しぇ": "she", "じぇ": "je", "ちぇ": "che"
        }
        base_map = {
            "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
            "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
            "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
            "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
            "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
            "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
            "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
            "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
            "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
            "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
            "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
            "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
            "や": "ya", "ゆ": "yu", "よ": "yo",
            "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
            "わ": "wa", "を": "o", "ん": "n",
            "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
            "ゔ": "vu"
        }

        parts = []
        i = 0
        pending_sokuon = False

        while i < len(text):
            char = text[i]

            if char in " 　":
                i += 1
                continue

            if char == "っ":
                pending_sokuon = True
                i += 1
                continue

            if char == "ー":
                if parts:
                    last = parts[-1]
                    if last[-1] in "aeiou":
                        parts[-1] = last + last[-1]
                i += 1
                continue

            kana = text[i:i + 2] if i + 1 < len(text) else ""
            if kana in digraph_map:
                romaji = digraph_map[kana]
                i += 2
            else:
                romaji = base_map.get(char, char)
                i += 1

            if pending_sokuon and romaji:
                romaji = romaji[0] + romaji
                pending_sokuon = False

            parts.append(romaji)

        compact = "".join(parts)
        compact = compact.replace("ouei", "ou ei")

        compact = re.sub(r"([aeiou])([kgsztdnhbpmrywjfvc][a-z]+)$", r"\1 \2", compact)
        compact = compact.replace("nn", "n n")
        compact = re.sub(r"([aeiou])\s+n([aeiou])", r"\1n \2", compact)
        compact = re.sub(r"([aeiou])\s+n([kgsztdnhbpmrywjfvc])", r"\1n \2", compact)
        compact = re.sub(r"\s+", " ", compact).strip()
        return compact

    def normalize_exam_reading(self, text):
        text = str(text).strip().lower()
        if not text:
            return ""

        text = self.to_hiragana(text)
        text = re.sub(r"[^a-z0-9ぁ-ん]", "", text)
        return text

    def split_exam_readings(self, text):
        raw = str(text).strip()
        if not raw:
            return []

        parts = re.split(r"\s*[/／;,；，]\s*", raw)
        return [part.strip() for part in parts if part.strip()]

    def build_exam_reading_answers(self, reading_text):
        answers = set()

        for reading in self.split_exam_readings(reading_text):
            normalized_hiragana = self.normalize_exam_reading(reading)
            if normalized_hiragana:
                answers.add(normalized_hiragana)

            romaji = self.kana_to_romaji(reading)
            answers.update(self.build_exam_romaji_variants(romaji))

        return answers

    def build_exam_romaji_variants(self, romaji):
        normalized = self.normalize_exam_reading(romaji)
        if not normalized:
            return set()

        variants = {normalized}
        replacement_groups = [
            ("fu", "hu"),
            ("shi", "si"),
            ("chi", "ti"),
            ("tsu", "tu"),
            ("ji", "zi"),
        ]

        for left, right in replacement_groups:
            current_variants = list(variants)
            for value in current_variants:
                if left in value:
                    variants.add(value.replace(left, right))
                if right in value:
                    variants.add(value.replace(right, left))

        return variants

    def sanitize_english_text(self, text, limit=4):
        raw = str(text).strip()
        if not raw:
            return ""

        parts = [part.strip() for part in raw.split(";") if part.strip()]
        english_parts = []

        for part in parts:
            if re.fullmatch(r"[A-Za-z0-9 ,.'/(){}\[\]\-:+?!&%]+", part):
                english_parts.append(part)

        if not english_parts:
            fallback = raw[:120].strip()
            return fallback + "..." if len(raw) > 120 else fallback

        return "; ".join(english_parts[:limit])

    def format_reading_with_romaji(self, reading):
        readings = self.split_exam_readings(reading)
        if not readings:
            return "未填寫"

        formatted = []
        for item in readings:
            hira = self.to_hiragana(item)
            romaji = self.kana_to_romaji(item)
            if romaji:
                formatted.append(f"{hira} ({romaji})")
            else:
                formatted.append(hira)

        return " / ".join(formatted)

    def set_exam_choice(self, value):
        self.exam_choice_var.set(value)

        for btn in self.exam_choice_buttons:
            option = getattr(btn, "option_value", "")
            is_selected = option == value
            marker = "◎" if is_selected else "○"
            btn.config(
                text=f"{marker}  {option}",
                fg="#8B5E3C" if is_selected else "#6A4A35"
            )

    def get_language_name(self, code):
        mapping = {
            "ja": "日文字典",
            "en": "英文字典",
            "zh": "中文字典",
            "new": "新增字典"
        }
        return mapping.get(code, "字典")

    def build_index_page_callback(self):
        if not self.confirm_collection_unsaved_change():
            return

        language_name = self.get_language_name(self.selected_language)
        self.build_index_page(language_name)

    def hide_toolbar(self):
        try:
            self.parent_window.withdraw()
        except Exception:
            messagebox.showwarning("提示", "目前無法隱藏工具列")

    def close_dictionary_window(self):
        if self.collection_has_unsaved_changes and self.current_entry is not None:
            answer = messagebox.askyesnocancel(
                "尚未保存",
                "目前單字內容尚未保存，要先保存再關閉嗎？",
                parent=self.window
            )
            if answer is None:
                return
            if answer:
                if not self.save_collection_entry(show_message=False, refresh_list=False):
                    return

        self.cancel_collection_enrich_refresh()
        self.window.destroy()

    def get_external_translation_context(self):
        if hasattr(self.parent, "get_current_translation_context"):
            try:
                context = self.parent.get_current_translation_context()
                if isinstance(context, dict):
                    source_text = str(context.get("source_text", "")).strip()
                    translated_text = str(context.get("translated_text", "")).strip()
                    if source_text or translated_text:
                        return {
                            "source_text": source_text,
                            "translated_text": translated_text
                        }
            except Exception:
                pass

        clipboard_text = ""
        try:
            clipboard_text = pyperclip.paste().strip()
        except Exception:
            clipboard_text = ""

        return {
            "source_text": clipboard_text,
            "translated_text": ""
        }

    def refresh_external_context(self):
        if hasattr(self, "translation_source_text") and hasattr(self, "translation_result_text"):
            self.populate_translation_area()

    def populate_translation_area(self):
        if not hasattr(self, "translation_source_text") or not hasattr(self, "translation_result_text"):
            return

        context = self.get_external_translation_context()
        source_text = str(context.get("source_text", "")).strip()
        translated_text = str(context.get("translated_text", "")).strip()

        self.translation_source_text.delete("1.0", tk.END)
        self.translation_result_text.delete("1.0", tk.END)

        self.translation_source_text.insert("1.0", source_text or "目前沒有可顯示的原文")
        if translated_text:
            self.translation_result_text.insert("1.0", translated_text)
        elif source_text:
            self.translation_result_text.insert("1.0", "翻譯中，請稍候...")
            self.translate_area_text_async(source_text)
        else:
            self.translation_result_text.insert("1.0", "目前沒有可顯示的翻譯")

    def translate_area_text_async(self, source_text):
        source_text = str(source_text).strip()
        if not source_text:
            return

        self.translation_area_job_source = source_text
        thread = threading.Thread(
            target=self.translate_area_text_worker,
            args=(source_text,),
            daemon=True
        )
        thread.start()

    def translate_area_text_worker(self, source_text):
        try:
            mode = load_settings().get("translation_mode", "local")
            result = translate(source_text, mode)
        except Exception as e:
            result = f"翻譯失敗：{e}"

        self.window.after(0, lambda: self.apply_translation_area_result(source_text, result))

    def apply_translation_area_result(self, source_text, result):
        if not hasattr(self, "translation_result_text"):
            return
        if getattr(self, "translation_area_job_source", "") != source_text:
            return

        self.translation_result_text.delete("1.0", tk.END)
        self.translation_result_text.insert("1.0", result or "翻譯結果為空")

    def _retranslate_from_source_text(self):
        """讀取翻譯區原文欄位的當前內容，重新觸發非同步翻譯。"""
        if not hasattr(self, "translation_source_text"):
            return
        source = self.translation_source_text.get("1.0", tk.END).strip()
        if not source:
            messagebox.showinfo("翻譯", "請先在原文區輸入文字", parent=self.window)
            return
        if hasattr(self, "translation_result_text"):
            self.translation_result_text.delete("1.0", tk.END)
            self.translation_result_text.insert("1.0", "翻譯中，請稍候…")
        self.translate_area_text_async(source)

    def get_selected_text_from_widget(self, widget):
        try:
            return widget.get("sel.first", "sel.last").strip()
        except Exception:
            return ""

    def add_selected_translation_text_to_dict(self, widget):
        selected_text = self.get_selected_text_from_widget(widget)
        if not selected_text:
            messagebox.showinfo("字典", "請先反白要加入字典的文字", parent=self.window)
            return

        try:
            result = add_word_fast(selected_text)
            if result.startswith("已加入字典"):
                messagebox.showinfo(
                    "字典",
                    f"{result}\n背景正在補充讀音 / 中文 / 英文 / 詞性",
                    parent=self.window
                )
                self.window.after(500, lambda word=selected_text: enrich_word_data_async(word))
            else:
                messagebox.showinfo("字典", result, parent=self.window)
        except Exception as e:
            messagebox.showerror("錯誤", f"加入字典失敗：{e}", parent=self.window)

    def copy_selected_text_from_widget(self, widget):
        selected_text = self.get_selected_text_from_widget(widget)
        if not selected_text:
            return

        self.window.clipboard_clear()
        self.window.clipboard_append(selected_text)
        self.window.update()

    def show_translation_menu(self, event, widget):
        self.translation_context_widget = widget
        self.translation_menu.tk_popup(event.x_root, event.y_root)
        self.translation_menu.grab_release()

    def handle_translation_ctrl_c(self, event, widget):
        self.copy_selected_text_from_widget(widget)
        return "break"

    # =========================================================
    # 首頁
    # =========================================================
    def get_home_bookshelf_languages(self):
        return [
            ("日文字典", "ja", "OCR 日文、讀音、詞性、例句", "#9B6A46"),
            ("英文字典", "en", "單字查詢、片語與基本分類", "#4F6F7D"),
            ("新增字典", "new", "預留新的語言字典或分類", "#6B7A4D")
        ]

    def draw_bookshelf_home(self, canvas):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 900)
        height = max(canvas.winfo_height(), 460)

        canvas.create_rectangle(0, 0, width, height, fill="#5A3A28", outline="")

        for y in range(26, height, 32):
            canvas.create_line(0, y, width, y, fill="#694732", width=1)

        for x in range(48, width, 110):
            canvas.create_line(x, 0, x, height, fill="#4D301F", width=1)

        canvas.create_rectangle(38, 22, width - 38, height - 28, outline="#8A6547", width=5)
        canvas.create_rectangle(56, 42, width - 56, height - 48, outline="#3F281C", width=2)

        title_y = 42
        canvas.create_text(
            width / 2,
            title_y,
            text="選一本字典",
            font=("Microsoft JhengHei", 24, "bold"),
            fill="#FFF2DA"
        )
        canvas.create_text(
            width / 2,
            title_y + 38,
            text="點選書本進入索引",
            font=("Microsoft JhengHei", 12),
            fill="#E7D6BE"
        )

        shelf_y = int(height * 0.73)
        canvas.create_rectangle(78, shelf_y - 10, width - 78, shelf_y, fill="#3F281C", outline="")
        canvas.create_rectangle(60, shelf_y, width - 60, shelf_y + 24, fill="#B27B50", outline="")
        canvas.create_rectangle(78, shelf_y + 24, width - 78, shelf_y + 40, fill="#7A4B2E", outline="")
        canvas.create_line(60, shelf_y, width - 60, shelf_y, fill="#D2A06D", width=2)

        languages = self.get_home_bookshelf_languages()
        total_book_width = min(width - 180, 720)
        gap = 18
        book_width = max(108, min(142, (total_book_width - gap * (len(languages) - 1)) / len(languages)))
        start_x = (width - (book_width * len(languages) + gap * (len(languages) - 1))) / 2
        bottom_y = shelf_y

        for index, (title_text, code, _desc, color) in enumerate(languages):
            book_height = 245 + (index % 2) * 26
            x1 = start_x + index * (book_width + gap)
            x2 = x1 + book_width
            y2 = bottom_y
            y1 = y2 - book_height
            tag = f"home_book_{code}"

            canvas.create_rectangle(
                x1 + 8,
                y1 + 10,
                x2 + 8,
                y2 + 8,
                fill="#D4C4AE",
                outline="",
                tags=(tag, "home_book")
            )
            canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=color,
                outline="#5F432F",
                width=2,
                tags=(tag, "home_book")
            )
            canvas.create_rectangle(
                x1 + 12,
                y1 + 14,
                x2 - 12,
                y1 + 46,
                fill="#FBF6EE",
                outline="",
                tags=(tag, "home_book")
            )
            canvas.create_line(x1 + 18, y1 + 58, x1 + 18, y2 - 18, fill="#F4EADC", width=2, tags=(tag, "home_book"))
            canvas.create_line(x2 - 18, y1 + 58, x2 - 18, y2 - 18, fill="#F4EADC", width=2, tags=(tag, "home_book"))

            vertical_title = "\n".join(title_text)
            canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2 + 8,
                text=vertical_title,
                font=("Microsoft JhengHei", 18, "bold"),
                fill="#FFF8EE",
                justify="center",
                tags=(tag, "home_book")
            )
            canvas.create_text(
                (x1 + x2) / 2,
                y1 + 30,
                text="字典",
                font=("Microsoft JhengHei", 10, "bold"),
                fill="#4A2F21",
                tags=(tag, "home_book")
            )
            canvas.tag_bind(tag, "<Button-1>", lambda event, lang=code, name=title_text: self.open_index_page(lang, name))
            canvas.tag_bind(tag, "<Enter>", lambda event: canvas.config(cursor="hand2"))
            canvas.tag_bind(tag, "<Leave>", lambda event: canvas.config(cursor=""))

    def build_home_page(self):
        self.clear_page()

        outer = tk.Frame(self.main_frame, bg="#5A3A28")
        outer.pack(fill=tk.BOTH, expand=True, padx=28, pady=28)

        bookshelf = tk.Canvas(
            outer,
            bg="#5A3A28",
            highlightthickness=0,
            bd=0
        )
        bookshelf.pack(fill=tk.BOTH, expand=True)
        bookshelf.bind("<Configure>", lambda event: self.draw_bookshelf_home(bookshelf))

        bottom = tk.Frame(outer, bg="#5A3A28")
        bottom.pack(fill=tk.X, pady=(14, 0))

        close_btn = self.create_footer_button(bottom, "關閉", self.window.destroy)
        close_btn.pack(side=tk.RIGHT)

    # =========================================================
    # 索引頁
    # =========================================================
    def open_index_page(self, lang_code, lang_name):
        self.selected_language = lang_code
        self.build_index_page(lang_name)

    def build_index_page(self, lang_name):
        self.clear_page()

        outer = tk.Frame(self.main_frame, bg="#F5EAD9")
        outer.pack(fill=tk.BOTH, expand=True, padx=28, pady=28)

        header = tk.Frame(outer, bg="#E7D6BE", bd=0)
        header.pack(fill=tk.X, pady=(0, 20))

        title = tk.Label(
            header,
            text=f"{lang_name}・索引",
            font=("Microsoft JhengHei", 22, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=18
        )
        title.pack()

        center = tk.Frame(outer, bg="#F5EAD9")
        center.pack(fill=tk.BOTH, expand=True)

        options = [
            ("1. 翻譯區", self.open_translation_area),
            ("2. 單字收藏", self.open_collection_area),
            ("3. 考試區", self.open_exam_area),
        ]

        for title_text, command in options:
            card = tk.Frame(
                center,
                bg="#EADCC8",
                bd=0,
                highlightthickness=0,
                padx=24,
                pady=24
            )
            card.pack(fill=tk.X, pady=10)

            title_label = tk.Label(
                card,
                text=title_text,
                font=("Microsoft JhengHei", 17, "bold"),
                bg="#EADCC8",
                fg="#4A2F21",
                anchor="w"
            )
            title_label.pack(anchor="w")

            enter_btn = self.create_soft_button(card, "進入", command, width=10)
            enter_btn.pack(anchor="w", pady=(14, 0))

        bottom = tk.Frame(outer, bg="#F5EAD9")
        bottom.pack(fill=tk.X, pady=(16, 0))

        back_btn = self.create_footer_button(bottom, "返回語言選擇", self.build_home_page, primary=True)
        back_btn.pack(side=tk.LEFT)

        close_btn = self.create_footer_button(bottom, "關閉", self.window.destroy)
        close_btn.pack(side=tk.RIGHT)

    # =========================================================
    # 1. 翻譯區
    # =========================================================
    def open_translation_area(self):
        self.clear_page()

        outer = tk.Frame(self.main_frame, bg="#F5EAD9")
        outer.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

        header = tk.Frame(outer, bg="#E7D6BE")
        header.pack(fill=tk.X, pady=(0, 18))

        title = tk.Label(
            header,
            text="翻譯區",
            font=("Microsoft JhengHei", 22, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=18
        )
        title.pack()

        content = tk.Frame(outer, bg="#F5EAD9")
        content.pack(fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=1, uniform="translation")
        content.grid_columnconfigure(1, weight=1, uniform="translation")
        content.grid_rowconfigure(0, weight=1)

        left_panel = tk.Frame(content, bg="#EADCC8", bd=0)
        right_panel = tk.Frame(content, bg="#EADCC8", bd=0)

        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        left_title = tk.Label(
            left_panel,
            text="原文區",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#EADCC8",
            fg="#4A2F21",
            padx=14,
            pady=12,
            anchor="w"
        )
        left_title.pack(fill=tk.X)

        self.translation_source_text = tk.Text(
            left_panel,
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#3A2A1F",
            relief="flat",
            bd=0,
            wrap=tk.WORD
        )
        self.translation_source_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        right_title = tk.Label(
            right_panel,
            text="翻譯區",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#EADCC8",
            fg="#4A2F21",
            padx=14,
            pady=12,
            anchor="w"
        )
        right_title.pack(fill=tk.X)

        self.translation_result_text = tk.Text(
            right_panel,
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#3A2A1F",
            relief="flat",
            bd=0,
            wrap=tk.WORD
        )
        self.translation_result_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.translation_context_widget = self.translation_source_text
        self.translation_menu = tk.Menu(self.window, tearoff=0)
        self.translation_menu.add_command(
            label="複製選取",
            command=lambda: self.copy_selected_text_from_widget(self.translation_context_widget)
        )
        self.translation_menu.add_command(
            label="加入字典",
            command=lambda: self.add_selected_translation_text_to_dict(self.translation_context_widget)
        )

        self.translation_source_text.bind(
            "<Button-3>",
            lambda event: self.show_translation_menu(event, self.translation_source_text)
        )
        self.translation_result_text.bind(
            "<Button-3>",
            lambda event: self.show_translation_menu(event, self.translation_result_text)
        )
        self.translation_source_text.bind(
            "<Control-c>",
            lambda event: self.handle_translation_ctrl_c(event, self.translation_source_text)
        )
        self.translation_result_text.bind(
            "<Control-c>",
            lambda event: self.handle_translation_ctrl_c(event, self.translation_result_text)
        )

        try:
            self.populate_translation_area()
        except Exception as e:
            self.translation_source_text.delete("1.0", tk.END)
            self.translation_result_text.delete("1.0", tk.END)
            self.translation_source_text.insert("1.0", "目前沒有可顯示的原文")
            self.translation_result_text.insert("1.0", f"翻譯區載入失敗：{e}")

        bottom = tk.Frame(outer, bg="#F5EAD9")
        bottom.pack(fill=tk.X, pady=(14, 0))

        left_actions = tk.Frame(bottom, bg="#F5EAD9")
        left_actions.pack(side=tk.LEFT)

        back_btn = self.create_footer_button(left_actions, "返回索引", self.build_index_page_callback, primary=True)
        back_btn.pack(side=tk.LEFT)

        hide_toolbar_btn = self.create_footer_button(left_actions, "隱藏工具列", self.hide_toolbar)
        hide_toolbar_btn.pack(side=tk.LEFT, padx=(12, 0))

        retranslate_btn = self.create_footer_button(
            left_actions,
            "🔄 重新翻譯",
            self._retranslate_from_source_text
        )
        retranslate_btn.pack(side=tk.LEFT, padx=(12, 0))

        close_btn = self.create_footer_button(bottom, "關閉", self.window.destroy)
        close_btn.pack(side=tk.RIGHT)

    # =========================================================
    # 2. 單字收藏
    # =========================================================
    def open_collection_area(self):
        self.clear_page()
        self.load_dictionary_data()

        outer = tk.Frame(self.main_frame, bg="#F5EAD9")
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        settings_btn = self.create_soft_button(outer, "設定", self.open_toolbar_settings, width=6)
        settings_btn.place(x=0, y=0)

        header = tk.Frame(outer, bg="#E7D6BE")
        header.pack(fill=tk.X, pady=(0, 18))

        title = tk.Label(
            header,
            text="單字收藏",
            font=("Microsoft JhengHei", 22, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=18
        )
        title.pack()

        body = tk.Frame(outer, bg="#F5EAD9")
        body.pack(fill=tk.BOTH, expand=True, pady=(0, 16))

        left_panel = tk.Frame(body, bg="#EADCC8", bd=0, width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        left_title = tk.Label(
            left_panel,
            text="單字索引",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#EADCC8",
            fg="#4A2F21",
            pady=12
        )
        left_title.pack(fill=tk.X)

        search_frame = tk.Frame(left_panel, bg="#EADCC8")
        search_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

        search_entry = tk.Entry(
            search_frame,
            textvariable=self.collection_search_var,
            font=("Microsoft JhengHei", 11),
            bg="#FBF6EE",
            fg="#3A2A1F",
            relief="flat",
            bd=0
        )
        search_entry.pack(fill=tk.X, ipady=6)
        search_entry.bind("<KeyRelease>", self.on_collection_search_changed)

        tag_frame = tk.Frame(left_panel, bg="#EADCC8")
        tag_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.collection_tag_menu = tk.OptionMenu(tag_frame, self.collection_tag_var, "全部")
        self.collection_tag_menu.config(
            font=("Microsoft JhengHei", 10),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            highlightthickness=0
        )
        self.collection_tag_menu["menu"].config(
            font=("Microsoft JhengHei", 10),
            bg="#FBF6EE",
            fg="#3A2A1F"
        )
        self.collection_tag_menu.pack(fill=tk.X)

        tree_frame = tk.Frame(left_panel, bg="#EADCC8")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        tree_scrollbar = tk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.collection_tree = ttk.Treeview(
            tree_frame,
            show="tree",
            yscrollcommand=tree_scrollbar.set,
            selectmode="extended"
        )
        self.collection_tree.pack(fill=tk.BOTH, expand=True)
        self.collection_tree.bind("<Configure>", self.on_collection_tree_resized)

        tree_scrollbar.config(command=self.collection_tree.yview)

        self.collection_tree.bind("<<TreeviewSelect>>", self.on_select_collection_word)
        self.collection_tree.bind("<Button-3>", self.show_collection_tree_context_menu)

        page_bar = tk.Frame(left_panel, bg="#EADCC8")
        page_bar.pack(fill=tk.X, padx=12, pady=(0, 12))

        button_row = tk.Frame(page_bar, bg="#EADCC8")
        button_row.pack(fill=tk.X)

        prev_btn = self.create_soft_button(button_row, "上一頁", self.prev_collection_page, width=8)
        prev_btn.pack(side=tk.LEFT)

        next_btn = self.create_soft_button(button_row, "下一頁", self.next_collection_page, width=8)
        next_btn.pack(side=tk.RIGHT)

        self.collection_page_label = tk.Label(
            page_bar,
            text="第 1 頁 / 共 1 頁",
            font=("Microsoft JhengHei", 10),
            bg="#EADCC8",
            fg="#6A4A35"
        )
        self.collection_page_label.pack(pady=(6, 0))

        book_frame = tk.Frame(body, bg="#D8C2A2", bd=0)
        book_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_page = tk.Frame(book_frame, bg="#FBF6EE", bd=0, width=620)
        left_page.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 8), pady=16)
        left_page.pack_propagate(False)

        # ── 右欄「詳解」：改為可滾動的 Canvas 容器 ──────────────────
        right_outer = tk.Frame(book_frame, bg="#D8C2A2", bd=0, width=430)
        right_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(8, 16), pady=16)
        right_outer.pack_propagate(False)

        right_canvas = tk.Canvas(right_outer, bg="#FBF6EE", highlightthickness=0)
        right_scroll = tk.Scrollbar(right_outer, orient=tk.VERTICAL, command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_page = tk.Frame(right_canvas, bg="#FBF6EE", bd=0)
        right_page_window = right_canvas.create_window((0, 0), window=right_page, anchor="nw")

        def _on_right_page_configure(event):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        def _on_right_canvas_configure(event):
            right_canvas.itemconfig(right_page_window, width=event.width)
        right_page.bind("<Configure>", _on_right_page_configure)
        right_canvas.bind("<Configure>", _on_right_canvas_configure)

        def _on_right_mousewheel(event):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        right_canvas.bind("<MouseWheel>", _on_right_mousewheel)
        right_page.bind("<MouseWheel>", _on_right_mousewheel)

        right_page_title = tk.Label(
            right_page,
            text="詳解",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            pady=12
        )
        right_page_title.pack()

        self.collection_translation_text = self.create_labeled_text(right_page, "中文", 4)
        self.collection_english_text = self.create_labeled_text(right_page, "英文", 3)
        self.collection_reading_entry = self.create_labeled_entry(right_page, "讀音")
        self.collection_pos_entry = self.create_labeled_entry(right_page, "詞性")
        self.collection_tag_entry = self.create_labeled_entry(right_page, "分類 tag（用逗號分隔）")
        self.collection_example_text = self.create_labeled_text(right_page, "例句（每行一個）", 5)
        self.collection_usage_text = self.create_labeled_text(right_page, "用法", 5)

        # 讓子元件的滾輪事件也能冒泡到 Canvas
        def _bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_right_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)

        right_page.after(200, lambda: _bind_mousewheel_recursive(right_page))
        self.bind_collection_autosave_events()

        left_page_title = tk.Label(
            left_page,
            text="內容",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            pady=12
        )
        left_page_title.pack()

        left_content = tk.Frame(left_page, bg="#FBF6EE")
        left_content.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        original_section = tk.Frame(left_content, bg="#FBF6EE", bd=0, height=90)
        original_section.pack(fill=tk.X, pady=(0, 10))
        original_section.pack_propagate(False)

        note_section = tk.Frame(left_content, bg="#FBF6EE", bd=0, height=180)
        note_section.pack(fill=tk.X, pady=(0, 10))
        note_section.pack_propagate(False)

        image_section = tk.Frame(left_content, bg="#FBF6EE", bd=0)
        image_section.pack(fill=tk.BOTH, expand=True)

        original_label = tk.Label(
            original_section,
            text="原文",
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            anchor="w"
        )
        original_label.pack(fill=tk.X, pady=(0, 4))

        self.collection_original_text = tk.Text(
            original_section,
            height=1,
            font=("Microsoft JhengHei", 11),
            bg="#F8F1E7",
            fg="#3A2A1F",
            relief="flat",
            bd=0,
            wrap=tk.WORD
        )
        self.collection_original_text.pack(fill=tk.BOTH, expand=True)

        note_label = tk.Label(
            note_section,
            text="補充",
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            anchor="w"
        )
        note_label.pack(fill=tk.X, pady=(0, 4))

        self.collection_note_text = tk.Text(
            note_section,
            height=5,
            font=("Microsoft JhengHei", 11),
            bg="#F8F1E7",
            fg="#3A2A1F",
            relief="flat",
            bd=0,
            wrap=tk.WORD
        )
        self.collection_note_text.pack(fill=tk.BOTH, expand=True)

        image_header = tk.Frame(image_section, bg="#FBF6EE")
        image_header.pack(fill=tk.X)

        image_label = tk.Label(
            image_header,
            text="圖片區",
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            anchor="w"
        )
        image_label.pack(side=tk.LEFT)

        image_add_btn = self.create_soft_button(image_header, "放入圖片", self.choose_collection_image, width=8)
        image_add_btn.pack(side=tk.RIGHT)

        image_clear_btn = self.create_soft_button(
            image_header,
            "清除圖片",
            self.clear_collection_image,
            width=8
        )
        image_clear_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.collection_image_info_entry = tk.Entry(
            image_section,
            textvariable=self.collection_image_path_var,
            font=("Microsoft JhengHei", 10),
            bg="#FBF6EE",
            fg="#6A4A35",
            relief="flat",
            bd=0
        )
        self.collection_image_info_entry.pack(fill=tk.X, pady=(6, 8), ipady=5)

        self.collection_image_preview_label = tk.Label(
            image_section,
            bg="#F8F1E7",
            fg="#6A4A35",
            text="尚未放入圖片",
            anchor="center",
            justify="center"
        )
        self.collection_image_preview_label.pack(fill=tk.BOTH, expand=True)




        bottom = tk.Frame(outer, bg="#F5EAD9")
        bottom.pack(fill=tk.X)

        left_actions = tk.Frame(bottom, bg="#F5EAD9")
        left_actions.pack(side=tk.LEFT)

        back_btn = self.create_footer_button(left_actions, "返回索引", self.build_index_page_callback, primary=True)
        back_btn.pack(side=tk.LEFT)

        save_btn = self.create_footer_button(bottom, "儲存內容", self.save_collection_entry)
        save_btn.pack(side=tk.RIGHT, padx=(10, 0))

        close_btn = self.create_footer_button(bottom, "關閉", self.close_dictionary_window)
        close_btn.pack(side=tk.RIGHT)

        self.refresh_collection_list()
        self.show_empty_collection_detail()


    def create_labeled_entry(self, parent, label_text):
        label = tk.Label(
            parent,
            text=label_text,
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            anchor="w"
        )
        label.pack(fill=tk.X, padx=14, pady=(6, 4))

        entry = tk.Entry(
            parent,
            font=("Microsoft JhengHei", 11),
            bg="#F8F1E7",
            fg="#3A2A1F",
            relief="flat",
            bd=0
        )
        entry.pack(fill=tk.X, padx=14, pady=(0, 10), ipady=6)
        return entry

    def create_labeled_text(self, parent, label_text, height):
        label = tk.Label(
            parent,
            text=label_text,
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#FBF6EE",
            fg="#4A2F21",
            anchor="w"
        )
        label.pack(fill=tk.X, padx=14, pady=(6, 4))

        text_widget = tk.Text(
            parent,
            height=height,
            font=("Microsoft JhengHei", 11),
            bg="#F8F1E7",
            fg="#3A2A1F",
            relief="flat",
            bd=0,
            wrap=tk.WORD
        )
        text_widget.pack(fill=tk.X, padx=14, pady=(0, 10))
        return text_widget

    def bind_collection_autosave_events(self):
        entry_widgets = [
            self.collection_reading_entry,
            self.collection_pos_entry,
            self.collection_tag_entry,
            self.collection_image_info_entry,
        ]
        text_widgets = [
            self.collection_original_text,
            self.collection_note_text,
            self.collection_translation_text,
            self.collection_english_text,
            self.collection_example_text,
            self.collection_usage_text,
        ]

        for widget in entry_widgets:
            widget.bind("<KeyRelease>", self.schedule_collection_autosave)
            widget.bind("<Return>", self.mark_collection_entry_dirty_from_event)

        for widget in text_widgets:
            widget.bind("<KeyRelease>", self.schedule_collection_autosave)
            widget.bind("<Return>", self.schedule_collection_autosave_after_text_return)

    def schedule_collection_autosave_after_text_return(self, event=None):
        self.window.after_idle(lambda: self.schedule_collection_autosave(delay=50))

    def schedule_collection_autosave(self, event=None, delay=700):
        if self.collection_detail_loading or self.current_entry is None:
            return

        self.collection_has_unsaved_changes = True

    def cancel_collection_autosave(self):
        if self.collection_autosave_job is not None:
            try:
                self.window.after_cancel(self.collection_autosave_job)
            except Exception:
                pass
            self.collection_autosave_job = None

    def cancel_collection_enrich_refresh(self):
        if self.collection_enrich_refresh_job is not None:
            try:
                self.window.after_cancel(self.collection_enrich_refresh_job)
            except Exception:
                pass
            self.collection_enrich_refresh_job = None

    def mark_collection_entry_dirty_from_event(self, event=None):
        if self.collection_detail_loading or self.current_entry is None:
            return

        self.collection_has_unsaved_changes = True

    def normalize_collection_split(self, value):
        default = [0.18, 0.32, 0.50]
        if not isinstance(value, list) or len(value) != 3:
            return default

        try:
            result = [float(x) for x in value]
        except Exception:
            return default

        total = sum(result)
        if total <= 0:
            return default

        result = [max(0.1, x / total) for x in result]
        total = sum(result)
        return [x / total for x in result]

    def apply_collection_split(self, split_value):
        if not hasattr(self, "collection_left_pane"):
            return

        split_value = self.normalize_collection_split(split_value)
        pane_height = max(self.collection_left_pane.winfo_height(), 320)
        sash1 = int(pane_height * split_value[0])
        sash2 = int(pane_height * (split_value[0] + split_value[1]))

        try:
            self.collection_left_pane.sash_place(0, 1, sash1)
            self.collection_left_pane.sash_place(1, 1, sash2)
        except Exception:
            pass

    def schedule_apply_collection_split(self, split_value):
        if not hasattr(self, "collection_left_pane"):
            return

        if self.collection_split_apply_job is not None:
            try:
                self.window.after_cancel(self.collection_split_apply_job)
            except Exception:
                pass

        self.collection_split_apply_job = self.window.after(
            80, lambda: self.apply_collection_split(split_value)
        )

    def get_current_collection_split(self):
        if not hasattr(self, "collection_left_pane"):
            return [0.18, 0.32, 0.50]

        pane_height = max(self.collection_left_pane.winfo_height(), 320)
        try:
            sash1 = self.collection_left_pane.sash_coord(0)[1]
            sash2 = self.collection_left_pane.sash_coord(1)[1]
        except Exception:
            return [0.18, 0.32, 0.50]

        top = max(0.1, sash1 / pane_height)
        middle = max(0.1, (sash2 - sash1) / pane_height)
        bottom = max(0.1, (pane_height - sash2) / pane_height)
        return self.normalize_collection_split([top, middle, bottom])

    def on_collection_pane_resize(self, event=None):
        if self.current_entry is None:
            return
        self.current_entry["左頁分割"] = self.get_current_collection_split()

    def choose_collection_image(self):
        if self.current_entry is None:
            messagebox.showwarning("提示", "請先從左邊選一個單字")
            return

        path = filedialog.askopenfilename(
            parent=self.window,
            title="選擇圖片",
            filetypes=[
                ("圖片檔", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"),
                ("所有檔案", "*.*")
            ]
        )
        if not path:
            return

        image_path = self.store_collection_image(path)
        self.collection_current_image_path = image_path
        self.show_collection_image(image_path)
        self.collection_image_path_var.set("")
        self.collection_has_unsaved_changes = True

    def store_collection_image(self, source_path):
        source_path = str(source_path).strip()
        if not source_path:
            return ""

        image_dir = os.path.join(os.getcwd(), "dictionary_images")
        os.makedirs(image_dir, exist_ok=True)

        _, ext = os.path.splitext(source_path)
        ext = ext.lower() or ".png"
        try:
            with open(source_path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            return source_path

        filename = f"{digest}{ext}"
        target_path = os.path.join(image_dir, filename)
        if not os.path.exists(target_path):
            shutil.copy2(source_path, target_path)

        return os.path.relpath(target_path, os.getcwd())

    def clear_collection_image(self):
        self.stop_collection_image_animation()
        self.collection_current_image_path = ""
        self.collection_image_preview = None
        self.collection_image_frames = []
        self.collection_image_frame_index = 0
        self.collection_image_path_var.set("")
        if hasattr(self, "collection_image_preview_label"):
            self.collection_image_preview_label.config(image="", text="尚未放入圖片")
        if not self.collection_detail_loading and self.current_entry is not None:
            self.collection_has_unsaved_changes = True

    def stop_collection_image_animation(self):
        if self.collection_image_animation_job is not None:
            try:
                self.window.after_cancel(self.collection_image_animation_job)
            except Exception:
                pass
            self.collection_image_animation_job = None

    def play_collection_gif_frame(self, delay):
        if not self.collection_image_frames:
            return

        self.collection_image_preview = self.collection_image_frames[self.collection_image_frame_index]
        self.collection_image_preview_label.config(image=self.collection_image_preview, text="")
        self.collection_image_frame_index = (
            self.collection_image_frame_index + 1
        ) % len(self.collection_image_frames)
        self.collection_image_animation_job = self.window.after(
            max(delay, 30), lambda: self.play_collection_gif_frame(delay)
        )

    def resolve_collection_image_path(self, path):
        path = str(path).strip()
        if not path:
            return ""
        if os.path.isabs(path):
            return path
        return os.path.abspath(path)

    def get_collection_image_cache_key(self, path):
        resolved_path = self.resolve_collection_image_path(path)
        try:
            modified_at = os.path.getmtime(resolved_path)
        except Exception:
            modified_at = 0
        return (resolved_path, modified_at)

    def show_collection_image(self, path):
        path = str(path).strip()
        if not path:
            self.clear_collection_image()
            return

        self.stop_collection_image_animation()
        self.collection_image_frames = []
        self.collection_image_frame_index = 0

        try:
            cache_key = self.get_collection_image_cache_key(path)
            cached = self.collection_image_cache.get(cache_key)
            if cached is None:
                image = Image.open(cache_key[0])
                if getattr(image, "is_animated", False):
                    delay = int(image.info.get("duration", 100) or 100)
                    frames = []
                    for frame in ImageSequence.Iterator(image):
                        preview = frame.convert("RGBA")
                        preview.thumbnail((420, 260))
                        frames.append(ImageTk.PhotoImage(preview))

                    if not frames:
                        raise ValueError("empty gif")

                    cached = {
                        "type": "gif",
                        "delay": delay,
                        "frames": frames
                    }
                else:
                    image.thumbnail((420, 260))
                    cached = {
                        "type": "image",
                        "photo": ImageTk.PhotoImage(image)
                    }
                self.collection_image_cache[cache_key] = cached

            if cached["type"] == "gif":
                self.collection_image_frames = cached["frames"]
                self.collection_image_path_var.set("")
                self.play_collection_gif_frame(cached["delay"])
            else:
                self.collection_image_preview = cached["photo"]
                self.collection_image_preview_label.config(image=self.collection_image_preview, text="")
                self.collection_image_path_var.set("")

            self.collection_current_image_path = path
        except Exception:
            self.collection_image_preview = None
            self.collection_image_frames = []
            self.collection_image_preview_label.config(image="", text="圖片載入失敗")
            self.collection_image_path_var.set("圖片載入失敗，請確認路徑")

    def get_collection_entry_key(self, item):
        return (
            str(item.get("單字", "")).strip(),
            str(item.get("language", "")).strip()
        )


    # =========================================================
    # 3. 考試區
    # =========================================================
    def open_exam_area(self):
        self.clear_page()
        self.load_dictionary_data()
        self.exam_candidates = []
        self.exam_current_question = None
        self.exam_recent_question_keys = []
        self.exam_answer_shown = False
        self.exam_score = 0
        self.exam_total = 0

        outer = tk.Frame(self.main_frame, bg="#F5EAD9")
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # ── 頁首區塊 ──────────────────────────────────────────
        header = tk.Frame(outer, bg="#E7D6BE")
        header.pack(fill=tk.X, pady=(0, 14))

        title = tk.Label(
            header,
            text=f"📖  {self.get_language_name(self.selected_language)} 考試",
            font=("Microsoft JhengHei", 22, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=16
        )
        title.pack()

        subtitle = tk.Label(
            header,
            text="依照目前字典分類出題，標準題組完全離線不耗 API",
            font=("Microsoft JhengHei", 11),
            bg="#E7D6BE",
            fg="#7A6555",
            pady=(0)
        )
        subtitle.pack(pady=(0, 10))

        # ── 底部按鈕（先 pack，確保永遠顯示在可視範圍）──────────
        bottom = tk.Frame(outer, bg="#F5EAD9")
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 4))

        back_btn = self.create_footer_button(bottom, "返回索引", self.build_index_page_callback, primary=True)
        back_btn.pack(side=tk.LEFT)

        close_btn = self.create_footer_button(bottom, "關閉", self.window.destroy)
        close_btn.pack(side=tk.RIGHT)

        # ── 主體內容區 ────────────────────────────────────────
        body = tk.Frame(outer, bg="#F5EAD9")
        body.pack(fill=tk.BOTH, expand=True)

        # 左側控制面板（外框）
        left_outer = tk.Frame(body, bg="#EADCC8", bd=0, width=330)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        left_outer.pack_propagate(False)

        # ── 左側：底部固定按鈕區 ──────────────────────────────────
        left_bottom = tk.Frame(left_outer, bg="#EADCC8")
        left_bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 14))

        report_row = tk.Frame(left_bottom, bg="#EADCC8")
        report_row.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 0))

        wrong_log_btn = self.create_soft_button(report_row, "📔 錯題本", self.show_wrong_log, width=10)
        wrong_log_btn.pack(side=tk.LEFT)

        report_btn = self.create_soft_button(report_row, "📊 學習報告", self.show_learning_report, width=10)
        report_btn.pack(side=tk.RIGHT)

        left_button_row = tk.Frame(left_bottom, bg="#EADCC8")
        left_button_row.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(0, 6))

        new_question_btn = self.create_soft_button(left_button_row, "▶ 下一題", self.next_exam_question, width=10)
        new_question_btn.pack(side=tk.LEFT)

        reset_score_btn = self.create_soft_button(left_button_row, "↺ 重置成績", self.reset_exam_score, width=10)
        reset_score_btn.pack(side=tk.RIGHT)

        self.exam_score_label = tk.Label(
            left_bottom,
            text="作答進度：0 / 0\n正確率：0%",
            font=("Microsoft JhengHei", 11),
            bg="#EADCC8", fg="#6A4A35",
            anchor="w", justify="left"
        )
        self.exam_score_label.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 12))

        self.exam_pool_label = tk.Label(
            left_bottom,
            text="可出題數：0",
            font=("Microsoft JhengHei", 11),
            bg="#EADCC8", fg="#6A4A35",
            anchor="w", justify="left"
        )
        self.exam_pool_label.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 4))

        sep2 = tk.Frame(left_bottom, bg="#D2B89A", height=1)
        sep2.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(4, 10))

        # ── 左側：上方可滾動出題選項區 ───────────────────────────
        left_canvas = tk.Canvas(left_outer, bg="#EADCC8", highlightthickness=0)
        left_scrollbar = tk.Scrollbar(left_outer, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        left_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_panel = tk.Frame(left_canvas, bg="#EADCC8", bd=0)
        left_canvas_window = left_canvas.create_window((0, 0), window=left_panel, anchor="nw")

        def _on_left_frame_configure(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        def _on_left_canvas_configure(event):
            left_canvas.itemconfig(left_canvas_window, width=event.width)
        left_panel.bind("<Configure>", _on_left_frame_configure)
        left_canvas.bind("<Configure>", _on_left_canvas_configure)
        
        def _on_left_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        left_canvas.bind("<MouseWheel>", _on_left_mousewheel)
        left_panel.bind("<MouseWheel>", _on_left_mousewheel)

        # 右側題目面板（帶滾動條避免溢出）
        right_wrapper = tk.Frame(body, bg="#EADCC8", bd=0)
        right_wrapper.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_canvas = tk.Canvas(right_wrapper, bg="#EADCC8", highlightthickness=0)
        right_scrollbar = tk.Scrollbar(right_wrapper, orient=tk.VERTICAL, command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scrollbar.set)

        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_panel = tk.Frame(self.right_canvas, bg="#EADCC8", bd=0)
        right_canvas_window = self.right_canvas.create_window((0, 0), window=right_panel, anchor="nw")

        def _on_right_frame_configure(event):
            self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))
        def _on_right_canvas_configure(event):
            self.right_canvas.itemconfig(right_canvas_window, width=event.width)
        right_panel.bind("<Configure>", _on_right_frame_configure)
        self.right_canvas.bind("<Configure>", _on_right_canvas_configure)

        # 滾輪與鍵盤滾動支援
        def _on_mousewheel(event):
            self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _on_keyboard_scroll(event):
            if event.keysym == "Up":
                self.right_canvas.yview_scroll(-1, "units")
            elif event.keysym == "Down":
                self.right_canvas.yview_scroll(1, "units")
                
        self.right_canvas.bind("<MouseWheel>", _on_mousewheel)
        right_panel.bind("<MouseWheel>", _on_mousewheel)
        self.window.bind("<Up>", _on_keyboard_scroll)
        self.window.bind("<Down>", _on_keyboard_scroll)

        # ── 左側：出題設定 ────────────────────────────────────
        control_title = tk.Label(
            left_panel,
            text="⚙ 出題設定",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#EADCC8",
            fg="#4A2F21",
            pady=14,
            padx=16,
            anchor="w"
        )
        control_title.pack(fill=tk.X)

        sep1 = tk.Frame(left_panel, bg="#D2B89A", height=1)
        sep1.pack(fill=tk.X, padx=14, pady=(0, 10))

        tag_label = tk.Label(
            left_panel,
            text="出題分類",
            font=("Microsoft JhengHei", 11, "bold"),
            bg="#EADCC8",
            fg="#4A2F21",
            anchor="w"
        )
        tag_label.pack(fill=tk.X, padx=16, pady=(4, 6))

        exam_tag_options = self.get_exam_tag_options()
        if self.exam_tag_var.get() not in exam_tag_options:
            self.exam_tag_var.set(exam_tag_options[0])

        self.exam_tag_menu = tk.OptionMenu(
            left_panel,
            self.exam_tag_var,
            *exam_tag_options,
            command=lambda _value: self.on_exam_filter_changed()
        )
        self.exam_tag_menu.config(
            font=("Microsoft JhengHei", 10),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            highlightthickness=0
        )
        self.exam_tag_menu["menu"].config(
            font=("Microsoft JhengHei", 10),
            bg="#FBF6EE",
            fg="#3A2A1F"
        )
        self.exam_tag_menu.pack(fill=tk.X, padx=16, pady=(0, 12))

        # ── 標準練習題 LabelFrame ──────────────────────────────
        std_frame = tk.LabelFrame(
            left_panel,
            text="  📚 標準練習題（本地，不耗 API）  ",
            font=("Microsoft JhengHei", 10, "bold"),
            bg="#EADCC8", fg="#4A2F21",
            padx=10, pady=8,
            relief="groove"
        )
        std_frame.pack(fill=tk.X, padx=14, pady=(0, 8))

        self.exam_mode_rbs = {}
        
        exam_lang = self.get_exam_language()
        if exam_lang == "en":
            std_modes = [
                ("📝 拼寫練習", "reading_input"),
                ("📝 看中文選單字", "meaning_choice"),
                ("🔀 英文混淆選擇題", "local_distractor"),
                ("⏱️ 詞性限時分類", "pos_sorting"),
            ]
        else:
            std_modes = [
                ("📝 看單字輸入讀音", "reading_input"),
                ("📝 看中文選單字", "meaning_choice"),
                ("🔀 內部混淆選擇題", "local_distractor"),
                ("⏱️ 詞性限時分類", "pos_sorting"),
            ]

        for text, value in std_modes:
            rb = tk.Radiobutton(
                std_frame, text=text,
                variable=self.exam_mode_var, value=value,
                command=self.on_exam_filter_changed,
                font=("Microsoft JhengHei", 11),
                bg="#EADCC8", fg="#4A2F21",
                selectcolor="#FBF6EE",
                activebackground="#EADCC8", activeforeground="#4A2F21",
                highlightthickness=0, bd=0, anchor="w", justify="left"
            )
            rb.pack(fill=tk.X, pady=3)
            self.exam_mode_rbs[value] = rb

        # ── 進階 AI 考題 LabelFrame ────────────────────────────────
        adv_mode_frame = tk.LabelFrame(
            left_panel,
            text="  ✨ 進階 AI 考題（消耗 API 額度）  ",
            font=("Microsoft JhengHei", 10, "bold"),
            bg="#EADCC8", fg="#B94A48",
            padx=10, pady=8,
            relief="groove"
        )
        adv_mode_frame.pack(fill=tk.X, padx=14, pady=(0, 8))

        for text, value in [
            ("✨ AI 情境克漏字（單選）", "ai_cloze"),
            ("✨ 翻譯微調與評分", "ai_translation"),
            ("✨ 換句話說 / 語意重構", "ai_paraphrasing"),
        ]:
            rb = tk.Radiobutton(
                adv_mode_frame, text=text,
                variable=self.exam_mode_var, value=value,
                command=self.on_exam_filter_changed,
                font=("Microsoft JhengHei", 11, "bold"),
                bg="#EADCC8", fg="#8B2020",
                selectcolor="#FBF6EE",
                activebackground="#EADCC8", activeforeground="#8B2020",
                highlightthickness=0, bd=0, anchor="w", justify="left"
            )
            rb.pack(fill=tk.X, pady=3)
            self.exam_mode_rbs[value] = rb

        # ── 🎮 遊戲模式 LabelFrame ──────────────────────────────
        game_frame = tk.LabelFrame(
            left_panel,
            text="  🎮 遊戲模式（本地，不耗 API）  ",
            font=("Microsoft JhengHei", 10, "bold"),
            bg="#EADCC8", fg="#2A6A4A",
            padx=10, pady=8,
            relief="groove"
        )
        if exam_lang != "en":
            game_frame.pack(fill=tk.X, padx=14, pady=(0, 10))

        match_btn = self.create_soft_button(
            game_frame, "🃏 記憶翻牌矩陣",
            lambda: self._open_memory_match(), width=16
        )
        match_btn.pack(fill=tk.X, pady=3)

        falling_btn = self.create_soft_button(
            game_frame, "🌧️ 假名雨打字防禦",
            lambda: self._open_falling_words(), width=16
        )
        falling_btn.pack(fill=tk.X, pady=3)

        # (下半部的標籤與按鈕已移至 left_bottom 固定區域，此處移除)

        # ── 右側：題目區（在可滾動面板內）────────────────────────
        quiz_title_bar = tk.Frame(right_panel, bg="#D8C4A8")
        quiz_title_bar.pack(fill=tk.X)

        quiz_title = tk.Label(
            quiz_title_bar,
            text="題目區",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#D8C4A8",
            fg="#4A2F21",
            pady=14,
            padx=20,
            anchor="w"
        )
        quiz_title.pack(fill=tk.X)

        quiz_card = tk.Frame(right_panel, bg="#FBF6EE", bd=0)
        quiz_card.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))

        # 讓 quiz_card 內部也繫結滾輪
        quiz_card.bind("<MouseWheel>", _on_mousewheel)

        self.exam_question_type_label = tk.Label(
            quiz_card,
            text="",
            font=("Microsoft JhengHei", 11, "bold"),
            bg="#FBF6EE",
            fg="#8B5E3C",
            anchor="w"
        )
        self.exam_question_type_label.pack(fill=tk.X, padx=20, pady=(20, 6))

        self.exam_prompt_label = tk.Label(
            quiz_card,
            text="",
            font=("Microsoft JhengHei", 28, "bold"),
            bg="#FBF6EE",
            fg="#2E1B10",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.exam_prompt_label.pack(fill=tk.X, padx=20, pady=(0, 10))

        self.exam_hint_label = tk.Label(
            quiz_card,
            text="",
            font=("Microsoft JhengHei", 11),
            bg="#FBF6EE",
            fg="#7A6555",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.exam_hint_label.pack(fill=tk.X, padx=20, pady=(0, 14))

        sep3 = tk.Frame(quiz_card, bg="#E2D4BE", height=1)
        sep3.pack(fill=tk.X, padx=20, pady=(0, 14))

        self.exam_answer_entry = tk.Entry(
            quiz_card,
            font=("Microsoft JhengHei", 14),
            bg="#FFFDF8",
            fg="#2E231B",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#8B5E3C",
            highlightbackground="#EADCC8"
        )
        self.exam_answer_entry.pack(fill=tk.X, padx=20, pady=(0, 14), ipady=10)
        self.exam_answer_entry.bind("<Return>", self.submit_exam_answer)

        self.exam_choice_var = tk.StringVar(value="")
        self.exam_choice_buttons = []
        choice_frame = tk.Frame(quiz_card, bg="#FBF6EE")
        choice_frame.pack(fill=tk.X, padx=20, pady=(0, 14))
        for _ in range(6):  # 6 buttons: 4 for normal/distractor, 6 for pos_sorting
            btn = tk.Button(
                choice_frame,
                text="",
                font=("Microsoft JhengHei", 12),
                bg="#F0EAE0",
                fg="#4A2F21",
                activebackground="#E0D4C0",
                activeforeground="#2E1B10",
                highlightthickness=1,
                highlightbackground="#CCBBA0",
                bd=0,
                anchor="w",
                justify="left",
                relief="flat",
                cursor="hand2",
                padx=16,
                pady=10
            )
            btn.pack(fill=tk.X, pady=4)
            self.exam_choice_buttons.append(btn)

        action_row = tk.Frame(quiz_card, bg="#FBF6EE")
        action_row.pack(fill=tk.X, padx=20, pady=(4, 12))

        submit_btn = self.create_soft_button(action_row, "✓ 送出答案", self.submit_exam_answer, width=11)
        submit_btn.pack(side=tk.LEFT)

        reveal_btn = self.create_soft_button(action_row, "👁 看答案", self.reveal_exam_answer, width=10)
        reveal_btn.pack(side=tk.LEFT, padx=10)

        next_btn = self.create_soft_button(action_row, "▶ 換一題", self.next_exam_question, width=10)
        next_btn.pack(side=tk.LEFT)

        sep4 = tk.Frame(quiz_card, bg="#E2D4BE", height=1)
        sep4.pack(fill=tk.X, padx=20, pady=(4, 12))

        self.exam_feedback_label = tk.Label(
            quiz_card,
            text="",
            font=("Microsoft JhengHei", 14, "bold"),
            bg="#FBF6EE",
            fg="#8B5E3C",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.exam_feedback_label.pack(fill=tk.X, padx=20, pady=(0, 8))

        self.exam_answer_label = tk.Label(
            quiz_card,
            text="",
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#4A2F21",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.exam_answer_label.pack(fill=tk.X, padx=20, pady=(0, 20))

        self.on_exam_filter_changed()

        # ── AI 克漏字題目區塊（預先建立，依題型顯示/隐藏）──────────
        self.ai_cloze_frame = tk.Frame(quiz_card, bg="#FBF6EE")
        self.ai_cloze_context_label = tk.Label(
            self.ai_cloze_frame,
            text="",
            font=("Microsoft JhengHei", 14),
            bg="#FBF6EE",
            fg="#2E1B10",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.ai_cloze_context_label.pack(fill=tk.X, padx=6, pady=(0, 10))

        self.ai_cloze_hint_label = tk.Label(
            self.ai_cloze_frame,
            text="",
            font=("Microsoft JhengHei", 11),
            bg="#FBF6EE",
            fg="#7A6555",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.ai_cloze_hint_label.pack(fill=tk.X, padx=6, pady=(0, 10))

        self.ai_cloze_choice_buttons = []
        cloze_choice_frame = tk.Frame(self.ai_cloze_frame, bg="#FBF6EE")
        cloze_choice_frame.pack(fill=tk.X, padx=6, pady=(0, 14))
        for _ in range(4):
            btn = tk.Button(
                cloze_choice_frame,
                text="",
                font=("Microsoft JhengHei", 13),
                bg="#F0EAE0",
                fg="#2E231B",
                activebackground="#E0D4C0",
                activeforeground="#2E1B10",
                highlightthickness=1,
                highlightbackground="#CCBBA0",
                bd=0,
                anchor="w",
                justify="left",
                relief="flat",
                cursor="hand2",
                padx=16,
                pady=10
            )
            btn.pack(fill=tk.X, pady=5)
            self.ai_cloze_choice_buttons.append(btn)

        ai_cloze_btn_row = tk.Frame(self.ai_cloze_frame, bg="#FBF6EE")
        ai_cloze_btn_row.pack(fill=tk.X, padx=6, pady=(0, 10))
        self.create_soft_button(ai_cloze_btn_row, "👁 看答案", self.reveal_ai_cloze_answer, width=10).pack(side=tk.LEFT)
        self.create_soft_button(ai_cloze_btn_row, "▶ 換一題", self.next_exam_question, width=10).pack(side=tk.LEFT, padx=10)
        self.ai_cloze_save_btn = self.create_soft_button(ai_cloze_btn_row, "⭐ 收藏句子", self.save_ai_cloze_sentence, width=10)
        self.ai_cloze_save_btn.pack(side=tk.LEFT)
        self.ai_cloze_save_btn.pack_forget()

        self.ai_cloze_feedback_label = tk.Label(
            self.ai_cloze_frame,
            text="",
            font=("Microsoft JhengHei", 14, "bold"),
            bg="#FBF6EE",
            fg="#8B5E3C",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.ai_cloze_feedback_label.pack(fill=tk.X, padx=6, pady=(0, 8))

        self.ai_cloze_answer_reveal_label = tk.Label(
            self.ai_cloze_frame,
            text="",
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#4A2F21",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.ai_cloze_answer_reveal_label.pack(fill=tk.X, padx=6, pady=(0, 12))

        # ── AI 翻譯微調與評分題目區塊 ─────────────────────────────
        self.ai_translation_frame = tk.Frame(quiz_card, bg="#FBF6EE")
        self.ai_translation_prompt = tk.Label(
            self.ai_translation_frame,
            text="",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#FBF6EE",
            fg="#2E1B10",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.ai_translation_prompt.pack(fill=tk.X, padx=6, pady=(0, 14))

        self.ai_translation_entry = tk.Entry(
            self.ai_translation_frame,
            font=("Microsoft JhengHei", 13),
            bg="#FFFDF8",
            fg="#2E231B",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#8B5E3C",
            highlightbackground="#EADCC8"
        )
        self.ai_translation_entry.pack(fill=tk.X, padx=6, pady=(0, 14), ipady=10)
        self.ai_translation_entry.bind("<Return>", self.submit_ai_translation)

        ai_trans_btn_row = tk.Frame(self.ai_translation_frame, bg="#FBF6EE")
        ai_trans_btn_row.pack(fill=tk.X, padx=6, pady=(0, 10))
        self.create_soft_button(ai_trans_btn_row, "✓ 送出翻譯", self.submit_ai_translation, width=11).pack(side=tk.LEFT)
        self.create_soft_button(ai_trans_btn_row, "▶ 換一題", self.next_exam_question, width=10).pack(side=tk.LEFT, padx=10)

        self.ai_translation_feedback = tk.Label(
            self.ai_translation_frame,
            text="",
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#4A2F21",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.ai_translation_feedback.pack(fill=tk.X, padx=6, pady=(0, 8))

        # ── AI 換句話說 / 語意重構區塊 ───────────────────────────
        self.ai_paraphrase_frame = tk.Frame(quiz_card, bg="#FBF6EE")
        self.ai_paraphrase_prompt = tk.Label(
            self.ai_paraphrase_frame,
            text="",
            font=("Microsoft JhengHei", 13),
            bg="#FBF6EE",
            fg="#2E1B10",
            wraplength=820,
            justify="left",
            anchor="w"
        )
        self.ai_paraphrase_prompt.pack(fill=tk.X, padx=6, pady=(0, 14))

        self.ai_paraphrase_entry = tk.Entry(
            self.ai_paraphrase_frame,
            font=("Microsoft JhengHei", 13),
            bg="#FFFDF8",
            fg="#2E231B",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#8B5E3C",
            highlightbackground="#EADCC8"
        )
        self.ai_paraphrase_entry.pack(fill=tk.X, padx=6, pady=(0, 14), ipady=10)
        self.ai_paraphrase_entry.bind("<Return>", self.submit_ai_paraphrase)

        ai_para_btn_row = tk.Frame(self.ai_paraphrase_frame, bg="#FBF6EE")
        ai_para_btn_row.pack(fill=tk.X, padx=6, pady=(0, 10))
        self.create_soft_button(ai_para_btn_row, "✓ 送出造句", self.submit_ai_paraphrase, width=11).pack(side=tk.LEFT)
        self.create_soft_button(ai_para_btn_row, "▶ 換一題", self.next_exam_question, width=10).pack(side=tk.LEFT, padx=10)

        self.ai_paraphrase_feedback = tk.Label(
            self.ai_paraphrase_frame,
            text="",
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#4A2F21",
            justify="left",
            anchor="w",
            wraplength=820
        )
        self.ai_paraphrase_feedback.pack(fill=tk.X, padx=6, pady=(0, 10))

    def get_exam_language(self):
        selected_language = (self.selected_language or "").strip()
        if selected_language and selected_language != "new":
            return selected_language
        return ""

    def get_exam_tag_options(self):
        tags = set()
        has_unclassified = False
        exam_language = self.get_exam_language()

        for item in self.dictionary_data:
            if exam_language and str(item.get("language", "")).strip() != exam_language:
                continue

            normalized_tags = self.get_normalized_tags(item)
            if normalized_tags == ["未分類"]:
                has_unclassified = True
            else:
                for tag in normalized_tags:
                    tags.add(tag)

        ordered_tags = []
        if has_unclassified:
            ordered_tags.append("未分類")

        ordered_tags.extend(sorted(tags))
        return ordered_tags or ["未分類"]

    def on_exam_filter_changed(self):
        self.exam_candidates = self.get_exam_candidates()
        self.exam_current_question = None
        self.exam_recent_question_keys = []
        self.exam_answer_shown = False
        self.exam_choice_var.set("")

        self.update_exam_score_label()

        if hasattr(self, "exam_pool_label"):
            mode = self.exam_mode_var.get().strip()
            mode_names = {
                "reading_input": "讀音輸入",
                "meaning_choice": "中文選字",
                "local_distractor": "內部混淆選擇",
                "pos_sorting": "詞性分類",
                "ai_cloze": "AI 克漏字",
                "ai_translation": "翻譯評分",
                "ai_paraphrasing": "語意重構",
            }
            self.exam_pool_label.config(
                text=f"可出題數：{len(self.exam_candidates)}\n目前題型：{mode_names.get(mode, mode)}"
            )

        self.next_exam_question()

    def get_exam_candidates(self):
        selected_tag = self.exam_tag_var.get().strip()
        mode = self.exam_mode_var.get().strip()
        exam_language = self.get_exam_language()
        result = []

        for item in self.dictionary_data:
            if exam_language and str(item.get("language", "")).strip() != exam_language:
                continue

            normalized_tags = self.get_normalized_tags(item)
            if selected_tag not in normalized_tags:
                continue

            word = str(item.get("單字", "")).strip()
            reading = str(item.get("讀音", "")).strip()
            chinese = str(item.get("中文", "")).strip()

            if not word:
                continue

            # AI / 進階模式：只需要有單字
            if mode in ("ai_cloze", "ai_translation", "ai_paraphrasing"):
                result.append(item)
                continue

            # 詞性分類：需要詞性資料
            if mode == "pos_sorting" and not str(item.get("詞性", "")).strip():
                continue

            # 內部混淤：需要有中文
            if mode == "local_distractor" and not chinese:
                continue

            if mode == "reading_input" and not reading:
                continue

            if mode == "reading_input" and self.is_katakana_only(word):
                continue

            if mode == "meaning_choice" and not chinese:
                continue

            result.append(item)

        return result

    def next_exam_question(self):
        if hasattr(self, "right_canvas"):
            self.right_canvas.yview_moveto(0)
            
        if not hasattr(self, "exam_prompt_label"):
            return

        self.exam_feedback_label.config(text="")
        self.exam_answer_label.config(text="")
        self.exam_answer_shown = False
        self.exam_choice_var.set("")
        self.exam_answer_entry.delete(0, tk.END)

        mode = self.exam_mode_var.get().strip()

        # 進階考題模式切換 UI
        self._switch_to_normal_mode_exam_widgets()
        if mode == "ai_cloze":
            self._switch_to_ai_cloze_mode()
        elif mode == "ai_translation":
            self._switch_to_ai_translation_mode()
        elif mode == "ai_paraphrasing":
            self._switch_to_ai_paraphrasing_mode()
        else:
            self._switch_to_normal_mode()

        if not self.exam_candidates:
            self.exam_current_question = None
            self.exam_question_type_label.config(text="目前無法出題")
            self.exam_prompt_label.config(text="這個分類目前沒有可用的題目")
            self.exam_hint_label.config(text="提示：你可以先去單字收藏補上讀音或中文，再回來練習。")
            self.exam_answer_entry.pack_forget()
            for btn in self.exam_choice_buttons:
                btn.pack_forget()
            return

        item = self.choose_next_exam_question()
        self.exam_current_question = item
        self.remember_exam_question(item)

        if mode == "ai_cloze":
            self.exam_question_type_label.config(text="題型：AI 情境克漏字")
            word = str(item.get("單字", "")).strip()
            self.exam_prompt_label.config(text=f"目標單字：{word}")
            self.exam_hint_label.config(text="請等待 AI 生成情境句子…")
            self.generate_ai_cloze(item)
            return
        elif mode == "ai_translation":
            self.exam_question_type_label.config(text="題型：翻譯微調與評分")
            word = str(item.get("單字", "")).strip()
            self.exam_prompt_label.config(text=f"目標單字：{word}")
            self.exam_hint_label.config(text="請等待 AI 生成日文句子…")
            self.generate_ai_translation(item)
            return
        elif mode == "ai_paraphrasing":
            self.exam_question_type_label.config(text="題型：換句話說 / 語意重構")
            word = str(item.get("單字", "")).strip()
            self.exam_prompt_label.config(text=f"目標單字：{word}")
            self.exam_hint_label.config(text="請等待 AI 設計語意重構情境…")
            self.generate_ai_paraphrase(item)
            return
        elif mode == "local_distractor":
            self._show_local_distractor_question(item)
            return
        elif mode == "pos_sorting":
            self._show_pos_sorting_question(item)
            return

        exam_lang = self.get_exam_language()
        if mode == "reading_input":
            if exam_lang == "en":
                self.exam_question_type_label.config(text="題型：拼寫練習 (英)")
                chinese = str(item.get("中文", "")).strip()
                self.exam_prompt_label.config(text=chinese or "無中文提示")
                self.exam_hint_label.config(text="請拼寫出對應的英文單字")
            else:
                self.exam_question_type_label.config(text="題型：看單字輸入讀音")
                self.exam_prompt_label.config(text=item.get("單字", ""))
                chinese = str(item.get("中文", "")).strip()
                hint_text = f"中文提示：{chinese}" if chinese else "中文提示：目前沒有中文，可直接憑記憶作答"
                hint_text += "\n請輸入羅馬讀音或平假名"
                self.exam_hint_label.config(text=hint_text)

            for btn in self.exam_choice_buttons:
                btn.pack_forget()
            self.exam_answer_entry.pack(fill=tk.X, padx=20, pady=(0, 14), ipady=10)
            self.exam_answer_entry.focus_set()
            return

        if exam_lang == "en":
            self.exam_question_type_label.config(text="題型：看中文選單字 (英)")
            self.exam_prompt_label.config(text=str(item.get("中文", "")).strip())
            self.exam_hint_label.config(text="請選出對應的英文單字")
        else:
            self.exam_question_type_label.config(text="題型：看中文選單字")
            self.exam_prompt_label.config(text=str(item.get("中文", "")).strip())
            reading = str(item.get("讀音", "")).strip()
            self.exam_hint_label.config(
                text=f"讀音提示：{self.format_reading_with_romaji(reading)}" if reading else "讀音提示：無"
            )
        self.exam_answer_entry.pack_forget()

        options = self.build_exam_choices(item)
        for btn in self.exam_choice_buttons:
            btn.pack_forget()

        for btn, option in zip(self.exam_choice_buttons, options):
            btn.option_value = option
            btn.config(command=lambda value=option: self.set_exam_choice(value))
            btn.pack(fill=tk.X, pady=3)

        self.set_exam_choice("")

    def _switch_to_normal_mode_exam_widgets(self):
        """ai_cloze 等切換時，選題按鈕和輸入框先隐藏"""
        pass

    def choose_next_exam_question(self):
        if len(self.exam_candidates) <= 1:
            return self.exam_candidates[0]

        available_items = [
            item for item in self.exam_candidates
            if self.get_collection_entry_key(item) not in self.exam_recent_question_keys
        ]

        if not available_items:
            self.exam_recent_question_keys = []
            available_items = list(self.exam_candidates)

        return random.choice(available_items)

    def remember_exam_question(self, item):
        key = self.get_collection_entry_key(item)
        if not key[0]:
            return

        self.exam_recent_question_keys.append(key)
        max_recent_count = max(1, min(5, len(self.exam_candidates) - 1))
        if len(self.exam_recent_question_keys) > max_recent_count:
            self.exam_recent_question_keys = self.exam_recent_question_keys[-max_recent_count:]

    def build_exam_choices(self, correct_item):
        correct_word = str(correct_item.get("單字", "")).strip()

        pool = []
        for item in self.exam_candidates:
            word = str(item.get("單字", "")).strip()
            if word and word != correct_word:
                pool.append(word)

        unique_pool = []
        seen = set()
        for word in pool:
            if word in seen:
                continue
            seen.add(word)
            unique_pool.append(word)

        random.shuffle(unique_pool)
        options = unique_pool[:3] + [correct_word]
        random.shuffle(options)
        return options

    def submit_exam_answer(self, event=None):
        if not self.exam_current_question:
            return

        if self.exam_answer_shown:
            self.next_exam_question()
            return

        mode = self.exam_mode_var.get().strip()
        correct_answer = ""
        user_answer = ""

        exam_lang = self.get_exam_language()
        if mode == "reading_input":
            if exam_lang == "en":
                correct_answer = str(self.exam_current_question.get("單字", "")).strip()
            else:
                correct_answer = str(self.exam_current_question.get("讀音", "")).strip()
            user_answer = self.exam_answer_entry.get().strip()
        else:
            correct_answer = str(self.exam_current_question.get("單字", "")).strip()
            user_answer = self.exam_choice_var.get().strip()

        if not user_answer:
            self.exam_feedback_label.config(text="請先作答再送出", fg="#A14A2A")
            return

        if mode == "reading_input":
            if exam_lang == "en":
                is_correct = user_answer.lower() == correct_answer.lower()
            else:
                normalized_user_answer = self.normalize_exam_reading(user_answer)
                accepted_answers = self.build_exam_reading_answers(correct_answer)
                is_correct = normalized_user_answer in accepted_answers
        else:
            is_correct = user_answer == correct_answer

        self.exam_total += 1
        if is_correct:
            self.exam_score += 1

        self.update_exam_score_label()
        self.exam_answer_shown = True

        # 記錄答題歷史
        self._record_exam_history(
            str(self.exam_current_question.get("單字", "")).strip(),
            is_correct,
            mode,
            self.exam_current_question
        )

        if is_correct:
            self.exam_feedback_label.config(text="答對了", fg="#2E7D32")
        else:
            self.exam_feedback_label.config(text=f"答錯了，你的答案：{user_answer}", fg="#A14A2A")

        self.exam_answer_label.config(text=self.format_exam_answer_text())

    def reveal_exam_answer(self):
        if not self.exam_current_question:
            return

        self.exam_answer_shown = True
        self.exam_feedback_label.config(text="答案已顯示，這題不計分", fg="#8B5E3C")
        self.exam_answer_label.config(text=self.format_exam_answer_text())

    def format_exam_answer_text(self):
        if not self.exam_current_question:
            return ""

        word = str(self.exam_current_question.get("單字", "")).strip()
        reading = str(self.exam_current_question.get("讀音", "")).strip()
        chinese = str(self.exam_current_question.get("中文", "")).strip()
        english = self.sanitize_english_text(self.exam_current_question.get("英文", ""))
        tags = ", ".join(self.get_normalized_tags(self.exam_current_question))

        return (
            f"正解：{word}\n"
            f"讀音：{self.format_reading_with_romaji(reading)}\n"
            f"中文：{chinese or '未填寫'}\n"
            f"英文：{english or '未填寫'}\n"
            f"分類：{tags}"
        )

    def reset_exam_score(self):
        self.exam_score = 0
        self.exam_total = 0
        self.update_exam_score_label()
        if hasattr(self, "exam_feedback_label"):
            self.exam_feedback_label.config(text="成績已重置", fg="#8B5E3C")

    def update_exam_score_label(self):
        if not hasattr(self, "exam_score_label"):
            return

        accuracy = 0
        if self.exam_total:
            accuracy = round((self.exam_score / self.exam_total) * 100)

        self.exam_score_label.config(
            text=f"作答進度：{self.exam_score} / {self.exam_total}\n正確率：{accuracy}%"
        )

    def _record_exam_history(self, word, correct, mode, item=None):
        pos = ""
        tag = ""
        if item:
            pos = str(item.get("詞性", "")).strip() or "未知"
            tags = self.get_normalized_tags(item)
            tag = tags[0] if tags else "未分類"

        record = {
            "word": word,
            "correct": correct,
            "mode": mode,
            "pos": pos,
            "tag": tag,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.exam_history.append(record)

        if not correct:
            existing_words = [r["word"] for r in self.exam_wrong_log]
            if word not in existing_words:
                self.exam_wrong_log.append(record)
            else:
                for r in self.exam_wrong_log:
                    if r["word"] == word:
                        r["count"] = r.get("count", 1) + 1
                        break

    # =========================================================
    # AI 克漏字
    # =========================================================

    def _hide_all_ai_frames(self):
        if hasattr(self, "ai_cloze_frame"):
            self.ai_cloze_frame.pack_forget()
        if hasattr(self, "ai_translation_frame"):
            self.ai_translation_frame.pack_forget()
        if hasattr(self, "ai_paraphrase_frame"):
            self.ai_paraphrase_frame.pack_forget()

    def _switch_to_ai_cloze_mode(self):
        if hasattr(self, "exam_answer_entry"):
            self.exam_answer_entry.pack_forget()
        if hasattr(self, "exam_choice_buttons"):
            for btn in self.exam_choice_buttons:
                btn.pack_forget()
        self._hide_all_ai_frames()
        if hasattr(self, "ai_cloze_frame"):
            self.ai_cloze_frame.pack(fill=tk.X, padx=18, pady=(0, 8))

    def _switch_to_ai_translation_mode(self):
        if hasattr(self, "exam_answer_entry"):
            self.exam_answer_entry.pack_forget()
        if hasattr(self, "exam_choice_buttons"):
            for btn in self.exam_choice_buttons:
                btn.pack_forget()
        self._hide_all_ai_frames()
        if hasattr(self, "ai_translation_frame"):
            self.ai_translation_frame.pack(fill=tk.X, padx=18, pady=(0, 8))

    def _switch_to_ai_paraphrasing_mode(self):
        if hasattr(self, "exam_answer_entry"):
            self.exam_answer_entry.pack_forget()
        if hasattr(self, "exam_choice_buttons"):
            for btn in self.exam_choice_buttons:
                btn.pack_forget()
        self._hide_all_ai_frames()
        if hasattr(self, "ai_paraphrase_frame"):
            self.ai_paraphrase_frame.pack(fill=tk.X, padx=18, pady=(0, 8))

    def _switch_to_normal_mode(self):
        self._hide_all_ai_frames()

    # =========================================================
    # 🔀 內部混淆選擇題 (local_distractor)
    # =========================================================

    def _show_local_distractor_question(self, item):
        """顯示「看單字 → 選中文」的本地干擾選擇題。"""
        exam_lang = self.get_exam_language()
        title_text = "題型：🔀 英文混淆選擇題" if exam_lang == "en" else "題型：🔀 內部混淆選擇題"
        self.exam_question_type_label.config(text=title_text)
        word = str(item.get("單字", "")).strip()
        reading = str(item.get("讀音", "")).strip()
        pos = str(item.get("詞性", "")).strip()

        self.exam_prompt_label.config(
            text=word,
            font=("Microsoft JhengHei", 28, "bold")
        )
        hint = f"讀音：{reading}" if reading else ""
        if pos:
            hint += f"　詞性：{pos}"
        self.exam_hint_label.config(text=hint or "請選出正確的中文意思")

        correct_zh = str(item.get("中文", "")).strip()
        options = self._build_distractor_choices(item, correct_zh, pos)

        self.exam_answer_entry.pack_forget()
        for btn in self.exam_choice_buttons:
            btn.pack_forget()
        for btn, option in zip(self.exam_choice_buttons, options):
            btn.option_value = option
            btn.config(
                text=option,
                bg="#FBF6EE", fg="#2E231B",
                font=("Microsoft JhengHei", 11),
                relief="solid", bd=1,
                highlightbackground="#EADCC8",
                command=lambda v=option, c=correct_zh: self._submit_local_distractor(v, c, item)
            )
            btn.pack(fill=tk.X, pady=3)
        self.exam_answer_label.config(text="")
        self.exam_feedback_label.config(text="")

    def _build_distractor_choices(self, correct_item, correct_zh, pos):
        """從資料庫選出干擾選項：優先同詞性，否則隨機。"""
        correct_word = str(correct_item.get("單字", "")).strip()
        distractors = []

        # 優先同詞性
        same_pos = [
            str(e.get("中文", "")).strip()
            for e in self.dictionary_data
            if isinstance(e, dict)
            and str(e.get("單字", "")).strip() != correct_word
            and str(e.get("詞性", "")).strip() == pos
            and str(e.get("中文", "")).strip()
            and str(e.get("中文", "")).strip() != correct_zh
        ]
        random.shuffle(same_pos)
        distractors.extend(same_pos[:3])

        # 補充隨機的
        if len(distractors) < 3:
            others = [
                str(e.get("中文", "")).strip()
                for e in self.dictionary_data
                if isinstance(e, dict)
                and str(e.get("單字", "")).strip() != correct_word
                and str(e.get("中文", "")).strip()
                and str(e.get("中文", "")).strip() != correct_zh
                and str(e.get("中文", "")).strip() not in distractors
            ]
            random.shuffle(others)
            distractors.extend(others[:3 - len(distractors)])

        options = distractors[:3] + [correct_zh]
        random.shuffle(options)
        return options

    def _submit_local_distractor(self, chosen, correct_zh, item):
        if self.exam_answer_shown:
            return
        self.exam_answer_shown = True
        word = str(item.get("單字", "")).strip()
        is_correct = chosen == correct_zh

        self.exam_total += 1
        if is_correct:
            self.exam_score += 1
        self.update_exam_score_label()
        self._record_exam_history(word, is_correct, "local_distractor", item)

        for btn in self.exam_choice_buttons:
            opt = getattr(btn, "option_value", "")
            if opt == correct_zh:
                btn.config(bg="#C8E6C9", fg="#1B5E20")
            elif opt == chosen and not is_correct:
                btn.config(bg="#FFCCBC", fg="#BF360C")

        if is_correct:
            self.exam_feedback_label.config(text="✔ 答對了！", fg="#2E7D32")
        else:
            self.exam_feedback_label.config(text=f"✘ 答錯了，正解是：{correct_zh}", fg="#A14A2A")

        reading = str(item.get("讀音", "")).strip()
        self.exam_answer_label.config(
            text=f"單字：{word}　讀音：{reading}　中文：{correct_zh}"
        )

    # =========================================================
    # ⏱️ 詞性限時分類 (pos_sorting)
    # =========================================================

    def _show_pos_sorting_question(self, item):
        """顯示詞性限時分類題，3 秒倒數。"""
        self.exam_question_type_label.config(text="題型：⏱️ 詞性限時分類（3 秒）")
        word = str(item.get("單字", "")).strip()
        self.exam_prompt_label.config(
            text=word,
            font=("Microsoft JhengHei", 32, "bold")
        )
        self.exam_feedback_label.config(text="")
        self.exam_answer_label.config(text="")
        self.exam_answer_entry.pack_forget()

        correct_pos = str(item.get("詞性", "")).strip()
        # 解析正解可能包含的全部詞性
        correct_cats = self._normalize_pos_categories(correct_pos)

        if len(correct_cats) > 1:
            self.exam_hint_label.config(text="⚠️ 此單字具備多個詞性（多選題，選中任一正確詞性即算答對！）")
        else:
            self.exam_hint_label.config(text="請在 3 秒內選出此單字的詞性！")

        # 顯示選項按鈕
        for btn in self.exam_choice_buttons:
            btn.pack_forget()

        exam_lang = self.get_exam_language()
        if exam_lang == "en":
            cats = ["Noun", "Verb", "Adjective", "Adverb", "Pronoun", "Preposition"]
        else:
            cats = ["名詞", "動詞", "い形容詞", "な形容詞", "副詞", "助詞"]

        # 確保正確的選項一定會出現在 cats 中
        for c in correct_cats:
            if c not in cats:
                for i in range(len(cats)):
                    if cats[i] not in correct_cats:
                        cats[i] = c
                        break

        for btn, cat in zip(self.exam_choice_buttons, cats):
            btn.option_value = cat
            btn.config(
                text=cat,
                bg="#FBF6EE", fg="#2E231B",
                font=("Microsoft JhengHei", 13, "bold"),
                relief="solid", bd=1,
                highlightbackground="#EADCC8",
                command=lambda v=cat: self._submit_pos_sorting(v, correct_cats, item)
            )
            btn.pack(fill=tk.X, pady=2)

        # 3 秒倒數 Progress Bar（用 Label 模擬）
        if hasattr(self, "_pos_timer_id") and self._pos_timer_id:
            try:
                self.window.after_cancel(self._pos_timer_id)
            except Exception:
                pass
        self._pos_time_left = 30  # 30 × 100ms = 3s
        self._pos_correct_cats = correct_cats
        self._pos_item = item
        self._pos_timer_tick()

    def _pos_timer_tick(self):
        if not hasattr(self, "exam_hint_label"):
            return
        if self.exam_answer_shown:
            return
        self._pos_time_left -= 1
        progress = "█" * (self._pos_time_left // 3) + "░" * (10 - self._pos_time_left // 3)
        color = "#2E7D32" if self._pos_time_left > 15 else ("#FF8C00" if self._pos_time_left > 8 else "#B71C1C")
        
        hint_text = "⚠️ 具備多個詞性（多選題）！" if len(self._pos_correct_cats) > 1 else ""
        self.exam_hint_label.config(
            text=f"{hint_text} 剩餘時間  {progress}  {self._pos_time_left // 10}.{self._pos_time_left % 10}s",
            fg=color
        )
        if self._pos_time_left <= 0:
            # 超時！
            self._submit_pos_sorting(None, self._pos_correct_cats, self._pos_item)
            return
        self._pos_timer_id = self.window.after(100, self._pos_timer_tick)

    def _normalize_pos_categories(self, pos: str) -> list:
        pos = pos.strip()
        cats = []
        if "代名詞" in pos:
            cats.append("代名詞")
        elif "名詞" in pos:
            cats.append("名詞")
            
        if "副詞" in pos:
            cats.append("副詞")
        if "い形" in pos or ("形容詞" in pos and "な" not in pos and "イ" not in pos.upper()):
            cats.append("い形容詞")
        if "な形" in pos or "ナ形" in pos:
            cats.append("な形容詞")
        if "動詞" in pos and "助動詞" not in pos:
            cats.append("動詞")
        if "助詞" in pos:
            cats.append("助詞")
        if "接續詞" in pos or "連詞" in pos:
            cats.append("接續詞")
            
        if not cats:
            parts = [p.strip() for p in pos.replace("、", ",").replace(";", ",").replace("，", ",").split(",") if p.strip()]
            cats = parts if parts else ["未知詞性"]
            
        # 移除重複並保持順序
        return list(dict.fromkeys(cats))

    def _submit_pos_sorting(self, chosen, correct_cats, item):
        if self.exam_answer_shown:
            return
        self.exam_answer_shown = True
        if hasattr(self, "_pos_timer_id") and self._pos_timer_id:
            try:
                self.window.after_cancel(self._pos_timer_id)
            except Exception:
                pass

        word = str(item.get("單字", "")).strip()
        is_correct = (chosen in correct_cats)

        self.exam_total += 1
        if is_correct:
            self.exam_score += 1
        self.update_exam_score_label()
        self._record_exam_history(word, is_correct, "pos_sorting", item)

        for btn in self.exam_choice_buttons:
            opt = getattr(btn, "option_value", "")
            if opt in correct_cats:
                btn.config(bg="#C8E6C9", fg="#1B5E20")
            elif opt == chosen and not is_correct:
                btn.config(bg="#FFCCBC", fg="#BF360C")

        if chosen is None:
            self.exam_feedback_label.config(text="⏰ 時間到！沒來得及回答", fg="#A14A2A")
        elif is_correct:
            self.exam_feedback_label.config(text="✔ 答對了！反應神速！", fg="#2E7D32")
        else:
            correct_str = "、".join(correct_cats)
            self.exam_feedback_label.config(text=f"✘ 答錯了，正確詞性包含：{correct_str}", fg="#A14A2A")

        pos_full = str(item.get("詞性", "")).strip()
        zh = str(item.get("中文", "")).strip()
        self.exam_answer_label.config(text=f"詞性：{pos_full}　中文：{zh}")

    # =========================================================
    # 🎮 遊戲開啟方法
    # =========================================================

    def _open_memory_match(self):
        try:
            from game_memory_match import open_memory_match
            open_memory_match(self.window, self.dictionary_data)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("錯誤", f"無法開啟記憶翻牌矩陣：{e}", parent=self.window)

    def _open_falling_words(self):
        try:
            from game_falling_words import open_falling_words
            open_falling_words(self.window, self.dictionary_data)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("錯誤", f"無法開啟假名雨打字防禦：{e}", parent=self.window)

    # =========================================================
    # ✨ AI 克漏字生成
    # =========================================================

    def generate_ai_cloze(self, item):
        """呼叫 AI 生成情境克漏字題目（選項式），並在完成後更新 UI。"""
        if self.ai_cloze_loading:
            return

        self.ai_cloze_loading = True
        self.ai_cloze_current = None

        if hasattr(self, "ai_cloze_context_label"):
            self.ai_cloze_context_label.config(text="AI 正在生成情境填空題，請稍候…")
        if hasattr(self, "ai_cloze_hint_label"):
            self.ai_cloze_hint_label.config(text="")
        if hasattr(self, "ai_cloze_feedback_label"):
            self.ai_cloze_feedback_label.config(text="")
        if hasattr(self, "ai_cloze_answer_reveal_label"):
            self.ai_cloze_answer_reveal_label.config(text="")
        if hasattr(self, "ai_cloze_answer_entry"):
            self.ai_cloze_answer_entry.delete(0, tk.END)

        word = str(item.get("單字", "")).strip()
        tags = self.get_normalized_tags(item)
        context_tag = tags[0] if tags and tags[0] != "未分類" else ""

        def worker():
            try:
                from ai_service import generate_cloze_question
                result = generate_cloze_question(word, context_tag, lang=self.get_exam_language())
            except Exception as e:
                result = {}
                print(f"[dictionary_home] AI 克漏字生成失敗：{e}")
            self.window.after(0, lambda: self._apply_ai_cloze_result(item, result))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_ai_cloze_result(self, item, result):
        self.ai_cloze_loading = False

        if not result:
            if hasattr(self, "ai_cloze_context_label"):
                self.ai_cloze_context_label.config(
                    text="AI 生成失敗（請確認 API Key 設定，或檢查網路連線）"
                )
            return

        self.ai_cloze_current = result
        self.ai_cloze_current["_source_item"] = item
        self.exam_answer_shown = False
        self.ai_cloze_selected_choice = ""

        sentence_display = result.get("sentence_display", "")
        hint_zh = result.get("hint_zh", "")
        hint_pos = result.get("hint_pos", "")
        difficulty = result.get("difficulty", "")
        answer = result.get("answer", "")
        distractors = result.get("distractors", [])

        if hasattr(self, "ai_cloze_context_label"):
            self.ai_cloze_context_label.config(text=sentence_display or "（題目生成中…）")

        hint_parts = []
        if hint_zh:
            hint_parts.append(f"語境：{hint_zh}")
        if hint_pos:
            hint_parts.append(f"詞性：{hint_pos}")
        if difficulty:
            hint_parts.append(f"難度：{difficulty}")
        if hasattr(self, "ai_cloze_hint_label"):
            self.ai_cloze_hint_label.config(text="　".join(hint_parts))

        options = distractors[:3] + [answer]
        random.shuffle(options)
        
        for btn in self.ai_cloze_choice_buttons:
            btn.pack_forget()

        for btn, option in zip(self.ai_cloze_choice_buttons, options):
            btn.option_value = option
            btn.config(
                text=option,
                bg="#FFFDF8", fg="#2E231B",
                command=lambda value=option: self.set_ai_cloze_choice(value)
            )
            btn.pack(fill=tk.X, pady=4)

        if hasattr(self, "ai_cloze_save_btn"):
            self.ai_cloze_save_btn.pack_forget()

    def set_ai_cloze_choice(self, value):
        if self.exam_answer_shown:
            return
        self.ai_cloze_selected_choice = value
        for btn in self.ai_cloze_choice_buttons:
            if getattr(btn, "option_value", None) == value:
                btn.config(bg="#EADCC8", fg="#2E231B")
            else:
                btn.config(bg="#FFFDF8", fg="#6A4A35")

    def submit_ai_cloze_answer(self, event=None):
        if not self.ai_cloze_current:
            return
        if self.exam_answer_shown:
            self.next_exam_question()
            return
        if self.ai_cloze_loading:
            return

        user_answer = getattr(self, "ai_cloze_selected_choice", "").strip()
        if not user_answer:
            if hasattr(self, "ai_cloze_feedback_label"):
                self.ai_cloze_feedback_label.config(text="請先選擇答案", fg="#A14A2A")
            return

        correct_answer = self.ai_cloze_current.get("answer", "")
        source_item = self.ai_cloze_current.get("_source_item", {})
        word = str(source_item.get("單字", correct_answer)).strip()

        is_correct_local = (
            user_answer.strip() == correct_answer.strip()
            or user_answer.strip() == word
        )

        self.exam_total += 1
        if is_correct_local:
            self.exam_score += 1

        self.update_exam_score_label()
        self.exam_answer_shown = True
        self._record_exam_history(word, is_correct_local, "ai_cloze", source_item)

        if is_correct_local:
            if hasattr(self, "ai_cloze_feedback_label"):
                self.ai_cloze_feedback_label.config(text="答對了！", fg="#2E7D32")
            if hasattr(self, "ai_cloze_save_btn"):
                self.ai_cloze_save_btn.pack(side=tk.LEFT, padx=8)
        else:
            if hasattr(self, "ai_cloze_feedback_label"):
                self.ai_cloze_feedback_label.config(
                    text=f"答錯了。你的答案：{user_answer}", fg="#A14A2A"
                )

        sentence_full = self.ai_cloze_current.get("sentence_full", "")
        if hasattr(self, "ai_cloze_answer_reveal_label"):
            self.ai_cloze_answer_reveal_label.config(
                text=f"正確答案：{correct_answer}\n完整句子：{sentence_full}"
            )

        for btn in self.ai_cloze_choice_buttons:
            opt = getattr(btn, "option_value", "")
            if opt == correct_answer:
                btn.config(bg="#C8E6C9", fg="#1B5E20")  # Green for correct
            elif opt == user_answer and not is_correct_local:
                btn.config(bg="#FFCCBC", fg="#BF360C")  # Red for wrong

    def save_ai_cloze_sentence(self):
        if not self.ai_cloze_current:
            return
        sentence_full = self.ai_cloze_current.get("sentence_full", "")
        if sentence_full:
            self.window.clipboard_clear()
            self.window.clipboard_append(sentence_full)
            messagebox.showinfo("已複製", "情境句子已複製到剪貼簿！您可以到主畫面的『查詢 / 新增』新增它！")

    def reveal_ai_cloze_answer(self):
        if not self.ai_cloze_current:
            return

        correct_answer = self.ai_cloze_current.get("answer", "")
        sentence_full = self.ai_cloze_current.get("sentence_full", "")
        self.exam_answer_shown = True
        
        for btn in self.ai_cloze_choice_buttons:
            if getattr(btn, "option_value", "") == correct_answer:
                btn.config(bg="#C8E6C9", fg="#1B5E20")
                
        if hasattr(self, "ai_cloze_feedback_label"):
            self.ai_cloze_feedback_label.config(text="答案已顯示，這題不計分", fg="#8B5E3C")
        if hasattr(self, "ai_cloze_answer_reveal_label"):
            self.ai_cloze_answer_reveal_label.config(
                text=f"正確答案：{correct_answer}\n完整句子：{sentence_full}"
            )

    # =========================================================
    # AI 翻譯微調與評分
    # =========================================================

    def generate_ai_translation(self, item):
        if getattr(self, "ai_translation_loading", False):
            return
        self.ai_translation_loading = True
        self.ai_translation_current = None
        
        if hasattr(self, "ai_translation_prompt"):
            self.ai_translation_prompt.config(text="AI 正在生成日文情境句，請稍候…")
        if hasattr(self, "ai_translation_feedback"):
            self.ai_translation_feedback.config(text="")
        if hasattr(self, "ai_translation_entry"):
            self.ai_translation_entry.delete(0, tk.END)
            self.ai_translation_entry.config(state="normal")
            
        word = str(item.get("單字", "")).strip()

        def worker():
            try:
                from ai_service import generate_translation_question
                result = generate_translation_question(word, lang=self.get_exam_language())
            except Exception as e:
                result = {}
                print(f"[dictionary_home] AI 翻譯題目生成失敗：{e}")
            self.window.after(0, lambda: self._apply_ai_translation_result(item, result))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_ai_translation_result(self, item, result):
        self.ai_translation_loading = False
        if not result:
            if hasattr(self, "ai_translation_prompt"):
                self.ai_translation_prompt.config(text="AI 生成失敗，請確認 API Key")
            return

        self.ai_translation_current = result
        self.ai_translation_current["_source_item"] = item
        self.exam_answer_shown = False
        
        jp_sentence = result.get("japanese_sentence", "")
        if hasattr(self, "ai_translation_prompt"):
            self.ai_translation_prompt.config(text=jp_sentence)
        if hasattr(self, "ai_translation_entry"):
            self.ai_translation_entry.focus_set()

    def submit_ai_translation(self, event=None):
        if not hasattr(self, "ai_translation_current") or not self.ai_translation_current:
            return
        if self.exam_answer_shown:
            self.next_exam_question()
            return
            
        user_answer = self.ai_translation_entry.get().strip()
        if not user_answer:
            self.ai_translation_feedback.config(text="請輸入您的中文翻譯再送出", fg="#A14A2A")
            return
            
        self.exam_answer_shown = True
        self.ai_translation_entry.config(state="disabled")
        self.ai_translation_feedback.config(text="AI 正在為您的翻譯評分中...", fg="#8B5E3C")
        
        jp_sentence = self.ai_translation_current.get("japanese_sentence", "")
        ref_translation = self.ai_translation_current.get("reference_translation", "")
        
        def worker():
            try:
                from ai_service import evaluate_translation
                res = evaluate_translation(jp_sentence, ref_translation, user_answer, lang=self.get_exam_language())
            except Exception:
                res = {"score": 0, "feedback": "評分失敗"}
            self.window.after(0, lambda: self._show_ai_translation_feedback(res, ref_translation))
            
        threading.Thread(target=worker, daemon=True).start()
        
    def _show_ai_translation_feedback(self, res, ref_translation):
        score = res.get("score", 0)
        feedback = res.get("feedback", "")
        self.exam_total += 1
        if score >= 6:
            self.exam_score += 1
        self.update_exam_score_label()
        
        color = "#2E7D32" if score >= 8 else ("#A07020" if score >= 5 else "#A14A2A")
        text = f"評分：{score}/10\n參考翻譯：{ref_translation}\n老師講評：{feedback}"
        self.ai_translation_feedback.config(text=text, fg=color)

    # =========================================================
    # AI 換句話說 / 語意重構
    # =========================================================

    def generate_ai_paraphrase(self, item):
        if getattr(self, "ai_paraphrase_loading", False):
            return
        self.ai_paraphrase_loading = True
        self.ai_paraphrase_current = None
        
        if hasattr(self, "ai_paraphrase_prompt"):
            self.ai_paraphrase_prompt.config(text="AI 正在設計語意重構情境，請稍候…")
        if hasattr(self, "ai_paraphrase_feedback"):
            self.ai_paraphrase_feedback.config(text="")
        if hasattr(self, "ai_paraphrase_entry"):
            self.ai_paraphrase_entry.delete(0, tk.END)
            self.ai_paraphrase_entry.config(state="normal")
            
        word = str(item.get("單字", "")).strip()

        def worker():
            try:
                from ai_service import generate_paraphrasing_question
                result = generate_paraphrasing_question(word, lang=self.get_exam_language())
            except Exception as e:
                result = {}
                print(f"[dictionary_home] AI 語意重構題目生成失敗：{e}")
            self.window.after(0, lambda: self._apply_ai_paraphrase_result(item, result))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_ai_paraphrase_result(self, item, result):
        self.ai_paraphrase_loading = False
        if not result:
            if hasattr(self, "ai_paraphrase_prompt"):
                self.ai_paraphrase_prompt.config(text="AI 生成失敗，請確認 API Key")
            return

        self.ai_paraphrase_current = result
        self.ai_paraphrase_current["_source_item"] = item
        self.exam_answer_shown = False
        
        simple = result.get("simple_sentence", "")
        meaning = result.get("simple_meaning", "")
        target = result.get("target_word", "")
        
        prompt_text = (
            f"原句：{simple}\n"
            f"意思：{meaning}\n"
            f"👉 請使用這個單字重構：【 {target} 】"
        )
        
        if hasattr(self, "ai_paraphrase_prompt"):
            self.ai_paraphrase_prompt.config(text=prompt_text)
        if hasattr(self, "ai_paraphrase_entry"):
            self.ai_paraphrase_entry.focus_set()

    def submit_ai_paraphrase(self, event=None):
        if not hasattr(self, "ai_paraphrase_current") or not self.ai_paraphrase_current:
            return
        if self.exam_answer_shown:
            self.next_exam_question()
            return
            
        user_answer = self.ai_paraphrase_entry.get().strip()
        if not user_answer:
            self.ai_paraphrase_feedback.config(text="請輸入您造的句子", fg="#A14A2A")
            return
            
        self.exam_answer_shown = True
        self.ai_paraphrase_entry.config(state="disabled")
        self.ai_paraphrase_feedback.config(text="AI 正在審閱您的句子...", fg="#8B5E3C")
        
        simple_sentence = self.ai_paraphrase_current.get("simple_sentence", "")
        target_word = self.ai_paraphrase_current.get("target_word", "")
        ref_answer = self.ai_paraphrase_current.get("reference_answer", "")
        
        def worker():
            try:
                from ai_service import evaluate_paraphrasing
                res = evaluate_paraphrasing(simple_sentence, target_word, user_answer, lang=self.get_exam_language())
            except Exception:
                res = {"is_correct": False, "feedback": "評分失敗"}
            self.window.after(0, lambda: self._show_ai_paraphrase_feedback(res, ref_answer))
            
        threading.Thread(target=worker, daemon=True).start()
        
    def _show_ai_paraphrase_feedback(self, res, ref_answer):
        is_correct = res.get("is_correct", False)
        feedback = res.get("feedback", "")
        
        self.exam_total += 1
        if is_correct:
            self.exam_score += 1
        self.update_exam_score_label()
        
        color = "#2E7D32" if is_correct else "#A14A2A"
        text = f"結果：{'成功' if is_correct else '需改進'}\n標準改寫參考：{ref_answer}\n老師講評：{feedback}"
        self.ai_paraphrase_feedback.config(text=text, fg=color)

    # =========================================================
    # 錯題本
    # =========================================================

    def show_wrong_log(self):
        # 計算安全的對話框位置（不超出螢幕，且有安全邊距）
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        dw, dh = 680, 560
        dx = max(40, (sw - dw) // 2)
        dy = max(40, (sh - dh) // 2)

        dialog = tk.Toplevel(self.window)
        dialog.title("📔 錯題本")
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dialog.minsize(500, 400)
        dialog.configure(bg="#F5EAD9")
        dialog.transient(self.window)
        dialog.grab_set()

        # 標題區
        header = tk.Frame(dialog, bg="#E7D6BE")
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="📔 錯題本",
            font=("Microsoft JhengHei", 18, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=16,
            padx=20,
            anchor="w"
        ).pack(fill=tk.X)

        count_text = f"共記錄了 {len(self.exam_wrong_log)} 個錯題" if self.exam_wrong_log else "目前還沒有錯題記錄，繼續加油！"
        tk.Label(
            dialog,
            text=count_text,
            font=("Microsoft JhengHei", 11),
            bg="#F5EAD9",
            fg="#6A4A35"
        ).pack(pady=(12, 8))

        # 底部按鈕（先 pack 確保不被擠出）
        btn_row = tk.Frame(dialog, bg="#F5EAD9")
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(8, 20))

        def clear_wrong_log():
            self.exam_wrong_log.clear()
            dialog.destroy()
            messagebox.showinfo("錯題本", "錯題記錄已清除", parent=self.window)

        self.create_soft_button(btn_row, "🗑 清除錯題", clear_wrong_log, width=10).pack(side=tk.LEFT)
        self.create_soft_button(btn_row, "關閉", dialog.destroy, width=10).pack(side=tk.RIGHT)

        # 表格區（中間可展開）
        frame = tk.Frame(dialog, bg="#F5EAD9")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 0))

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        columns = ("單字", "詞性", "分類", "答錯次數", "時間")
        tree = ttk.Treeview(frame, columns=columns, show="headings", yscrollcommand=scrollbar.set)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor="w", minwidth=60)
        tree.column("單字", width=130, minwidth=80)
        tree.column("時間", width=150, minwidth=100)

        for record in self.exam_wrong_log:
            tree.insert("", tk.END, values=(
                record.get("word", ""),
                record.get("pos", ""),
                record.get("tag", ""),
                record.get("count", 1),
                record.get("timestamp", "")[:16]
            ))

        tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)

    # =========================================================
    # 學習報告（matplotlib 視覺化）
    # =========================================================

    def show_learning_report(self):
        if not self.exam_history:
            messagebox.showinfo("學習報告", "目前還沒有答題記錄，請先作答幾題再查看。", parent=self.window)
            return

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
            from io import BytesIO
        except ImportError:
            messagebox.showerror("錯誤", "需要安裝 matplotlib\n請執行：pip install matplotlib", parent=self.window)
            return

        # 嘗試使用系統中文字型
        chinese_font = None
        for font_name in ["Microsoft JhengHei", "Microsoft YaHei", "SimHei"]:
            try:
                prop = fm.FontProperties(family=font_name)
                chinese_font = prop
                plt.rcParams["font.family"] = font_name
                break
            except Exception:
                pass

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.patch.set_facecolor("#F5EAD9")

        title_kw = {"fontproperties": chinese_font} if chinese_font else {}
        fig.suptitle("學習報告", fontsize=16, color="#4A2F21", **title_kw)

        # 圖1：正確率趨勢
        ax1 = axes[0]
        ax1.set_facecolor("#EADCC8")
        correct_list = [1 if r["correct"] else 0 for r in self.exam_history]
        window_size = min(5, len(correct_list))
        if len(correct_list) >= window_size and window_size > 1:
            moving_avg = []
            for i in range(len(correct_list) - window_size + 1):
                avg = sum(correct_list[i:i + window_size]) / window_size * 100
                moving_avg.append(avg)
            ax1.plot(range(window_size, len(correct_list) + 1), moving_avg,
                     color="#8B5E3C", linewidth=2, marker="o", markersize=4)
        else:
            ax1.plot(range(1, len(correct_list) + 1), [v * 100 for v in correct_list],
                     color="#8B5E3C", linewidth=2, marker="o", markersize=4)
        ax1.set_title("答題正確率趨勢", **title_kw, color="#4A2F21")
        ax1.set_ylabel("正確率 (%)", **title_kw, color="#6A4A35")
        ax1.set_xlabel("題目順序", **title_kw, color="#6A4A35")
        ax1.set_ylim(0, 110)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)

        # 圖2：最常出錯詞性
        ax2 = axes[1]
        ax2.set_facecolor("#EADCC8")

        # 詞性縮寫對照表
        POS_LABEL_MAP = {
            "n": "名詞", "v": "動詞", "v1": "一段動詞", "v5": "五段動詞",
            "vs": "サ變動詞", "vk": "カ變動詞", "vi": "自動詞", "vt": "他動詞",
            "adj-i": "い形容詞", "adj-na": "な形容詞", "adj-no": "の形容詞", "adj": "形容詞",
            "adv": "副詞", "prt": "助詞", "conj": "接續詞", "exp": "慣用語",
            "int": "感嘆詞", "pn": "代名詞", "pref": "前綴", "suf": "後綴",
            "aux": "助動詞", "aux-v": "助動詞", "ctr": "助數詞",
            "Noun": "名詞 (EN)", "Verb": "動詞 (EN)",
            "Adjective": "形容詞 (EN)", "Adverb": "副詞 (EN)",
            "Pronoun": "代名詞 (EN)", "Preposition": "介系詞 (EN)",
        }

        def normalize_pos_label(raw_pos: str) -> list:
            """將原始詞性字串分解並映射為友善名稱，回傳清單。"""
            if not raw_pos:
                return ["未知詞性"]
            parts = [p.strip() for p in raw_pos.replace("、", ",").replace("；", ",").replace(";", ",").split(",") if p.strip()]
            result = []
            for part in parts:
                result.append(POS_LABEL_MAP.get(part, part))
            return result if result else ["未知詞性"]

        pos_errors = {}
        for r in self.exam_history:
            if not r["correct"]:
                raw_pos = r.get("pos", "") or ""
                for label in normalize_pos_label(raw_pos):
                    pos_errors[label] = pos_errors.get(label, 0) + 1

        if pos_errors:
            pos_sorted = sorted(pos_errors.items(), key=lambda x: x[1], reverse=True)[:8]
            labels_pos = [x[0] for x in pos_sorted]
            values_pos = [x[1] for x in pos_sorted]
            ax2.barh(labels_pos, values_pos, color="#A06A43")
            ax2.set_title("最常出錯的詞性", **title_kw, color="#4A2F21")
            ax2.set_xlabel("錯誤次數", **title_kw, color="#6A4A35")
            if chinese_font:
                for lbl in ax2.get_yticklabels():
                    lbl.set_fontproperties(chinese_font)
        else:
            ax2.text(0.5, 0.5, "尚無錯題", ha="center", va="center",
                     transform=ax2.transAxes, **title_kw, color="#6A4A35")
            ax2.set_title("最常出錯的詞性", **title_kw, color="#4A2F21")
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)

        # 圖3：各標籤正確率圓餅圖
        ax3 = axes[2]
        ax3.set_facecolor("#EADCC8")
        tag_stats = {}
        for r in self.exam_history:
            tag = r.get("tag", "未分類") or "未分類"
            if tag not in tag_stats:
                tag_stats[tag] = {"correct": 0, "total": 0}
            tag_stats[tag]["total"] += 1
            if r["correct"]:
                tag_stats[tag]["correct"] += 1

        if tag_stats:
            pie_labels = []
            pie_values = []
            for tag, stat in tag_stats.items():
                acc = stat["correct"] / stat["total"] * 100 if stat["total"] else 0
                pie_labels.append(f"{tag}\n({acc:.0f}%)")
                pie_values.append(stat["total"])
            colors_pie = ["#8B5E3C", "#A06A43", "#C8860A", "#4F6F7D", "#7B5B86", "#6B7A4D"]
            text_props = {"fontproperties": chinese_font, "color": "#4A2F21"} if chinese_font else {"color": "#4A2F21"}
            ax3.pie(pie_values, labels=pie_labels, colors=colors_pie[:len(pie_values)],
                    autopct="%1.0f%%", startangle=90, textprops=text_props)
            ax3.set_title("各標籤出題分布", **title_kw, color="#4A2F21")
        else:
            ax3.text(0.5, 0.5, "尚無記錄", ha="center", va="center",
                     transform=ax3.transAxes, **title_kw, color="#6A4A35")
            ax3.set_title("各標籤出題分布", **title_kw, color="#4A2F21")

        plt.tight_layout(rect=[0, 0, 1, 0.93])

        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=96, bbox_inches="tight", facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)

        report_img = Image.open(buf)
        report_photo = ImageTk.PhotoImage(report_img)

        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        dw = min(1500, sw - 80)
        dh = min(700, sh - 120)
        dx = max(40, (sw - dw) // 2)
        dy = max(40, (sh - dh) // 2)

        dialog = tk.Toplevel(self.window)
        dialog.title("📊 學習報告")
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dialog.minsize(800, 500)
        dialog.configure(bg="#F5EAD9")
        dialog.transient(self.window)
        dialog.grab_set()

        # 標題區
        header = tk.Frame(dialog, bg="#E7D6BE")
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="📊 學習報告",
            font=("Microsoft JhengHei", 18, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=16,
            padx=20,
            anchor="w"
        ).pack(fill=tk.X)

        acc_val = round(self.exam_score / self.exam_total * 100) if self.exam_total else 0
        stats_text = (
            f"總答題：{self.exam_total} 題　 答對：{self.exam_score} 題　"
            f"正確率：{acc_val}%　 錯題數：{len(self.exam_wrong_log)} 個"
        )
        tk.Label(dialog, text=stats_text, font=("Microsoft JhengHei", 12),
                 bg="#F5EAD9", fg="#4A2F21").pack(pady=(14, 8))

        # 底部關閉按鈕（先 pack）
        self.create_soft_button(dialog, "關閉", dialog.destroy, width=10).pack(
            side=tk.BOTTOM, pady=(8, 20)
        )

        img_frame = tk.Frame(dialog, bg="#F5EAD9")
        img_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        canvas_r = tk.Canvas(img_frame, bg="#F5EAD9", highlightthickness=0)
        sb_r = tk.Scrollbar(img_frame, orient=tk.HORIZONTAL, command=canvas_r.xview)
        canvas_r.configure(xscrollcommand=sb_r.set)
        sb_r.pack(side=tk.BOTTOM, fill=tk.X)
        canvas_r.pack(fill=tk.BOTH, expand=True)

        img_label = tk.Label(canvas_r, image=report_photo, bg="#F5EAD9")
        img_label.image = report_photo
        canvas_r.create_window((0, 0), window=img_label, anchor="nw")
        canvas_r.configure(scrollregion=canvas_r.bbox("all"))

    # =========================================================
    # 單字收藏資料
    # =========================================================
    def load_dictionary_data(self):
        try:
            data = load_dictionary()

            if not isinstance(data, list):
                self.dictionary_data = []
                return

            cleaned = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                word = str(item.get("單字", "")).strip()
                if not word:
                    continue

                cleaned.append({
                    "language": str(item.get("language", "unknown")).strip() or "unknown",
                    "單字": str(item.get("單字", "")).strip(),
                    "讀音": str(item.get("讀音", "")).strip(),
                    "中文": str(item.get("中文", "")).strip(),
                    "英文": str(item.get("英文", "")).strip(),
                    "詞性": str(item.get("詞性", "")).strip(),
                    "分類": item.get("分類", []) if isinstance(item.get("分類", []), list) else [],
                    "例句": item.get("例句", []) if isinstance(item.get("例句", []), list) else [],
                    "用法": str(item.get("用法", "")).strip(),
                    "補充": str(item.get("補充", "")).strip(),
                    "圖片": str(item.get("圖片", "")).strip(),
                    "左頁分割": item.get("左頁分割", [0.18, 0.42, 0.40]) if isinstance(item.get("左頁分割", [0.18, 0.42, 0.40]), list) else [0.18, 0.42, 0.40]
                })

            self.dictionary_data = cleaned

        except Exception as e:
            print("load_dictionary_data error:", e)
            self.dictionary_data = []

    def get_all_tags(self):
        tags = set()
        has_unclassified = False

        for item in self.dictionary_data:
            item_tags = item.get("分類", [])
            if isinstance(item_tags, list) and item_tags:
                for tag in item_tags:
                    tag_text = str(tag).strip()
                    if tag_text:
                        tags.add(tag_text)
            else:
                has_unclassified = True

        if has_unclassified:
            tags.add("未分類")

        return ["全部"] + sorted(tags)

    def get_entry_sort_key(self, item):
        normalized_tags = self.get_normalized_tags(item)
        first_tag = normalized_tags[0] if normalized_tags else "未分類"

        return (
            1 if first_tag == "未分類" else 0,
            first_tag.lower(),
            str(item.get("單字", "")).lower()
        )

    def get_normalized_tags(self, item):
        tags = item.get("分類", [])
        if not isinstance(tags, list):
            tags = []

        normalized_tags = []
        seen_tags = set()
        for tag in tags:
            for tag_text in re.split(r"[,，]", str(tag)):
                tag_text = tag_text.strip()
                if tag_text and tag_text not in seen_tags:
                    normalized_tags.append(tag_text)
                    seen_tags.add(tag_text)

        if not normalized_tags:
            normalized_tags = ["未分類"]

        return normalized_tags

    def split_collection_tag_text(self, tag_raw):
        tags = []
        seen_tags = set()
        for tag in re.split(r"[,，]", str(tag_raw)):
            tag_text = tag.strip()
            if tag_text and tag_text not in seen_tags:
                tags.append(tag_text)
                seen_tags.add(tag_text)
        return tags

    def refresh_collection_tag_menu(self):
        if not hasattr(self, "collection_tag_menu"):
            return

        menu = self.collection_tag_menu["menu"]
        menu.delete(0, "end")

        tag_list = self.get_all_tags()

        for tag in tag_list:
            menu.add_command(
                label=tag,
                command=lambda value=tag: self.set_collection_tag(value)
            )

        if self.collection_tag_var.get() not in tag_list:
            self.collection_tag_var.set("全部")

    def set_collection_tag(self, value):
        self.collection_tag_var.set(value)
        self.collection_page = 1
        self.refresh_collection_list()

    def apply_collection_filters(self):
        keyword = self.collection_search_var.get().strip().lower()
        selected_tag = self.collection_tag_var.get().strip()
        selected_language = (self.selected_language or "").strip()

        result = []
        unclassified_items = []

        for item in self.dictionary_data:
            language = str(item.get("language", "unknown")).strip()
            word = str(item.get("單字", "")).strip()
            chinese = str(item.get("中文", "")).strip()
            reading = str(item.get("讀音", "")).strip()
            english = str(item.get("英文", "")).strip()

            # 入口先決定語言
            if selected_language and selected_language != "new":
                if language != selected_language:
                    continue

            normalized_tags = self.get_normalized_tags(item)

            full_text = f"{word} {chinese} {reading} {english} {' '.join(normalized_tags)}".lower()

            if keyword and keyword not in full_text:
                continue

            if selected_tag != "全部" and selected_tag not in normalized_tags:
                continue

            if normalized_tags == ["未分類"]:
                unclassified_items.append(item)
            else:
                result.append(item)

        sorted_unclassified_items = sorted(unclassified_items, key=self.get_entry_sort_key)
        sorted_result = sorted(result, key=self.get_entry_sort_key)

        if selected_tag == "未分類":
            self.collection_flat_items = sorted_unclassified_items
            self.filtered_dictionary_data = list(self.collection_flat_items)
            return

        if selected_tag == "全部":
            expanded_result = []
            for item in sorted_result:
                for tag in self.get_normalized_tags(item):
                    if tag == "未分類":
                        continue
                    display_item = dict(item)
                    display_item["_display_tag"] = tag
                    expanded_result.append(display_item)
            self.collection_flat_items = expanded_result + sorted_unclassified_items
        else:
            self.collection_flat_items = sorted_result + sorted_unclassified_items

        self.filtered_dictionary_data = list(self.collection_flat_items)

    def get_collection_total_pages(self):
        if not self.collection_pages:
            return 1
        return len(self.collection_pages)

    def get_collection_page_data(self):
        if not self.collection_pages:
            return [], None

        page_index = max(0, min(self.collection_page - 1, len(self.collection_pages) - 1))
        page_info = self.collection_pages[page_index]
        return page_info["items"], page_info["previous_tag"]

    def get_collection_item_tag(self, item):
        normalized_tags = self.get_normalized_tags(item)
        return normalized_tags[0] if normalized_tags else "未分類"

    def get_collection_display_tag(self, item, selected_tag="全部"):
        if isinstance(item, dict) and "_display_tag" in item:
            return str(item.get("_display_tag", "")).strip() or "未分類"

        if selected_tag and selected_tag != "全部":
            return selected_tag

        return self.get_collection_item_tag(item)

    def get_collection_row_budget(self):
        if not hasattr(self, "collection_tree"):
            return self.collection_page_size

        tree_height = self.collection_tree.winfo_height()
        try:
            row_height = int(ttk.Style().lookup("Treeview", "rowheight") or 20)
        except Exception:
            row_height = 20

        if row_height <= 0:
            row_height = 20

        if tree_height <= 1:
            return max(self.collection_page_size, 18)

        visible_rows = max(8, (tree_height - 8) // row_height)
        return visible_rows

    def build_collection_pages(self):
        row_budget = self.get_collection_row_budget()
        selected_tag = self.collection_tag_var.get().strip()

        if not self.collection_flat_items:
            self.collection_pages = []
            return

        pages = []
        current_items = []
        current_rows = 0
        previous_tag_global = None
        page_previous_tag = None

        for item in self.collection_flat_items:
            item_tag = self.get_collection_display_tag(item, selected_tag)
            header_needed = previous_tag_global != item_tag
            needed_rows = 1 + (1 if header_needed else 0)

            if current_items and current_rows + needed_rows > row_budget:
                pages.append({
                    "items": current_items,
                    "previous_tag": page_previous_tag
                })
                current_items = []
                current_rows = 0
                page_previous_tag = previous_tag_global

            if not current_items:
                page_previous_tag = previous_tag_global

            current_items.append(item)
            current_rows += needed_rows
            previous_tag_global = item_tag

        if current_items:
            pages.append({
                "items": current_items,
                "previous_tag": page_previous_tag
            })

        self.collection_pages = pages

    def on_collection_tree_resized(self, event=None):
        if not hasattr(self, "collection_tree"):
            return

        new_budget = self.get_collection_row_budget()
        if new_budget == self.collection_page_size:
            return

        self.collection_page_size = new_budget

        if self.collection_resize_refresh_job is not None:
            try:
                self.window.after_cancel(self.collection_resize_refresh_job)
            except Exception:
                pass

        self.collection_resize_refresh_job = self.window.after(80, self.refresh_collection_list)

    def on_collection_search_changed(self, event=None):
        self.collection_page = 1
        self.refresh_collection_list()

    def prev_collection_page(self):
        if self.collection_page > 1:
            self.collection_page -= 1
            self.refresh_collection_list()

    def next_collection_page(self):
        total_pages = self.get_collection_total_pages()
        if self.collection_page < total_pages:
            self.collection_page += 1
            self.refresh_collection_list()

    def build_collection_tree(self, page_data, previous_tag=None):
        if not hasattr(self, "collection_tree"):
            return

        self.collection_tree.delete(*self.collection_tree.get_children())
        self.tree_item_to_entry = {}

        selected_tag = self.collection_tag_var.get().strip()
        if selected_tag == "未分類":
            unclassified_node = ""
            if previous_tag != "未分類":
                unclassified_node = self.collection_tree.insert(
                    "",
                    "end",
                    text="未分類",
                    open=True
                )

            for item in page_data:
                word = str(item.get("單字", "")).strip()
                reading = str(item.get("讀音", "")).strip()
                chinese = str(item.get("中文", "")).strip()

                if reading:
                    display_text = f"{word} ({reading})"
                elif chinese:
                    display_text = f"{word} - {chinese}"
                else:
                    display_text = word

                item_id = self.collection_tree.insert(
                    unclassified_node,
                    "end",
                    text=display_text,
                    open=False
                )

                self.tree_item_to_entry[item_id] = item

            return

        category_nodes = {}

        for item in page_data:
            first_tag = self.get_collection_display_tag(item, selected_tag)

            if first_tag not in category_nodes:
                if previous_tag == first_tag and not category_nodes:
                    category_nodes[first_tag] = ""
                else:
                    category_nodes[first_tag] = self.collection_tree.insert(
                        "",
                        "end",
                        text=first_tag,
                        open=True
                    )

            parent_category_id = category_nodes[first_tag]

            word = str(item.get("單字", "")).strip()
            reading = str(item.get("讀音", "")).strip()
            chinese = str(item.get("中文", "")).strip()

            if reading:
                display_text = f"{word} ({reading})"
            elif chinese:
                display_text = f"{word} - {chinese}"
            else:
                display_text = word

            item_id = self.collection_tree.insert(
                parent_category_id,
                "end",
                text=display_text,
                open=False
            )

            self.tree_item_to_entry[item_id] = item

    def refresh_collection_list(self):
        if not hasattr(self, "collection_tree"):
            return

        self.load_dictionary_data()
        self.refresh_collection_tag_menu()
        self.apply_collection_filters()
        self.build_collection_pages()

        total_pages = self.get_collection_total_pages()
        if self.collection_page > total_pages:
            self.collection_page = total_pages

        page_data, previous_tag = self.get_collection_page_data()

        print("dictionary_data =", len(self.dictionary_data))
        print("filtered_dictionary_data =", len(self.filtered_dictionary_data))
        print("page_data =", len(page_data))

        self.build_collection_tree(page_data, previous_tag)

        self.collection_page_label.config(
            text=f"第 {self.collection_page} 頁 / 共 {total_pages} 頁"
        )

    def refresh_collection_list_select_entry(self, entry):
        entry_key = self.get_collection_entry_key(entry)
        if not entry_key[0]:
            self.refresh_collection_list()
            return

        self.refresh_collection_list()

        for item_id, item in self.tree_item_to_entry.items():
            if self.get_collection_entry_key(item) != entry_key:
                continue

            self.collection_tree.selection_set(item_id)
            self.collection_tree.focus(item_id)
            self.collection_tree.see(item_id)
            break

    def on_select_collection_word(self, event=None):
        if not hasattr(self, "collection_tree"):
            return

        selection = self.collection_tree.selection()
        if not selection:
            return

        selected_id = self.get_first_selected_collection_entry_id(selection)
        if not selected_id:
            return

        selected_entry = self.tree_item_to_entry[selected_id]
        if (
            self.current_entry is not None
            and self.get_collection_entry_key(selected_entry) == self.get_collection_entry_key(self.current_entry)
        ):
            return

        if not self.confirm_collection_unsaved_change():
            self.restore_current_collection_tree_selection()
            return

        self.current_entry = selected_entry
        self.show_collection_detail(self.current_entry)

    def confirm_collection_unsaved_change(self):
        if not self.collection_has_unsaved_changes or self.current_entry is None:
            return True

        answer = messagebox.askyesnocancel(
            "尚未保存",
            "目前單字內容尚未保存，要先保存再切換嗎？",
            parent=self.window
        )
        if answer is None:
            return False
        if answer:
            return self.save_collection_entry(show_message=False, refresh_list=False)

        self.collection_has_unsaved_changes = False
        return True

    def restore_current_collection_tree_selection(self):
        if self.current_entry is None or not hasattr(self, "collection_tree"):
            return

        current_key = self.get_collection_entry_key(self.current_entry)
        for item_id, item in self.tree_item_to_entry.items():
            if self.get_collection_entry_key(item) != current_key:
                continue

            self.collection_tree.selection_set(item_id)
            self.collection_tree.focus(item_id)
            self.collection_tree.see(item_id)
            break

    def get_first_selected_collection_entry_id(self, selection=None):
        if selection is None:
            selection = self.collection_tree.selection()

        for item_id in selection:
            if item_id in self.tree_item_to_entry:
                return item_id
        return ""

    def get_selected_collection_entries(self):
        if not hasattr(self, "collection_tree"):
            return []

        entries = []
        seen = set()
        for item_id in self.collection_tree.selection():
            item = self.tree_item_to_entry.get(item_id)
            if not item:
                continue

            key = (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            if not key[0] or key in seen:
                continue

            seen.add(key)
            entries.append(item)

        return entries

    def get_existing_dictionary_language_options(self):
        options = [
            ("ja", "日文"),
            ("zh", "中文"),
            ("en", "英文"),
            ("ko", "韓文")
        ]
        return [(code, label) for code, label in options if code != "new"]

    def get_existing_collection_tag_options(self):
        selected_language = (self.selected_language or "").strip()
        tags = []
        seen = set()

        for item in self.dictionary_data:
            language = str(item.get("language", "")).strip()
            if selected_language and selected_language != "new" and language != selected_language:
                continue

            for tag in self.get_normalized_tags(item):
                if tag == "未分類" or tag in seen:
                    continue
                tags.append(tag)
                seen.add(tag)

        return sorted(tags)

    def show_collection_tree_context_menu(self, event):
        if not hasattr(self, "collection_tree"):
            return "break"

        clicked_id = self.collection_tree.identify_row(event.y)
        if not clicked_id or clicked_id not in self.tree_item_to_entry:
            return "break"

        if clicked_id not in self.collection_tree.selection():
            self.collection_tree.selection_set(clicked_id)
            self.collection_tree.focus(clicked_id)

        menu = tk.Menu(self.window, tearoff=0)
        menu.add_command(label="刪除選取單字", command=self.delete_selected_collection_words)

        tag_menu = tk.Menu(menu, tearoff=0)
        tag_options = self.get_existing_collection_tag_options()
        if tag_options:
            for tag in tag_options:
                tag_menu.add_command(
                    label=tag,
                    command=lambda value=tag: self.add_tag_to_selected_collection_words(value)
                )
        else:
            tag_menu.add_command(label="目前沒有分類", state=tk.DISABLED)
        menu.add_cascade(label="加入分類", menu=tag_menu)

        language_menu = tk.Menu(menu, tearoff=0)
        for code, label in self.get_existing_dictionary_language_options():
            language_menu.add_command(
                label=label,
                command=lambda value=code: self.change_selected_collection_words_language(value)
            )
        menu.add_cascade(label="切換語言", menu=language_menu)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

        return "break"

    def show_collection_detail(self, item):
        if not hasattr(self, "collection_original_text"):
            return

        self.cancel_collection_enrich_refresh()
        self.cancel_collection_autosave()
        self.collection_detail_loading = True

        self.collection_original_text.delete("1.0", tk.END)
        self.collection_note_text.delete("1.0", tk.END)
        self.collection_translation_text.delete("1.0", tk.END)
        self.collection_english_text.delete("1.0", tk.END)
        self.collection_reading_entry.delete(0, tk.END)
        self.collection_pos_entry.delete(0, tk.END)
        self.collection_tag_entry.delete(0, tk.END)
        self.collection_example_text.delete("1.0", tk.END)
        self.collection_usage_text.delete("1.0", tk.END)

        self.collection_original_text.insert("1.0", item.get("單字", ""))
        self.collection_note_text.insert("1.0", item.get("補充", ""))
        self.collection_translation_text.insert("1.0", item.get("中文", ""))
        self.collection_english_text.insert("1.0", item.get("英文", ""))
        self.collection_reading_entry.insert(0, item.get("讀音", ""))
        self.collection_pos_entry.insert(0, item.get("詞性", ""))

        tags = item.get("分類", [])
        if isinstance(tags, list):
            self.collection_tag_entry.insert(0, ", ".join(self.get_normalized_tags(item)))

        examples = item.get("例句", [])
        if isinstance(examples, list):
            self.collection_example_text.insert("1.0", "\n".join(examples))

        self.collection_usage_text.insert("1.0", item.get("用法", ""))
        self.show_collection_image(item.get("圖片", ""))
        self.schedule_apply_collection_split(item.get("左頁分割", [0.18, 0.32, 0.50]))
        self.collection_detail_loading = False
        self.collection_has_unsaved_changes = False
        self.schedule_collection_enrichment_if_needed(item)

    def show_empty_collection_detail(self):
        if not hasattr(self, "collection_original_text"):
            return

        self.cancel_collection_enrich_refresh()
        self.cancel_collection_autosave()
        self.collection_detail_loading = True

        self.collection_original_text.delete("1.0", tk.END)
        self.collection_note_text.delete("1.0", tk.END)
        self.collection_translation_text.delete("1.0", tk.END)
        self.collection_english_text.delete("1.0", tk.END)
        self.collection_reading_entry.delete(0, tk.END)
        self.collection_pos_entry.delete(0, tk.END)
        self.collection_tag_entry.delete(0, tk.END)
        self.collection_example_text.delete("1.0", tk.END)
        self.collection_usage_text.delete("1.0", tk.END)

        self.collection_original_text.insert("1.0", "")
        self.collection_note_text.insert("1.0", "")
        self.collection_translation_text.insert("1.0", "")
        self.collection_english_text.insert("1.0", "")
        self.clear_collection_image()
        self.schedule_apply_collection_split([0.18, 0.32, 0.50])
        self.collection_detail_loading = False
        self.collection_has_unsaved_changes = False

    def collection_entry_needs_enrichment(self, item):
        if str(item.get("language", "")).strip() != "ja":
            return False

        return not (
            str(item.get("讀音", "")).strip()
            and str(item.get("英文", "")).strip()
            and str(item.get("詞性", "")).strip()
        )

    def schedule_collection_enrichment_if_needed(self, item):
        if self.collection_detail_loading or self.collection_has_unsaved_changes:
            return
        if not self.collection_entry_needs_enrichment(item):
            return

        word = str(item.get("單字", "")).strip()
        language = str(item.get("language", "")).strip()
        if not word:
            return

        try:
            enrich_word_data_async(word)
        except Exception:
            return

        self.collection_enrich_refresh_job = self.window.after(
            1600,
            lambda word=word, language=language: self.refresh_enriched_collection_entry(word, language, attempts_left=5)
        )

    def refresh_enriched_collection_entry(self, word, language, attempts_left):
        self.collection_enrich_refresh_job = None

        if self.current_entry is None:
            return
        if self.collection_has_unsaved_changes or self.collection_detail_loading:
            return
        if self.get_collection_entry_key(self.current_entry) != (word, language):
            return

        data = load_dictionary()
        refreshed_item = None
        for item in data:
            if self.get_collection_entry_key(item) == (word, language):
                refreshed_item = item
                break

        if refreshed_item is None:
            return

        if not self.collection_entry_needs_enrichment(refreshed_item):
            self.current_entry = refreshed_item
            self.show_collection_detail(refreshed_item)
            self.refresh_collection_list_select_entry(refreshed_item)
            return

        if attempts_left > 0:
            self.collection_enrich_refresh_job = self.window.after(
                1600,
                lambda: self.refresh_enriched_collection_entry(word, language, attempts_left - 1)
            )

    def save_collection_entry(self, show_message=True, refresh_list=True):
        if self.current_entry is None:
            if show_message:
                messagebox.showwarning("提示", "請先從左邊選一個單字")
            return False

        self.cancel_collection_autosave()

        original = self.collection_original_text.get("1.0", tk.END).strip()
        note = self.collection_note_text.get("1.0", tk.END).strip()
        chinese = self.collection_translation_text.get("1.0", tk.END).strip()
        english = self.collection_english_text.get("1.0", tk.END).strip()
        reading = self.collection_reading_entry.get().strip()
        pos = self.collection_pos_entry.get().strip()
        tag_raw = self.collection_tag_entry.get().strip()
        example_raw = self.collection_example_text.get("1.0", tk.END).strip()
        usage = self.collection_usage_text.get("1.0", tk.END).strip()
        image_path = self.collection_current_image_path.strip()
        split_value = self.get_current_collection_split()

        if not original:
            if show_message:
                messagebox.showwarning("提示", "單字不能空白")
            return False

        tags = self.split_collection_tag_text(tag_raw)
        examples = [x.strip() for x in example_raw.splitlines() if x.strip()]

        data = load_dictionary()

        target_index = None
        for i, item in enumerate(data):
            if item.get("單字", "") == self.current_entry.get("單字", ""):
                target_index = i
                break

        if target_index is None:
            if show_message:
                messagebox.showerror("錯誤", "找不到要儲存的單字")
            return False

        data[target_index]["單字"] = original
        data[target_index]["中文"] = chinese
        data[target_index]["英文"] = english
        data[target_index]["讀音"] = reading
        data[target_index]["詞性"] = pos
        data[target_index]["分類"] = tags
        data[target_index]["例句"] = examples
        data[target_index]["用法"] = usage
        data[target_index]["補充"] = note
        data[target_index]["圖片"] = image_path
        data[target_index]["左頁分割"] = split_value

        save_dictionary(data)

        self.current_entry = data[target_index]
        self.collection_has_unsaved_changes = False
        if refresh_list:
            self.refresh_collection_list_select_entry(self.current_entry)
        if show_message:
            messagebox.showinfo("成功", "已儲存單字內容")
        return True

    def reload_collection_area(self):
        self.collection_search_var.set("")
        self.collection_tag_var.set("全部")
        self.collection_page = 1
        self.current_entry = None
        self.refresh_collection_list()
        self.show_empty_collection_detail()
    
    def delete_current_word(self):
        self.delete_selected_collection_words()

    def add_tag_to_selected_collection_words(self, tag):
        tag = str(tag).strip()
        selected_entries = self.get_selected_collection_entries()
        if not tag or not selected_entries:
            messagebox.showwarning("提示", "請先選取要加入分類的單字")
            return

        selected_keys = {
            (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            for item in selected_entries
        }

        data = load_dictionary()
        changed_count = 0
        last_changed_item = None

        for item in data:
            key = (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            if key not in selected_keys:
                continue

            tags = self.get_normalized_tags(item)
            if tags == ["未分類"]:
                tags = []
            if tag in tags:
                continue

            tags.append(tag)
            item["分類"] = tags
            changed_count += 1
            last_changed_item = item

        if not changed_count:
            messagebox.showinfo("提示", "選取的單字已經有這個分類")
            return

        save_dictionary(data)
        self.current_entry = last_changed_item
        self.refresh_collection_list_select_entry(self.current_entry)
        if self.current_entry is not None:
            self.show_collection_detail(self.current_entry)
        messagebox.showinfo("成功", f"已加入分類到 {changed_count} 個單字")

    def delete_selected_collection_words(self):
        selected_entries = self.get_selected_collection_entries()
        if not selected_entries:
            messagebox.showwarning("提示", "請先選取要刪除的單字")
            return

        words = [str(item.get("單字", "")).strip() for item in selected_entries]
        if len(words) == 1:
            confirm_text = f"確定要刪除「{words[0]}」嗎？"
        else:
            confirm_text = f"確定要刪除選取的 {len(words)} 個單字嗎？"

        confirm = messagebox.askyesno("確認刪除", confirm_text)
        if not confirm:
            return

        selected_keys = {
            (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            for item in selected_entries
        }
        data = load_dictionary()
        new_data = []
        deleted_count = 0

        for item in data:
            key = (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            if key in selected_keys:
                deleted_count += 1
                continue
            new_data.append(item)

        if deleted_count:
            save_dictionary(new_data)
            self.current_entry = None
            self.refresh_collection_list()
            self.show_empty_collection_detail()
            messagebox.showinfo("成功", f"已刪除 {deleted_count} 個單字")
        else:
            messagebox.showerror("錯誤", "找不到要刪除的單字")

    def change_current_word_language(self):
        selected_entries = self.get_selected_collection_entries()
        if not selected_entries and self.current_entry is not None:
            selected_entries = [self.current_entry]

        if not selected_entries:
            messagebox.showwarning("提示", "請先選取要切換語言的單字")
            return

        self.change_selected_collection_words_language_menu(selected_entries)

    def change_selected_collection_words_language_menu(self, selected_entries):
        menu = tk.Menu(self.window, tearoff=0)
        for code, label in self.get_existing_dictionary_language_options():
            menu.add_command(
                label=label,
                command=lambda value=code: self.change_selected_collection_words_language(value, selected_entries)
            )

        try:
            x = self.window.winfo_pointerx()
            y = self.window.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def change_selected_collection_words_language(self, new_language, selected_entries=None):
        if selected_entries is None:
            selected_entries = self.get_selected_collection_entries()

        if not selected_entries:
            messagebox.showwarning("提示", "請先選取要切換語言的單字")
            return

        selected_keys = {
            (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            for item in selected_entries
        }

        data = load_dictionary()
        changed_count = 0
        last_changed_item = None

        for item in data:
            key = (
                str(item.get("單字", "")).strip(),
                str(item.get("language", "")).strip()
            )
            if key not in selected_keys:
                continue

            if str(item.get("language", "")).strip() == new_language:
                continue

            item["language"] = new_language
            changed_count += 1
            last_changed_item = item

        if not changed_count:
            messagebox.showinfo("提示", "選取的單字已經是這個語言")
            return

        save_dictionary(data)
        self.current_entry = last_changed_item
        self.refresh_collection_list()
        if self.current_entry is not None:
            self.show_collection_detail(self.current_entry)
        messagebox.showinfo("成功", f"已切換 {changed_count} 個單字")
