import logging
import os
import random
import subprocess
import threading
import queue
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import chess

log = logging.getLogger(__name__)
from misc_bot import PLAYSTYLES

C = {
    "bg":"#0f0f0f", "panel":"#161616", "card":"#1a1a1a", "border":"#0a0808", "text":"#e8e8e8",
    "muted":"#555555", "green":"#00d26a", "red":"#ff4444", "blue":"#0094ff", "orange":"#ffaa00",
    "purple":"#a855f7",
}

_MIN_MOVE_MS = 400 
_MAX_MOVE_MS = 6000 

@dataclass
class MultiResult:
    engine_best: Optional[Tuple[str, int]] = None
    engine_2nd: Optional[Tuple[str, int]] = None
    human_pick: Optional[Tuple[str, int]] = None
    brilliant: Optional[Tuple[str, int]] = None
    eval_cp: int = 0
    eval_mate: Optional[int] = None

class TimeManager:
    def budget_ms(self, remaining_ms: int, board: chess.Board, style: dict) -> int:
        if len(list(board.legal_moves)) == 1: return 100
        if remaining_ms and remaining_ms < 15000: return max(250, int(remaining_ms * 0.04))

        raw = remaining_ms / 40 if remaining_ms else 2000
        moves_count = len(list(board.legal_moves))
        complexity_mod = min(1.5, max(0.6, moves_count / 30.0))
        style_mod = style.get("think_mu_scale", 1.0) if style else 1.0
        final_ms = int(raw * complexity_mod * style_mod)
        final_ms = int(final_ms * random.uniform(0.85, 1.15))

        return max(_MIN_MOVE_MS, min(final_ms, _MAX_MOVE_MS))

