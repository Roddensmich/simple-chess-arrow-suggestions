import argparse
import logging
import os
import subprocess
import sys
import time
from typing import Optional

from colorama import init  # type: ignore
from king_chess import KING_SLAYER
from misc_bot import elo_to_sf_params, BROWSERS

init()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("KING_SLAYER")

_DEFAULT_ELO = 1300
_DEFAULT_PLAYSTYLE = "magnus"
_DEFAULT_TIME_CONTROL = "blitz"
_DEFAULT_PORT = 9222


def find_patricia() -> str:
    import shutil
    if (f := shutil.which("PATRICIA")):
        return f
    for c in [
        r".\PATRICIA.exe", r".\PATRICIA",
        "/usr/games/PATRICIA", "/usr/local/bin/PATRICIA",
        "/opt/homebrew/bin/PATRICIA",
    ]:
        if os.path.isfile(c):
            return c
    return "PATRICIA"


def find_browser_binary(name: Optional[str]) -> Optional[str]:
    import shutil
    for key in ([name] if name and name in BROWSERS else list(BROWSERS)):
        for path in BROWSERS.get(key, []):
            if path and os.path.isfile(path):
                return path
        if (f := shutil.which(key)):
            return f
    return None


def launch_browser(binary: Optional[str], name: Optional[str], port: int) -> subprocess.Popen:
    path = binary or find_browser_binary(name)
    if not path:
        log.error("Browser not found — install Brave or Chrome and try again.")
        sys.exit(1)
    bname = next((k for k in BROWSERS if k in path.lower()), "browser")
    profile = os.path.join(os.environ.get("TEMP", "C:/tmp"), f"chess-{bname}")
    log.info("Launching %s on port %d…", bname, port)
    return subprocess.Popen(
        [
            path,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.chess.com/play/online",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    browser_proc = launch_browser(None, "brave", _DEFAULT_PORT)
    log.info("Waiting for browser to open…")
    time.sleep(2.5)

    _, auto_depth = elo_to_sf_params(_DEFAULT_ELO)
    args = argparse.Namespace(
        elo=_DEFAULT_ELO,
        playstyle=_DEFAULT_PLAYSTYLE,
        time_control=_DEFAULT_TIME_CONTROL,
        patricia=find_patricia(),
        depth=auto_depth,
        port=_DEFAULT_PORT,
        profile="human",
    )
    bot = KING_SLAYER(args)
    try:
        bot.start()
    finally:
        if browser_proc:
            browser_proc.terminate()


if __name__ == "__main__":
    main()