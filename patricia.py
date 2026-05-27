import logging
import math
import random
import select
import subprocess
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import chess  # type: ignore

log = logging.getLogger(__name__)

from misc_bot import PLAYSTYLES


C = {
    "bg":"#0f0f0f",
    "panel":"#161616",
    "card":"#1a1a1a",
    "border":"#0a0808",
    "text":"#e8e8e8",
    "muted":"#555555",
    "green":"#00d26a",
    "red":"#ff4444",
    "blue":"#0094ff",
    "orange":"#ffaa00",
    "purple":"#a855f7",
}

_BRILLIANT_WINDOW_CP = 25
_SACRIFICE_BONUS = 3.0
_DEPTH_EMERGENCE_BONUS = 2.0
_QUIET_COUNTER_BONUS = 1.6
_DEFLECTION_BONUS = 1.5

_MOVES_LEFT_ESTIMATE = 25
_MIN_MOVE_MS = 500
_MAX_MOVE_MS = 10_000
_EMERGENCY_MS = 10_000
_SHALLOW_DEPTH = 8
_COLLECT_MAX_LINES = 50_000
_READLINE_TIMEOUT_S = 15.0

_BRILLIANCY_THRESHOLD = 1.05

_PIECE_CP: Dict[int, int] = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
    chess.ROOK: 500, chess.QUEEN: 900,
}

_UNSET_MS = 60_000


@dataclass
class MultiResult:
    engine_best: Optional[Tuple[str, int]] = None # red    — rank-1 engine move
    engine_2nd: Optional[Tuple[str, int]] = None # orange — rank-2 engine move
    human_pick: Optional[Tuple[str, int]] = None # green  — style-weighted choice
    brilliant: Optional[Tuple[str, int]] = None # blue   — sacrifice / depth-emergence


class TimeManager:
    def __init__(self, overhead_buffer: int = 3):
        self.overhead = overhead_buffer

    def budget_ms(self, remaining_ms: int, moves_left: int = _MOVES_LEFT_ESTIMATE) -> int:
        raw = remaining_ms / (moves_left + self.overhead)
        return int(max(_MIN_MOVE_MS, min(raw, _MAX_MOVE_MS)))

    def is_emergency(self, remaining_ms: int) -> bool:
        return remaining_ms <= _EMERGENCY_MS


@dataclass
class MoveProfile:
    uci: str
    deep_score: int
    deep_rank: int
    shallow_rank: int = 999
    is_sacrifice: bool = False
    material_given: int = 0
    is_quiet: bool = False
    defender_delta: int = 0
    brilliancy: float = 0.0


def _piece_cp(pt: Optional[int]) -> int:
    return _PIECE_CP.get(pt, 0) if pt else 0


def _is_sacrifice(board: chess.Board, move: chess.Move) -> Tuple[bool, int]:
    mover_val = _piece_cp(board.piece_type_at(move.from_square))
    captured_val = _piece_cp(board.piece_type_at(move.to_square))
    if board.is_en_passant(move):
        captured_val = _PIECE_CP[chess.PAWN]
    board.push(move)
    try:
        en_prise = board.is_attacked_by(board.turn, move.to_square)
    finally:
        board.pop()
    if en_prise:
        net = captured_val - mover_val
        if net < -50:
            return True, -net
    return False, 0


def _is_quiet(board: chess.Board, move: chess.Move) -> bool:
    if board.is_capture(move) or move.promotion:
        return False
    board.push(move)
    try:
        return not board.is_check()
    finally:
        board.pop()


def _defender_delta(board: chess.Board, move: chess.Move) -> int:
    before = len(board.attackers(board.turn, move.to_square))
    board.push(move)
    try:
        after = len(board.attackers(not board.turn, move.to_square))
    finally:
        board.pop()
    return after - before


def _tension(moves: List[Tuple[str, int]]) -> float:
    if len(moves) < 2:
        return 0.0
    return min((moves[0][1] - moves[-1][1]) / 400.0, 1.0)


def _rank_in(uci: str, lst: List[Tuple[str, int]]) -> int:
    for i, (m, _) in enumerate(lst):
        if m == uci:
            return i
    return len(lst)


def _build_profile(board: chess.Board, uci: str, deep_score: int, deep_rank: int, shallow_rank: int,) -> Optional[MoveProfile]:
    try:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            log.warning("_build_profile: illegal move %s — skipped", uci)
            return None
        sac, given = _is_sacrifice(board, move)
        return MoveProfile(
            uci=uci, deep_score=deep_score, deep_rank=deep_rank,
            shallow_rank=shallow_rank,
            is_sacrifice=sac, material_given=given,
            is_quiet=_is_quiet(board, move),
            defender_delta=_defender_delta(board, move),
        )
    except Exception as exc:
        log.warning("_build_profile: error on %s — %s", uci, exc)
        return None


