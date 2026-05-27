from __future__ import annotations
import threading
import tkinter as tk
from typing import TYPE_CHECKING, Dict, List, Optional

from misc_bot import PLAYSTYLES, elo_to_sf_params
from patricia import C

if TYPE_CHECKING:
    from king_chess import KING_SLAYER

_TIME_CONTROLS = ["bullet", "blitz", "rapid", "classical"]


class GUI:
    W, H = 300, 510

    def __init__(self, bot: "KING_SLAYER"):
        self.bot = bot
        self._move_history: List[str] = []
        self._games = 0
        self._style_popup: Optional[tk.Toplevel] = None
        self._elo_editing = False
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.title("KING SLAYER — Suggest")
        self.root.geometry(f"{self.W}x{self.H}")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])
        self.root.attributes("-topmost", True)
        self._offset_x = 0
        self._offset_y = 0
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_move(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _do_move(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")

    def _lbl(self, parent, text="", fg=None, font=("Segoe UI", 9), **kw):
        return tk.Label(
            parent, text=text, bg=parent["bg"],
            fg=fg or C["text"], font=font, **kw,
        )

    def _btn(self, parent, text, cmd, bg, fg="white", **kw):
        return tk.Button(
            parent, text=text, command=cmd,
            bg=bg, fg=fg, activebackground=bg,
            font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", pady=7, **kw,
        )

    def _build(self):
        hdr = tk.Frame(self.root, bg=C["panel"], height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>", self._start_move)
        hdr.bind("<B1-Motion>", self._do_move)

        close_btn = tk.Label(
            hdr, text="✕", fg=C["red"], bg=C["panel"],
            font=("Segoe UI", 11, "bold"), cursor="hand2",
        )
        close_btn.pack(side="right", padx=8)
        close_btn.bind("<Button-1>", lambda e: self._on_close())

        self._lbl(hdr, "♟  KING SLAYER  ·  SUGGEST", fg=C["green"], font=("Segoe UI", 12, "bold"), ).pack(side="left", padx=14)

        self._dot = self._lbl(hdr, "●", fg=C["red"], font=("Segoe UI", 12))
        self._dot.pack(side="right", padx=6)

        for w in hdr.winfo_children():
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

        sc = tk.Frame(self.root, bg=C["card"])
        sc.pack(fill="x", padx=10, pady=(8, 3))
        self._sv = tk.StringVar(value="Connecting…")
        self._ssv = tk.StringVar(value="")
        self._lbl(sc, "", textvariable=self._sv, font=("Segoe UI", 10, "bold")).pack(pady=(6, 1))
        self._lbl(sc, "", textvariable=self._ssv, fg=C["muted"], font=("Segoe UI", 8)).pack(pady=(0, 6))

        sf = tk.Frame(self.root, bg=C["bg"])
        sf.pack(fill="x", padx=10, pady=(0, 4))
        self._stats: dict = {}
        for key, label, color in [
            ("eval", "EVAL", C["green"]),
            ("move", "BEST MOVE", C["blue"]),
            ("games", "RESTARTS", C["purple"]),
        ]:
            card = tk.Frame(sf, bg=C["card"], padx=6, pady=6)
            card.pack(side="left", fill="both", expand=True, padx=2)
            self._lbl(card, label, fg=C["muted"], font=("Segoe UI", 7, "bold")).pack()
            v = tk.StringVar(value="—")
            self._lbl(card, "", textvariable=v, fg=color, font=("Segoe UI", 11, "bold")).pack()
            self._stats[key] = v

        lf = tk.Frame(self.root, bg=C["bg"])
        lf.pack(fill="x", padx=10, pady=(0, 3))
        for dot_color, label in [
            (C["red"], "Engine #1"),
            (C["orange"], "Engine #2"),
            (C["green"], "Style pick"),
            (C["blue"], "Brilliant"),
        ]:
            fi = tk.Frame(lf, bg=C["bg"])
            fi.pack(side="left", expand=True)
            self._lbl(fi, "●", fg=dot_color, font=("Segoe UI", 8)).pack(side="left")
            self._lbl(fi, label, fg=C["muted"],
                      font=("Segoe UI", 7)).pack(side="left", padx=(1, 4))

        eb = tk.Canvas(self.root, height=7, bg=C["border"], highlightthickness=0)
        eb.pack(fill="x", padx=10, pady=(0, 6))
        self._eb = eb
        self._eb_rect = eb.create_rectangle(0, 0, 150, 7, fill=C["green"], outline="")

        cf = tk.Frame(self.root, bg=C["bg"])
        cf.pack(fill="x", padx=10, pady=(0, 3))

        elo_card = tk.Frame(cf, bg=C["card"], padx=6, pady=4, cursor="hand2")
        elo_card.pack(side="left", fill="both", expand=True, padx=2)
        self._lbl(elo_card, "ELO", fg=C["muted"], font=("Segoe UI", 7)).pack()

        self._elo_var = tk.StringVar(value=str(self.bot.elo))
        self._elo_val_lbl = self._lbl(
            elo_card, "", textvariable=self._elo_var,
            font=("Segoe UI", 9, "bold"),
        )
        self._elo_val_lbl.pack()

        self._elo_entry = tk.Entry(
            elo_card, width=5, justify="center",
            font=("Segoe UI", 9, "bold"),
            bg=C["bg"], fg=C["green"],
            insertbackground=C["green"],
            relief="flat",
        )
        self._elo_entry.bind("<Return>", self._finish_elo_edit)
        self._elo_entry.bind("<FocusOut>", self._finish_elo_edit)
        self._elo_entry.bind("<Escape>", lambda e: self._cancel_elo_edit())

        for w in (elo_card, self._elo_val_lbl):
            w.bind("<Button-1>", lambda e: self._start_elo_edit())

        self._style_card = tk.Frame(cf, bg=C["card"], padx=6, pady=4, cursor="hand2")
        self._style_card.pack(side="left", fill="both", expand=True, padx=2)
        self._lbl(self._style_card, "STYLE", fg=C["muted"], font=("Segoe UI", 7)).pack()

        self._style_var = tk.StringVar(value=self.bot.playstyle.upper())
        style_val_lbl = self._lbl(
            self._style_card, "", textvariable=self._style_var,
            font=("Segoe UI", 9, "bold"),
        )
        style_val_lbl.pack()

        for w in (self._style_card, style_val_lbl):
            w.bind("<Button-1>", lambda e: self._open_style_picker())

        depth_card = tk.Frame(cf, bg=C["card"], padx=6, pady=4)
        depth_card.pack(side="left", fill="both", expand=True, padx=2)
        self._lbl(depth_card, "DEPTH", fg=C["muted"], font=("Segoe UI", 7)).pack()
        self._depth_var = tk.StringVar(value=str(self.bot.depth))
        self._lbl(depth_card, "", textvariable=self._depth_var, font=("Segoe UI", 9, "bold")).pack()

        tf = tk.Frame(self.root, bg=C["bg"])
        tf.pack(fill="x", padx=10, pady=(0, 4))
        self._tc_btns: Dict[str, tk.Button] = {}
        current_tc = self.bot.time_control
        for tc in _TIME_CONTROLS:
            active = tc == current_tc
            btn = tk.Button(
                tf, text=tc.upper(),
                command=lambda t=tc: self._set_time_control(t),
                bg=C["green"] if active else C["card"],
                fg=C["bg"] if active else C["muted"],
                activebackground=C["green"], activeforeground=C["bg"],
                font=("Segoe UI", 7, "bold"),
                relief="flat", cursor="hand2", pady=4,
            )
            btn.pack(side="left", fill="both", expand=True, padx=2)
            self._tc_btns[tc] = btn

        hf = tk.Frame(self.root, bg=C["card"])
        hf.pack(fill="x", padx=10, pady=(0, 6))
        self._lbl(hf, "SUGGESTION HISTORY", fg=C["muted"],
                  font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=8, pady=(5, 2))
        self._hv = tk.StringVar(value="No suggestions yet")
        self._lbl(hf, "", textvariable=self._hv, fg=C["text"], font=("Courier New", 9), wraplength=256, justify="left").pack(anchor="w", padx=8, pady=(0, 6))

        bf = tk.Frame(self.root, bg=C["bg"])
        bf.pack(fill="x", padx=10, pady=(0, 4))

        self._auto_txt = tk.StringVar(value="▶  ENABLE SUGGESTIONS")
        self._auto_btn = tk.Button(
            bf, textvariable=self._auto_txt, command=self._toggle,
            bg=C["red"], fg="white", activebackground=C["green"],
            font=("Segoe UI", 9, "bold"), relief="flat",
            cursor="hand2", pady=7,
        )
        self._auto_btn.pack(fill="x", pady=(0, 4))

        self._btn(bf, "↺  RESTART", self._restart, C["blue"]).pack(fill="x", pady=(0, 4))
        self._btn(bf, "⟳  RECONNECT CDP", self._reconnect, "#333333").pack(fill="x")

        self._lbl(
            self.root, "made by nbeater678 [@saddigup]",
            fg=C["muted"], font=("Segoe UI", 7),
        ).pack(pady=(6, 3))

    def _start_elo_edit(self):
        if self._elo_editing:
            return
        self._close_style_popup()
        self._elo_editing = True
        self._elo_val_lbl.pack_forget()
        self._elo_entry.delete(0, tk.END)
        self._elo_entry.insert(0, self._elo_var.get())
        self._elo_entry.pack()
        self._elo_entry.focus_set()
        self._elo_entry.select_range(0, tk.END)

    def _cancel_elo_edit(self):
        if not self._elo_editing:
            return
        self._elo_editing = False
        self._elo_entry.pack_forget()
        self._elo_val_lbl.pack()

    def _finish_elo_edit(self, event=None):
        if not self._elo_editing:
            return
        self._elo_editing = False
        val = self._elo_entry.get().strip()
        self._elo_entry.pack_forget()
        self._elo_val_lbl.pack()
        if val.isdigit():
            elo = int(val)
            if 300 <= elo <= 3000:
                _, depth = elo_to_sf_params(elo)
                self._elo_var.set(str(elo))
                self._depth_var.set(str(depth))
                threading.Thread(
                    target=lambda: self.bot.apply_settings(
                        elo, self.bot.playstyle, self.bot.time_control,
                    ),
                    daemon=True,
                ).start()

    def _open_style_picker(self):
        if self._style_popup and self._style_popup.winfo_exists():
            self._close_style_popup()
            return

        self._cancel_elo_edit()

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(bg=C["border"])
        popup.attributes("-topmost", True)
        self._style_popup = popup

        inner = tk.Frame(popup, bg=C["panel"], padx=4, pady=4)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        self._lbl(inner, "PLAYSTYLE", fg=C["muted"], font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(0, 3))

        for style in PLAYSTYLES.keys():
            active = style == self.bot.playstyle
            tk.Button(
                inner,
                text=f"  {style.upper()}",
                command=lambda s=style: self._select_style(s),
                bg=C["green"] if active else C["card"],
                fg=C["bg"] if active else C["text"],
                activebackground=C["green"], activeforeground=C["bg"],
                font=("Segoe UI", 8, "bold"),
                relief="flat", cursor="hand2",
                anchor="w", pady=4,
            ).pack(fill="x", pady=1)

        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        cx = self._style_card.winfo_rootx()
        cy = self._style_card.winfo_rooty()
        cw = self._style_card.winfo_width()
        ch = self._style_card.winfo_height()
        px = cx + cw // 2 - pw // 2
        py = cy + ch + 4

        if py + ph > self.root.winfo_screenheight() - 40:
            py = cy - ph - 4
        popup.geometry(f"+{px}+{py}")

        popup.focus_force()
        popup.bind(
            "<FocusOut>",
            lambda e: popup.after(150, self._close_style_popup),
        )

    def _select_style(self, style: str):
        self._close_style_popup()
        self._style_var.set(style.upper())
        threading.Thread(
            target=lambda: self.bot.apply_settings(
                self.bot.elo, style, self.bot.time_control,
            ),
            daemon=True,
        ).start()

    def _close_style_popup(self):
        if self._style_popup and self._style_popup.winfo_exists():
            self._style_popup.destroy()
        self._style_popup = None

    def _set_time_control(self, tc: str):
        self.bot.time_control = tc
        for t, btn in self._tc_btns.items():
            active = t == tc
            btn.configure(
                bg=C["green"] if active else C["card"],
                fg=C["bg"] if active else C["muted"],
            )

    def set_status(self, text: str, sub: str = "", dot: str = None):
        def _do():
            self._sv.set(text)
            self._ssv.set(sub)
            if dot:
                self._dot.configure(fg=dot)
        self.root.after(0, _do)

    def push_move(self, move: str, ev: int, result=None):
        def _do():
            self._move_history.append(move)
            sign = "+" if ev >= 0 else ""
            self._stats["eval"].set(f"{sign}{ev}")
            self._stats["games"].set(str(self._games))

            if result and result.brilliant:
                self._stats["move"].set(f"★ {result.brilliant[0]}")
            else:
                self._stats["move"].set(move)

            pct = max(0.0, min(1.0, (ev + 500) / 1000))
            w = self._eb.winfo_width() or self.W - 20
            color = C["green"] if ev > 50 else C["red"] if ev < -50 else C["orange"]
            self._eb.coords(self._eb_rect, 0, 0, int(pct * w), 7)
            self._eb.itemconfig(self._eb_rect, fill=color)

            h = self._move_history[-16:]
            pairs = [
                f"{i//2+1}.{h[i]} {h[i+1] if i+1 < len(h) else '...'}"
                for i in range(0, len(h), 2)
            ]
            self._hv.set("  ".join(pairs) if pairs else "No suggestions yet")
        self.root.after(0, _do)

    def trigger_restart(self):
        """Called from the bot thread when game-over is detected."""
        self.root.after(0, self._restart)

    def _toggle(self):
        self.bot.auto_move = not self.bot.auto_move
        if self.bot.auto_move:
            self.bot.reset_state()
            self._auto_txt.set("⏸  PAUSE SUGGESTIONS")
            self._auto_btn.configure(bg=C["green"], activebackground=C["green"])
            self.set_status("Suggestions ON", dot=C["green"])
            print("\033[2;31m Suggestions ENABLED")
        else:
            self.bot._analysis_gen += 1
            self.bot.engine.stop_search()
            self.bot._abort.set()
            self._auto_txt.set("▶  ENABLE SUGGESTIONS")
            self._auto_btn.configure(bg="#555555", activebackground="#555555")
            self.set_status("Suggestions paused", dot=C["orange"])
            print("\033[2;31m Suggestions PAUSED")

    def _restart(self):
        self.set_status("Restarting…", dot=C["orange"])
        def _do():
            self.bot.auto_move = True
            self.bot.reset_state()
            self._games += 1
            self._move_history.clear()
            games_snapshot = self._games

            def _reset_ui():
                self._hv.set("No suggestions yet")
                self._stats["eval"].set("—")
                self._stats["move"].set("—")
                self._stats["games"].set(str(games_snapshot))
                self._auto_txt.set("⏸  PAUSE SUGGESTIONS")
                self._auto_btn.configure(bg=C["green"], activebackground=C["green"])

            self.root.after(0, _reset_ui)
            self.set_status("Ready", sub="Restarted — waiting for your turn", dot=C["green"])
            print("\033[2;31m Restarted!")
        threading.Thread(target=_do, daemon=True).start()

    def _reconnect(self):
        self.set_status("Reconnecting…", dot=C["orange"])
        def _do():
            ok = self.bot.cdp.reconnect()
            if ok:
                self.bot.auto_move = True
                self.bot.reset_state()
                def _update_ui():
                    self._auto_txt.set("⏸  PAUSE SUGGESTIONS")
                    self._auto_btn.configure(bg=C["green"], activebackground=C["green"])
                self.root.after(0, _update_ui)
                self.set_status("Reconnected", sub="CDP restored", dot=C["green"])
                print("\033[2;31m CDP Reconnected!")
            else:
                self.set_status("Reconnect failed", sub="Check browser is open", dot=C["red"])
        threading.Thread(target=_do, daemon=True).start()

    def _on_close(self):
        self._close_style_popup()
        self.bot._running = False
        self.bot._analysis_gen += 1
        self.bot._abort.set()
        if self.bot.engine:
            self.bot.engine.stop_search()
        self.root.destroy()

    def run(self):
        self.root.mainloop()