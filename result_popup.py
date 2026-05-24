import tkinter as tk
from tkinter import messagebox, ttk
import threading

from app_settings import load_settings
from translator import translate
from dictionary_manager import add_word, add_word_fast, enrich_word_data_async, enrich_word_with_gpt_async, load_dictionary


class ResultPopup:
    def __init__(self, parent, source_text, initial_translation=None, translation_mode=None):
        self.parent = parent
        self.source_text = source_text.strip()
        self.translated_text = ""
        self.translate_job_id = 0
        self.initial_translation = initial_translation
        self.translation_mode = translation_mode or load_settings().get("translation_mode", "local")

        # 計算安全位置（置中，不超出螢幕）
        sw = self.parent.winfo_screenwidth()
        sh = self.parent.winfo_screenheight()
        ww, wh = 1040, 600
        wx = max(20, (sw - ww) // 2)
        wy = max(20, min((sh - wh) // 2, sh - wh - 40))

        self.window = tk.Toplevel(self.parent)
        self.window.title("🔍 OCR 翻譯結果")
        self.window.geometry(f"{ww}x{wh}+{wx}+{wy}")
        self.window.minsize(760, 420)
        self.window.configure(bg="#F5EAD9")
        self.window.attributes("-topmost", True)

        self.build_ui()
        self.update_content(self.source_text, self.initial_translation)

    def build_ui(self):
        self.main_frame = tk.Frame(self.window, bg="#F5EAD9")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        # ── 頁首操作列 ───────────────────────────────────────────
        self.top_bar = tk.Frame(self.main_frame, bg="#E7D6BE")
        self.top_bar.pack(fill=tk.X, pady=(0, 12))

        def _make_btn(parent, text, command, accent=False):
            return tk.Button(
                parent,
                text=text,
                command=command,
                font=("Microsoft JhengHei", 10, "bold"),
                bg="#C8860A" if accent else "#8B5E3C",
                fg="#FFF8EE",
                activebackground="#E09A15" if accent else "#A06A43",
                activeforeground="#FFF8EE",
                relief="flat",
                bd=0,
                padx=16,
                pady=9,
                cursor="hand2"
            )

        self.add_dict_button  = _make_btn(self.top_bar, "⭐ 收藏單字", self.add_current_to_dict, accent=True)
        self.add_dict_button.pack(side=tk.LEFT, padx=(10, 6), pady=8)

        self.copy_source_button = _make_btn(self.top_bar, "📋 複製原文", self.copy_source)
        self.copy_source_button.pack(side=tk.LEFT, padx=4, pady=8)

        self.copy_translated_button = _make_btn(self.top_bar, "📋 複製翻譯", self.copy_translated)
        self.copy_translated_button.pack(side=tk.LEFT, padx=4, pady=8)

        self.hide_toolbar_button = _make_btn(self.top_bar, "👁 隱藏工具列", self.hide_toolbar)
        self.hide_toolbar_button.pack(side=tk.LEFT, padx=4, pady=8)

        spacer = tk.Frame(self.top_bar, bg="#E7D6BE")
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.close_button = _make_btn(self.top_bar, "✕ 關閉", self.window.destroy)
        self.close_button.pack(side=tk.RIGHT, padx=(6, 10), pady=8)

        # ── 内容區：左原文 / 右翻譯 ────────────────────────────
        self.content_paned = ttk.Panedwindow(self.main_frame, orient=tk.HORIZONTAL)
        self.content_paned.pack(fill=tk.BOTH, expand=True)

        self.left_panel = tk.Frame(self.content_paned, bg="#E7D6BE", bd=0)
        self.content_paned.add(self.left_panel, weight=3)

        self.source_title = tk.Label(
            self.left_panel,
            text="📝  原文",
            font=("Microsoft JhengHei", 13, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            anchor="w",
            padx=14,
            pady=12
        )
        self.source_title.pack(fill=tk.X)

        self.source_textbox = tk.Text(
            self.left_panel,
            wrap=tk.WORD,
            font=("Microsoft JhengHei", 13),
            bg="#FBF6EE",
            fg="#2E1B10",
            relief="flat",
            bd=0,
            padx=14,
            pady=14,
            spacing1=4,
            spacing2=2,
            spacing3=4
        )
        self.source_textbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.right_panel = tk.Frame(self.content_paned, bg="#E7D6BE", bd=0)
        self.content_paned.add(self.right_panel, weight=2)

        self.translated_title = tk.Label(
            self.right_panel,
            text="🌐  翻譯",
            font=("Microsoft JhengHei", 13, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            anchor="w",
            padx=14,
            pady=12
        )
        self.translated_title.pack(fill=tk.X)

        self.translated_textbox = tk.Text(
            self.right_panel,
            wrap=tk.WORD,
            font=("Microsoft JhengHei", 13),
            bg="#FBF6EE",
            fg="#2E1B10",
            relief="flat",
            bd=0,
            padx=14,
            pady=14,
            spacing1=4,
            spacing2=2,
            spacing3=4
        )
        self.translated_textbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # ── 狀態列（底部，不被擠出）──────────────────────────────
        self.status_label = tk.Label(
            self.main_frame,
            text="狀態：準備完成",
            font=("Microsoft JhengHei", 10),
            bg="#E7D6BE",
            fg="#6A4A35",
            anchor="w",
            padx=14,
            pady=8
        )
        self.status_label.pack(fill=tk.X, pady=(10, 0))

    def update_content(self, new_source_text, initial_translation=None):
        self.source_text = new_source_text.strip()
        self.translated_text = ""
        self.initial_translation = initial_translation

        self.source_textbox.delete("1.0", tk.END)
        self.translated_textbox.delete("1.0", tk.END)

        self.source_textbox.insert("1.0", self.source_text)

        if not self.source_text:
            self.translated_textbox.insert("1.0", "沒有可翻譯文字")
            self.set_status("沒有可翻譯文字")
            return

        if initial_translation:
            self.translated_text = str(initial_translation).strip()
            self.translated_textbox.insert("1.0", self.translated_text)
            self.set_status("翻譯完成")
            return

        self.translated_textbox.insert("1.0", "翻譯中，請稍候...")
        self.start_translate_async()

    def start_translate_async(self):
        self.translate_job_id += 1
        current_job_id = self.translate_job_id

        self.set_status("正在翻譯...")

        thread = threading.Thread(
            target=self._translate_worker,
            args=(self.source_text, current_job_id),
            daemon=True
        )
        thread.start()

    def _translate_worker(self, text, job_id):
        try:
            result = translate(text, self.translation_mode)
        except Exception as e:
            result = f"翻譯失敗：{e}"

        self.window.after(0, lambda: self._apply_translation_result(job_id, result))

    def _apply_translation_result(self, job_id, result):
        if not self.window.winfo_exists():
            return

        if job_id != self.translate_job_id:
            return

        self.translated_text = result if result else "翻譯結果為空"

        self.translated_textbox.delete("1.0", tk.END)
        self.translated_textbox.insert("1.0", self.translated_text)
        self.set_status("翻譯完成")
        
    def add_current_to_dict(self):
        """點選⭐收藏單字，彈出標籤選擇 Dialog。"""
        try:
            try:
                selected_text = self.source_textbox.get("sel.first", "sel.last").strip()
            except Exception:
                selected_text = ""

            word = selected_text if selected_text else self.source_text

            if not word.strip():
                messagebox.showwarning("提示", "沒有可收藏的文字", parent=self.window)
                return

            self._show_save_with_tag_dialog(word.strip())

        except Exception as e:
            messagebox.showerror("錯誤", f"收藏失敗：{e}", parent=self.window)
            self.set_status("收藏失敗")

    def _show_save_with_tag_dialog(self, word):
        """彈出標籤選擇對話框，選擇完後存入字典並觸發 GPT 補資料。"""
        # 動態計算置中位置
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        dw, dh = 460, 520
        dx = max(20, (sw - dw) // 2)
        dy = max(20, min((sh - dh) // 2, sh - dh - 40))

        dialog = tk.Toplevel(self.window)
        dialog.title("⭐ 收藏單字")
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dialog.minsize(380, 420)
        dialog.resizable(True, True)
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.configure(bg="#F5EAD9")

        # 頁首標題
        header = tk.Frame(dialog, bg="#E7D6BE")
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=f"⭐  收藏：{word}",
            font=("Microsoft JhengHei", 15, "bold"),
            bg="#E7D6BE",
            fg="#4A2F21",
            pady=14,
            padx=16,
            anchor="w"
        ).pack(fill=tk.X)

        tk.Label(
            dialog,
            text="請勾選情境標籤（可多選），或手動輸入自訂標籤",
            font=("Microsoft JhengHei", 11),
            bg="#F5EAD9",
            fg="#6A4A35"
        ).pack(pady=(12, 8))

        # 底部按鈕（先 pack，確保不被擠出）
        btn_row = tk.Frame(dialog, bg="#F5EAD9")
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(8, 20))

        def do_save():
            selected_tags = [tag for tag, var in check_vars.items() if var.get()]
            custom_raw = custom_tag_var.get().strip()
            if custom_raw:
                for part in custom_raw.replace("，", ",").split(","):
                    part = part.strip()
                    if part and part not in selected_tags:
                        selected_tags.append(part)

            result = add_word_fast(word)
            dialog.destroy()

            if result.startswith("已加入字典") or result == "已存在":
                if selected_tags:
                    try:
                        from dictionary_manager import load_dictionary, save_dictionary
                        data = load_dictionary()
                        for item in data:
                            if item.get("單字", "") == word:
                                existing = item.get("分類", [])
                                merged = list(existing)
                                for t in selected_tags:
                                    if t not in merged:
                                        merged.append(t)
                                item["分類"] = merged
                                break
                        save_dictionary(data)
                    except Exception as e:
                        print(f"更新標籤失敗：{e}")

                tag_text = "、".join(selected_tags) if selected_tags else "未分類"
                messagebox.showinfo(
                    "字典",
                    f"⭐ {result}\n標籤：{tag_text}\n背景正在補充 AI 資料…",
                    parent=self.window
                )
                self.set_status(f"已收藏：{word}")
                self.window.after(300, lambda w=word: enrich_word_data_async(w))
                self.window.after(1500, lambda w=word: enrich_word_with_gpt_async(w))
            else:
                messagebox.showinfo("字典", result, parent=self.window)
                self.set_status(f"字典：{result}")

        tk.Button(
            btn_row,
            text="⭐ 確認收藏",
            command=do_save,
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#C8860A",
            fg="#FFF8EE",
            activebackground="#E09A15",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2"
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_row,
            text="取消",
            command=dialog.destroy,
            font=("Microsoft JhengHei", 12, "bold"),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(12, 0))

        # 標籤核選區（中間，帶滾動條）
        existing_tags = set()
        try:
            data = load_dictionary()
            for item in data:
                for tag in item.get("分類", []):
                    tag_text = str(tag).strip()
                    if tag_text and tag_text != "未分類":
                        existing_tags.add(tag_text)
        except Exception:
            pass

        preset_tags = ["動漫台詞", "新詞用語", "小說文學", "商務正式", "日常對話", "考試用語"]
        all_tags = list(dict.fromkeys(preset_tags + sorted(existing_tags)))

        # 滾動容器
        tag_outer = tk.Frame(dialog, bg="#F5EAD9")
        tag_outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 8))

        tag_canvas = tk.Canvas(tag_outer, bg="#EADCC8", highlightthickness=0)
        tag_scroll = tk.Scrollbar(tag_outer, orient=tk.VERTICAL, command=tag_canvas.yview)
        tag_canvas.configure(yscrollcommand=tag_scroll.set)
        tag_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        check_frame = tk.Frame(tag_canvas, bg="#EADCC8", bd=0)
        check_canvas_window = tag_canvas.create_window((0, 0), window=check_frame, anchor="nw")

        def _on_check_frame_configure(event):
            tag_canvas.configure(scrollregion=tag_canvas.bbox("all"))
        def _on_tag_canvas_configure(event):
            tag_canvas.itemconfig(check_canvas_window, width=event.width)
        check_frame.bind("<Configure>", _on_check_frame_configure)
        tag_canvas.bind("<Configure>", _on_tag_canvas_configure)

        check_vars = {}
        for tag in all_tags:
            var = tk.BooleanVar(value=False)
            check_vars[tag] = var
            cb = tk.Checkbutton(
                check_frame,
                text=f"  {tag}",
                variable=var,
                font=("Microsoft JhengHei", 11),
                bg="#EADCC8",
                fg="#4A2F21",
                selectcolor="#FBF6EE",
                activebackground="#EADCC8",
                activeforeground="#4A2F21",
                anchor="w"
            )
            cb.pack(anchor="w", padx=10, pady=4, fill=tk.X)

        # 自訂輸入
        tk.Label(
            dialog,
            text="或輸入自訂標籤（逗號分隔）：",
            font=("Microsoft JhengHei", 11),
            bg="#F5EAD9",
            fg="#6A4A35",
            anchor="w"
        ).pack(anchor="w", padx=20, pady=(0, 4))

        custom_tag_var = tk.StringVar()
        custom_entry = tk.Entry(
            dialog,
            textvariable=custom_tag_var,
            font=("Microsoft JhengHei", 12),
            bg="#FBF6EE",
            fg="#2E1B10",
            relief="solid",
            bd=1,
            highlightthickness=2,
            highlightcolor="#8B5E3C",
            highlightbackground="#EADCC8"
        )
        custom_entry.pack(fill=tk.X, padx=20, pady=(0, 8), ipady=8)

        custom_entry.focus_set()
        dialog.bind("<Return>", lambda e: do_save())


    # def add_current_to_dict(self): 換抓部分文字
    #     try:
    #         result = add_word_fast(self.source_text)
    #
    #         if result.startswith("已加入字典"):
    #             enrich_word_data_async(self.source_text)
    #             messagebox.showinfo(
    #                 "字典",
    #                 f"{result}\n背景正在補完讀音 / 中文 / 英文 / 詞性",
    #                 parent=self.window
    #             )
    #             self.set_status("已加入字典，背景補資料中")
    #         else:
    #             messagebox.showinfo("字典", result, parent=self.window)
    #             self.set_status(f"字典：{result}")
    #
    #     except Exception as e:
    #         messagebox.showerror("錯誤", f"加入字典失敗：{e}", parent=self.window)
    #         self.set_status("加入字典失敗")

    def copy_source(self):
        text = self.source_textbox.get("1.0", tk.END).strip()
        if not text:
            return

        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        self.set_status("已複製原文")

    def copy_translated(self):
        text = self.translated_textbox.get("1.0", tk.END).strip()
        if not text:
            return

        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        self.set_status("已複製翻譯")

    def hide_toolbar(self):
        try:
            self.parent.withdraw()
            self.set_status("已隱藏工具列")
        except Exception:
            self.set_status("隱藏工具列失敗")

    def set_status(self, text):
        self.status_label.config(text=f"狀態：{text}")

    def show(self):
        self.window.lift()
        self.window.focus_force()

    def add_word_with_language(self, selected_text, language, dialog):
        result = add_word_fast(selected_text, forced_language=language)
        dialog.destroy()
        messagebox.showinfo("字典", result, parent=self.window)
        self.set_status(f"字典：{result}")

        if result.startswith("已加入字典"):
            self.window.after(500, lambda: enrich_word_data_async(selected_text))

    def ask_dictionary_language(self, selected_text):
        # 動態置中
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        dw, dh = 360, 200
        dx = max(20, (sw - dw) // 2)
        dy = max(20, (sh - dh) // 2)

        dialog = tk.Toplevel(self.window)
        dialog.title("選擇字典")
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dialog.minsize(300, 180)
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.configure(bg="#F5EAD9")

        label = tk.Label(
            dialog,
            text=f"「{selected_text}」只有漢字\n請選擇要加入哪個字典：",
            font=("Microsoft JhengHei", 12),
            bg="#F5EAD9",
            fg="#4A2F21",
            justify="center"
        )
        label.pack(pady=(24, 18))

        button_frame = tk.Frame(dialog, bg="#F5EAD9")
        button_frame.pack()

        ja_btn = tk.Button(
            button_frame,
            text="🇯🇵  日文字典",
            font=("Microsoft JhengHei", 11, "bold"),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=lambda: self.add_word_with_language(selected_text, "ja", dialog)
        )
        ja_btn.pack(side=tk.LEFT, padx=10)

        zh_btn = tk.Button(
            button_frame,
            text="🇹🇼  中文字典",
            font=("Microsoft JhengHei", 11, "bold"),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=lambda: self.add_word_with_language(selected_text, "zh", dialog)
        )
        zh_btn.pack(side=tk.LEFT, padx=10)