def _score_brilliancy(p: MoveProfile, t: float) -> float:
    score = 1.0
    if p.is_sacrifice:
        score *= _SACRIFICE_BONUS * (1.0 + math.log1p(p.material_given / 100.0))
    rank_jump = p.shallow_rank - p.deep_rank
    if rank_jump >= 2:
        score *= _DEPTH_EMERGENCE_BONUS ** min(rank_jump / 2.0, 2.0)
    if p.is_quiet and t > 0.4:
        score *= _QUIET_COUNTER_BONUS
    if p.defender_delta >= 2:
        score *= _DEFLECTION_BONUS
    return score


def normalize_style(style: dict) -> dict:
    if not style:
        return style
    style.setdefault("weights", style.get("candidate_weights", [1, 0.6, 0.3, 0.15]))
    style.setdefault("quick_rate", style.get("quick_move_rate", 0.07))
    style.setdefault("long_rate",  style.get("long_think_rate", 0.09))
    return style


class Patricia:
    
    def __init__(self, path: str, depth: int, skill: int, elo: int, playstyle: Optional[str]):
        self._path  = path
        self.depth  = depth
        self.skill  = skill
        self.elo    = elo
        self.style  = normalize_style(PLAYSTYLES.get(playstyle)) if playstyle else None
        self.last_eval = 0
        self._time_mgr = TimeManager()

        self._lock_q = threading.Lock()
        self._lock_d = threading.Lock()
        self._proc_q = self._spawn()
        self._proc_d = self._spawn()

    def _spawn(self) -> subprocess.Popen:
        proc = subprocess.Popen(
            [self._path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self._send_raw(proc, "uci")
        self._wait_raw(proc, "uciok")
        self._send_raw(proc, "setoption name UCI_LimitStrength value true")
        self._send_raw(proc, f"setoption name UCI_Elo value {self.elo}")
        self._send_raw(proc, f"setoption name Skill Level value {self.skill}")
        self._send_raw(proc, "setoption name MultiPV value 4")
        self._send_raw(proc, "isready")
        self._wait_raw(proc, "readyok")
        return proc

    def _is_alive(self, proc: subprocess.Popen) -> bool:
        return proc.poll() is None

    def _ensure_alive(self, proc: subprocess.Popen, attr: str) -> subprocess.Popen:
        if self._is_alive(proc):
            return proc
        log.warning("Patricia %s died (exit %s) — restarting", attr, proc.returncode)
        try:
            proc.kill()
        except Exception:
            pass
        try:
            new_proc = self._spawn()
            setattr(self, attr, new_proc)
            log.info("Patricia %s restarted", attr)
            return new_proc
        except Exception as exc:
            log.error("Patricia %s restart failed: %s", attr, exc)
            raise

    @staticmethod
    def _send_raw(proc: subprocess.Popen, cmd: str) -> None:
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()

    @staticmethod
    def _readline_timeout(proc: subprocess.Popen, timeout: float = _READLINE_TIMEOUT_S) -> str:
        """readline() with a timeout; returns '' on timeout or closed pipe."""
        import sys as _sys
        if _sys.platform == "win32":
            # select() doesn't work on Windows pipes; fall back to blocking read
            return proc.stdout.readline()
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            log.warning("_readline_timeout: timed out after %.1fs", timeout)
            return ""
        return proc.stdout.readline()

    @staticmethod
    def _wait_raw(proc: subprocess.Popen, token: str) -> None:
        for _ in range(_COLLECT_MAX_LINES):
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"Patricia closed before '{token}'")
            if token in line:
                return
        raise RuntimeError(f"'{token}' never received")

    def _flush_proc(self, proc: subprocess.Popen) -> None:
        try:
            self._send_raw(proc, "stop")
            self._send_raw(proc, "isready")
        except OSError:
            return
        for _ in range(_COLLECT_MAX_LINES):
            line = self._readline_timeout(proc)
            if not line:
                log.error("_flush: pipe closed or timed out")
                return
            if "readyok" in line:
                return
        log.error("_flush: readyok never received")

    def _collect_proc(self, proc: subprocess.Popen) -> List[Tuple[str, int]]:
        moves_by_rank: Dict[int, Tuple[str, int]] = {}
        fallback: Optional[str] = None

        for _ in range(_COLLECT_MAX_LINES):
            line = self._readline_timeout(proc)
            if not line:
                log.error("_collect: Patricia pipe closed or timed out mid-search")
                break
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                bm = parts[1] if len(parts) >= 2 else None
                if bm and bm != "(none)":
                    fallback = bm
                break
            if "multipv" in line and " pv " in line:
                parts = line.split()
                try:
                    rank = int(parts[parts.index("multipv") + 1])
                    move = parts[parts.index("pv") + 1]
                    if move == "(none)":
                        continue
                    if "cp" in parts:
                        score = int(parts[parts.index("cp") + 1])
                    elif "mate" in parts:
                        mate_in = int(parts[parts.index("mate") + 1])
                        score   = 100_000 if mate_in > 0 else -100_000
                    else:
                        score = 0
                    moves_by_rank[rank] = (move, score)
                except (ValueError, IndexError):
                    pass

        moves = [v for _, v in sorted(moves_by_rank.items())]
        if not moves:
            return [(fallback, 0)] if fallback else []
        moves.sort(key=lambda x: x[1], reverse=True)
        return moves

    def analyse_quick(self, fen: str) -> List[Tuple[str, int]]:
        with self._lock_q:
            proc = self._ensure_alive(self._proc_q, "_proc_q")
            self._flush_proc(proc)
            self._send_raw(proc, f"position fen {fen}")
            self._send_raw(proc, f"go depth {_SHALLOW_DEPTH}")
            return self._collect_proc(proc)

    def analyse_deep(self, fen: str, budget_ms: int) -> List[Tuple[str, int]]:
        with self._lock_d:
            proc = self._ensure_alive(self._proc_d, "_proc_d")
            self._flush_proc(proc)
            self._send_raw(proc, f"position fen {fen}")
            self._send_raw(proc, f"go movetime {budget_ms}")
            return self._collect_proc(proc)

    def stop_search(self) -> None:
        for proc in (self._proc_q, self._proc_d):
            try:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
            except Exception:
                pass

    def build_multi_result(self, board: chess.Board, deep: List[Tuple[str, int]], shallow: List[Tuple[str, int]], ) -> MultiResult:
        if not deep:
            return MultiResult()

        best_score  = deep[0][1]
        ref_shallow = shallow if shallow else deep

        engine_best = deep[0]
        engine_2nd  = deep[1] if len(deep) > 1 else None

        # UCIs already claimed by the engine-arrow slots
        claimed: set = {deep[0][0]}
        if engine_2nd:
            claimed.add(deep[1][0])

        # Candidate pool for the human/brilliant slots:
        # moves not already shown AND within the brilliancy scoring window.
        pool = [
            (u, s) for u, s in deep
            if u not in claimed and best_score - s <= _BRILLIANT_WINDOW_CP
        ]

        brilliant  = None
        human_pick = None

        if pool:
            # --- first pass: find the best pick from the pool ----------------
            picked = self._brilliant_pick(board, pool, ref_shallow, best_score)

            if picked.brilliancy >= _BRILLIANCY_THRESHOLD and picked.is_sacrifice:
                brilliant = (picked.uci, picked.deep_score)
                claimed.add(picked.uci)
            else:
                human_pick = (picked.uci, picked.deep_score)
                claimed.add(picked.uci)

            # --- second pass: fill the other slot from remaining pool --------
            pool2 = [(u, s) for u, s in pool if u not in claimed]
            if pool2:
                if brilliant is None:
                    # Look specifically for a sacrifice/brilliancy in pool2
                    t = _tension(deep)
                    for rank, (uci, score) in enumerate(pool2):
                        p = _build_profile(board, uci, score, rank, _rank_in(uci, ref_shallow))
                        if p is None:
                            continue
                        p.brilliancy = _score_brilliancy(p, t)
                        if p.is_sacrifice and p.brilliancy >= _BRILLIANCY_THRESHOLD:
                            brilliant = (p.uci, p.deep_score)
                            break
                elif human_pick is None:
                    picked2 = self._brilliant_pick(board, pool2, ref_shallow, best_score)
                    human_pick = (picked2.uci, picked2.deep_score)

        return MultiResult(
            engine_best=engine_best,
            engine_2nd=engine_2nd,
            human_pick=human_pick,
            brilliant=brilliant,
        )

    def new_game(self) -> None:
        for lock, proc_attr in ((self._lock_q, "_proc_q"), (self._lock_d, "_proc_d")):
            with lock:
                proc = self._ensure_alive(getattr(self, proc_attr), proc_attr)
                self._send_raw(proc, "ucinewgame")
                self._send_raw(proc, "isready")
                self._wait_raw(proc, "readyok")

    def update_elo(self, elo: int, skill: int) -> None:
        self.elo = elo
        self.skill = skill
        for lock, attr in ((self._lock_q, "_proc_q"), (self._lock_d, "_proc_d")):
            with lock:
                proc = self._ensure_alive(getattr(self, attr), attr)
                try:
                    self._send_raw(proc, f"setoption name UCI_Elo value {elo}")
                    self._send_raw(proc, f"setoption name Skill Level value {skill}")
                    self._send_raw(proc, "isready")
                    self._wait_raw(proc, "readyok")
                except Exception as e:
                    log.warning("update_elo %s failed: %s", attr, e)

    def update_playstyle(self, playstyle: Optional[str]) -> None:
        self.style = normalize_style(PLAYSTYLES.get(playstyle)) if playstyle else None

    def close(self) -> None:
        for proc in (self._proc_q, self._proc_d):
            try:
                self._send_raw(proc, "quit")
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def best_move(self, fen: str, remaining_ms: int = _UNSET_MS, depth: int = None, ) -> Tuple[Optional[str], int]:
        if remaining_ms == _UNSET_MS:
            log.warning("best_move() called without remaining_ms — degraded time management")
        board = chess.Board(fen)
        if board.is_game_over():
            return None, 0
        tm = self._time_mgr
        with self._lock_d:
            proc = self._ensure_alive(self._proc_d, "_proc_d")
            self._flush_proc(proc)

            if tm.is_emergency(remaining_ms):
                self._send_raw(proc, f"position fen {fen}")
                self._send_raw(proc, f"go movetime {_MIN_MOVE_MS}")
                deep = self._collect_proc(proc)
                if not deep:
                    return None, 0
                self.last_eval = deep[0][1]
                return deep[0][0], deep[0][1]

            if abs(self.last_eval) >= 100_000:
                self._send_raw(proc, f"position fen {fen}")
                self._send_raw(proc, f"go movetime {_MIN_MOVE_MS}")
                deep = self._collect_proc(proc)
                if not deep:
                    return None, 0
                self.last_eval = deep[0][1]
                return deep[0][0], deep[0][1]

            budget_ms = tm.budget_ms(remaining_ms)
            self._send_raw(proc, f"position fen {fen}")
            self._send_raw(proc, f"go movetime {budget_ms}")
            deep = self._collect_proc(proc)

        if not deep:
            return None, 0
        best_score     = deep[0][1]
        self.last_eval = best_score

        shallow: List[Tuple[str, int]] = []
        try:
            with self._lock_q:
                proc_q = self._ensure_alive(self._proc_q, "_proc_q")
                self._flush_proc(proc_q)
                self._send_raw(proc_q, f"position fen {fen}")
                self._send_raw(proc_q, f"go depth {_SHALLOW_DEPTH}")
                shallow = self._collect_proc(proc_q)
        except Exception:
            pass

        chosen = self._brilliant_pick(board, deep, shallow or deep, best_score)
        if chosen.uci != deep[0][0] and chosen.brilliancy >= _BRILLIANCY_THRESHOLD:
            return chosen.uci, chosen.deep_score
        return deep[0][0], best_score

    def _brilliant_pick(self, board: chess.Board, deep: List[Tuple[str, int]], shallow: List[Tuple[str, int]], best_score: int,) -> MoveProfile:
        t = _tension(deep)
        candidates = [
            (uci, sc) for uci, sc in deep
            if best_score - sc <= _BRILLIANT_WINDOW_CP
        ] or [deep[0]]

        profiles: List[MoveProfile] = []
        for rank, (uci, score) in enumerate(candidates):
            p = _build_profile(board, uci, score, rank, _rank_in(uci, shallow))
            if p is None:
                continue
            p.brilliancy = _score_brilliancy(p, t)
            profiles.append(p)

        if not profiles:
            return MoveProfile(uci=deep[0][0], deep_score=deep[0][1], deep_rank=0)

        any_signal = any(p.brilliancy >= _BRILLIANCY_THRESHOLD for p in profiles)
        if not any_signal:
            return profiles[0]

        weights = [p.brilliancy for p in profiles]
        if self.style:
            sw = (
                self.style.get("weights", [1.0, 0.6, 0.3, 0.15])
                + [0.01] * len(weights)
            )[:len(weights)]
            weights = [w * s for w, s in zip(weights, sw)]

        total = sum(weights)
        if total == 0:
            return profiles[0]
        weights = [w / total for w in weights]
        return random.choices(profiles, weights=weights, k=1)[0]