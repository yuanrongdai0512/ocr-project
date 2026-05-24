"""
game_falling_words.py
假名雨打字防禦戰 — 漢字從頂端落下，在觸底前輸入正確讀音即可消除。
"""
import tkinter as tk
from tkinter import messagebox
import random
import time


class FallingWordsGame:
    WIDTH = 820
    HEIGHT = 550
    BOTTOM_Y = 490
    LIVES = 3
    INITIAL_SPEED = 0.6      # px/frame
    SPEED_INCREMENT = 0.03   # 每消除 5 個加速
    FALL_INTERVAL = 60       # ms between frames (≈16fps)
    SPAWN_INTERVAL = 3500    # ms between new words

    BG = "#0D0B1E"
    TEXT_COLOR = "#E8E0FF"
    WORD_COLORS = ["#FF79C6", "#BD93F9", "#8BE9FD", "#50FA7B", "#FFB86C", "#FF5555"]
    HEART_COLOR = "#FF5555"
    SCORE_COLOR = "#F1FA8C"
    INPUT_BG = "#282A36"
    INPUT_FG = "#F8F8F2"
    DANGER_COLOR = "#FF5555"

    def __init__(self, parent, dictionary_data: list):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("🌧️ 假名雨打字防禦")
        self.window.configure(bg=self.BG)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 篩選有讀音的單字
        self.word_pool = [
            (str(e.get("單字", "")).strip(), str(e.get("讀音", "")).strip())
            for e in dictionary_data
            if isinstance(e, dict)
            and str(e.get("單字", "")).strip()
            and str(e.get("讀音", "")).strip()
        ]
        if len(self.word_pool) < 5:
            messagebox.showwarning("資料不足",
                                   "字典中有讀音的單字不足 5 個，請先填充單字或補上讀音！",
                                   parent=self.window)
            self.window.destroy()
            return

        self.falling = []   # list of {id, word, reading, x, y, speed, color, romaji_list}
        self.score = 0
        self.lives = self.LIVES
        self.eliminated = 0
        self.running = True
        self.speed = self.INITIAL_SPEED
        self._next_word_id = 0
        self.start_time = time.time()

        self._build_ui()
        self._schedule_spawn()
        self._game_loop()

    def _build_ui(self):
        w = self.window

        # 頂部狀態列
        top = tk.Frame(w, bg=self.BG)
        top.pack(fill=tk.X, padx=14, pady=(10, 0))

        self.score_label = tk.Label(top, text="分數：0",
                                    font=("Microsoft JhengHei", 13, "bold"),
                                    bg=self.BG, fg=self.SCORE_COLOR)
        self.score_label.pack(side=tk.LEFT)

        self.life_label = tk.Label(top, text="❤️ " * self.LIVES,
                                   font=("Microsoft JhengHei", 13),
                                   bg=self.BG, fg=self.HEART_COLOR)
        self.life_label.pack(side=tk.RIGHT)

        # Canvas
        self.canvas = tk.Canvas(w, width=self.WIDTH, height=self.HEIGHT,
                                bg=self.BG, highlightthickness=0)
        self.canvas.pack(padx=14, pady=(6, 0))

        # 底部危險線
        self.canvas.create_line(0, self.BOTTOM_Y, self.WIDTH, self.BOTTOM_Y,
                                fill="#FF5555", width=2, dash=(8, 4))

        # 輸入區
        input_frame = tk.Frame(w, bg=self.BG)
        input_frame.pack(fill=tk.X, padx=14, pady=8)

        # 輸入模式選擇
        mode_frame = tk.Frame(input_frame, bg=self.BG)
        mode_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        self.input_mode = tk.StringVar(value="kana")
        tk.Radiobutton(mode_frame, text="假名輸入", variable=self.input_mode, value="kana",
                       bg=self.BG, fg=self.TEXT_COLOR, selectcolor=self.INPUT_BG, font=("Microsoft JhengHei", 10)).pack(side=tk.TOP, anchor="w")
        tk.Radiobutton(mode_frame, text="羅馬拼音", variable=self.input_mode, value="romaji",
                       bg=self.BG, fg=self.TEXT_COLOR, selectcolor=self.INPUT_BG, font=("Microsoft JhengHei", 10)).pack(side=tk.BOTTOM, anchor="w")

        tk.Label(input_frame, text="輸入：",
                 font=("Microsoft JhengHei", 12), bg=self.BG, fg=self.TEXT_COLOR
                 ).pack(side=tk.LEFT)

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(input_frame, textvariable=self.entry_var,
                              font=("Microsoft JhengHei", 14),
                              bg=self.INPUT_BG, fg=self.INPUT_FG,
                              insertbackground=self.INPUT_FG,
                              relief="flat", bd=0, width=20)
        self.entry.pack(side=tk.LEFT, ipady=5, padx=(4, 8))
        self.entry.focus_set()
        self.entry.bind("<Return>", self._on_submit)

        submit_btn = tk.Button(input_frame, text="送出 (Enter)",
                               font=("Microsoft JhengHei", 12, "bold"),
                               bg="#BD93F9", fg=self.BG,
                               activebackground="#FF79C6", activeforeground=self.BG,
                               relief="flat", cursor="hand2", padx=10, pady=2,
                               command=self._on_submit)
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.feedback_label = tk.Label(input_frame, text="",
                                       font=("Microsoft JhengHei", 11, "bold"),
                                       bg=self.BG, fg="#50FA7B")
        self.feedback_label.pack(side=tk.LEFT)

        # 初始化 pykakasi
        try:
            import pykakasi
            self.kks = pykakasi.kakasi()
        except ImportError:
            self.kks = None

    def _spawn_word(self):
        if not self.running or len(self.falling) >= 6:
            return
        word, reading = random.choice(self.word_pool)
        x = random.randint(60, self.WIDTH - 80)
        color = random.choice(self.WORD_COLORS)
        wid = self._next_word_id
        self._next_word_id += 1

        romaji = ""
        if self.kks:
            romaji = "".join([i['hepburn'] for i in self.kks.convert(reading)])

        # 根據模式決定接受的答案
        # 其實可以直接將兩者都放入 accepted，讓玩家隨時自由切換
        accepted = {reading}
        if romaji:
            accepted.add(romaji)
        accepted.add(word)

        canvas_id = self.canvas.create_text(
            x, 0,
            text=word,
            font=("Microsoft JhengHei", 18, "bold"),
            fill=color,
            tags=f"word_{wid}"
        )
        
        # 如果是羅馬音模式，可以在單字下方顯示羅馬音提示 (可選)，或維持不顯示增加難度
        hint = romaji if self.input_mode.get() == "romaji" else reading
        hint_id = self.canvas.create_text(
            x, 25,
            text=hint,
            font=("Microsoft JhengHei", 12),
            fill="#888888",
            tags=f"hint_{wid}"
        )

        self.falling.append({
            "id": wid,
            "canvas_id": canvas_id,
            "hint_id": hint_id,
            "word": word,
            "reading": reading,
            "romaji": romaji,
            "accepted": accepted,
            "x": x,
            "y": 0.0,
            "speed": self.speed,
            "color": color,
        })

    def _schedule_spawn(self):
        if not self.running:
            return
        self._spawn_word()
        interval = max(1500, self.SPAWN_INTERVAL - self.eliminated * 60)
        self.window.after(interval, self._schedule_spawn)

    def _game_loop(self):
        if not self.running:
            return
        to_remove = []
        for item in self.falling:
            item["y"] += item["speed"]
            self.canvas.coords(item["canvas_id"], item["x"], item["y"])
            self.canvas.coords(item["hint_id"], item["x"], item["y"] + 25)
            if item["y"] >= self.BOTTOM_Y:
                to_remove.append(item)

        for item in to_remove:
            self._lose_life(item)

        self.window.after(self.FALL_INTERVAL, self._game_loop)

    def _on_submit(self, event=None):
        raw_input = self.entry_var.get().strip()
        self.entry_var.set("")
        if not raw_input:
            return
            
        # 轉小寫並過濾掉所有空格，以防使用者打出 "na ka na ka"
        user_input = raw_input.lower().replace(" ", "")

        # 找出第一個符合的單字
        matched = None
        for item in self.falling:
            if user_input in item["accepted"] or user_input == item["reading"]:
                matched = item
                break

        if matched:
            self._eliminate(matched)
        else:
            self.feedback_label.config(text="✗ 沒有匹配到", fg=self.DANGER_COLOR)
            self.window.after(800, lambda: self.feedback_label.config(text=""))

    def _eliminate(self, item):
        self.canvas.delete(item["canvas_id"])
        self.canvas.delete(item["hint_id"])
        # 爆炸特效（短暫閃光文字）
        flash = self.canvas.create_text(
            item["x"], item["y"],
            text="✨ CLEAR!",
            font=("Microsoft JhengHei", 16, "bold"),
            fill="#FFD700"
        )
        self.window.after(500, lambda: self.canvas.delete(flash))

        self.falling.remove(item)
        self.score += 10
        self.eliminated += 1
        self.score_label.config(text=f"分數：{self.score}")
        self.feedback_label.config(text=f"✔ {item['word']}（{item['reading']}）", fg="#50FA7B")
        self.window.after(1200, lambda: self.feedback_label.config(text=""))

        # 難度提升
        if self.eliminated % 5 == 0:
            self.speed += self.SPEED_INCREMENT
            for f in self.falling:
                f["speed"] = self.speed

    def _lose_life(self, item):
        self.canvas.delete(item["canvas_id"])
        self.canvas.delete(item["hint_id"])
        if item in self.falling:
            self.falling.remove(item)
        self.lives -= 1
        hearts = "❤️ " * self.lives + "🖤 " * (self.LIVES - self.lives)
        self.life_label.config(text=hearts)

        # 畫面紅色閃爍
        self.canvas.config(bg="#3D0000")
        self.window.after(300, lambda: self.canvas.config(bg=self.BG))

        if self.lives <= 0:
            self._game_over()

    def _game_over(self):
        self.running = False
        elapsed = int(time.time() - self.start_time)
        m, s = divmod(elapsed, 60)
        for item in self.falling:
            self.canvas.delete(item["canvas_id"])
            self.canvas.delete(item["hint_id"])
        self.falling.clear()

        result = messagebox.askyesno(
            "遊戲結束",
            f"💀 Game Over！\n\n最終分數：{self.score}\n消除單字：{self.eliminated} 個\n耗時：{m:02d}:{s:02d}\n\n要再玩一次嗎？",
            parent=self.window
        )
        if result:
            self._restart()
        else:
            self.window.destroy()

    def _restart(self):
        self.window.destroy()
        FallingWordsGame(self.parent, [
            {"單字": item["word"], "讀音": item["reading"]}
            for item in self.word_pool
            # Rebuild from stored pool
        ] if False else self._orig_data)

    def _on_close(self):
        self.running = False
        self.window.destroy()


def open_falling_words(parent, dictionary_data):
    game = FallingWordsGame(parent, dictionary_data)
    # 儲存原始資料以便重啟
    if hasattr(game, 'window') and game.window.winfo_exists():
        game._orig_data = dictionary_data
