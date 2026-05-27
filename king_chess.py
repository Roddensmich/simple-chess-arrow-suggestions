import json
import logging
import queue
import sys
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

from CDPCLIENT import CDPClient
from chess_ui import GUI
from misc_bot import JS_GET_STATE, JS_DRAW_ARROWS, JS_CLEAR_ARROWS, JS_IS_GAME_OVER, elo_to_sf_params
from patricia import C, Patricia, MultiResult

import chess # type: ignore

_SUGGEST_BUDGET_MS = 2500
_SUGGEST_BUDGET_MS_BULLET = 1000

_COLOR_ENGINE_BEST = C["red"]
_COLOR_ENGINE_2ND = C["orange"]
_COLOR_HUMAN = C["green"]
_COLOR_BRILLIANT = C["blue"]

_PRELIM_DELAY_S = 0.40


class KING_SLAYER:
    def __init__(self, args):
        self.args = args
        self.elo = args.elo
        self.playstyle = args.playstyle
        skill, auto_depth = elo_to_sf_params(self.elo)
        self.skill = skill
        self.depth = args.depth or auto_depth
        self.cdp = CDPClient(port=args.port)
        self.engine: Optional[Patricia] = None
        self.gui: Optional[GUI] = None
        self.auto_move = False
        self._running = False
        self._processing = False
        self._abort = threading.Event()

        self._state_lock = threading.Lock()
        self._suggested_fen = "" 
        self._pending_fen = ""
        self._last_arrows_json = ""
        self._arrow_drawn = False

        self._dragging = False
        self._analysis_gen = 0
        self._analysis_queue: queue.Queue = queue.Queue()
        self._game_over_triggered = False
        self._last_queued_fen = ""
        self.time_control = args.time_control

    def apply_settings(self, elo: int, playstyle: str, time_control: str) -> None:
        """Hot-apply new ELO, playstyle, and time control; resets analysis state."""
        skill, auto_depth = elo_to_sf_params(elo)
        self.elo = elo
        self.skill = skill
        self.depth = auto_depth
        self.playstyle = playstyle
        self.time_control = time_control
        if self.engine:
            self.engine.update_elo(elo, skill)
            self.engine.update_playstyle(playstyle)
        self.reset_state()
        log.info(
            "Settings applied: ELO=%d  playstyle=%s  depth=%d  tc=%s",
            elo, playstyle, auto_depth, time_control,
        )

    def reset_state(self):
        self._analysis_gen += 1
        self._abort.set()
        if self.engine:
            self.engine.stop_search()
        self._processing = False
        with self._state_lock:
            self._suggested_fen = ""
            self._pending_fen = ""
            self._last_arrows_json = ""
        self._last_queued_fen = ""
        self._clear_arrow()
        time.sleep(0.06)
        self._abort.clear()
        if self.engine:
            try:
                self.engine.new_game()
            except Exception as e:
                log.warning("new_game() failed: %s", e)
        log.info("Suggester state reset")

    def start(self):
        if not self.cdp.connect():
            sys.exit(1)
        try:
            self.engine = Patricia(self.args.patricia, self.depth, self.skill, self.elo, self.playstyle)
        except FileNotFoundError:
            log.error("Patricia not found at '%s'.", self.args.patricia)
            sys.exit(1)
        self.gui = GUI(self)
        self.gui.set_status("Connected", sub=f"ELO {self.elo} · {self.playstyle} · suggestion mode", dot=C["green"])
        self._running = True
        threading.Thread(target=self._analysis_worker, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()
        self.gui.run()
        self._running = False
        self._abort.set()
        self._analysis_gen += 1
        self._cleanup()

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                log.warning("Tick error: %s", e)
                if self.gui:
                    self.gui.set_status("Error", sub=str(e)[:48], dot=C["orange"])
                time.sleep(1.0)
            time.sleep(0.15)

    def _tick(self):
        if not self.auto_move:
            return
        try:
            state = self.cdp.eval_js(JS_GET_STATE)
        except Exception:
            if self.gui:
                self.gui.set_status("CDP error", sub="Click Reconnect", dot=C["red"])
            return

        if not state:
            self._dragging = False
            with self._state_lock:
                self._suggested_fen = ""
                self._pending_fen   = ""
                self._last_arrows_json = ""
            self._clear_arrow()
            if self.gui:
                self.gui.set_status("No board", dot=C["muted"])
            return

        if state.get("dragging"):
            self._dragging = True
            if self.gui:
                self.gui.set_status("Dragging piece…", dot=C["blue"])
            return

        if self._dragging:
            self._dragging = False
            with self._state_lock:
                last_json = self._last_arrows_json
                drawn     = self._arrow_drawn
            if last_json and not drawn:
                try:
                    self.cdp.eval_js(JS_DRAW_ARROWS % last_json)
                    with self._state_lock:
                        self._arrow_drawn = True
                except Exception:
                    pass

        if not state.get("gameActive"):
            try:
                if self.cdp.eval_js(JS_IS_GAME_OVER):
                    if not self._game_over_triggered and self.auto_move:
                        self._game_over_triggered = True
                        log.info("Game over detected — triggering restart")
                        if self.gui:
                            self.gui.trigger_restart()
                else:
                    self._game_over_triggered = False
            except Exception:
                pass
            with self._state_lock:
                cached_json = self._last_arrows_json
                self._suggested_fen = ""
                self._pending_fen = ""
                self._last_arrows_json = ""
            self._clear_arrow(clear_cache=False)
            if self.gui:
                self.gui.set_status("Waiting for game…", dot=C["muted"])
            return

        fen = state["fen"]
        my_color = state["myColor"]
        active = state["active"]
        clock = state.get("myClock")
        self._game_over_triggered = False

        if active != my_color:
            if self._processing:
                self._analysis_gen += 1
                self.engine.stop_search()
            self._clear_arrow()
            with self._state_lock:
                self._suggested_fen = ""
                self._pending_fen   = ""
                self._last_arrows_json = ""
            clk = f"{state.get('oppClock', '')}s" if state.get("oppClock") else ""
            if self.gui:
                self.gui.set_status("Opponent's turn…", sub=clk, dot=C["blue"])
            return

        with self._state_lock:
            suggested = self._suggested_fen
            pending = self._pending_fen
            last_json = self._last_arrows_json
            drawn = self._arrow_drawn

        if fen == suggested:
            if not drawn and last_json:
                try:
                    self.cdp.eval_js(JS_DRAW_ARROWS % last_json)
                    with self._state_lock:
                        self._arrow_drawn = True
                except Exception:
                    pass
            return

        if fen == pending:
            return

        self._analysis_gen += 1
        gen = self._analysis_gen
        self.engine.stop_search()

        with self._state_lock:
            self._pending_fen      = fen
            self._suggested_fen    = ""
            self._last_arrows_json = ""
        self._clear_arrow()

        while True:
            try:
                self._analysis_queue.get_nowait()
            except queue.Empty:
                break

        self._analysis_queue.put((fen, clock, gen))

        if fen != self._last_queued_fen:
            self._last_queued_fen = fen
            clk_str = f"{clock}s left" if clock else ""
            print(f"\033[2;31m Calculating suggestion… {clk_str}")
            if self.gui:
                self.gui.set_status("Thinking…", sub=clk_str, dot=C["orange"])

    def _analysis_worker(self):
        while self._running:
            try:
                fen, clock, gen = self._analysis_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._analysis_gen != gen or self._abort.is_set():
                with self._state_lock:
                    if self._pending_fen == fen:
                        self._pending_fen = ""
                continue

            self._processing = True
            try:
                self._run_analysis(fen, clock, gen)
            except Exception as e:
                log.warning("Analysis error: %s", e)
                with self._state_lock:
                    if self._pending_fen == fen:
                        self._pending_fen = ""
                if self.gui:
                    self.gui.set_status("Engine error", sub=str(e)[:48], dot=C["red"])
            finally:
                if self._analysis_gen == gen:
                    self._processing = False

    def _run_analysis(self, fen: str, clock: Optional[int], gen: int):
        def stale() -> bool:
            return self._analysis_gen != gen or self._abort.is_set()

        board = chess.Board(fen)
        if board.is_game_over():
            with self._state_lock:
                if self._pending_fen == fen:
                    self._pending_fen = ""
            return

        budget_ms = _SUGGEST_BUDGET_MS_BULLET if clock and clock < 30 else _SUGGEST_BUDGET_MS

        shallow: list = []
        deep:    list = []
        quick_done = threading.Event()

        def _run_quick():
            try:
                r = self.engine.analyse_quick(fen)
                if r:
                    shallow.extend(r)
            except Exception as e:
                log.warning("_run_quick error: %s", e)
            finally:
                quick_done.set()

        def _run_deep():
            try:
                r = self.engine.analyse_deep(fen, budget_ms)
                if r:
                    deep.extend(r)
            except Exception as e:
                log.warning("_run_deep error: %s", e)

        t_q = threading.Thread(target=_run_quick, daemon=True)
        t_d = threading.Thread(target=_run_deep,  daemon=True)
        t_q.start()
        t_d.start()

        quick_done.wait()
        if stale():
            with self._state_lock:
                if self._pending_fen == fen:
                    self._pending_fen = ""
            return

        t_d.join(timeout=_PRELIM_DELAY_S)
        if t_d.is_alive():
            if shallow and not stale():
                prelim = self.engine.build_multi_result(board, shallow, [])
                self._draw_multi_arrows(prelim, preliminary=True)
            t_d.join()

        if stale():
            with self._state_lock:
                if self._pending_fen == fen:
                    self._pending_fen = ""
            return

        if deep:
            final = self.engine.build_multi_result(board, deep, shallow)
            self._draw_multi_arrows(final, preliminary=False)
            with self._state_lock:
                self._suggested_fen = fen
                self._pending_fen   = ""
        else:
            with self._state_lock:
                if self._pending_fen == fen:
                    self._pending_fen = ""

    def _draw_multi_arrows(self, result: MultiResult, preliminary: bool):
        arrows = []
        seen: set = set()

        log.debug(
            "candidates: brilliant=%s human=%s best=%s second=%s",
            result.brilliant, result.human_pick, result.engine_best, result.engine_2nd
        )

        def add(move_tuple, color: str, alpha: float):
            if not move_tuple:
                return
            uci = move_tuple[0]
            if not uci or len(uci) < 4:
                return
            if uci in seen:
                return
            seen.add(uci)
            arrows.append({
                "from":  uci[:2],
                "to":    uci[2:4],
                "color": color,
                "alpha": alpha,
            })

        add(result.brilliant, _COLOR_BRILLIANT, 0.92)
        add(result.human_pick,  _COLOR_HUMAN, 0.88)
        add(result.engine_best, _COLOR_ENGINE_BEST, 0.78)
        add(result.engine_2nd, _COLOR_ENGINE_2ND, 0.62)

        if not arrows:
            return

        arrows_json = json.dumps(arrows)
        try:
            self.cdp.eval_js(JS_DRAW_ARROWS % arrows_json)
            with self._state_lock:
                self._last_arrows_json = arrows_json
                self._arrow_drawn = True
        except Exception as e:
            log.warning("_draw_multi_arrows: %s", e)
            with self._state_lock:
                self._arrow_drawn = False
            return

        if preliminary:
            return

        primary = result.brilliant or result.human_pick or result.engine_best
        if not primary:
            return
        uci, ev = primary
        promo = (
            f"  →  promote to {uci[4].upper()}"
            if len(uci) == 5 else ""
        )
        tag = "★ " if result.brilliant else ""
        print(f"\033[2;31m ➜ Suggestion: {tag}{uci}{promo}  (eval {ev:+d})")
        if self.gui:
            self.gui.set_status(
                f"Suggest  {tag}{uci}{promo}",
                sub=f"eval {ev:+d} ·  you move",
                dot=C["green"],
            )
            self.gui.push_move(uci, ev, result)

    def _clear_arrow(self, clear_cache: bool = True):
        with self._state_lock:
            drawn     = self._arrow_drawn
            has_cache = bool(self._last_arrows_json)

        if not drawn:
            if clear_cache:
                with self._state_lock:
                    self._last_arrows_json = ""
            return

        try:
            self.cdp.eval_js(JS_CLEAR_ARROWS)
        except Exception:
            pass

        with self._state_lock:
            self._arrow_drawn = False
            if clear_cache:
                self._last_arrows_json = ""

    def _cleanup(self):
        self._clear_arrow()
        if self.engine:
            self.engine.close()
        self.cdp.close()