class Patricia:
    def __init__(self, path: str, depth: int, skill: int, elo: int, playstyle: Optional[str]):
        self._path = path
        self.depth, self.skill, self.elo = depth, skill, elo
        self.style = PLAYSTYLES.get(playstyle) if playstyle else None
        self._time_mgr = TimeManager()

        self._lock_d = threading.Lock()
        self._proc_d = self._spawn(multipv=4)

    def _spawn(self, multipv: int = 4) -> subprocess.Popen:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            [self._path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env,
        )

        # FIX BUG 6: bind the reader to this queue so a dying old reader
        # can never write into the newly-spawned engine's queue.
        q = queue.Queue()
        self._q_d = q
        def _reader(p=proc, qq=q):
            for line in iter(p.stdout.readline, ''):
                qq.put(line)
            qq.put("EOF")
        threading.Thread(target=_reader, daemon=True).start()

        self._send_raw(proc, "uci")
        self._wait_raw(self._q_d, "uciok")
        self._send_raw(proc, f"setoption name UCI_Elo value {self.elo}")
        self._send_raw(proc, f"setoption name Skill Level value {self.skill}")
        self._send_raw(proc, f"setoption name MultiPV value {multipv}")
        self._send_raw(proc, "isready")
        self._wait_raw(self._q_d, "readyok")
        return proc

    @staticmethod
    def _send_raw(proc, cmd):
        try:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
        except OSError:
            pass

    def _wait_raw(self, q, token):
        for _ in range(10000):
            try:
                line = q.get(timeout=5.0)
                if line == "EOF" or token in line: return
            except queue.Empty:
                raise RuntimeError(f"Engine timed out waiting for {token}")

    def _flush_proc(self, proc, q):
        try:
            self._send_raw(proc, "stop")
            self._send_raw(proc, "isready")
            while True:
                line = q.get(timeout=3.0)
                if line == "EOF" or "readyok" in line:
                    break
        except (OSError, queue.Empty): pass

    def _collect_proc(self, q, timeout_sec=10.0):
        moves = []
        bestmove = None
        eval_cp = 0
        eval_mate = None
        
        while True:
            try:
                line = q.get(timeout=timeout_sec)
                if line == "EOF":
                    break
                if line.startswith("bestmove"):
                    parts = line.split()
                    if len(parts) > 1:
                        bestmove = parts[1]
                    break
                
                if " pv " in line:
                    parts = line.split()
                    try:
                        move = parts[parts.index("pv") + 1]
                        rank = int(parts[parts.index("multipv") + 1]) if "multipv" in parts else 1
                        
                        if "mate" in parts:
                            m_val = int(parts[parts.index("mate") + 1])
                            score = 10000 if m_val > 0 else -10000
                            if rank == 1: eval_mate = m_val
                        elif "cp" in parts:
                            score = int(parts[parts.index("cp") + 1])
                            if rank == 1: eval_cp = score
                        else:
                            score = 0
                            
                        moves.append((rank, move, score))
                    except Exception: pass
            except queue.Empty:
                # TIMEOUT: Force stop and drain
                self._send_raw(self._proc_d, "stop")
                try:
                    while True:
                        line = q.get(timeout=1.0)
                        if line.startswith("bestmove") or line == "EOF":
                            break
                except queue.Empty: pass
                break
        
        if not moves and bestmove and bestmove != "(none)":
            moves = [(1, bestmove, 0)]
            
        moves.sort(key=lambda x: x[0])
        return [(m[1], m[2]) for m in moves], eval_cp, eval_mate

    def analyse_quick(self, fen: str) -> List[Tuple[str, int]]:
        return self.analyse_deep(fen, 300)

    def analyse_deep(self, fen: str, budget_ms: int) -> List[Tuple[str, int]]:
        board = chess.Board(fen)
        with self._lock_d:
            self._flush_proc(self._proc_d, self._q_d)
            self._send_raw(self._proc_d, f"position fen {fen}")
            self._send_raw(self._proc_d, f"go movetime {budget_ms}")
            raw, _, _ = self._collect_proc(self._q_d, timeout_sec=(budget_ms / 1000.0) + 5.0)
        legal = {m.uci() for m in board.legal_moves}
        return [(u, s) for u, s in raw if u in legal]

    def build_multi_result(self, board: chess.Board, deep: List[Tuple[str, int]], shallow: List[Tuple[str, int]]) -> MultiResult:
        if not deep: return MultiResult()
        best_score = deep[0][1]
        engine_best = deep[0]
        engine_2nd = deep[1] if len(deep) > 1 else None
        mistake_rate = self.style.get("mistake_rate", 0.05) if self.style else 0.05

        is_black = board.turn == chess.BLACK
        eval_cp = best_score

        # FIX BUG 2: Negate every score passed to the UI when it's Black's turn
        if is_black:
            eval_cp = -eval_cp
            engine_best = (engine_best[0], -engine_best[1])
            if engine_2nd:
                engine_2nd = (engine_2nd[0], -engine_2nd[1])

        if random.random() < mistake_rate and len(deep) > 2:
            min_diff = 30
            max_diff = 80
            for move, score in deep[1:4]:
                if min_diff <= (best_score - score) <= max_diff:
                    ui_score = -score if is_black else score
                    return MultiResult(engine_best=engine_best, engine_2nd=engine_2nd, human_pick=(move, ui_score), eval_cp=eval_cp)
            ui_score = -deep[1][1] if is_black else deep[1][1]
            return MultiResult(engine_best=engine_best, engine_2nd=engine_2nd, human_pick=(deep[1][0], ui_score), eval_cp=eval_cp)

        return MultiResult(engine_best=engine_best, engine_2nd=engine_2nd, human_pick=engine_best, eval_cp=eval_cp)

    def stop_search(self):
        try:
            self._send_raw(self._proc_d, "stop")
        except Exception: pass

    def new_game(self):
        with self._lock_d:
            self._send_raw(self._proc_d, "ucinewgame")
            self._flush_proc(self._proc_d, self._q_d)

    def update_elo(self, elo: int, skill: int):
        with self._lock_d:
            self._send_raw(self._proc_d, "stop")
            # Drain queue completely
            while not self._q_d.empty():
                try: self._q_d.get_nowait()
                except queue.Empty: break
                
            self.elo, self.skill = elo, skill
            self._send_raw(self._proc_d, f"setoption name UCI_Elo value {elo}")
            self._send_raw(self._proc_d, f"setoption name Skill Level value {skill}")
            self._send_raw(self._proc_d, "isready")
            
            try:
                self._wait_raw(self._q_d, "readyok")
            except RuntimeError:
                log.warning("Engine timeout in update_elo - forcing restart")
                try:
                    self._proc_d.kill()
                except Exception:
                    pass
                # FIX BUG 6: drain the old queue so any blocked consumer unblocks
                while not self._q_d.empty():
                    try: self._q_d.get_nowait()
                    except queue.Empty: break
                self._proc_d = self._spawn()

    def update_playstyle(self, playstyle: str):
        self.style = PLAYSTYLES.get(playstyle) if playstyle else None

    def close(self):
        try: self._send_raw(self._proc_d, "quit")
        except: pass