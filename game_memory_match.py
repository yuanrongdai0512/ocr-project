"""
game_memory_match.py
記憶翻牌矩陣遊戲 — 使用 Tkinter 製作的配對記憶遊戲。
單字（日文）配對中文意思，玩家須找出所有配對。
"""
import tkinter as tk
from tkinter import messagebox
import random
import time


class MemoryMatchGame:
    CARD_W = 140
    CARD_H = 70
    COLS = 4
    ROWS = 3
    PAD = 12
    FLIP_DELAY = 900  # ms before flipping back

    BG = "#1E1B2E"
    CARD_BACK = "#3D3660"
    CARD_FRONT_WORD = "#5A4FCC"
    CARD_FRONT_MEAN = "#3A7ACA"
    CARD_MATCHED = "#2E7D32"
    TEXT_COLOR = "#FFFFFF"
    ACCENT = "#9C89FF"

    def __init__(self, parent, dictionary_data: list):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("🃏 記憶翻牌矩陣")
        self.window.configure(bg=self.BG)
        self.window.resizable(False, False)

        # 從字典撈有中文的詞
        unique_candidates = {}
        for e in dictionary_data:
            if isinstance(e, dict):
                w = str(e.get("單字", "")).strip()
                m = str(e.get("中文", "")).strip()
                if w and m and w not in unique_candidates:
                    unique_candidates[w] = m
        candidates = list(unique_candidates.items())
        if len(candidates) < 6:
            messagebox.showwarning("資料不足", "字典中有中文的單字不足 6 個，請先填充單字！", parent=self.window)
            self.window.destroy()
            return

        random.shuffle(candidates)
        pairs = candidates[:6]

        # 建立 12 張牌 (6 對)
        cards = []
        for ja, zh in pairs:
            cards.append({"label": ja, "pair_id": ja, "type": "word"})
            # 截短中文避免超出按鈕
            zh_short = zh[:12] + "…" if len(zh) > 12 else zh
            cards.append({"label": zh_short, "pair_id": ja, "type": "meaning"})

        random.shuffle(cards)
        self.cards = cards
        self.buttons = []
        self.flipped = []   # 目前翻開中（最多 2 張）
        self.matched_ids = set()
        self.flip_locked = False
        self.moves = 0
        self.start_time = time.time()

        self._build_ui()
        self._update_timer()

    def _build_ui(self):
        w = self.window

        title = tk.Label(w, text="🃏 記憶翻牌矩陣", font=("Microsoft JhengHei", 16, "bold"),
                         bg=self.BG, fg=self.ACCENT)
        title.pack(pady=(14, 4))

        sub = tk.Label(w, text="翻開兩張配對（日文 ↔ 中文）即可消除",
                       font=("Microsoft JhengHei", 10), bg=self.BG, fg="#AAA8CC")
        sub.pack(pady=(0, 10))

        stat_frame = tk.Frame(w, bg=self.BG)
        stat_frame.pack(pady=(0, 8))
        self.moves_label = tk.Label(stat_frame, text="翻牌次數：0",
                                    font=("Microsoft JhengHei", 11), bg=self.BG, fg=self.ACCENT)
        self.moves_label.pack(side=tk.LEFT, padx=20)
        self.timer_label = tk.Label(stat_frame, text="⏱ 00:00",
                                    font=("Microsoft JhengHei", 11), bg=self.BG, fg=self.ACCENT)
        self.timer_label.pack(side=tk.LEFT, padx=20)

        grid_frame = tk.Frame(w, bg=self.BG)
        grid_frame.pack(padx=16, pady=8)

        for idx, card in enumerate(self.cards):
            row = idx // self.COLS
            col = idx % self.COLS
            btn = tk.Button(
                grid_frame,
                text="？",
                width=12, height=3,
                font=("Microsoft JhengHei", 12, "bold"),
                bg=self.CARD_BACK, fg=self.TEXT_COLOR,
                activebackground=self.CARD_FRONT_WORD,
                relief="flat", bd=0, cursor="hand2",
                command=lambda i=idx: self._on_click(i)
            )
            btn.grid(row=row, column=col, padx=self.PAD//2, pady=self.PAD//2)
            self.buttons.append(btn)

        restart_btn = tk.Button(w, text="🔄 重新開始",
                                font=("Microsoft JhengHei", 11),
                                bg=self.CARD_FRONT_WORD, fg=self.TEXT_COLOR,
                                relief="flat", cursor="hand2", padx=16, pady=6,
                                command=self._restart)
        restart_btn.pack(pady=(8, 16))

    def _on_click(self, idx):
        if self.flip_locked:
            return
        card = self.cards[idx]
        if card["pair_id"] in self.matched_ids:
            return
        if idx in [f[0] for f in self.flipped]:
            return

        self.flipped.append((idx, card))
        color = self.CARD_FRONT_WORD if card["type"] == "word" else self.CARD_FRONT_MEAN
        self.buttons[idx].config(text=card["label"], bg=color)

        if len(self.flipped) == 2:
            self.moves += 1
            self.moves_label.config(text=f"翻牌次數：{self.moves}")
            self.flip_locked = True
            self.window.after(self.FLIP_DELAY, self._check_match)

    def _check_match(self):
        (i1, c1), (i2, c2) = self.flipped
        if c1["pair_id"] == c2["pair_id"] and c1["type"] != c2["type"]:
            # 配對成功
            self.matched_ids.add(c1["pair_id"])
            for idx in (i1, i2):
                self.buttons[idx].config(bg=self.CARD_MATCHED, state="disabled")
            if len(self.matched_ids) == len(self.cards) // 2:
                elapsed = int(time.time() - self.start_time)
                m, s = divmod(elapsed, 60)
                messagebox.showinfo(
                    "🎉 完成！",
                    f"恭喜！你用了 {self.moves} 次翻牌，耗時 {m:02d}:{s:02d} 完成！",
                    parent=self.window
                )
        else:
            # 配對失敗，翻回
            for idx in (i1, i2):
                self.buttons[idx].config(text="？", bg=self.CARD_BACK)

        self.flipped = []
        self.flip_locked = False

    def _update_timer(self):
        if not self.window.winfo_exists():
            return
        elapsed = int(time.time() - self.start_time)
        m, s = divmod(elapsed, 60)
        self.timer_label.config(text=f"⏱ {m:02d}:{s:02d}")
        self.window.after(1000, self._update_timer)

    def _restart(self):
        self.window.destroy()
        MemoryMatchGame(self.parent, [
            {"單字": c["label"] if c["type"] == "word" else c["pair_id"],
             "中文": c["label"] if c["type"] == "meaning" else "",
             "pair_id": c["pair_id"]}
            for c in self.cards
        ])


def open_memory_match(parent, dictionary_data):
    MemoryMatchGame(parent, dictionary_data)
