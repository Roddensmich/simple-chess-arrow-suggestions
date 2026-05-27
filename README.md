
# KING SLAYER

A chess.com move suggestion overlay powered by the Patricia chess engine.
It connects to your browser using Chrome DevTools Protocol (CDP) and draws move arrows directly on the board.

---

## Features

- Live move suggestions on chess.com
- Multiple move arrows:
  - Best move
  - Second-best move
  - Playstyle move
  - Brilliant move
- Auto engine strength based on target ELO
- Bullet / Blitz / Rapid / Classical support
- Small draggable HUD
- Auto restart after games
- Browser automation masking

---

## Requirements

- Python 3.10+
- Patricia chess engine
- Chrome, Brave, Edge, Opera, or Vivaldi

Install dependencies:

```bash
pip install requests websocket-client chess colorama
````

> `tkinter` is usually included with Python.

---

## Setup

1. Put the Patricia binary in the project folder:

   * `PATRICIA.exe` (Windows)
   * `PATRICIA` (Linux/macOS)

2. Install dependencies:

```bash
pip install requests websocket-client chess colorama
```

3. Run:

```bash
python king_slayer.py
```

The tool will open your browser, connect to chess.com, and start the overlay HUD.

---

## Files

| File             | Purpose                 |
| ---------------- | ----------------------- |
| `king_slayer.py` | Main launcher           |
| `king_chess.py`  | Main chess logic        |
| `chess_ui.py`    | GUI / HUD               |
| `CDPCLIENT.py`   | Browser CDP connection  |
| `patricia.py`    | Patricia engine wrapper |
| `misc_bot.py`    | Configs and JS helpers  |

---

## Controls

| Button                             | Action                |
| ---------------------------------- | --------------------- |
| ENABLE / PAUSE                     | Toggle suggestions    |
| RESTART                            | Reset current session |
| RECONNECT                          | Reconnect browser     |
| ELO                                | Change target ELO     |
| STYLE                              | Select playstyle      |
| BULLET / BLITZ / RAPID / CLASSICAL | Change time mode      |

---

## Arrow Colors

| Color     | Meaning          |
| --------- | ---------------- |
| 🔴 Red    | Best engine move |
| 🟠 Orange | Second-best move |
| 🟢 Green  | Playstyle move   |
| 🔵 Blue   | Brilliant move   |

---

## Default Config

```python
_DEFAULT_ELO = 1300
_DEFAULT_PLAYSTYLE = "magnus"
_DEFAULT_TIME_CONTROL = "blitz"
_DEFAULT_PORT = 9222
```

---

## Credits

* Patricia engine - [Adam Treat](https://github.com/Adam-Kulju/Patricia)
* python-chess - [Niklas Fiekas](https://github.com/niklasf/python-chess)
* nbeater678 - [Hersovan Deguzman](https://github.com/DRIPSCRIPTER)

---

## Disclaimer

For personal learning and analysis only.
Use responsibly and follow chess.com’s terms of service.
