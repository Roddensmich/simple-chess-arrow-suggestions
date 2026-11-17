import logging
import requests
from typing import Optional
import chess

log = logging.getLogger(__name__)

_LICHESS_API = "https://explorer.lichess.ovh/masters"
_HEADERS = {"User-Agent": "KING_SLAYER"}

def get_book_move(fen: str) -> Optional[str]:
    try:
        board = chess.Board(fen)
        if board.fullmove_number > 12:
            return None

        r = requests.get(_LICHESS_API, params={"fen": fen, "topGames": 0, "moves": 3}, headers=_HEADERS, timeout=1.0)
        if r.status_code != 200:
            return None
            
        data = r.json()
        moves = data.get("moves", [])
        if not moves:
            return None

        top_move = moves[0]
        total_games = top_move.get("white", 0) + top_move.get("draws", 0) + top_move.get("black", 0)
        
        if total_games >= 100:
            uci = top_move["uci"]
            if uci in [m.uci() for m in board.legal_moves]:
                return uci
                
    except Exception:
        pass
    return None