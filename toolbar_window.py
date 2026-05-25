import tkinter as tk
import ctypes
import pyperclip
from PIL import ImageGrab

from app_settings import load_openai_api_key, save_openai_api_key, load_google_api_key, save_google_api_key, load_settings, save_settings
from ocr_engine import OCREngine
from select_area import ScreenSelector
from result_popup import ResultPopup
from dictionary_home import DictionaryHome


class ToolbarWindow:
    def __init__(self):
        self.root = tk.Tk()

        self.root.title("Toolbar")
        self.root.geometry("320x58+260+80")
        self.root.minsize(260, 58)
        self.root.resizable(True, False)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#3A2A1F")

        self.offset_x = 0
        self.offset_y = 0

        self.ocr_engine = OCREngine()
        self.settings = load_settings()
        self.dictionary_home = None
        self.result_popup = None
        self.clipboard_monitor_enabled = True
        self.clipboard_error_count = 0
        self.last_clipboard_sequence = self.get_clipboard_sequence()

        try:
            self.last_clipboard_text = self.read_clipboard_text()
        except Exception:
            self.last_clipboard_text = ""

        self.build_ui()
        self.bind_drag()
        self.monitor_clipboard()

    def build_ui(self):
        container = tk.Frame(self.root, bg="#3A2A1F")
        container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.create_button(container, "OCR", self.run_ocr).pack(side=tk.LEFT, padx=4)
        self.create_button(container, "字典", self.open_dictionary).pack(side=tk.LEFT, padx=4)

        self.clipboard_toggle_button = self.create_button(
            container,
            "剪貼簿監聽：開",
            self.toggle_clipboard_monitor
        )
        self.clipboard_toggle_button.pack(side=tk.LEFT, padx=4)

        self.create_button(container, "設定", self.open_settings).pack(side=tk.LEFT, padx=4)

        spacer = tk.Frame(container, bg="#3A2A1F")
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.create_button(container, "X", self.root.destroy).pack(side=tk.RIGHT, padx=4)

    def create_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Microsoft JhengHei", 10, "bold"),
            bg="#8B5E3C",
            fg="#FFF8EE",
            activebackground="#A06A43",
            activeforeground="#FFF8EE",
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2"
        )

    def bind_drag(self):
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)

    def start_move(self, event):
        self.offset_x = event.x
        self.offset_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() + event.x - self.offset_x
        y = self.root.winfo_y() + event.y - self.offset_y
        self.root.geometry(f"+{x}+{y}")

    def run_ocr(self):
        selector = ScreenSelector()
        bbox = selector.get_area()

        if not bbox:
            return

        try:
            img = ImageGrab.grab(bbox=bbox)
            img.save("temp_ocr.png")

            ocr_mode = self.settings.get("ocr_mode", "gemini")

            if ocr_mode == "gemini":
                from app_settings import load_google_api_key
                google_key = load_google_api_key()
                if google_key:
                    result = self.ocr_engine.read_gemini_ocr("temp_ocr.png")
                    source_text = result.get("source_text", "").strip()
                    translated_text = result.get("translated_text", "").strip()
                    # 若 Gemini 成功辨識則顯示，否則 fallback 到 EasyOCR
                    if source_text and not translated_text.startswith("Gemini OCR 失敗"):
                        self.open_result_popup(source_text, translated_text or None)
                        return
                    elif not source_text and translated_text.startswith("Gemini OCR 失敗"):
                        print(f"[OCR] Gemini OCR 失敗，自動切換 EasyOCR：{translated_text}")
                        # fallthrough 到 EasyOCR
                    else:
                        self.open_result_popup(source_text or "Gemini OCR 沒有辨識到原文", translated_text or None)
                        return
                else:
                    print("[OCR] 未設定 Google API Key，改用 EasyOCR")

            elif ocr_mode == "gpt" and self.settings.get("gpt_ocr_enabled", False):
                result = self.ocr_engine.read_gpt_ocr("temp_ocr.png")
                source_text = result.get("source_text", "").strip()
                translated_text = result.get("translated_text", "").strip()
                if source_text or translated_text:
                    self.open_result_popup(source_text or "GPT OCR 沒有辨識到原文", translated_text)
                return

            # 預設或 fallback： EasyOCR
            text = self.ocr_engine.read("temp_ocr.png", "easyocr")
            if text.strip():
                self.open_result_popup(text)
        except Exception as e:
            print("OCR失敗：", e)

    def open_result_popup(self, source_text, initial_translation=None):
        if self.result_popup is not None:
            try:
                if self.result_popup.window.winfo_exists():
                    self.result_popup.translation_mode = self.settings.get("translation_mode", "local")
                    self.result_popup.update_content(source_text, initial_translation)
                    self.result_popup.window.lift()
                    self.result_popup.window.focus_force()
                    return
            except Exception:
                self.result_popup = None

        self.result_popup = ResultPopup(
            self.root,
            source_text,
            initial_translation=initial_translation,
            translation_mode=self.settings.get("translation_mode", "local")
        )
        self.result_popup.show()

    def read_clipboard_text(self):
        try:
            return pyperclip.paste()
        except Exception:
            pass

        try:
            return self.root.clipboard_get()
        except Exception:
            return ""

    def get_clipboard_sequence(self):
        try:
            return ctypes.windll.user32.GetClipboardSequenceNumber()
        except Exception:
            return 0

    def monitor_clipboard(self):
        if self.clipboard_monitor_enabled:
            text = self.read_clipboard_text()
            sequence = self.get_clipboard_sequence()

            if text:
                self.clipboard_error_count = 0
                clipboard_changed = (
                    text != self.last_clipboard_text
                    or (sequence and sequence != self.last_clipboard_sequence)
                )

                if text.strip() and clipboard_changed:
                    self.last_clipboard_text = text
                    self.last_clipboard_sequence = sequence
                    self.open_result_popup(text)
            else:
                self.clipboard_error_count += 1

        self.root.after(400, self.monitor_clipboard)

    def open_dictionary(self):
        self.sync_clipboard_before_dictionary()

        if self.dictionary_home is not None:
            try:
                if self.dictionary_home.window.winfo_exists():
                    self.dictionary_home.refresh_external_context()
                    self.dictionary_home.window.lift()
                    self.dictionary_home.window.focus_force()
                    return
            except Exception:
                self.dictionary_home = None

        self.dictionary_home = DictionaryHome(self)

    def sync_clipboard_before_dictionary(self):
        text = self.read_clipboard_text()
        if text.strip():
            self.last_clipboard_text = text
            self.last_clipboard_sequence = self.get_clipboard_sequence()

    def get_current_translation_context(self):
        source_text = ""
        translated_text = ""

        if self.result_popup is not None:
            try:
                if self.result_popup.window.winfo_exists():
                    if hasattr(self.result_popup, "source_textbox"):
                        source_text = self.result_popup.source_textbox.get("1.0", tk.END).strip()
                    else:
                        source_text = str(getattr(self.result_popup, "source_text", "")).strip()

                    if hasattr(self.result_popup, "translated_textbox"):
                        translated_text = self.result_popup.translated_textbox.get("1.0", tk.END).strip()
                    else:
                        translated_text = str(getattr(self.result_popup, "translated_text", "")).strip()
            except Exception:
                pass

        return {
            "source_text": source_text,
            "translated_text": translated_text
        }

    def open_settings(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dw, dh = 580, min(720, sh - 80)
        dx = max(20, (sw - dw) // 2)
        dy = max(20, (sh - dh) // 2)

        dialog = tk.Toplevel(self.root)
        dialog.title("⚙️ 系統設定")
        dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dialog.minsize(520, 560)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg="#F5EAD9")
        dialog.grid_rowconfigure(0, weight=1)
        dialog.grid_columnconfigure(0, weight=1)

        # ── 底部按鈕（先 pack 確保永遠可見）─────────────────────────────
        button_row = tk.Frame(dialog, bg="#F5EAD9")
        button_row.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(8, 20))

        def apply_settings():
            self.settings["translation_mode"] = translation_mode_var.get()
            self.settings["gpt_ocr_enabled"] = bool(gpt_ocr_var.get())
            self.settings["ai_provider"] = ai_provider_var.get()
            self.settings["ocr_mode"] = ocr_mode_var.get()
            self.settings = save_settings(self.settings)
            save_openai_api_key(api_key_var.get())
            save_google_api_key(google_api_key_var.get())
            dialog.destroy()

        def clear_api_key():
            api_key_var.set("")
            google_api_key_var.set("")
            save_openai_api_key("")
            save_google_api_key("")

        self.create_button(button_row, "儲存設定", apply_settings).pack(side=tk.RIGHT, padx=(8, 0))
        self.create_button(button_row, "取消", dialog.destroy).pack(side=tk.RIGHT)
        self.create_button(button_row, "清除 Key", clear_api_key).pack(side=tk.LEFT)

        # ── 可滾動內容區 ────────────────────────────────────────
        scroll_outer = tk.Frame(dialog, bg="#F5EAD9")
        scroll_outer.pack(fill=tk.BOTH, expand=True)

        scroll_canvas = tk.Canvas(scroll_outer, bg="#F5EAD9", highlightthickness=0)
        scroll_bar = tk.Scrollbar(scroll_outer, orient=tk.VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scroll_bar.set)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content = tk.Frame(scroll_canvas, bg="#F5EAD9")
        content_window = scroll_canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(event):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        def _on_canvas_configure(event):
            scroll_canvas.itemconfig(content_window, width=event.width)
        content.bind("<Configure>", _on_content_configure)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)
        scroll_canvas.bind("<MouseWheel>", lambda e: scroll_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        translation_mode_var = tk.StringVar(value=self.settings.get("translation_mode", "local"))
        gpt_ocr_var = tk.BooleanVar(value=self.settings.get("gpt_ocr_enabled", False))
        ai_provider_var = tk.StringVar(value=self.settings.get("ai_provider", "openai"))
        ocr_mode_var = tk.StringVar(value=self.settings.get("ocr_mode", "gemini"))
        api_key_var = tk.StringVar(value=load_openai_api_key())
        google_api_key_var = tk.StringVar(value=load_google_api_key())

        title = tk.Label(
            content,
            text="⚙️  系統設定",
            font=("Microsoft JhengHei", 18, "bold"),
            bg="#F5EAD9",
            fg="#4A2F21"
        )
        title.pack(fill=tk.X, padx=20, pady=(20, 16))

        def _make_lframe(parent, text, fg="#4A2F21"):
            return tk.LabelFrame(
                parent,
                text=f"  {text}  ",
                font=("Microsoft JhengHei", 11, "bold"),
                bg="#F5EAD9",
                fg=fg,
                padx=14,
                pady=12,
                relief="groove"
            )

        def _make_radio(parent, text, var, value):
            return tk.Radiobutton(
                parent,
                text=text,
                variable=var,
                value=value,
                bg="#F5EAD9",
                fg="#4A2F21",
                selectcolor="#FBF6EE",
                activebackground="#F5EAD9",
                font=("Microsoft JhengHei", 11),
                highlightthickness=0
            )

        ai_provider_frame = _make_lframe(content, "AI 服務供應商（單字解析、情境克漏字）")
        ai_provider_frame.pack(fill=tk.X, padx=20, pady=(0, 14))
        _make_radio(ai_provider_frame, "OpenAI（GPT-4o 等系列）", ai_provider_var, "openai").pack(anchor="w", pady=4)
        _make_radio(ai_provider_frame, "Google（Gemini 1.5 Flash）", ai_provider_var, "google").pack(anchor="w", pady=4)

        translation_frame = _make_lframe(content, "翻譯 API（浮動視窗翻譯）")
        translation_frame.pack(fill=tk.X, padx=20, pady=(0, 14))
        _make_radio(translation_frame, "Google 翻譯（免費）", translation_mode_var, "local").pack(anchor="w", pady=4)
        _make_radio(translation_frame, "GPT 翻譯（需要 OPENAI_API_KEY）", translation_mode_var, "gpt").pack(anchor="w", pady=4)

        ocr_frame = _make_lframe(content, "OCR 辨識模式")
        ocr_frame.pack(fill=tk.X, padx=20, pady=(0, 14))
        _make_radio(
            ocr_frame,
            "🤖 Gemini OCR（優先推薦，需要 Google API Key）",
            ocr_mode_var, "gemini"
        ).pack(anchor="w", pady=4)
        _make_radio(
            ocr_frame,
            "📜 EasyOCR（離線，日文準確度較低）",
            ocr_mode_var, "easyocr"
        ).pack(anchor="w", pady=4)
        _make_radio(
            ocr_frame,
            "💰 GPT OCR（高精度，需要 OpenAI API Key）",
            ocr_mode_var, "gpt"
        ).pack(anchor="w", pady=4)
        tk.Label(
            ocr_frame,
            text="• Gemini OCR 若未設定 Google Key 則自動回倒 EasyOCR\n• GPT OCR 若未啟用或未設定 Key 則自動回倒 EasyOCR",
            font=("Microsoft JhengHei", 9),
            bg="#F5EAD9",
            fg="#6A4A35",
            anchor="w",
            justify="left",
            wraplength=460
        ).pack(fill=tk.X, pady=(6, 0))

        def _make_key_entry(parent, var):
            e = tk.Entry(
                parent,
                textvariable=var,
                show="*",
                font=("Microsoft JhengHei", 11),
                bg="#FBF6EE",
                fg="#2E1B10",
                relief="solid",
                bd=1,
                highlightthickness=2,
                highlightcolor="#8B5E3C",
                highlightbackground="#EADCC8"
            )
            e.pack(fill=tk.X, ipady=8)
            return e

        account_frame = _make_lframe(content, "OpenAI 登入（用於 OpenAI 服務）")
        account_frame.pack(fill=tk.X, padx=20, pady=(0, 14))
        _make_key_entry(account_frame, api_key_var)
        tk.Label(
            account_frame,
            text="可貼上 OpenAI API Key；若系統已有 OPENAI_API_KEY 環境變數，會優先使用。",
            font=("Microsoft JhengHei", 9),
            bg="#F5EAD9",
            fg="#6A4A35",
            anchor="w",
            justify="left",
            wraplength=480
        ).pack(fill=tk.X, pady=(8, 0))

        google_account_frame = _make_lframe(content, "Google Gemini 登入（用於 Google 服務）")
        google_account_frame.pack(fill=tk.X, padx=20, pady=(0, 20))
        _make_key_entry(google_account_frame, google_api_key_var)
        tk.Label(
            google_account_frame,
            text="請貼上您的 Google API Key（例如：AIzaSy...）。",
            font=("Microsoft JhengHei", 9),
            bg="#F5EAD9",
            fg="#6A4A35",
            anchor="w",
            justify="left",
            wraplength=480
        ).pack(fill=tk.X, pady=(8, 0))

    def show(self):
        self.root.mainloop()

    def toggle_clipboard_monitor(self):
        self.clipboard_monitor_enabled = not self.clipboard_monitor_enabled

        if self.clipboard_monitor_enabled:
            self.clipboard_toggle_button.config(text="剪貼簿監聽：開")
            print("剪貼簿監聽已開啟")
        else:
            self.clipboard_toggle_button.config(text="剪貼簿監聽：關")
            print("剪貼簿監聽已關閉")
