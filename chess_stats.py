import logging
import requests
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

_BASE = "https://api.chess.com/pub"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KING_SLAYER/1.0",
    "Accept": "application/json"
}
_TIMEOUT = 4

def _get(url: str) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 404: return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.warning("Chess.com API error: %s", e)
        return None
    except ValueError:  # FIX BUG 3: HTML error page / invalid JSON
        log.warning("Chess.com API returned invalid JSON")
        return None

def _win_rate(record: dict) -> Optional[float]:
    if not record: return None
    w, l, d = record.get("win", 0), record.get("loss", 0), record.get("draw", 0)
    total = w + l + d
    return round((w / total) * 100, 1) if total else None

def get_player_summary(username: str) -> Optional[Dict[str, Any]]:
    if not username: return None
    stats = _get(f"{_BASE}/player/{username.strip().lower()}/stats")
    if not stats: return None

    summary = {"username": username, "ratings": {}}
    for tc in ("chess_bullet", "chess_blitz", "chess_rapid", "chess_daily"):
        block = stats.get(tc)
        if not block: continue
        
        record = block.get("record", {})
        summary["ratings"][tc.replace("chess_", "")] = {
            "current": block.get("last", {}).get("rating"),
            "win_rate": _win_rate(record)
        }
    return summary

def get_rating_for_time_control(stats: dict, time_control: str) -> Optional[dict]:
    if not stats or not stats.get("ratings"):
        return None
    
    ratings = stats["ratings"]
    if time_control in ratings:
        return ratings[time_control]
    return ratings.get("blitz") or next(iter(ratings.values()), None)